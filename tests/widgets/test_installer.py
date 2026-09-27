"""Installing, listing, tampering with and removing third-party widgets."""

import json
import os
import shutil

import pytest

from StreamDock.widgets.installer import InstallError, WidgetInstaller
from StreamDock.widgets.registry import MANIFEST_FILE, WidgetRegistry

FIXTURES = os.path.join(os.path.dirname(__file__), 'fixtures')


@pytest.fixture
def registry(tmp_path):
    return WidgetRegistry(install_dir=str(tmp_path / 'widgets'))


@pytest.fixture
def installer(registry):
    return WidgetInstaller(registry)


def install(installer, name, source=None):
    staged = installer.stage(source or os.path.join(FIXTURES, name))
    try:
        installer.test_run(staged)
        assert staged.report.ok, staged.report.errors
        return installer.install(staged)
    finally:
        installer.discard(staged)


def approve(installer, widget_id):
    staged = installer.stage_installed(widget_id)
    try:
        installer.test_run(staged)
        return installer.approve(widget_id, staged)
    finally:
        installer.discard(staged)


def test_installed_widget_is_listed_from_its_manifest(installer, registry):
    spec = install(installer, 'good.py')

    assert spec.id == 'fixture_good'
    assert not spec.builtin and spec.runnable
    assert os.path.isfile(os.path.join(registry.install_dir, 'fixture_good', 'widget.py'))
    assert WidgetRegistry(install_dir=registry.install_dir).get('fixture_good').events == ('press',)


def test_folder_widget_keeps_its_helpers(installer, registry):
    install(installer, 'folder_widget')
    assert os.path.isfile(os.path.join(registry.install_dir, 'fixture_folder', 'helper.py'))


def test_edited_files_need_approval_again(installer, registry):
    # Consent covers the files the user saw; an edit must not inherit it.
    spec = install(installer, 'good.py')
    with open(spec.script_path, 'a', encoding='utf-8') as handle:
        handle.write('\n# changed\n')
    registry.refresh()

    assert registry.get('fixture_good').problem is not None

    approve(installer, 'fixture_good')
    assert registry.get('fixture_good').runnable


def test_failed_validation_cannot_be_installed(installer):
    staged = installer.stage(os.path.join(FIXTURES, 'clash.py'))
    with pytest.raises(InstallError):
        installer.install(staged)
    installer.discard(staged)


def test_reinstall_replaces_the_old_copy(installer, registry):
    install(installer, 'good.py')
    install(installer, 'good.py')
    names = [name for name in os.listdir(registry.install_dir) if not name.startswith('.')]
    assert names == ['fixture_good']


def test_remove(installer, registry):
    install(installer, 'good.py')
    installer.remove('fixture_good')
    assert registry.get('fixture_good') is None


def test_builtins_cannot_be_removed(installer):
    with pytest.raises(InstallError):
        installer.remove('digital_clock')


def good_folder(tmp_path):
    folder = tmp_path / 'src'
    folder.mkdir()
    shutil.copyfile(os.path.join(FIXTURES, 'good.py'), folder / 'widget.py')
    return folder


def test_the_checked_copy_is_what_gets_installed(installer, registry, tmp_path):
    # The source changing after the check (or after consent) must not reach the install.
    folder = good_folder(tmp_path)
    staged = installer.stage(str(folder))
    installer.test_run(staged)
    (folder / 'widget.py').write_text('raise SystemExit("swapped")\n')
    (folder / 'extra.py').write_text('x = 1\n')

    spec = installer.install(staged)

    assert spec.runnable
    with open(spec.script_path, encoding='utf-8') as handle:
        assert 'swapped' not in handle.read()
    assert not os.path.exists(os.path.join(spec.folder, 'extra.py'))


def test_nothing_runs_before_the_test_run(installer, tmp_path):
    # Staging is the pre-consent step: it must not execute the widget.
    folder = good_folder(tmp_path)
    marker = tmp_path / 'ran'
    with open(folder / 'widget.py', 'a', encoding='utf-8') as handle:
        handle.write(f'\nopen({str(marker)!r}, "w").close()\n')

    staged = installer.stage(str(folder))
    assert staged.report.ok, staged.report.errors
    assert not marker.exists()
    installer.test_run(staged)
    assert marker.exists()
    installer.discard(staged)


def test_a_widget_rewriting_itself_during_the_test_run_is_refused(installer, tmp_path):
    folder = good_folder(tmp_path)
    with open(folder / 'widget.py', 'a', encoding='utf-8') as handle:
        handle.write('\nwith open(__file__, "a") as _f:\n    _f.write("# later\\n")\n')

    staged = installer.stage(str(folder))
    installer.test_run(staged)
    assert any('changed its own files' in error for error in staged.report.errors)
    with pytest.raises(InstallError):
        installer.install(staged)
    installer.discard(staged)


def test_approval_refuses_files_changed_after_the_check(installer, registry):
    spec = install(installer, 'good.py')
    with open(spec.script_path, 'a', encoding='utf-8') as handle:
        handle.write('\n# first edit\n')
    registry.refresh()
    staged = installer.stage_installed('fixture_good')
    installer.test_run(staged)
    with open(spec.script_path, 'a', encoding='utf-8') as handle:
        handle.write('\n# second edit\n')

    with pytest.raises(InstallError):
        installer.approve('fixture_good', staged)
    installer.discard(staged)
    assert registry.get('fixture_good').problem is not None


