"""
The controls the key and layout editors are built from.

The switch and the segmented control replaced a checkbox and a pair of radio
buttons; what matters is that they still carry the same values in and out.
"""

import pytest
from PyQt6.QtCore import QMimeData, QPointF, Qt
from PyQt6.QtGui import QDropEvent

from StreamDock.application.config_document import KeyDefinition
from StreamDock.ui.dialogs import (
    DISPLAY_ICON,
    DISPLAY_TEXT,
    ActionEditorWidget,
    KeyEditorDialog,
    LayoutEditorDialog,
)
from StreamDock.ui.widgets import (
    ACTION_MIME_TYPE,
    ActionListItem,
    ElidedLabel,
    SegmentedControl,
)


@pytest.fixture
def segments(qtbot):
    control = SegmentedControl(["One", "Two", "Three"])
    qtbot.addWidget(control)
    return control


@pytest.fixture
def text_key():
    key_def = KeyDefinition("Volume")
    key_def.text = "Vol+"
    key_def.bold = False
    return key_def


def open_key_editor(qtbot, key_def=None):
    dialog = KeyEditorDialog(key_def)
    qtbot.addWidget(dialog)
    return dialog


class TestSegmentedControl:
    """One pill, one option lit."""

    def test_it_starts_on_the_first_option(self, segments):
        assert segments.current() == "One"

    def test_choosing_an_option_reports_it_once(self, segments, qtbot):
        with qtbot.waitSignal(segments.selection_changed) as chosen:
            segments.set_current("Three")

        assert chosen.args == ["Three"]
        assert segments.current() == "Three"

    def test_an_unknown_option_leaves_the_selection_alone(self, segments):
        segments.set_current("Four")

        assert segments.current() == "One"

    def test_only_one_option_is_ever_selected(self, segments):
        segments.set_current("Two")
        segments.set_current("Three")

        assert segments.current() == "Three"


class TestKeyEditorDisplayType:
    """The segmented control drives which half of the form is shown."""

    def test_a_new_key_starts_on_icon(self, qtbot):
        dialog = open_key_editor(qtbot)

        assert dialog.display_type.current() == DISPLAY_ICON
        assert not dialog.icon_widget.isHidden()
        assert dialog.text_widget.isHidden()

    def test_a_text_key_opens_on_text(self, qtbot, text_key):
        dialog = open_key_editor(qtbot, text_key)

        assert dialog.display_type.current() == DISPLAY_TEXT
        assert dialog.icon_widget.isHidden()
        assert not dialog.text_widget.isHidden()

    def test_switching_to_text_swaps_the_panels(self, qtbot):
        dialog = open_key_editor(qtbot)

        dialog.display_type.set_current(DISPLAY_TEXT)

        assert dialog.icon_widget.isHidden()
        assert not dialog.text_widget.isHidden()

    def test_the_chosen_type_decides_what_is_saved(self, qtbot, text_key):
        dialog = open_key_editor(qtbot, text_key)
        dialog.display_type.set_current(DISPLAY_ICON)

        key_def = dialog.get_key_definition()

        assert key_def.text is None


class TestKeyEditorBoldSwitch:
    """Bold is a switch now; it must still round-trip."""

    def test_it_loads_the_keys_value(self, qtbot, text_key):
        dialog = open_key_editor(qtbot, text_key)

        assert dialog.bold_toggle.isChecked() is False

    def test_it_reaches_the_saved_key(self, qtbot, text_key):
        dialog = open_key_editor(qtbot, text_key)

        dialog.bold_toggle.setChecked(True)

        assert dialog.get_key_definition().bold is True


class TestLayoutEditorClearAll:
    """The layout editor's checkbox is a switch now."""

    def test_it_opens_on_the_layouts_value(self, qtbot):
        dialog = LayoutEditorDialog("Main", clear_all=True)
        qtbot.addWidget(dialog)

        assert dialog.clear_all_toggle.isChecked()

    def test_it_reaches_the_layout_data(self, qtbot):
        dialog = LayoutEditorDialog("Main", clear_all=False)
        qtbot.addWidget(dialog)

        dialog.clear_all_toggle.setChecked(True)

        assert dialog.get_layout_data()['clear_all'] is True


LONG_ACTION = {"EXECUTE_COMMAND": "/usr/bin/playerctl --player=spotify next-track"}


def shown_at(qtbot, text: str, width: int) -> ElidedLabel:
    """An ElidedLabel laid out at a given width; eliding follows a resize."""
    label = ElidedLabel(text)
    qtbot.addWidget(label)
    label.resize(width, 20)
    label.show()
    return label


@pytest.fixture
def action_list(qtbot):
    widget = ActionEditorWidget()
    qtbot.addWidget(widget)
    return widget


