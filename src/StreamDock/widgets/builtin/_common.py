"""Helpers shared by the built-in widgets."""

import logging
from datetime import datetime, tzinfo
from typing import Optional, Tuple
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from PIL import Image, ImageDraw

from streamdock_sdk import draw

logger = logging.getLogger(__name__)

# Draw at this multiple of the key size and scale down, for smooth edges.
SUPERSAMPLE = 4


def now(zone: Optional[tzinfo] = None) -> datetime:
    """The current time; tests replace this to freeze the clock."""
    return datetime.now(zone)


def parse_zone(name: str) -> Optional[tzinfo]:
    """The zone called ``name``, or None (local time) when it's empty or unknown."""
    if not name.strip():
        return None
    try:
        return ZoneInfo(name.strip())
    except (ZoneInfoNotFoundError, ValueError):
        logger.warning('Unknown time zone %r; showing local time', name)
        return None


def supersampled(size: Tuple[int, int], background: str) -> Tuple[Image.Image, ImageDraw.ImageDraw, int]:
    image = Image.new('RGB', (size[0] * SUPERSAMPLE, size[1] * SUPERSAMPLE), background)
    return image, ImageDraw.Draw(image), SUPERSAMPLE


def downsample(image: Image.Image, size: Tuple[int, int]) -> Image.Image:
    return image.resize(tuple(size), Image.LANCZOS)


def status_tile(size: Tuple[int, int], background: str, caption: str, caption_color: str = 'white'):
    """
    A supersampled canvas for an icon-plus-caption status key.

    Returns (image, draw, scale, icon_box), where icon_box is the area above
    the caption in supersampled pixels. Pass the image to ``finish_status_tile``.
    """
    image, canvas, scale = supersampled(size, background)
    width, height = image.size
    caption_top = int(height * 0.70)
    draw.centered_text(canvas, (6 * scale, caption_top, width - 6 * scale, height - 6 * scale),
                       caption, color=caption_color)
    icon_box = (int(width * 0.22), int(height * 0.10), int(width * 0.78), caption_top - 4 * scale)
    return image, canvas, scale, icon_box


def slash(canvas: ImageDraw.ImageDraw, box, color: str, width: int) -> None:
    """The diagonal 'off' stroke across an icon."""
    left, top, right, bottom = box
    canvas.line((left, bottom, right, top), fill=color, width=width)
