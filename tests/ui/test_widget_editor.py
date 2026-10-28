"""Widget keys in the editor: the key dialog's Widget mode, grid previews, the manager."""

import os
from unittest.mock import patch

import pytest
from PIL import Image
from PyQt6.QtCore import Qt

from StreamDock.application.config_document import KeyDefinition
from StreamDock.ui.dialogs import DISPLAY_TEXT, DISPLAY_WIDGET, KeyEditorDialog
from StreamDock.ui.widget_support import WidgetManagerDialog, WidgetPreviewService
from StreamDock.ui.widgets import KeySquare
from StreamDock.widgets.registry import WidgetRegistry

FIXTURES = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'widgets', 'fixtures')


@pytest.fixture
def registry(tmp_path):
    return WidgetRegistry(install_dir=str(tmp_path / 'widgets'))


@pytest.fixture
def previews(registry):
    return WidgetPreviewService(registry)


def open_editor(qtbot, registry, previews, key_def=None):
    dialog = KeyEditorDialog(key_def, widget_registry=registry, widget_previews=previews)
    qtbot.addWidget(dialog)
    return dialog


def clock_key(**options):
    return KeyDefinition('Clock', {'widget': 'digital_clock', 'widget_options': options,
                                   'on_press_actions': [{'KEY_PRESS': 'a'}]})


class TestKeyEditorWidgetMode:
    def test_a_widget_key_opens_in_widget_mode_with_its_options(self, qtbot, registry, previews):
        dialog = open_editor(qtbot, registry, previews, clock_key(format='12h'))

        assert dialog.display_type.current() == DISPLAY_WIDGET
        assert dialog.current_widget_id() == 'digital_clock'
        assert dialog.widget_options() == {'format': '12h'}

    def test_only_changed_options_are_written(self, qtbot, registry, previews):
        # Keeps config.yml short: defaults stay implicit unless the file had them.
        dialog = open_editor(qtbot, registry, previews, clock_key(format='12h'))
        dialog.widget_options_form.set_raw('show_seconds', True)

        key_def = dialog.get_key_definition()
        assert key_def.widget == 'digital_clock'
        assert key_def.widget_options == {'format': '12h', 'show_seconds': True}
        assert key_def.on_press_actions == [{'KEY_PRESS': 'a'}]

    def test_choosing_widget_mode_on_a_text_key_drops_the_text(self, qtbot, registry, previews):
        key_def = KeyDefinition('K', {'text': 'hi', 'on_press_actions': [{'KEY_PRESS': 'a'}]})
        dialog = open_editor(qtbot, registry, previews, key_def)
        dialog.display_type.set_current(DISPLAY_WIDGET)
        dialog.select_widget('date')

        result = dialog.get_key_definition().to_dict()
        assert result['widget'] == 'date'
        assert 'text' not in result

    def test_fields_the_dialog_does_not_show_survive_an_edit(self, qtbot, registry, previews):
        key_def = KeyDefinition('K', {'text': 'hi', 'text_position': 'top', 'future_field': 1,
                                      'on_press_actions': [{'KEY_PRESS': 'a'}]})
        dialog = open_editor(qtbot, registry, previews, key_def)
        assert dialog.display_type.current() == DISPLAY_TEXT

        result = dialog.get_key_definition().to_dict()
        assert result['text_position'] == 'top'
        assert result['future_field'] == 1

    def test_uninstalled_widget_keeps_its_settings(self, qtbot, registry, previews):
        key_def = KeyDefinition('W', {'widget': 'gone', 'widget_options': {'x': 1}})
        dialog = open_editor(qtbot, registry, previews, key_def)

        assert 'not installed' in dialog.widget_combo.currentText()
        assert dialog.get_key_definition().widget_options == {'x': 1}

    def test_invalid_option_keeps_the_dialog_open(self, qtbot, registry, previews):
        dialog = open_editor(qtbot, registry, previews, clock_key())
        dialog.widget_options_form.set_raw('color', 'not-a-colour')

        with patch('StreamDock.ui.dialogs.QMessageBox.warning') as warning:
            dialog.accept()
        warning.assert_called_once()
        assert dialog.result() != dialog.DialogCode.Accepted

    def test_preview_arrives(self, qtbot, registry, previews):
        dialog = open_editor(qtbot, registry, previews, clock_key())
        qtbot.waitUntil(lambda: dialog.widget_preview.pixmap() is not None
                        and not dialog.widget_preview.pixmap().isNull(), timeout=5000)


def test_grid_square_shows_the_widget_snapshot(qtbot, previews):
    square = KeySquare(1)
    qtbot.addWidget(square)
    square.set_preview_service(previews)
    square.set_key('Clock', clock_key())

    qtbot.waitUntil(lambda: square.label.pixmap() is not None and not square.label.pixmap().isNull(),
                    timeout=5000)


