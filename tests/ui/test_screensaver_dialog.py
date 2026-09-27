"""
The Screensaver dialog: what it shows, what it hands back, and the edit it makes.
"""

from unittest.mock import patch

import pytest
from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import QApplication, QDialog

from StreamDock.application.config_document import ScreensaverSettings
from StreamDock.ui.dialogs import ScreensaverDialog
from StreamDock.ui.main_window import MainWindow


@pytest.fixture
def window(qtbot):
    w = MainWindow()
    qtbot.addWidget(w)
    return w


def open_dialog(qtbot, settings, config_dir='/configs'):
    dialog = ScreensaverDialog(settings, config_dir)
    qtbot.addWidget(dialog)
    return dialog


class TestScreensaverDialog:

    def test_it_shows_the_configured_values(self, qtbot):
        settings = ScreensaverSettings({'enabled': True, 'source': 'online', 'provider': 'bing',
                                        'interval': 7.5, 'turn_off_after': 20,
                                        'folder': 'pics', 'shuffle': False})

        dialog = open_dialog(qtbot, settings)

        assert dialog.get_settings() == {
            'enabled': True, 'source': 'online', 'folder': 'pics', 'provider': 'bing',
            'interval': 7.5, 'turn_off_after': 20, 'shuffle': False, 'brightness': None}

    def test_defaults_hand_back_no_change(self, qtbot):
        settings = ScreensaverSettings()

        dialog = open_dialog(qtbot, settings)

        assert not settings.update(dialog.get_settings())

    def test_its_own_brightness_is_handed_back(self, qtbot):
        dialog = open_dialog(qtbot, ScreensaverSettings({'enabled': True, 'brightness': 40}))

        assert dialog.brightness_toggle.isChecked()
        assert dialog.get_settings()['brightness'] == 40

        dialog.brightness_slider.setValue(70)
        assert dialog.get_settings()['brightness'] == 70

        dialog.brightness_toggle.setChecked(False)
        assert dialog.get_settings()['brightness'] is None
        assert not dialog.brightness_slider.isEnabled()

    def test_a_dim_hand_written_brightness_survives_the_dialog(self, qtbot):
        # The slider stops at the device minimum; opening and saving must
        # not rewrite a value the user chose in the file.
        dialog = open_dialog(qtbot, ScreensaverSettings({'enabled': True, 'brightness': 5}))

        assert dialog.get_settings()['brightness'] == 5

    def test_zero_minutes_reads_never(self, qtbot):
        dialog = open_dialog(qtbot, ScreensaverSettings())

        assert dialog.turn_off_spin.text() == "Never"

    def test_the_rows_follow_the_source(self, qtbot):
        dialog = open_dialog(qtbot, ScreensaverSettings({'enabled': True}))
        dialog.show()

        dialog.online_radio.setChecked(True)

        assert dialog.provider_combo.isVisible()
        assert not dialog.folder_widget.isVisible()

    def test_a_missing_folder_is_not_accepted(self, qtbot, tmp_path):
        dialog = open_dialog(qtbot, ScreensaverSettings(
            {'enabled': True, 'folder': 'nowhere'}), config_dir=str(tmp_path))

        with patch('StreamDock.ui.dialogs.QMessageBox.warning') as warning:
            dialog.validate_and_accept()

        warning.assert_called_once()
        assert dialog.result() != QDialog.DialogCode.Accepted

    def test_an_existing_folder_is_accepted(self, qtbot, tmp_path):
        (tmp_path / 'pics').mkdir()
        dialog = open_dialog(qtbot, ScreensaverSettings(
            {'enabled': True, 'folder': 'pics'}), config_dir=str(tmp_path))

        dialog.validate_and_accept()

        assert dialog.result() == QDialog.DialogCode.Accepted


class TestMenuCommand:

    def test_accepting_a_change_marks_the_document(self, window):
        with patch('StreamDock.ui.main_window.ScreensaverDialog') as dialog_cls:
            dialog_cls.return_value.exec.return_value = QDialog.DialogCode.Accepted
            dialog_cls.return_value.get_settings.return_value = {
                'enabled': True, 'source': 'online', 'provider': 'picsum'}

            window.show_screensaver_settings()

        assert window.config.settings.screensaver.enabled
        assert window.modified

    def test_accepting_no_change_is_not_an_edit(self, window):
        with patch('StreamDock.ui.main_window.ScreensaverDialog') as dialog_cls:
            dialog_cls.return_value.exec.return_value = QDialog.DialogCode.Accepted
            dialog_cls.return_value.get_settings.return_value = {'enabled': False}

            window.show_screensaver_settings()

        assert not window.modified


class TestRealDialog:
    """Through the real exec(): the mocked tests above could not see the dialog being deleted."""

    def test_choosing_online_pictures_is_saved(self, window):
        def drive():
            dialog = next(w for w in QApplication.topLevelWidgets()
                          if isinstance(w, ScreensaverDialog) and w.isVisible())
            dialog.enabled_toggle.click()
            dialog.online_radio.click()
            dialog.affirmative_button.click()

        QTimer.singleShot(0, drive)
        window.show_screensaver_settings()

        assert window.config.settings.screensaver.to_dict() == {'enabled': True,
                                                                'source': 'online'}
        assert window.modified
