"""
The colours each design paints with.

A palette is built once per session from the desktop's own settings, falling
back to the stock Breeze and Adwaita colours when the session cannot be asked.
Every role the stylesheet and the hand-painted widgets use is named here, so
adding a colour never means hunting through the widget code for a literal.
"""

from dataclasses import asdict, dataclass
from typing import Dict

from StreamDock.ui.theme import color as c
from StreamDock.ui.theme.detection import (
    DEFAULT_FRAME_CONTRAST,
    Flavor,
    Scheme,
    read_gnome_accent,
    read_kde_colors,
    read_kde_frame_contrast,
)


@dataclass(frozen=True)
class Palette:  # pylint: disable=too-many-instance-attributes
    """
    Every colour role, resolved to ``#rrggbb``.

    The names ending in the older ``bg_``/``text_`` conventions are the ones
    the widgets already ask for by key, so they stay whatever the design maps
    them to rather than being renamed.
    """

    # Accent and its states
    primary: str
    primary_hover: str
    primary_dark: str
    on_primary: str

    # Semantic colours
    secondary: str
    secondary_hover: str
    success: str
    success_hover: str
    danger: str
    danger_hover: str
    warning: str
    warning_hover: str
    info: str
    info_hover: str

    # Surfaces
    bg_primary: str      # the window itself
    bg_secondary: str    # cards, group boxes, the header strip
    bg_tertiary: str     # buttons and other raised controls
    bg_input: str        # text fields and list views
    bg_hover: str
    bg_pressed: str
    bg_alternate: str    # alternating rows
    bg_light: str
    bg_card: str
    bg_selection: str
    bg_tooltip: str
    bg_menu: str
    bg_header: str           # the tools area: menu bar, toolbar, header bar
    bg_header_inactive: str  # the same strip when the window is not focused

    # Text
    text_primary: str
    text_secondary: str
    text_light: str
    text_dark: str
    text_tooltip: str
    text_selection: str
    text_disabled: str

    # Lines
    border: str
    border_strong: str
    border_focus: str
    separator: str

    def as_dict(self) -> Dict[str, str]:
        """
        The palette as the plain mapping the widgets index into.

        Returns:
            Role name to ``#rrggbb``
        """
        return asdict(self)


def build_palette(flavor: Flavor, scheme: Scheme,
                  follow_desktop: bool = True) -> Palette:
    """
    Assemble the palette for one design.

    Args:
        flavor: Which design to build
        scheme: Light or dark
        follow_desktop: Read the desktop's own colours where it exposes them.
            Off, the stock Breeze or Adwaita colours are used, which is what
            a forced design wants when it does not match the session.

    Returns:
        The palette
    """
    if flavor is Flavor.KDE:
        return _breeze_palette(scheme, follow_desktop)
    return _adwaita_palette(scheme, follow_desktop)


# ── KDE: Breeze ──────────────────────────────────────────────────────────────

# Stock Breeze, used when kdeglobals cannot be read. These are the values in
# the colour schemes Plasma 6 ships, so a session without a readable
# configuration still looks like the desktop around it.
_BREEZE_DARK = {
    'window_bg': '#202326', 'window_alt_bg': '#292C30', 'window_fg': '#FCFCFC',
    'window_fg_inactive': '#A1A9B1', 'view_bg': '#141618', 'view_alt_bg': '#1D1F22',
    'view_fg': '#FCFCFC', 'button_bg': '#292C30',
    'header_bg': '#292C30', 'header_bg_inactive': '#202326',
    'tooltip_bg': '#292C30', 'tooltip_fg': '#FCFCFC', 'selection_bg': '#3DAEE9',
    'selection_fg': '#FCFCFC', 'focus': '#3DAEE9', 'hover': '#3DAEE9',
    'negative': '#DA4453', 'positive': '#27AE60', 'neutral': '#F67400',
    'link': '#1D99F3', 'visited': '#9B59B6',
}

_BREEZE_LIGHT = {
    'window_bg': '#EFF0F1', 'window_alt_bg': '#E3E5E7', 'window_fg': '#232629',
    'window_fg_inactive': '#707D8A', 'view_bg': '#FFFFFF', 'view_alt_bg': '#F7F7F7',
    'view_fg': '#232629', 'button_bg': '#FCFCFC',
    # The tools area is a shade darker than the window in Breeze Light; it
    # falls back to the window colour when the window loses focus.
    'header_bg': '#DEE0E2', 'header_bg_inactive': '#EFF0F1',
    'tooltip_bg': '#F7F7F7', 'tooltip_fg': '#232629', 'selection_bg': '#3DAEE9',
    'selection_fg': '#FFFFFF', 'focus': '#3DAEE9', 'hover': '#3DAEE9',
    'negative': '#DA4453', 'positive': '#27AE60', 'neutral': '#F67400',
    'link': '#2980B9', 'visited': '#9B59B6',
}

