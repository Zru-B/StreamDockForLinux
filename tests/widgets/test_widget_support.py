"""The manager dialog's install order and how it shows a widget's own text."""

import os
import shutil
import threading
from unittest.mock import patch

import pytest
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QLabel, QMessageBox

from streamdock_sdk import Option
from StreamDock.ui import widget_support
from StreamDock.ui.widget_support import WidgetManagerDialog, WidgetOptionsForm, render_preview
from StreamDock.widgets.registry import WidgetRegistry, file_digests

FIXTURES = os.path.join(os.path.dirname(__file__), 'fixtures')


@pytest.fixture
def registry(tmp_path):
    return WidgetRegistry(install_dir=str(tmp_path / 'widgets'))


@pytest.fixture
def dialog(qtbot, registry):
    dialog = WidgetManagerDialog(registry)
    qtbot.addWidget(dialog)
    return dialog


def widget_folder(tmp_path, name="'Good'", extra=''):
    folder = tmp_path / 'src'
    folder.mkdir()
    source = open(os.path.join(FIXTURES, 'good.py'), encoding='utf-8').read()
    (folder / 'widget.py').write_text(source.replace("name = 'Good'", f'name = {name}') + extra)
    return str(folder)


def test_the_widget_runs_only_after_consent(dialog, registry, tmp_path):
    # Checking a widget before asking used to execute it before the user agreed.
    marker = tmp_path / 'ran'
    source = widget_folder(tmp_path, extra=f'\nopen({str(marker)!r}, "w").close()\n')
    ran_before_consent = []
    dialog.choose_source = lambda: source
    dialog.confirm_consent = lambda *args: ran_before_consent.append(marker.exists()) or True

    dialog.install()

    assert ran_before_consent == [False]
    assert marker.exists()
    assert registry.get('fixture_good').runnable


def test_declined_consent_runs_nothing_and_leaves_no_staging(dialog, registry, tmp_path):
    marker = tmp_path / 'ran'
    source = widget_folder(tmp_path, extra=f'\nopen({str(marker)!r}, "w").close()\n')
    dialog.choose_source = lambda: source
    dialog.confirm_consent = lambda *args: False

    dialog.install()

    assert not marker.exists()
    assert os.listdir(registry.install_dir) == []


def test_approve_again_uses_the_checked_copy(dialog, registry, tmp_path):
    dialog.choose_source = lambda: widget_folder(tmp_path)
    dialog.confirm_consent = lambda *args: True
    dialog.install()
    script = registry.get('fixture_good').script_path
    with open(script, 'a', encoding='utf-8') as handle:
        handle.write('\n# edited\n')
    registry.refresh()
    dialog.refresh(select='fixture_good')

    dialog.approve_again()

    assert registry.get('fixture_good').runnable


def test_details_show_the_widget_text_literally(dialog, registry, tmp_path):
    dialog.choose_source = lambda: widget_folder(tmp_path, name="'<img src=x>Clock'")
    dialog.confirm_consent = lambda *args: True
    dialog.install()

    assert dialog.selected().id == 'fixture_good'
    assert '&lt;img src=x&gt;Clock' in dialog.details.text()
    assert '<img' not in dialog.details.text()


def test_consent_prompt_is_plain_text(dialog, tmp_path):
    staged = dialog.installer.stage(widget_folder(tmp_path, name="'<b>Bold</b>'"))
    formats = []

    def capture(box):
        formats.extend(label.textFormat() for label in box.findChildren(QLabel) if label.text())
        return 0

    try:
        with patch.object(QMessageBox, 'exec', capture):
            dialog.confirm_consent(staged.report, 'Install?', '')
    finally:
        dialog.installer.discard(staged)
    assert formats and set(formats) == {Qt.TextFormat.PlainText}


def test_option_description_tooltip_is_escaped(qtbot):
    form = WidgetOptionsForm([Option.string('label', description='<img src=x> & more')])
    qtbot.addWidget(form)
    editor = form._editors['label']
    assert editor.toolTip() == '<p>&lt;img src=x&gt; &amp; more</p>'


def test_preview_refuses_files_changed_since_approval(tmp_path, monkeypatch):
    folder = tmp_path / 'w'
    folder.mkdir()
    shutil.copyfile(os.path.join(FIXTURES, 'good.py'), folder / 'widget.py')
    registry = WidgetRegistry(install_dir=str(tmp_path / 'none'))
    spec = registry.get('digital_clock')
    spec = type(spec)(manifest={'id': 'fixture_good', 'options': []}, builtin=False,
                      script_path=str(folder / 'widget.py'), folder=str(folder),
                      files=file_digests(str(folder)))
    (folder / 'widget.py').write_text('raise SystemExit(1)\n')
    spawned = []
    monkeypatch.setattr(widget_support, 'render_in_subprocess', lambda *args: spawned.append(args))

    render_preview(spec, 'fixture_good', {})

    assert spawned == []


