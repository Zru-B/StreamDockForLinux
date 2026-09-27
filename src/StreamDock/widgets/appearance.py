"""
A widget key shown through the user's own images.

A widget reports a state ("connected", "muted") and optionally a badge text
("3"). A key can map states to images of its own (``state_icons``), give one
image for every state (``icon``), and have the badge drawn in a corner on top.
The widget's own drawing is the fallback for a state with no image.

Composed here, in the app, so a third-party widget only ever sends a state
name and a short text, never touches the user's files, and costs nothing to
draw when the user's images replace its drawing entirely.
"""

import logging
import os
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Any, Dict, Mapping, Optional, Tuple

from PIL import Image, ImageColor, ImageDraw

from streamdock_sdk import draw
from StreamDock.image_helpers.pil_helper import render_key_image

logger = logging.getLogger(__name__)

BADGE_POSITIONS = ('top_right', 'top_left', 'bottom_right', 'bottom_left')
DEFAULT_BADGE_COLOR = '#e53935'
DEFAULT_BADGE_TEXT_COLOR = '#ffffff'
SUPERSAMPLE = 4


@dataclass(frozen=True)
class BadgeStyle:
    position: str = 'top_right'
    color: str = DEFAULT_BADGE_COLOR
    text_color: str = DEFAULT_BADGE_TEXT_COLOR

    @classmethod
    def from_config(cls, value: Any) -> Optional['BadgeStyle']:
        """``badge:`` from config.yml: a mapping, true/absent for the default, false to hide."""
        if value is False:
            return None
        if not isinstance(value, Mapping):
            return cls()
        return cls(position=value.get('position', 'top_right'),
                   color=value.get('color', DEFAULT_BADGE_COLOR),
                   text_color=value.get('text_color', DEFAULT_BADGE_TEXT_COLOR))


@dataclass(frozen=True)
class Appearance:
    """How a widget key uses the user's images; paths are absolute."""

    icon: Optional[str] = None
    state_icons: Tuple[Tuple[str, str], ...] = ()
    badge: Optional[BadgeStyle] = field(default_factory=BadgeStyle)

    @classmethod
    def from_key_config(cls, key_data: Mapping[str, Any], config_dir: str = '/') -> 'Appearance':
        # Imported here: the application package imports the widget host, which imports this.
        from StreamDock.application.configuration_manager import (  # pylint: disable=import-outside-toplevel
            resolve_icon_path)

        icon = key_data.get('icon')
        state_icons = key_data.get('state_icons') or {}
        return cls(
            icon=resolve_icon_path(icon, config_dir) if isinstance(icon, str) and icon else None,
            state_icons=tuple(sorted((state, resolve_icon_path(path, config_dir))
                                     for state, path in state_icons.items() if isinstance(path, str))),
            badge=BadgeStyle.from_config(key_data.get('badge', True)),
        )

    @property
    def uses_images(self) -> bool:
        return bool(self.icon or self.state_icons)

    @property
    def replaces_drawing(self) -> bool:
        """True when every state has an image, so the widget need not draw at all."""
        return bool(self.icon)

    def image_for(self, state: Optional[str]) -> Optional[str]:
        return dict(self.state_icons).get(state) or self.icon


@lru_cache(maxsize=64)
def _load(path: str, mtime: float, size: Tuple[int, int]) -> Image.Image:  # pylint: disable=unused-argument
    return render_key_image(size=size, icon_path=path)


def load_key_image(path: str, size: Tuple[int, int]) -> Optional[Image.Image]:
    """The icon scaled to the key, cached until the file changes."""
    try:
        return _load(path, os.path.getmtime(path), tuple(size))
    except OSError:
        logger.warning('Widget key image not found: %s', path)
        return None