class TestWidgetManager:
    @pytest.fixture
    def dialog(self, qtbot, registry):
        dialog = WidgetManagerDialog(registry)
        qtbot.addWidget(dialog)
        return dialog

    def test_lists_the_builtins(self, dialog):
        ids = [dialog.list.item(row).data(Qt.ItemDataRole.UserRole) for row in range(dialog.list.count())]
        assert 'digital_clock' in ids and 'mic_muted' in ids
        assert not dialog.remove_btn.isEnabled()

    def test_install_asks_consent_then_lists_the_widget(self, dialog, qtbot, registry):
        consent = []
        dialog.choose_source = lambda: os.path.join(FIXTURES, 'capabilities.py')
        dialog.confirm_consent = lambda report, question, extra: consent.append(report.capabilities) or True

        with qtbot.waitSignal(dialog.widgets_changed):
            dialog.install()

        assert consent == [['runs code built at runtime', 'runs other programs', 'uses the network']]
        assert registry.get('fixture_capable') is not None
        assert dialog.selected().id == 'fixture_capable'
        assert dialog.remove_btn.isEnabled()

    def test_declined_consent_installs_nothing(self, dialog, registry):
        dialog.choose_source = lambda: os.path.join(FIXTURES, 'good.py')
        dialog.confirm_consent = lambda *args: False
        dialog.install()
        assert registry.get('fixture_good') is None

    def test_invalid_widget_is_reported_not_installed(self, dialog, registry):
        reported = []
        dialog.choose_source = lambda: os.path.join(FIXTURES, 'clash.py')
        dialog._report_errors = lambda report, title: reported.append(report.errors) or report.ok
        dialog.install()
        assert reported and 'built-in' in reported[0][0]


class TestImagesTab:
    @pytest.fixture
    def images(self, tmp_path):
        for name, color in (('slack.png', 'white'), ('on.png', 'green')):
            Image.new('RGB', (112, 112), color).save(tmp_path / name)
        return tmp_path

    def test_state_rows_follow_the_widget(self, qtbot, registry, previews):
        dialog = open_editor(qtbot, registry, previews, KeyDefinition('V', {'widget': 'vpn_connected'}))
        assert list(dialog.widget_images_form.state_fields) == ['connected', 'disconnected', 'unknown']
        assert dialog.widget_images_form.badge_show is None

        dialog.select_widget('slack_notifications')
        assert list(dialog.widget_images_form.state_fields) == ['unread', 'none', 'unavailable']
        assert dialog.widget_images_form.badge_show is not None

    def test_images_and_badge_round_trip(self, qtbot, registry, previews):
        data = {'widget': 'slack_notifications', 'icon': 'slack.png',
                'state_icons': {'unread': 'on.png'}, 'badge': {'position': 'bottom_left'}}
        dialog = open_editor(qtbot, registry, previews, KeyDefinition('S', data))
        assert dialog.get_key_definition().to_dict() == data

    def test_default_badge_is_left_out_and_hidden_badge_is_false(self, qtbot, registry, previews):
        dialog = open_editor(qtbot, registry, previews, KeyDefinition('S', {'widget': 'slack_notifications',
                                                                             'icon': 'slack.png'}))
        assert 'badge' not in dialog.get_key_definition().to_dict()
        dialog.widget_images_form.badge_show.setChecked(False)
        assert dialog.get_key_definition().to_dict()['badge'] is False

    def test_switching_widget_keeps_the_base_image_but_not_state_images(self, qtbot, registry, previews):
        dialog = open_editor(qtbot, registry, previews, KeyDefinition('V', {
            'widget': 'vpn_connected', 'icon': 'base.png', 'state_icons': {'connected': 'on.png'}}))
        dialog.select_widget('mic_muted')
        result = dialog.get_key_definition().to_dict()
        assert result['icon'] == 'base.png'
        assert 'state_icons' not in result

    def test_preview_is_the_users_image_with_a_sample_badge(self, qtbot, registry, previews, images):
        dialog = KeyEditorDialog(KeyDefinition('S', {'widget': 'slack_notifications', 'icon': 'slack.png'}),
                                 config_dir=str(images), widget_registry=registry, widget_previews=previews)
        qtbot.addWidget(dialog)
        qtbot.waitUntil(lambda: dialog.widget_preview.pixmap() is not None
                        and not dialog.widget_preview.pixmap().isNull(), timeout=5000)
        preview = dialog.widget_preview.pixmap().toImage()
        assert preview.pixelColor(20, 90).name() == '#ffffff'
        assert preview.pixelColor(100, 18).red() > 200 and preview.pixelColor(100, 18).green() < 100
