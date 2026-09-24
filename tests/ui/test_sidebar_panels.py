"""
The Layouts and Window Rules panels, and the dialogs they open.

Guards: a rule whose window_name is a list used to crash the editor; rows
must show what a rule does and in what order rules are tried; and the
keyboard and double-click paths must reach the same handlers as the menu.
"""

import os
import tempfile
import pytest
import yaml
from PyQt6.QtWidgets import QDialog

from StreamDock.domain.Models import WindowInfo
from StreamDock.ui.dialogs import DeleteLayoutDialog, LayoutEditorDialog, WindowRuleDialog
from StreamDock.ui.main_window import MainWindow
from StreamDock.ui.widgets import SIDEBAR_CAPTION_ROLE, SIDEBAR_PROBLEM_ROLE, LayoutListWidget


CONFIG = {"streamdock": {
    "keys": {"A": {"text": "A", "on_press_actions": [{"KEY_PRESS": "a"}]},
             "ToIde": {"text": "I", "on_press_actions": [{"CHANGE_LAYOUT": "IDE"}]}},
    "layouts": {"Main": {"Default": True, "keys": [{1: "A"}, {2: "ToIde"}]},
                "IDE": {"keys": [{1: "A"}]},
                "Spare": {"keys": [{3: "A"}]}},
    "windows_rules": {
        "Idea": {"window_name": ["jetbrains-idea", "pycharm"], "layout": "IDE"},
        "Meet": {"window_name": "Google Meet", "layout": "Main", "match_field": "title"},
    },
}}

WINDOWS = [WindowInfo(title="Google Meet - Standup", class_="chrome"),
           WindowInfo(title="main.py - PyCharm", class_="jetbrains-pycharm"),
           WindowInfo(title="StreamDock", class_="streamdock")]


@pytest.fixture
def window(qtbot):
    with tempfile.TemporaryDirectory() as workdir:
        path = os.path.join(workdir, "config.yml")
        with open(path, "w", encoding="utf-8") as handle:
            yaml.dump(CONFIG, handle)
        w = MainWindow()
        qtbot.addWidget(w)
        w.load_config(path)
        w.recent_windows_provider = lambda: list(WINDOWS)
        yield w


def rows(section):
    return [(section.list_widget.item(i).text(), section.list_widget.item(i).data(SIDEBAR_CAPTION_ROLE),
             section.list_widget.item(i).data(SIDEBAR_PROBLEM_ROLE))
            for i in range(section.list_widget.count())]


def test_rule_rows_show_pattern_target_and_field(window):
    assert rows(window.window_rules_widget) == [
        ("jetbrains-idea, pycharm", "→ IDE · by class", None),
        ("Google Meet", "→ Main · by title", None),
    ]


def test_layout_rows_show_fill_and_reachability(window):
    captions = {text: (caption, problem) for text, caption, problem in rows(window.layout_list)}
    assert captions["Main"] == ("2 / 15 keys · 1 rule", None)
    assert captions["IDE"] == ("1 / 15 keys · 1 rule · via key", None)
    assert captions["Spare"] == ("1 / 15 keys · unreachable", "warning")


def test_editing_a_list_pattern_rule_round_trips(window, qtbot):
    rule = window.config.window_rules["Idea"]
    dialog = WindowRuleDialog(list(window.config.layouts), "Idea", rule, parent=window,
                              recent_windows=WINDOWS)
    qtbot.addWidget(dialog)
    assert dialog.window_name_input.text() == "jetbrains-idea, pycharm"
    assert dialog.get_rule_data()["window_name"] == ["jetbrains-idea", "pycharm"]
    # The PyCharm window matches through the second pattern, the same way the runtime decides.
    bold = [dialog.recent_list.item(i).font().bold() for i in range(dialog.recent_list.count())]
    assert bold == [False, True, False]
    assert "Matches 1" in dialog.match_summary.text()


