"""
ActionDialog and KeyEditorDialog: what opens must come back out unchanged,
and what is edited must come back out as edited.
"""

from unittest.mock import Mock, patch

import pytest
from PyQt6.QtCore import QObject, Qt, pyqtSignal
from PyQt6.QtWidgets import QRadioButton

from StreamDock.application.config_document import KeyDefinition
from StreamDock.application.configuration_manager import MAX_FONT_SIZE, MIN_FONT_SIZE
from StreamDock.ui.dialogs import (
    ActionDialog,
    KeyEditorDialog,
    WindowRuleDialog,
)


def dialog_for(qtbot, action, **kwargs):
    dialog = ActionDialog(action, **kwargs)
    qtbot.addWidget(dialog)
    return dialog


def choose_type(dialog, display_name):
    dialog.action_type_combo.setCurrentText(display_name)


class TestBareStringAction:
    """`- DEVICE_BRIGHTNESS_UP` in YAML reaches the dialog as a str."""

    def test_it_opens_and_round_trips(self, qtbot):
        dialog = dialog_for(qtbot, "DEVICE_BRIGHTNESS_UP")

        assert dialog.get_action() == {"DEVICE_BRIGHTNESS_UP": ""}


class TestRadioPairs:
    """Stale radios from an earlier field build used to share the exclusive group."""

    def test_only_the_current_fields_exist(self, qtbot):
        dialog = dialog_for(qtbot, {"DBUS": {"action": "next"}})
        choose_type(dialog, "Change Layout")
        choose_type(dialog, "D-Bus")

        radios = dialog.fields_widget.findChildren(QRadioButton)

        assert len(radios) == 2

    def test_custom_dbus_command_is_saved_as_a_command(self, qtbot):
        dialog = dialog_for(qtbot, None)
        choose_type(dialog, "D-Bus")
        dialog.dbus_custom_radio.setChecked(True)
        dialog.dbus_custom_edit.setText("playerctl stop")

        assert dialog.dbus_preset_radio.isChecked() is False
        assert dialog.get_action() == {"DBUS": "playerctl stop"}

    def test_advanced_change_layout_keeps_its_options(self, qtbot):
        action = {"CHANGE_LAYOUT": {"layout": "B", "clear_all": True}}
        dialog = dialog_for(qtbot, action, available_layouts=["A", "B"])

        assert dialog.get_action() == action

    def test_advanced_launch_application_is_not_lost(self, qtbot):
        dialog = dialog_for(qtbot, None)
        choose_type(dialog, "Launch Application")
        dialog.launch_advanced_radio.setChecked(True)
        dialog.launch_command_edit.setText("firefox --new-window")

        assert dialog.get_action() == {
            "LAUNCH_APPLICATION": {"command": ["firefox", "--new-window"]}}

    def test_nested_sub_layout_widgets_are_removed(self, qtbot):
        """CHANGE_KEY_TEXT puts rows in sub-layouts, which used to stay behind."""
        dialog = dialog_for(qtbot, {"CHANGE_KEY_TEXT": "x"})
        old_bold = dialog.key_text_bold_check
        choose_type(dialog, "Key Press")

        assert old_bold.parent() is None or not old_bold.isVisible()
        assert dialog.fields_layout.count() == 2


class TestDbusRoundTrip:
    """A string is a shell command, a dict a named shortcut; never swapped."""

    def test_a_string_stays_a_string_even_when_it_names_a_shortcut(self, qtbot):
        assert dialog_for(qtbot, {"DBUS": "play_pause"}).get_action() == {"DBUS": "play_pause"}

    def test_a_shortcut_stays_a_shortcut(self, qtbot):
        action = {"DBUS": {"action": "volume_up"}}
        assert dialog_for(qtbot, action).get_action() == action

    def test_an_unlisted_shortcut_stays_a_shortcut(self, qtbot):
        action = {"DBUS": {"action": "play_pause_any"}}
        assert dialog_for(qtbot, action).get_action() == action


