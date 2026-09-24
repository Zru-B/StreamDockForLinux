"""
Choosing an existing key for a grid square by its thumbnail.

The picker replaced a flat menu of every key; what it must keep is that the
chosen key lands on the square, and that filtering then Enter picks a match.
"""

import os
import tempfile

import pytest
import yaml

from StreamDock.ui.dialogs import KeyPickerDialog
from StreamDock.ui.main_window import MainWindow


CONFIG = {"streamdock": {
    "keys": {name: {"text": name, "on_press_actions": [{"KEY_PRESS": "a"}]}
             for name in ("Volume", "mute", "Browser", "Terminal")},
    "layouts": {"Main": {"Default": True, "keys": [{1: "Volume"}, {2: "Browser"}]}},
}}


@pytest.fixture
def window(qtbot):
    with tempfile.TemporaryDirectory() as workdir:
        path = os.path.join(workdir, "config.yml")
        with open(path, "w", encoding="utf-8") as handle:
            yaml.dump(CONFIG, handle)
        w = MainWindow()
        qtbot.addWidget(w)
        w.load_config(path)
        yield w


def picker(window, qtbot, **kwargs) -> KeyPickerDialog:
    dialog = KeyPickerDialog(window.config.keys, "Assign Key", window.config.config_dir,
                             parent=window, **kwargs)
    qtbot.addWidget(dialog)
    return dialog


def test_keys_are_sorted_without_prefix_and_excluded_key_is_absent(window, qtbot):
    dialog = picker(window, qtbot, exclude={"Volume"})
    assert dialog.grid.visible_names() == ["Browser", "mute", "Terminal"]
    assert [dialog.grid.list.item(row).text() for row in range(3)] == ["Browser", "mute", "Terminal"]
    assert not dialog.grid.list.item(0).icon().isNull()


def test_filter_then_enter_picks_first_match(window, qtbot):
    dialog = picker(window, qtbot)
    dialog.search.setText("TER")
    assert dialog.grid.visible_names() == ["Terminal"]
    dialog.search.returnPressed.emit()
    assert dialog.selected_key == "Terminal"


def test_no_match_disables_assign(window, qtbot):
    dialog = picker(window, qtbot)
    dialog.search.setText("zzz")
    assert dialog.grid.visible_names() == []
    assert not dialog.affirmative_button.isEnabled()
    assert not dialog.grid.empty_label.isHidden()


def test_keys_on_the_layout_are_marked(window, qtbot):
    dialog = picker(window, qtbot, in_layout={"Browser"})
    item = dialog.grid.list.item(0)
    assert item.text() == "Browser"
    assert "Already on this layout" in item.toolTip()


def test_picked_key_lands_on_the_square(window, monkeypatch):
    def fake_exec(dialog):
        dialog.selected_key = "Terminal"
        return dialog.DialogCode.Accepted
    monkeypatch.setattr(KeyPickerDialog, "exec", fake_exec)
    square = window.key_squares[4]
    window.pick_key_for_position(5, square, "Assign Key")
    assert window.current_layout.keys[5] == "Terminal"
    assert square.key_name == "Terminal"