# How far a pressed control is pulled towards the accent. Breeze fills a
# pressed or checked button with a translucent wash of the highlight colour.
PRESSED_ACCENT_MIX = 0.33


def _breeze_palette(scheme: Scheme, follow_desktop: bool) -> Palette:
    """
    Build the KDE palette, preferring the session's own colour scheme.

    Args:
        scheme: Light or dark
        follow_desktop: Read ``kdeglobals``

    Returns:
        The palette
    """
    stock = _BREEZE_DARK if scheme is Scheme.DARK else _BREEZE_LIGHT
    roles = dict(stock)
    frame_contrast = DEFAULT_FRAME_CONTRAST

    if follow_desktop:
        live = read_kde_colors()
        # Only adopt the live scheme when it agrees about light versus dark;
        # a user forcing the light design on a dark desktop wants light.
        if live.get('window_bg') and c.is_dark(live['window_bg']) == (scheme is Scheme.DARK):
            roles.update({key: value for key, value in live.items() if value})
            frame_contrast = read_kde_frame_contrast()

    window = roles['window_bg']
    text = roles['window_fg']
    view = roles['view_bg']
    button = roles.get('button_bg', roles.get('window_alt_bg', c.shade(window, 0.05)))
    accent = roles.get('accent') or roles['selection_bg']
    dark = c.is_dark(window)

    # Breeze draws every outline by pulling the surface towards the text
    # colour rather than naming a border role, so the lines are derived the
    # same way here. The stronger shade is for grooves and switch tracks,
    # which have to read against the outline itself.
    border = c.mix(window, text, frame_contrast)
    border_strong = c.mix(window, text, min(1.0, frame_contrast + 0.15))

    return Palette(
        primary=accent,
        primary_hover=c.lighten(accent, 0.15) if dark else c.darken(accent, 0.08),
        primary_dark=c.darken(accent, 0.22),
        on_primary=c.readable_on(accent),

        secondary=roles.get('visited', '#9B59B6'),
        secondary_hover=c.lighten(roles.get('visited', '#9B59B6'), 0.12),
        success=roles['positive'],
        success_hover=c.lighten(roles['positive'], 0.14),
        danger=roles['negative'],
        danger_hover=c.lighten(roles['negative'], 0.14),
        warning=roles['neutral'],
        warning_hover=c.lighten(roles['neutral'], 0.14),
        info=roles['link'],
        info_hover=c.lighten(roles['link'], 0.14),

        bg_primary=window,
        bg_secondary=roles.get('window_alt_bg', c.shade(window, 0.05)),
        bg_tertiary=button,
        bg_input=view,
        # Item views tint a hovered row with the accent; menus and menu bars
        # fill it outright.
        bg_hover=c.mix(view, accent, 0.18),
        bg_pressed=c.mix(button, accent, PRESSED_ACCENT_MIX),
        bg_alternate=roles.get('view_alt_bg', c.shade(view, 0.04)),
        bg_light=roles.get('window_alt_bg', c.shade(window, 0.05)),
        # A framed area that is neither window nor view: Breeze blends the
        # two for group boxes and the like.
        bg_card=c.mix(window, view, 0.3),
        bg_selection=roles['selection_bg'],
        bg_tooltip=roles.get('tooltip_bg', roles.get('window_alt_bg', window)),
        bg_menu=window,
        bg_header=roles.get('header_bg', window),
        bg_header_inactive=roles.get('header_bg_inactive', window),

        text_primary=text,
        text_secondary=roles['window_fg_inactive'],
        text_light=text,
        text_dark='#232629',
        text_tooltip=roles.get('tooltip_fg', text),
        text_selection=roles.get('selection_fg', c.readable_on(roles['selection_bg'])),
        text_disabled=c.mix(text, window, 0.55),

        border=border,
        border_strong=border_strong,
        border_focus=roles.get('focus', accent),
        separator=border,
    )


# ── GNOME: Adwaita ───────────────────────────────────────────────────────────

