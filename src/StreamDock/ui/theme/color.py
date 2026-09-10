"""
Colour arithmetic for the theme palettes.

Deliberately free of Qt: palettes are built before a QApplication exists and
are exercised by tests that never open a display.
"""

from typing import Tuple

RGB = Tuple[int, int, int]


def parse(value: str) -> RGB:
    """
    Read a colour in any of the notations the desktops hand us.

    Accepts ``#rrggbb``, ``#rgb`` and the ``r,g,b`` triplets KDE writes into
    ``kdeglobals``.

    Args:
        value: The colour text

    Returns:
        Red, green and blue, each 0-255

    Raises:
        ValueError: The text is not a colour
    """
    text = value.strip()

    if text.startswith('#'):
        digits = text[1:]
        if len(digits) == 3:
            digits = ''.join(c * 2 for c in digits)
        if len(digits) != 6:
            raise ValueError(f"not a hex colour: {value!r}")
        return (int(digits[0:2], 16), int(digits[2:4], 16), int(digits[4:6], 16))

    parts = [part.strip() for part in text.split(',')]
    if len(parts) not in (3, 4):
        raise ValueError(f"not a colour: {value!r}")
    # A fourth component is the alpha KDE sometimes appends; the stylesheet
    # has no use for it.
    return tuple(_clamp(int(part)) for part in parts[:3])  # type: ignore[return-value]


def to_hex(rgb: RGB) -> str:
    """
    Render a colour the way a stylesheet wants it.

    Args:
        rgb: Red, green and blue

    Returns:
        ``#rrggbb``
    """
    red, green, blue = (_clamp(channel) for channel in rgb)
    return f'#{red:02X}{green:02X}{blue:02X}'


def mix(start: str, end: str, ratio: float) -> str:
    """
    Blend two colours.

    Args:
        start: Colour at ratio 0
        end: Colour at ratio 1
        ratio: Position between the two, 0-1

    Returns:
        The blend, as ``#rrggbb``
    """
    ratio = min(1.0, max(0.0, ratio))
    first, second = parse(start), parse(end)
    return to_hex(tuple(round(a + (b - a) * ratio)      # type: ignore[arg-type]
                        for a, b in zip(first, second)))


def lighten(color: str, amount: float) -> str:
    """
    Move a colour towards white.

    Args:
        color: The colour
        amount: How far, 0-1

    Returns:
        The lightened colour
    """
    return mix(color, '#FFFFFF', amount)


def darken(color: str, amount: float) -> str:
    """
    Move a colour towards black.

    Args:
        color: The colour
        amount: How far, 0-1

    Returns:
        The darkened colour
    """
    return mix(color, '#000000', amount)


def shade(color: str, amount: float) -> str:
    """
    Separate a colour from its background, whichever way that is.

    Borders and hover fills have to lighten on a dark theme and darken on a
    light one; every caller wanting a border would otherwise repeat the test.

    Args:
        color: The colour to shift
        amount: How far, 0-1

    Returns:
        The shifted colour
    """
    return lighten(color, amount) if is_dark(color) else darken(color, amount)


def luminance(color: str) -> float:
    """
    Perceived brightness, by the WCAG relative-luminance formula.

    Args:
        color: The colour

    Returns:
        0 for black, 1 for white
    """
    weights = (0.2126, 0.7152, 0.0722)
    total = 0.0
    for weight, value in zip(weights, parse(color)):
        fraction = value / 255
        linear = (fraction / 12.92 if fraction <= 0.04045
                  else ((fraction + 0.055) / 1.055) ** 2.4)
        total += weight * linear
    return total


def is_dark(color: str) -> bool:
    """
    Whether text on this colour should be light.

    Args:
        color: The colour

    Returns:
        True when the colour is dark
    """
    return luminance(color) < 0.5


def readable_on(background: str, light: str = '#FFFFFF',
                dark: str = '#1B1B1B') -> str:
    """
    Pick the foreground that stays legible on a background.

    Accent colours come from the desktop and a user can pick a pale yellow;
    white label text on one is unreadable.

    Args:
        background: The colour behind the text
        light: Foreground to use on dark backgrounds
        dark: Foreground to use on light backgrounds

    Returns:
        Either ``light`` or ``dark``
    """
    return light if is_dark(background) else dark


def rgba(color: str, alpha: float) -> str:
    """
    A stylesheet ``rgba()`` string.

    Args:
        color: The colour
        alpha: Opacity, 0-1

    Returns:
        ``rgba(r, g, b, a)``
    """
    red, green, blue = parse(color)
    return f"rgba({red}, {green}, {blue}, {min(1.0, max(0.0, alpha)):.3f})"


def _clamp(value: int) -> int:
    """
    Hold a channel inside 0-255.

    Args:
        value: A channel value

    Returns:
        The value, clamped
    """
    return max(0, min(255, int(value)))
