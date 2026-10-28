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
from StreamDock.ui.widgets import KEY_MIME_TYPE, KeySquare


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


def key_mime(payload) -> QMimeData:
    mime = QMimeData()
    mime.setData(KEY_MIME_TYPE, str(payload).encode())
    return mime


def square_at(square, position: int):
    """The square at `position` in the same window, the drag's source widget."""
    for other in square.window().findChildren(KeySquare):
        if other.position == position:
            return other
    return square if square.position == position else None


class _Drop(QDropEvent):
    """A drop whose source() is a given widget, as Qt reports for an in-app drag."""

    def __init__(self, source, mime):
        super().__init__(QPointF(10, 10), Qt.DropAction.MoveAction, mime,
                         Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
        self._source = source
        # The event does not own its mime data; keep it alive for the call.
        self._mime = mime

    def source(self):
        return self._source


class _DragEnter(QDragEnterEvent):
    def __init__(self, source, mime):
        super().__init__(QPoint(10, 10), Qt.DropAction.MoveAction, mime,
                         Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
        self._source = source
        # The event does not own its mime data; keep it alive for the call.
        self._mime = mime

    def source(self):
        return self._source


def drop_on(square, source: int) -> None:
    """Drop the key from `source` onto this square."""
    square.dropEvent(_Drop(square_at(square, source), key_mime(source)))


def drag_over(square, source: int, source_widget=None) -> QDragEnterEvent:
    """Hover a drag from `source` over this square, and report the event."""
    event = _DragEnter(source_widget or square_at(square, source), key_mime(source))
    square.dragEnterEvent(event)
    return event


def positions(window) -> dict:
    return dict(sorted(window.current_layout.keys.items()))


class TestWhatASquareWillTake:
    """A square reads the drag before deciding to light up."""

    def test_a_key_from_another_square_is_taken(self, square):
        assert square.dragged_position(key_mime(7)) == 7

    def test_a_key_dropped_back_on_itself_is_not(self, square):
        assert square.dragged_position(key_mime(square.position)) is None

    def test_something_that_is_not_a_position_is_not(self, square):
        assert square.dragged_position(key_mime("a file from elsewhere")) is None

    def test_plain_text_from_another_application_is_not(self, square):
        """A number dragged from a text editor used to move a key."""
        mime = QMimeData()
        mime.setText("7")

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

    def test_a_drag_from_another_window_is_refused(self, window, qtbot):
        stranger = KeySquare(1)
        qtbot.addWidget(stranger)

        event = drag_over(window.key_squares[1], 1, source_widget=stranger)

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

    def test_a_position_outside_the_grid_is_ignored(self, window):
        """A layout may hold position 20; drawing or moving it must not index past the grid."""
        window.current_layout.keys[20] = "KeyA"
        window.modified = False

        window.on_key_moved(20, 3)
        window.show_key_at(20)

        assert window.current_layout.keys[20] == "KeyA"
        assert not window.modified
