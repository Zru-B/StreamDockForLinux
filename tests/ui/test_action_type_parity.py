"""
The editor must be able to edit every action the runtime can execute.

CHANGE_KEY_TEXT was missing from the hand-written list for a long time, so
this guards against the list drifting again.
"""

from StreamDock.business_logic.action_type import ActionType
from StreamDock.ui.dialogs import ActionDialog


def test_every_runtime_action_is_offered():
    assert set(ActionDialog.ACTION_TYPE_DISPLAY) == {a.name for a in ActionType}


def test_no_action_is_offered_that_the_runtime_cannot_run():
    assert set(ActionDialog.ACTION_TYPE_DISPLAY) <= {a.name for a in ActionType}


def test_labels_are_unique():
    labels = list(ActionDialog.ACTION_TYPE_DISPLAY.values())
    assert len(labels) == len(set(labels))


def test_reverse_lookup_round_trips():
    for name, label in ActionDialog.ACTION_TYPE_DISPLAY.items():
        assert ActionDialog.ACTION_TYPE_BACKEND[label] == name


def test_every_action_type_builds_its_field_editor(qtbot):
    """A field editor missing for one action would crash the dialog."""
    for name, label in ActionDialog.ACTION_TYPE_DISPLAY.items():
        dialog = ActionDialog(config_dir="/tmp")
        qtbot.addWidget(dialog)
        index = dialog.action_type_combo.findText(label)
        assert index >= 0, f"{name} missing from the combo"
        dialog.action_type_combo.setCurrentIndex(index)


def test_change_key_text_round_trips(qtbot):
    payload = {'CHANGE_KEY_TEXT': {
        'text': 'Hi', 'text_color': 'red', 'background_color': 'blue',
        'font_size': 33, 'bold': False, 'text_position': 'top'}}

    dialog = ActionDialog(payload, config_dir="/tmp")
    qtbot.addWidget(dialog)

    assert dialog.get_action() == payload