def test_picking_a_recent_window_fills_the_field_being_matched(window, qtbot):
    dialog = WindowRuleDialog(list(window.config.layouts), parent=window, recent_windows=WINDOWS,
                              suggest_name=window.config.suggest_rule_name)
    qtbot.addWidget(dialog)
    dialog.recent_list.itemClicked.emit(dialog.recent_list.item(1))
    assert dialog.window_name_input.text() == "jetbrains-pycharm"
    dialog.match_field_combo.setCurrentIndex(dialog.match_field_combo.findData("title"))
    dialog.recent_list.itemClicked.emit(dialog.recent_list.item(0))
    assert dialog.window_name_input.text() == "Google Meet - Standup"
    assert dialog.get_rule_data()["name"] == "GoogleMeetStandupRule"


def test_own_windows_are_left_out_of_the_picker(window):
    assert [w.class_ for w in window._recent_windows()] == ["chrome", "jetbrains-pycharm"]


def test_dragged_order_becomes_the_file_order(window, qtbot):
    window.window_rules_widget.order_changed.emit(["Meet", "Idea"])
    qtbot.waitUntil(lambda: list(window.config.window_rules) == ["Meet", "Idea"])
    assert [text for text, _, _ in rows(window.window_rules_widget)][0] == "Google Meet"
    assert window.modified


def test_move_menu_step_reorders(window, qtbot):
    window.window_rules_widget.move("Meet", -1)
    qtbot.waitUntil(lambda: list(window.config.window_rules) == ["Meet", "Idea"])


def test_clicking_a_rule_shows_its_layout(window):
    window.window_rules_widget.rule_selected.emit("Idea")
    assert window.current_layout.name == "IDE"


def test_activation_and_delete_key_reach_the_handlers(qtbot):
    section = LayoutListWidget()
    qtbot.addWidget(section)
    section.set_layouts(["Main", "Spare"], "Main")
    section.select("Spare")
    with qtbot.waitSignal(section.edit_layout_clicked) as edited:
        section.list_widget.itemActivated.emit(section.list_widget.currentItem())
    assert edited.args == ["Spare"]
    with qtbot.waitSignal(section.delete_layout_clicked) as deleted:
        section._delete_current()
    assert deleted.args == ["Spare"]


def test_deleting_a_layout_can_move_its_rules(window, monkeypatch):
    def accept_moving_to_spare(dialog):
        dialog.target_combo.setCurrentText("Spare")
        return QDialog.DialogCode.Accepted
    monkeypatch.setattr(DeleteLayoutDialog, "exec", accept_moving_to_spare)
    window.delete_layout("IDE")
    assert "IDE" not in window.config.layouts
    assert window.config.window_rules["Idea"].layout == "Spare"


def test_duplicate_and_rename_from_the_panel(window, monkeypatch):
    window.duplicate_layout("IDE")
    assert window.current_layout.name == "IDECopy"

    def rename(dialog):
        assert not dialog.clear_all_toggle.isVisibleTo(dialog)
        dialog.name_input.setText("Code")
        return QDialog.DialogCode.Accepted
    monkeypatch.setattr(LayoutEditorDialog, "exec", rename)
    window.edit_layout("IDE", rename_only=True)
    assert window.config.window_rules["Idea"].layout == "Code"
    assert window.config.keys["ToIde"].on_press_actions == [{"CHANGE_LAYOUT": "Code"}]


def test_new_rule_for_a_layout_starts_aimed_at_it(window, monkeypatch):
    seen = {}

    def capture(dialog):
        seen["layout"] = dialog.layout_combo.currentText()
        return QDialog.DialogCode.Rejected
    monkeypatch.setattr(WindowRuleDialog, "exec", capture)
    window.layout_list.add_rule_for_layout_clicked.emit("Spare")
    assert seen["layout"] == "Spare"


def test_regex_rules_preview_and_reject_bad_patterns(window, qtbot, monkeypatch):
    dialog = WindowRuleDialog(list(window.config.layouts), parent=window, recent_windows=WINDOWS)
    qtbot.addWidget(dialog)
    dialog.window_name_input.setText("^jetbrains-")
    assert "none" in dialog.match_summary.text()
    dialog.regex_check.setChecked(True)
    assert "Matches 1" in dialog.match_summary.text()
    dialog.window_name_input.setText("([")
    assert "Not a valid regular expression" in dialog.match_summary.text()
    warned = []
    monkeypatch.setattr("StreamDock.ui.dialogs.QMessageBox.warning", lambda *a: warned.append(a))
    dialog.validate_and_accept()
    assert warned and dialog.result() != QDialog.DialogCode.Accepted
