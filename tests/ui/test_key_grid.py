"""
Rearranging the key grid by dragging.

A deck is usually full, so the interesting case is dropping a key onto a
square that already has one: the two trade places rather than the drop being
refused.
"""

import os
import tempfile

import pytest
import yaml
from PyQt6.QtCore import QMimeData, QPoint, QPointF, Qt
from PyQt6.QtGui import QDragEnterEvent, QDropEvent

from StreamDock.ui.main_window import MainWindow
from StreamDock.ui.widgets import KeySquare


CONFIG = {"streamdock": {
    "keys": {name: {"text": name, "on_press_actions": [{"KEY_PRESS": "a"}]}
             for name in ("KeyA", "KeyB", "KeyC")},
    "layouts": {"Main": {"Default": True,
                         "keys": [{1: "KeyA"}, {2: "KeyB"}, {5: "KeyC"}]}},
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


@pytest.fixture
def square(qtbot):
    s = KeySquare(4)
    qtbot.addWidget(s)
    return s


def drop_on(square, source: int) -> None:
    """Drop the key from `source` onto this square."""
    mime = QMimeData()
    mime.setText(str(source))
    square.dropEvent(QDropEvent(
        QPointF(10, 10), Qt.DropAction.MoveAction, mime,
        Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier))


def drag_over(square, source: int) -> QDragEnterEvent:
    """Hover a drag from `source` over this square, and report the event."""
    mime = QMimeData()
    mime.setText(str(source))
    event = QDragEnterEvent(
        QPoint(10, 10), Qt.DropAction.MoveAction, mime,
        Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
    square.dragEnterEvent(event)
    return event


def positions(window) -> dict:
    return dict(sorted(window.current_layout.keys.items()))


class TestWhatASquareWillTake:
    """A square reads the drag before deciding to light up."""

    def test_a_key_from_another_square_is_taken(self, square):
        mime = QMimeData()
        mime.setText("7")

        assert square.dragged_position(mime) == 7

    def test_a_key_dropped_back_on_itself_is_not(self, square):
        mime = QMimeData()
        mime.setText(str(square.position))

        assert square.dragged_position(mime) is None

    def test_something_that_is_not_a_position_is_not(self, square):
        mime = QMimeData()
        mime.setText("a file from elsewhere")

        assert square.dragged_position(mime) is None

    def test_a_drag_with_no_text_is_not(self, square):
        assert square.dragged_position(QMimeData()) is None


class TestHoverFeedback:
    """The square says what the drop would do before it happens."""

    def test_an_occupied_square_still_accepts_the_drag(self, window):
        occupied = window.key_squares[1]

        event = drag_over(occupied, 1)

        assert event.isAccepted()
        assert occupied._overlay.isVisibleTo(occupied)

    def test_leaving_takes_the_highlight_away(self, window):
        occupied = window.key_squares[1]
        drag_over(occupied, 1)

        occupied.dragLeaveEvent(None)

        assert not occupied._overlay.isVisibleTo(occupied)

    def test_a_square_refuses_a_drag_from_itself(self, square):
        event = drag_over(square, square.position)

        assert not event.isAccepted()


class TestDroppingOnTheGrid:
    """Where the keys end up."""

    def test_dropping_on_an_occupied_square_swaps_the_two(self, window):
        drop_on(window.key_squares[1], 1)

        assert positions(window) == {1: "KeyB", 2: "KeyA", 5: "KeyC"}

    def test_both_squares_are_redrawn_after_a_swap(self, window):
        drop_on(window.key_squares[1], 1)

        assert window.key_squares[0].key_name == "KeyB"
        assert window.key_squares[1].key_name == "KeyA"

    def test_dropping_on_an_empty_square_moves_the_key(self, window):
        drop_on(window.key_squares[8], 1)

        assert positions(window) == {2: "KeyB", 5: "KeyC", 9: "KeyA"}
        assert window.key_squares[0].is_empty()
        assert window.key_squares[8].key_name == "KeyA"

    def test_a_swap_is_an_edit(self, window):
        window.modified = False

        drop_on(window.key_squares[1], 1)

        assert window.modified

    def test_dropping_a_key_back_where_it_was_changes_nothing(self, window):
        window.modified = False

        window.on_key_moved(1, 1)

        assert positions(window) == {1: "KeyA", 2: "KeyB", 5: "KeyC"}
        assert not window.modified

    def test_dragging_from_an_empty_square_does_nothing(self, window):
        window.modified = False

        drop_on(window.key_squares[1], 4)

        assert positions(window) == {1: "KeyA", 2: "KeyB", 5: "KeyC"}
        assert not window.modified

    def test_a_key_the_config_no_longer_defines_is_left_alone(self, window):
        window.current_layout.keys[3] = "Ghost"
        window.modified = False

        drop_on(window.key_squares[8], 3)

        assert window.current_layout.keys[3] == "Ghost"
        assert not window.modified
