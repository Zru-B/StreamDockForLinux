"""
The front panel of the deck, in millimetres and in key pixels.

One source for everything that has to line up with the hardware: the
screensaver spreading a picture across the keys, and the editor's preview
of the device. Only the ratios matter - KEY_PIXELS is what the device
accepts per key, whatever the panel's native resolution.
"""

from typing import Tuple

KEY_COLUMNS = 5
KEY_ROWS = 3
KEY_PIXELS = 112

# Visible display area of a key.
KEY_SCREEN_MM = 13.5
# The transparent keycap around it.
KEYCAP_MM = 15.0
# Between the visible display areas of neighbouring keys (published as
# 5.0-5.5 mm; with the screen this gives the 18.5-19 mm key pitch, and
# leaves the 3.5-4 mm between keycaps).
KEY_SCREEN_GAP_MM = 5.25

PIXELS_PER_MM = KEY_PIXELS / KEY_SCREEN_MM
KEY_GAP_PIXELS = KEY_SCREEN_GAP_MM * PIXELS_PER_MM
# Keycap beyond the screen, on each side.
KEYCAP_BORDER_PIXELS = (KEYCAP_MM - KEY_SCREEN_MM) / 2 * PIXELS_PER_MM


def panel_size() -> Tuple[int, int]:
    """Pixel size of all the key screens together, gaps included."""
    return (round(KEY_COLUMNS * KEY_PIXELS + (KEY_COLUMNS - 1) * KEY_GAP_PIXELS),
            round(KEY_ROWS * KEY_PIXELS + (KEY_ROWS - 1) * KEY_GAP_PIXELS))
