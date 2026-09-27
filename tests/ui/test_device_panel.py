"""
The key grid drawn at the device's proportions, so the preview lines up with
the deck (and with what the screensaver spreads across it).
"""

import pytest

from StreamDock.domain.device_geometry import (
    KEY_GAP_PIXELS,
    KEY_PIXELS,
    KEYCAP_BORDER_PIXELS,
    KEYCAP_MM,
    PIXELS_PER_MM,
)
from StreamDock.ui.main_window import MainWindow
from StreamDock.ui.widgets import DevicePanel, KeySquare


@pytest.fixture
def panel(qtbot):
    panel = DevicePanel()
    qtbot.addWidget(panel)
    squares = [KeySquare(position) for position in range(1, 16)]
    for position, square in enumerate(squares, start=1):
        panel.add_key(square, position)
    panel.show()
    qtbot.waitExposed(panel)
    return panel, squares


class TestDevicePanel:

    def test_keys_are_as_far_apart_as_their_screens(self, panel):
        _, squares = panel
        pitch = squares[1].geometry().left() - squares[0].geometry().left()
        row_pitch = squares[5].geometry().top() - squares[0].geometry().top()

        assert pitch == row_pitch == KEY_PIXELS + round(KEY_GAP_PIXELS)

    def test_keys_run_row_by_row_from_the_top_left(self, panel):
        _, squares = panel

        assert squares[4].geometry().top() == squares[0].geometry().top()
        assert squares[5].geometry().left() == squares[0].geometry().left()
        assert squares[5].geometry().top() > squares[0].geometry().top()

    def test_each_key_has_a_keycap_of_the_measured_size(self, panel):
        widget, squares = panel
        rects = widget.keycap_rects()

        assert len(rects) == 15
        assert rects[0].width() == pytest.approx(KEYCAP_MM * PIXELS_PER_MM)
        centre, key_centre = rects[0].center(), squares[0].geometry().toRectF().center()
        assert (centre.x(), centre.y()) == pytest.approx((key_centre.x(), key_centre.y()))

    def test_the_keycaps_fit_inside_the_panel(self, panel):
        widget, _ = panel
        bounds = widget.rect().toRectF()

        assert all(bounds.contains(rect) for rect in widget.keycap_rects())

    def test_neighbouring_keycaps_do_not_touch(self, panel):
        widget, _ = panel
        rects = widget.keycap_rects()

        assert rects[1].left() - rects[0].right() == pytest.approx(
            round(KEY_GAP_PIXELS) - 2 * KEYCAP_BORDER_PIXELS)


def test_the_main_window_uses_it(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)

    assert isinstance(window.device_panel, DevicePanel)
    assert [s.position for s in window.key_squares] == list(range(1, 16))