class TestLaunchApplication:
    """LAUNCH_APPLICATION forms survive an unrelated edit."""

    @pytest.mark.parametrize("value", [
        "firefox",
        ["code", "--new-window"],
        ["/opt/My App/app"],
        {"command": ["steam"], "process_name": "steamwebhelper", "future": 1},
        {"desktop_file": "firefox.desktop", "force_new": False, "match_type": "contains"},
    ])
    def test_an_untouched_action_comes_back_unchanged(self, qtbot, value):
        action = {"LAUNCH_APPLICATION": value}
        assert dialog_for(qtbot, action).get_action() == action

    def test_editing_advanced_keeps_keys_the_form_does_not_show(self, qtbot):
        dialog = dialog_for(qtbot, {"LAUNCH_APPLICATION": {
            "command": ["steam"], "process_name": "steamwebhelper"}})
        dialog.launch_class_edit.setText("Steam")

        assert dialog.get_action() == {"LAUNCH_APPLICATION": {
            "command": ["steam"], "process_name": "steamwebhelper", "class_name": "Steam"}}

    def test_a_desktop_file_in_simple_mode(self, qtbot):
        dialog = dialog_for(qtbot, None)
        choose_type(dialog, "Launch Application")
        dialog.launch_simple_edit.setText("org.kde.dolphin.desktop")

        assert dialog.get_action() == {
            "LAUNCH_APPLICATION": {"desktop_file": "org.kde.dolphin.desktop"}}

    def test_a_dotted_command_is_still_a_command(self, qtbot):
        """The old '.' heuristic stored `python3.12 app.py` as one string."""
        dialog = dialog_for(qtbot, None)
        choose_type(dialog, "Launch Application")
        dialog.launch_simple_edit.setText("python3.12 'my app.py'")

        assert dialog.get_action() == {"LAUNCH_APPLICATION": ["python3.12", "my app.py"]}


class TestWait:
    def test_a_fraction_of_a_second_survives(self, qtbot):
        assert dialog_for(qtbot, {"WAIT": 0.5}).get_action() == {"WAIT": 0.5}

    def test_a_whole_number_stays_an_int(self, qtbot):
        assert dialog_for(qtbot, {"WAIT": 2}).get_action() == {"WAIT": 2}


class TestChangeKeyTextFontRange:
    def test_the_spin_box_takes_the_validators_range(self, qtbot):
        dialog = dialog_for(qtbot, {"CHANGE_KEY_TEXT": "x"})

        assert dialog.key_text_size_spin.minimum() == MIN_FONT_SIZE
        assert dialog.key_text_size_spin.maximum() == MAX_FONT_SIZE


def key_editor(qtbot, key_def=None, existing=(), previews=None):
    editor = KeyEditorDialog(key_def, list(existing), widget_previews=previews)
    qtbot.addWidget(editor)
    return editor


class TestKeyEditorLoadsLooseValues:
    """Values straight from YAML used to raise TypeError in Qt's setters."""

    def test_odd_text_styling_loads(self, qtbot):
        key_def = KeyDefinition("K")
        key_def.text = 42
        key_def.text_color = 0xFFFFFF
        key_def.background_color = None
        key_def.font_size = 20.5
        key_def.bold = "yes"

        editor = key_editor(qtbot, key_def)

        assert editor.text_edit.text() == "42"
        assert editor.font_size_spin.value() == 20
        assert editor.bold_toggle.isChecked() is True

    def test_the_font_range_is_the_validators(self, qtbot):
        editor = key_editor(qtbot)

        assert editor.font_size_spin.minimum() == MIN_FONT_SIZE
        assert editor.font_size_spin.maximum() == MAX_FONT_SIZE


class TestKeyEditorNameCheck:
    """A refused name keeps the dialog, and the edits, open."""

    @pytest.mark.parametrize("name", ["Taken", "", "   "])
    def test_a_bad_name_is_refused_in_place(self, qtbot, name):
        editor = key_editor(qtbot, existing=["Taken"])
        editor.name_edit.setText(name)

        with patch('StreamDock.ui.dialogs.QMessageBox.warning') as warning:
            editor.accept()

        warning.assert_called_once()
        assert editor.result() != editor.DialogCode.Accepted

    def test_a_free_name_is_accepted(self, qtbot):
        editor = key_editor(qtbot, existing=["Taken"])
        editor.name_edit.setText("Fresh")

        editor.accept()

        assert editor.result() == editor.DialogCode.Accepted


class FakePreviews(QObject):
    preview_ready = pyqtSignal(str)

    def pixmap(self, *_args):
        return None

    def key(self, *_args):
        return ""