class TestElidedLabel:
    """Long text shortens rather than widening whatever holds it."""

    def test_it_keeps_the_text_it_was_given(self, qtbot):
        label = ElidedLabel("a fairly long description of an action")
        qtbot.addWidget(label)

        assert label.full_text() == "a fairly long description of an action"

    def test_a_narrow_label_shows_an_ellipsis(self, qtbot):
        label = shown_at(qtbot, "a fairly long description of an action", 60)

        qtbot.waitUntil(lambda: label.text() != label.full_text())
        assert label.text().endswith("\u2026")
        assert label.toolTip() == label.full_text()

    def test_a_wide_label_shows_everything(self, qtbot):
        label = shown_at(qtbot, "short", 400)

        qtbot.waitUntil(lambda: label.text() == "short")
        assert label.toolTip() == ""

    def test_it_never_demands_room_for_the_whole_text(self, qtbot):
        label = ElidedLabel("a fairly long description of an action")
        qtbot.addWidget(label)

        assert label.minimumSizeHint().width() == 0


class TestActionRows:
    """Each action is one row of fixed height, however many there are."""

    def test_a_row_is_one_line_tall(self, qtbot):
        row = ActionListItem(0, {"KEY_PRESS": "a"})
        qtbot.addWidget(row)

        assert row.height() == ActionListItem.ROW_HEIGHT

    def test_a_row_is_numbered_from_one(self, qtbot):
        row = ActionListItem(2, {"KEY_PRESS": "a"})
        qtbot.addWidget(row)

        assert row.number.text() == "3"

    def test_the_spare_room_goes_below_the_rows(self, action_list):
        """Without the trailing stretch the rows share out the whole box."""
        action_list.set_actions([{"KEY_PRESS": "a"}, LONG_ACTION])

        rows = [action_list.actions_layout.itemAt(i).widget()
                for i in range(action_list.actions_layout.count())]
        assert [type(row) for row in rows[:2]] == [ActionListItem, ActionListItem]
        assert action_list.actions_layout.itemAt(2).spacerItem() is not None

    def test_an_empty_list_says_so(self, action_list):
        action_list.set_actions([])

        assert action_list.actions_layout.count() == 1
        placeholder = action_list.actions_layout.itemAt(0).widget()
        assert placeholder.text() == "No actions yet"

    def test_removing_the_last_action_brings_the_placeholder_back(self, action_list):
        action_list.set_actions([{"KEY_PRESS": "a"}])

        action_list.remove_action(0)

        assert action_list.actions_layout.itemAt(0).widget().text() == "No actions yet"


KEYS = [{"KEY_PRESS": letter} for letter in "abcd"]


@pytest.fixture
def four_actions(qtbot):
    """An action list laid out on screen, so its rows have real geometry."""
    widget = ActionEditorWidget()
    qtbot.addWidget(widget)
    widget.resize(420, 300)
    widget.set_actions(KEYS)
    widget.show()
    qtbot.waitUntil(lambda: widget.actions_container.rows()[1].geometry().top()
                    > widget.actions_container.rows()[0].geometry().top())
    return widget


def drop(widget, source: int, y: float, payload: bytes = None) -> None:
    """Drop the row at `source` on height `y` of the container."""
    mime = QMimeData()
    mime.setData(ACTION_MIME_TYPE if payload is None else "text/plain",
                 str(source).encode() if payload is None else payload)
    widget.actions_container.dropEvent(QDropEvent(
        QPointF(10, y), Qt.DropAction.MoveAction, mime,
        Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier))


def row_bottom(widget, index: int) -> float:
    return widget.actions_container.rows()[index].geometry().bottom()


def letters(widget) -> str:
    return "".join(action["KEY_PRESS"] for action in widget.get_actions())


class TestReorderingByDrag:
    """Rows are carried to a new position rather than nudged with arrows."""

    def test_dragging_a_row_down_puts_it_after_the_row_dropped_on(self, four_actions):
        drop(four_actions, 0, row_bottom(four_actions, 2))

        assert letters(four_actions) == "bcad"

    def test_dragging_a_row_to_the_top_puts_it_first(self, four_actions):
        drop(four_actions, 3, 0)

        assert letters(four_actions) == "dabc"

    def test_dropping_a_row_back_on_itself_changes_nothing(self, four_actions):
        drop(four_actions, 1, row_bottom(four_actions, 1) - 1)

        assert letters(four_actions) == "abcd"

    def test_a_drop_from_somewhere_else_is_refused(self, four_actions):
        drop(four_actions, 0, row_bottom(four_actions, 2), payload=b"0")

        assert letters(four_actions) == "abcd"

    def test_the_rows_are_renumbered_after_a_move(self, four_actions):
        drop(four_actions, 0, row_bottom(four_actions, 2))

        rows = four_actions.actions_container.rows()
        assert [row.number.text() for row in rows] == ["1", "2", "3", "4"]
        assert rows[2].label.full_text() == "Key Press: a"

    def test_the_gap_above_the_first_row_is_gap_zero(self, four_actions):
        assert four_actions.actions_container.gap_at(0) == 0

    def test_a_drop_below_the_last_row_lands_at_the_end(self, four_actions):
        container = four_actions.actions_container

        assert container.gap_at(row_bottom(four_actions, 3) + 40) == 4

    def test_a_target_past_the_end_lands_on_the_end(self, four_actions):
        four_actions.move_action(0, 99)

        assert letters(four_actions) == "bcda"

    def test_an_index_that_is_not_there_is_ignored(self, four_actions):
        four_actions.move_action(9, 0)

        assert letters(four_actions) == "abcd"