def draw_badge(image: Image.Image, text: str, style: BadgeStyle) -> Image.Image:
    """A pill with ``text`` in one corner of ``image``; returns a new image."""
    width, height = image.size
    scale = SUPERSAMPLE
    pill_height = int(height * 0.34)
    margin = max(2, height // 40)
    layer = Image.new('RGBA', (width * scale, height * scale), (0, 0, 0, 0))
    canvas = ImageDraw.Draw(layer)
    text_font = draw.font(int(pill_height * 0.72) * scale)
    left, top, right, bottom = canvas.textbbox((0, 0), text, font=text_font, anchor='mm')
    pill_width = max(pill_height * scale, (right - left) + pill_height * scale // 2)
    pill_width = min(pill_width, (width - 2 * margin) * scale)
    pill_h = pill_height * scale

    x = margin * scale if style.position.endswith('left') else (width - margin) * scale - pill_width
    y = margin * scale if style.position.startswith('top') else (height - margin) * scale - pill_h
    outline = max(1, scale * 2)
    canvas.rounded_rectangle((x, y, x + pill_width, y + pill_h), radius=pill_h // 2,
                             fill=ImageColor.getrgb(style.color), outline=(0, 0, 0), width=outline)
    canvas.text((x + pill_width / 2, y + pill_h / 2), text, font=text_font, anchor='mm',
                fill=ImageColor.getrgb(style.text_color))

    badge = layer.resize(image.size, Image.LANCZOS)
    result = image.convert('RGBA')
    result.alpha_composite(badge)
    return result.convert('RGB')


def compose(appearance: Appearance, state: Optional[str], badge_text: Optional[str],
            drawn: Optional[Image.Image], size: Tuple[int, int]) -> Optional[Image.Image]:
    """
    The key image for a widget's current state and badge.

    Returns None when the key should show the widget's own drawing and there
    is none yet.
    """
    path = appearance.image_for(state)
    base = load_key_image(path, size) if path else None
    if base is None and appearance.icon and path != appearance.icon:
        # A state image that won't load falls back to the base image.
        base = load_key_image(appearance.icon, size)
    if base is None:
        return drawn
    if badge_text and appearance.badge is not None:
        return draw_badge(base, badge_text, appearance.badge)
    return base


def appearance_config_problems(key_name: str, key_data: Dict[str, Any], states: Optional[Tuple[str, ...]],
                               supports_badge: Optional[bool]) -> Tuple[str, ...]:
    """
    Shape errors in a widget key's image settings.

    ``states``/``supports_badge`` are None when the widget isn't known, in
    which case only the shape is checked.
    """
    problems = []
    state_icons = key_data.get('state_icons')
    if state_icons is not None:
        if not isinstance(state_icons, dict) or not all(isinstance(k, str) and isinstance(v, str)
                                                        for k, v in state_icons.items()):
            problems.append(f"Key '{key_name}' state_icons must map state names to image files")
        elif states is not None:
            unknown = sorted(set(state_icons) - set(states))
            if unknown:
                known = ', '.join(states) if states else 'none'
                problems.append(f"Key '{key_name}' state_icons names unknown state(s) "
                                f"{', '.join(unknown)}; this widget's states are: {known}")
    badge = key_data.get('badge')
    if badge is not None and not isinstance(badge, bool):
        if not isinstance(badge, dict):
            problems.append(f"Key '{key_name}' badge must be true, false or a mapping")
        else:
            position = badge.get('position', 'top_right')
            if position not in BADGE_POSITIONS:
                problems.append(f"Key '{key_name}' badge position must be one of {', '.join(BADGE_POSITIONS)}")
            for colour_field in ('color', 'text_color'):
                if colour_field in badge:
                    try:
                        ImageColor.getrgb(badge[colour_field])
                    except (ValueError, AttributeError, TypeError):
                        problems.append(f"Key '{key_name}' badge {colour_field} is not a colour")
            unknown = sorted(set(badge) - {'position', 'color', 'text_color'})
            if unknown:
                problems.append(f"Key '{key_name}' badge has unknown field(s): {', '.join(unknown)}")
    return tuple(problems)