class TestKeyEditorLifetime:
    """The shared preview service must not keep closed editors wired up."""

    def test_closing_disconnects_from_the_previews(self, qtbot):
        previews = FakePreviews()
        editor = key_editor(qtbot, previews=previews)
        editor._on_preview_ready = Mock()
        # Re-wire the mock so the test sees calls through the real connection.
        previews.preview_ready.disconnect()
        previews.preview_ready.connect(editor._on_preview_ready)

        editor.reject()
        previews.preview_ready.emit("k")

        editor._on_preview_ready.assert_not_called()

    def test_a_closed_dialog_is_deleted(self, qtbot):
        editor = key_editor(qtbot)

        assert editor.testAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)

    def test_the_widget_description_is_plain_text(self, qtbot):
        """It comes from third-party manifests."""
        editor = key_editor(qtbot)

        assert editor.widget_description.textFormat() == Qt.TextFormat.PlainText


class TestWindowRulePatterns:
    """Commas split plain patterns only; an unedited field is returned as loaded."""

    def rule(self, window_name, is_regex=False):
        return Mock(window_name=window_name, layout="Main", is_regex=is_regex,
                    match_field="class", patterns=lambda: (
                        list(window_name) if isinstance(window_name, list) else [window_name]))

    def open(self, qtbot, rule=None):
        dialog = WindowRuleDialog(["Main"], "R" if rule else None, rule)
        qtbot.addWidget(dialog)
        return dialog

    def test_a_regex_with_a_comma_is_not_split(self, qtbot):
        dialog = self.open(qtbot)
        dialog.regex_check.setChecked(True)
        dialog.window_name_input.setText(r"^fire\w{2,3}$")

        assert dialog.get_rule_data()['window_name'] == r"^fire\w{2,3}$"

    def test_an_unedited_title_with_a_comma_survives(self, qtbot):
        dialog = self.open(qtbot, self.rule("Hello, World"))
        dialog.layout_combo.setCurrentIndex(0)

        assert dialog.get_rule_data()['window_name'] == "Hello, World"

    def test_an_unedited_list_survives(self, qtbot):
        dialog = self.open(qtbot, self.rule(["a", "b"]))

        assert dialog.get_rule_data()['window_name'] == ["a", "b"]

    def test_plain_patterns_still_split_on_commas(self, qtbot):
        dialog = self.open(qtbot)
        dialog.window_name_input.setText("firefox, chromium")

        assert dialog.get_rule_data()['window_name'] == ["firefox", "chromium"]


class TestMissingTargets:
    """A CHANGE_KEY/CHANGE_LAYOUT whose target is gone must not be silently retargeted."""

    def test_a_missing_key_stays_selected(self, qtbot):
        dialog = dialog_for(qtbot, {"CHANGE_KEY": "Gone"}, available_keys=["A", "B"])

        assert dialog.change_key_combo.currentText() == "Gone (missing)"
        assert dialog.get_action() == {"CHANGE_KEY": "Gone"}

    def test_a_missing_key_is_kept_when_there_are_no_keys_at_all(self, qtbot):
        dialog = dialog_for(qtbot, {"CHANGE_KEY": "Gone"})

        assert dialog.get_action() == {"CHANGE_KEY": "Gone"}

    def test_a_missing_layout_stays_selected(self, qtbot):
        dialog = dialog_for(qtbot, {"CHANGE_LAYOUT": "Old"}, available_layouts=["Main"])

        assert dialog.layout_name_combo.currentText() == "Old (missing)"
        assert dialog.get_action() == {"CHANGE_LAYOUT": "Old"}

    def test_a_missing_layout_in_the_advanced_form(self, qtbot):
        dialog = dialog_for(qtbot, {"CHANGE_LAYOUT": {"layout": "Old", "clear_all": True}},
                            available_layouts=["Main"])

        assert dialog.get_action() == {"CHANGE_LAYOUT": {"layout": "Old", "clear_all": True}}

    def test_a_present_target_is_selected_plainly(self, qtbot):
        dialog = dialog_for(qtbot, {"CHANGE_KEY": "B"}, available_keys=["A", "B"])

        assert dialog.change_key_combo.currentText() == "B"


class TestLowercaseActionTypes:
    """The runtime takes any case; the dialog opens it as the right type and writes it upper."""

    def test_a_lowercase_type_opens_as_that_type(self, qtbot):
        dialog = dialog_for(qtbot, {"key_press": "ctrl+c"})

        assert dialog.get_action() == {"KEY_PRESS": "ctrl+c"}

    def test_a_lowercase_launch_is_kept_as_is(self, qtbot):
        dialog = dialog_for(qtbot, {"launch_application": {"command": "x", "process_name": "y"}})

        assert dialog.get_action() == {"LAUNCH_APPLICATION": {"command": "x", "process_name": "y"}}