# libadwaita's named colours. Adwaita states them as constants rather than
# deriving them, so they are quoted here rather than computed.
_ADWAITA_DARK = {
    'window_bg': '#242424', 'window_fg': '#FFFFFF',
    'view_bg': '#1E1E1E', 'view_fg': '#FFFFFF',
    'headerbar_bg': '#303030', 'sidebar_bg': '#2E2E2E',
    'card_bg': '#2D2D2D', 'dialog_bg': '#383838', 'popover_bg': '#383838',
    'accent_bg': '#3584E4', 'accent_fg': '#FFFFFF',
    'destructive_bg': '#C01C28', 'destructive_fg': '#FFFFFF',
    'success_bg': '#26A269', 'warning_bg': '#CD9309',
}

_ADWAITA_LIGHT = {
    'window_bg': '#FAFAFA', 'window_fg': '#323232',
    'view_bg': '#FFFFFF', 'view_fg': '#1E1E1E',
    'headerbar_bg': '#FFFFFF', 'sidebar_bg': '#EBEBEB',
    'card_bg': '#FFFFFF', 'dialog_bg': '#FAFAFA', 'popover_bg': '#FFFFFF',
    'accent_bg': '#3584E4', 'accent_fg': '#FFFFFF',
    'destructive_bg': '#E01B24', 'destructive_fg': '#FFFFFF',
    'success_bg': '#2EC27E', 'warning_bg': '#E5A50A',
}


def _adwaita_palette(scheme: Scheme, follow_desktop: bool) -> Palette:
    """
    Build the GNOME palette.

    GNOME exposes no per-role colours the way KDE does, so the Adwaita
    constants are used throughout and only the accent is read from the
    session.

    Args:
        scheme: Light or dark
        follow_desktop: Read the accent GNOME 47 and later expose

    Returns:
        The palette
    """
    roles = dict(_ADWAITA_DARK if scheme is Scheme.DARK else _ADWAITA_LIGHT)
    dark = scheme is Scheme.DARK

    accent_bg = roles['accent_bg']
    if follow_desktop:
        chosen = read_gnome_accent()
        if chosen:
            accent_bg = chosen
    # Adwaita lightens the accent for text and focus rings on dark backgrounds
    # so it keeps its contrast against the darker window.
    accent_text = c.lighten(accent_bg, 0.32) if dark else c.darken(accent_bg, 0.10)

    window = roles['window_bg']
    danger = roles['destructive_bg']
    success = roles['success_bg']
    warning = roles['warning_bg']

    return Palette(
        primary=accent_bg,
        primary_hover=c.lighten(accent_bg, 0.10) if dark else c.darken(accent_bg, 0.06),
        primary_dark=c.darken(accent_bg, 0.16),
        on_primary=c.readable_on(accent_bg),

        secondary=accent_text,
        secondary_hover=c.lighten(accent_text, 0.10),
        success=success,
        success_hover=c.lighten(success, 0.12) if dark else c.darken(success, 0.08),
        danger=danger,
        danger_hover=c.lighten(danger, 0.12) if dark else c.darken(danger, 0.08),
        warning=warning,
        warning_hover=c.lighten(warning, 0.12) if dark else c.darken(warning, 0.08),
        info=accent_text,
        info_hover=c.lighten(accent_text, 0.12),

        bg_primary=window,
        bg_secondary=roles['card_bg'],
        bg_tertiary=c.shade(window, 0.10 if dark else 0.07),
        bg_input=roles['view_bg'],
        bg_hover=c.shade(window, 0.16 if dark else 0.10),
        bg_pressed=c.shade(window, 0.22 if dark else 0.16),
        bg_alternate=c.shade(roles['view_bg'], 0.04),
        bg_light=roles['sidebar_bg'],
        bg_card=roles['card_bg'],
        bg_selection=accent_bg,
        bg_tooltip='#383838' if dark else '#303030',
        bg_menu=roles['popover_bg'],
        bg_header=roles['headerbar_bg'],
        bg_header_inactive=window,

        text_primary=roles['window_fg'],
        text_secondary=c.mix(roles['window_fg'], window, 0.40),
        text_light=roles['window_fg'],
        text_dark='#1E1E1E',
        text_tooltip='#FFFFFF',
        text_selection=c.readable_on(accent_bg),
        text_disabled=c.mix(roles['window_fg'], window, 0.60),

        border=c.shade(window, 0.14 if dark else 0.12),
        border_strong=c.shade(window, 0.26 if dark else 0.22),
        border_focus=accent_bg,
        separator=c.shade(window, 0.12 if dark else 0.10),
    )