@pytest.mark.parametrize('kind', ['file', 'dir'])
def test_symbolic_links_are_refused_at_install(installer, tmp_path, kind):
    folder = good_folder(tmp_path)
    outside = tmp_path / 'outside'
    outside.mkdir()
    (outside / 'secret.py').write_text('x = 1\n')
    target = outside / 'secret.py' if kind == 'file' else outside
    os.symlink(target, folder / 'link')

    staged = installer.stage(str(folder))
    assert any('symbolic links' in error for error in staged.report.errors), staged.report.errors
    installer.discard(staged)


@pytest.mark.parametrize('kind', ['file', 'dir'])
def test_a_link_added_after_install_blocks_running(installer, registry, tmp_path, kind):
    spec = install(installer, 'good.py')
    os.symlink(tmp_path if kind == 'dir' else spec.script_path, os.path.join(spec.folder, 'link'))
    registry.refresh()
    assert registry.get('fixture_good').problem is not None


def test_bytecode_appearing_in_an_installed_widget_needs_approval(installer, registry):
    # A planted .pyc could run instead of the approved source.
    spec = install(installer, 'good.py')
    os.mkdir(os.path.join(spec.folder, '__pycache__'))
    registry.refresh()
    assert registry.get('fixture_good').problem is not None

    approve(installer, 'fixture_good')
    assert registry.get('fixture_good').runnable
    assert not os.path.exists(os.path.join(spec.folder, '__pycache__'))


def test_record_whose_id_is_not_its_folder_is_ignored(installer, registry):
    # Remove and approve act on the id, so a record naming another folder must not load.
    spec = install(installer, 'good.py')
    moved = os.path.join(registry.install_dir, 'other_name')
    os.rename(spec.folder, moved)
    registry.refresh()
    assert registry.get('fixture_good') is None


@pytest.mark.parametrize('bad_id', ['fixture_good\n', '../fixture_good', 'Fixture'])
def test_record_with_a_malformed_id_is_ignored(installer, registry, bad_id):
    spec = install(installer, 'good.py')
    path = os.path.join(spec.folder, MANIFEST_FILE)
    with open(path, encoding='utf-8') as handle:
        record = json.load(handle)
    record['manifest']['id'] = bad_id
    with open(path, 'w', encoding='utf-8') as handle:
        json.dump(record, handle)
    registry.refresh()
    assert registry.all() and all(s.id != bad_id for s in registry.all())


def test_remove_deletes_only_the_widget_folder(installer, registry):
    install(installer, 'good.py')
    install(installer, 'folder_widget')
    installer.remove('fixture_good')
    assert registry.get('fixture_folder') is not None
    assert sorted(n for n in os.listdir(registry.install_dir) if not n.startswith('.')) == ['fixture_folder']


@pytest.mark.parametrize('record', [
    [],
    {'manifest': []},
    {'manifest': {'name': 'No id'}, 'files': {}},
    {'manifest': {'id': 'fixture_good', 'options': ['a']}, 'files': {}},
    {'manifest': {'id': 'fixture_good', 'name': 7}, 'files': {}},
])
def test_a_corrupt_record_never_breaks_the_registry(installer, registry, record):
    # One damaged folder used to raise out of WidgetRegistry() and hide every widget.
    install(installer, 'folder_widget')
    folder = os.path.join(registry.install_dir, 'fixture_good')
    os.makedirs(folder)
    with open(os.path.join(folder, MANIFEST_FILE), 'w', encoding='utf-8') as handle:
        json.dump(record, handle)

    fresh = WidgetRegistry(install_dir=registry.install_dir)

    assert fresh.get('fixture_good') is None
    assert fresh.get('fixture_folder') is not None
    assert fresh.all()


@pytest.mark.skipif(os.geteuid() == 0, reason='root reads any file')
def test_an_unreadable_file_marks_the_widget_changed(installer, registry):
    spec = install(installer, 'folder_widget')
    assert registry.get('fixture_folder').runnable
    helper = os.path.join(spec.folder, 'helper.py')
    os.chmod(helper, 0)
    try:
        registry.refresh()
        assert registry.get('fixture_folder').problem is not None
    finally:
        os.chmod(helper, 0o644)


def test_a_nested_manifest_json_is_one_of_the_widget_files(installer, registry, tmp_path):
    # Only the top-level approval record is the app's; a data/manifest.json was dropped too.
    source = tmp_path / 'src'
    shutil.copytree(os.path.join(FIXTURES, 'folder_widget'), source)
    (source / 'data').mkdir()
    (source / 'data' / MANIFEST_FILE).write_text('{"shipped": true}')
    (source / MANIFEST_FILE).write_text('{"forged": true}')

    staged = installer.stage(str(source))
    try:
        assert os.path.isfile(os.path.join(staged.folder, 'data', MANIFEST_FILE))
        assert not os.path.exists(os.path.join(staged.folder, MANIFEST_FILE))
        assert os.path.join('data', MANIFEST_FILE) in staged.files
    finally:
        installer.discard(staged)