@pytest.mark.parametrize('default', [0.125, 1 / 3, 2.5])
def test_an_untouched_float_form_writes_nothing(qtbot, default):
    # Two fixed decimals rounded 0.125 to 0.12, which then differed from the default.
    form = WidgetOptionsForm([Option.float('scale', default, minimum=0.0, maximum=10.0)])
    qtbot.addWidget(form)
    assert form.values() == {}
    assert form._raw(form._options[0]) == pytest.approx(default, abs=1e-6)


def test_int_bounds_round_inwards(qtbot):
    form = WidgetOptionsForm([Option('count', 'int', 2, minimum=1.5, maximum=4.5)])
    qtbot.addWidget(form)
    editor = form._editors['count']
    assert (editor.minimum(), editor.maximum()) == (2, 4)


def test_choosing_a_widget_py_asks_before_taking_its_folder(dialog, tmp_path, monkeypatch):
    folder = widget_folder(tmp_path)
    path = os.path.join(folder, 'widget.py')
    monkeypatch.setattr(widget_support.QFileDialog, 'getOpenFileName', lambda *args: (path, ''))
    asked = []
    dialog.confirm_folder = lambda chosen: asked.append(chosen) or False
    assert dialog.choose_source() is None
    dialog.confirm_folder = lambda chosen: asked.append(chosen) or True
    assert dialog.choose_source() == folder
    assert asked == [folder, folder]


def test_approving_again_labels_the_button_approve(dialog, tmp_path):
    staged = dialog.installer.stage(widget_folder(tmp_path))
    labels = []

    def capture(box):
        labels.extend(button.text() for button in box.buttons())
        return 0

    try:
        with patch.object(QMessageBox, 'exec', capture):
            dialog.confirm_consent(staged.report, 'Approve the changed files of Install Helper?', '', 'Approve')
    finally:
        dialog.installer.discard(staged)
    assert 'Approve' in labels and 'Install' not in labels


class TestPreviewService:
    @pytest.fixture
    def service(self, qtbot, registry):
        return widget_support.WidgetPreviewService(registry)

    def test_a_failed_preview_still_answers(self, qtbot, service, monkeypatch):
        # An exception escaping the job left the key pending, and the caller waiting, for good.
        def boom(*args):
            raise RuntimeError('boom')
        monkeypatch.setattr(widget_support, 'render_preview', boom)

        with qtbot.waitSignal(service.preview_ready, timeout=5000) as ready:
            assert service.pixmap('digital_clock', {}) is None
        assert ready.args[0] not in service._pending
        assert service.pixmap('digital_clock', {}) is not None

    def test_a_snapshot_from_before_clear_is_dropped(self, qtbot, service):
        key = service.key('digital_clock', {})
        service._pending.add(key)
        generation = service._generation
        service.clear()
        service._store(key, generation, widget_support.error_tile('x'))
        assert key not in service._cache and not service._pending

    def test_the_cache_is_bounded(self, qtbot, service, monkeypatch):
        monkeypatch.setattr(widget_support, 'PREVIEW_CACHE_SIZE', 3)
        for index in range(5):
            service._store(f'k{index}', service._generation, widget_support.error_tile('x'))
        assert list(service._cache) == ['k2', 'k3', 'k4']

    def test_the_key_changes_when_an_image_is_saved_again(self, tmp_path):
        from PIL import Image
        from StreamDock.widgets.appearance import Appearance
        icon = tmp_path / 'icon.png'
        Image.new('RGB', (4, 4)).save(icon)
        appearance = Appearance(icon=str(icon))
        before = widget_support._cache_key('w', {}, appearance)
        os.utime(icon, (1, 1))
        assert widget_support._cache_key('w', {}, appearance) != before

    def test_a_superseded_queued_request_is_cancelled(self, qtbot, service, monkeypatch):
        release = threading.Event()
        monkeypatch.setattr(widget_support, 'render_preview',
                            lambda *args: release.wait(5) and widget_support.error_tile('x'))
        requester = object()
        # Two workers: fill them, then queue two requests from one requester.
        service.pixmap('digital_clock', {'format': '12h'})
        service.pixmap('analog_clock', {})
        service.pixmap('date', {}, requester=requester)
        first = service._queued[id(requester)][1]
        service.pixmap('date', {'format': 'iso'}, requester=requester)
        release.set()
        assert first.cancelled()
        assert service.key('date', {}) not in service._pending

    def test_shutdown_stops_new_work(self, service):
        service.shutdown()
        assert service.pixmap('digital_clock', {}) is None
        assert not service._pending
