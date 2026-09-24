"""Installing, listing, tampering with and removing third-party widgets."""

import os

import pytest

from StreamDock.widgets.installer import InstallError, WidgetInstaller
from StreamDock.widgets.registry import WidgetRegistry

FIXTURES = os.path.join(os.path.dirname(__file__), 'fixtures')


@pytest.fixture
def registry(tmp_path):
    return WidgetRegistry(install_dir=str(tmp_path / 'widgets'))


@pytest.fixture
def installer(registry):
    return WidgetInstaller(registry)


def install(installer, name):
    source = os.path.join(FIXTURES, name)
    report = installer.validate(source)
    assert report.ok, report.errors
    return installer.install(source, report)


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

    report = installer.revalidate('fixture_good')
    installer.approve('fixture_good', report)
    assert registry.get('fixture_good').runnable


def test_failed_validation_cannot_be_installed(installer):
    report = installer.validate(os.path.join(FIXTURES, 'clash.py'))
    with pytest.raises(InstallError):
        installer.install(os.path.join(FIXTURES, 'clash.py'), report)


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
