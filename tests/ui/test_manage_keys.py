"""
Manage All Keys: thumbnails with usage, bulk delete, duplicate, and the editor wiring.

The editor once received this dialog as its config_dir (a positional slip),
and new keys got no config_dir at all; both are pinned here.
"""

from unittest.mock import patch

import pytest
from PyQt6.QtWidgets import QDialog, QMessageBox

from StreamDock.application.config_document import ConfigDocument, KeyDefinition
from StreamDock.ui.dialogs import CAPTION_ROLE, ManageKeysDialog


@pytest.fixture
def config(tmp_path):
    doc = ConfigDocument.from_dict({
        "keys": {"Mute": {"text": "M", "on_press_actions": [{"CHANGE_KEY": "Unmute"}]},
                 "Unmute": {"text": "U"},
                 "Old": {"text": "O"},
                 "Older": {"text": "O2"}},
        "layouts": {"Main": {"Default": True, "keys": [{1: "Mute"}]}},
    })
    doc._path = str(tmp_path / "config.yml")
    return doc


@pytest.fixture
def dialog(config, qtbot):
    d = ManageKeysDialog(config)
    qtbot.addWidget(d)
    return d


def caption(dialog, name):
    for row in range(dialog.grid.list.count()):
        item = dialog.grid.list.item(row)
        if item.text() == name:
            return item.data(CAPTION_ROLE)
    raise KeyError(name)


def test_captions_show_where_each_key_is_used(dialog):
    assert caption(dialog, "Mute") == "Main"
    assert caption(dialog, "Unmute") == "via CHANGE_KEY"
    assert caption(dialog, "Old") == "unused"
    assert dialog.summary.text() == "4 keys, 2 unused"


def test_unused_only_filter(dialog):
    dialog.unused_only.setChecked(True)
    assert dialog.grid.visible_names() == ["Old", "Older"]


def test_bulk_delete_of_selected_keys(dialog, config):
    dialog.unused_only.setChecked(True)
    dialog.grid.list.selectAll()
    assert dialog.delete_btn.text() == "Delete 2"
    assert not dialog.edit_btn.isEnabled()
    with patch.object(QMessageBox, "question", return_value=QMessageBox.StandardButton.Yes):
        dialog.delete_selected()
    assert set(config.keys) == {"Mute", "Unmute"}
    assert dialog.was_modified()


def test_declined_delete_keeps_keys(dialog, config):
    dialog.grid.select("Mute")
    with patch.object(QMessageBox, "question", return_value=QMessageBox.StandardButton.No) as ask:
        dialog.delete_selected()
    assert "Main" in ask.call_args.args[2]
    assert "Mute" in config.keys and not dialog.was_modified()


def test_duplicate_selects_the_copy(dialog, config):
    dialog.grid.select("Old")
    dialog.duplicate_selected()
    assert "OldCopy" in config.keys
    assert dialog.grid.current_name() == "OldCopy"


@pytest.mark.parametrize("key_name", [None, "Mute"])
def test_editor_gets_config_dir_and_parent(dialog, config, key_name):
    with patch("StreamDock.ui.dialogs.KeyEditorDialog") as editor_cls:
        editor_cls.return_value.exec.return_value = QDialog.DialogCode.Rejected
        if key_name:
            dialog.edit_key_by_name(key_name)
        else:
            dialog.add_new_key()
    kwargs = editor_cls.call_args.kwargs
    assert kwargs["config_dir"] == config.config_dir
    assert kwargs["parent"] is dialog


def test_rename_in_editor_updates_layouts(dialog, config):
    with patch("StreamDock.ui.dialogs.KeyEditorDialog") as editor_cls:
        editor = editor_cls.return_value
        editor.exec.return_value = QDialog.DialogCode.Accepted
        editor.get_key_definition.return_value = KeyDefinition("Silence", {"text": "M"})
        dialog.edit_key_by_name("Mute")
    assert config.layouts["Main"].keys == {1: "Silence"}
    assert dialog.grid.current_name() == "Silence"
