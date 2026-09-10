"""
Which desktop we are running under, and what it currently looks like.

Nothing here imports Qt, so the tests can run every branch without a display
and the answers can be computed before a QApplication exists.
"""

import configparser
import logging
import os
import shutil
import subprocess
from enum import Enum
from pathlib import Path
from typing import Dict, Optional

logger = logging.getLogger(__name__)


class Flavor(str, Enum):
    """The two interface designs the application ships."""

    KDE = "kde"
    GNOME = "gnome"


class Scheme(str, Enum):
    """Light or dark."""

    LIGHT = "light"
    DARK = "dark"


# Desktops built on Qt get the Breeze design; the rest get Adwaita. A session
# we do not recognise falls back to Breeze: this is a Qt application, and its
# own window decorations will be Qt's either way.
_QT_DESKTOPS = frozenset({
    'kde', 'plasma', 'plasma5', 'plasma6', 'lxqt', 'razor', 'trinity',
    'deepin', 'dde', 'ukui', 'lomiri', 'maui',
})

_GTK_DESKTOPS = frozenset({
    'gnome', 'gnome-classic', 'gnome-flashback', 'gnome-shell', 'ubuntu',
    'unity', 'cinnamon', 'x-cinnamon', 'mate', 'xfce', 'xubuntu', 'budgie',
    'budgie-desktop', 'pantheon', 'lxde', 'endless', 'phosh', 'cosmic',
})

DEFAULT_FLAVOR = Flavor.KDE

# GNOME 47 lets a user pick an accent by name rather than by colour. These are
# the values libadwaita paints for each.
GNOME_ACCENTS = {
    'blue': '#3584E4',
    'teal': '#2190A4',
    'green': '#3A944A',
    'yellow': '#C88800',
    'orange': '#ED5B00',
    'red': '#E62D42',
    'pink': '#D56199',
    'purple': '#9141AC',
    'slate': '#6F8396',
}

_GSETTINGS_TIMEOUT = 1.5


def detect_flavor() -> Flavor:
    """
    Work out which desktop design to wear.

    Returns:
        The flavour matching the running session
    """
    for name in _session_names():
        if name in _QT_DESKTOPS:
            logger.debug("Desktop %r resolves to the KDE design", name)
            return Flavor.KDE
        if name in _GTK_DESKTOPS:
            logger.debug("Desktop %r resolves to the GNOME design", name)
            return Flavor.GNOME

    if os.environ.get('KDE_FULL_SESSION'):
        return Flavor.KDE
    if os.environ.get('GNOME_DESKTOP_SESSION_ID'):
        return Flavor.GNOME

    logger.debug("No desktop recognised; using the %s design", DEFAULT_FLAVOR.value)
    return DEFAULT_FLAVOR


def _session_names() -> list:
    """
    Every name the session calls itself, lowercased and in priority order.

    Returns:
        Desktop identifiers, most authoritative first
    """
    names = []
    for variable in ('XDG_CURRENT_DESKTOP', 'XDG_SESSION_DESKTOP', 'DESKTOP_SESSION'):
        value = os.environ.get(variable, '')
        # XDG_CURRENT_DESKTOP is a colon-separated list ("ubuntu:GNOME"), and
        # DESKTOP_SESSION is sometimes a full path to a .desktop file.
        for entry in value.split(':'):
            entry = entry.strip()
            if not entry:
                continue
            if '/' in entry or entry.endswith('.desktop'):
                entry = Path(entry).stem
            names.append(entry.lower())
    return names


# ── the desktop's own colours ────────────────────────────────────────────────


def read_kde_colors() -> Dict[str, str]:
    """
    Read the colour scheme the user actually chose in System Settings.

    Following ``kdeglobals`` is what makes the window match the rest of the
    session: a custom accent or a third-party Breeze variant comes through
    without the application knowing anything about it.

    Returns:
        Role names mapped to ``#rrggbb``, empty when the file is missing or
        unreadable. Roles are only present when the file defines them.
    """
    path = _kdeglobals_path()
    if path is None:
        return {}

    parser = configparser.RawConfigParser(strict=False)
    # kdeglobals keys are case sensitive; the default lowercases them.
    parser.optionxform = str
    try:
        with open(path, 'r', encoding='utf-8', errors='replace') as handle:
            parser.read_file(handle)
    except (OSError, configparser.Error) as e:
        logger.debug("Could not read %s: %s", path, e)
        return {}

    colors: Dict[str, str] = {}
    for role, section, key in (
            ('window_bg', 'Colors:Window', 'BackgroundNormal'),
            ('window_alt_bg', 'Colors:Window', 'BackgroundAlternate'),
            ('window_fg', 'Colors:Window', 'ForegroundNormal'),
            ('window_fg_inactive', 'Colors:Window', 'ForegroundInactive'),
            ('view_bg', 'Colors:View', 'BackgroundNormal'),
            ('view_alt_bg', 'Colors:View', 'BackgroundAlternate'),
            ('view_fg', 'Colors:View', 'ForegroundNormal'),
            ('button_bg', 'Colors:Button', 'BackgroundNormal'),
            ('button_fg', 'Colors:Button', 'ForegroundNormal'),
            ('header_bg', 'Colors:Header', 'BackgroundNormal'),
            ('tooltip_bg', 'Colors:Tooltip', 'BackgroundNormal'),
            ('tooltip_fg', 'Colors:Tooltip', 'ForegroundNormal'),
            ('selection_bg', 'Colors:Selection', 'BackgroundNormal'),
            ('selection_fg', 'Colors:Selection', 'ForegroundNormal'),
            ('focus', 'Colors:Window', 'DecorationFocus'),
            ('hover', 'Colors:Window', 'DecorationHover'),
            ('negative', 'Colors:View', 'ForegroundNegative'),
            ('positive', 'Colors:View', 'ForegroundPositive'),
            ('neutral', 'Colors:View', 'ForegroundNeutral'),
            ('link', 'Colors:View', 'ForegroundLink'),
            ('accent', 'General', 'AccentColor'),
    ):
        value = _color_from(parser, section, key)
        if value:
            colors[role] = value

    return colors


def _kdeglobals_path() -> Optional[Path]:
    """
    Locate the user's ``kdeglobals``.

    Returns:
        The path, or None when there is none to read
    """
    base = os.environ.get('XDG_CONFIG_HOME') or os.path.join(Path.home(), '.config')
    path = Path(base) / 'kdeglobals'
    return path if path.is_file() else None


def _color_from(parser: configparser.RawConfigParser, section: str,
                key: str) -> Optional[str]:
    """
    Pull one colour out of a parsed INI file.

    Args:
        parser: The parsed file
        section: Section name
        key: Key within the section

    Returns:
        ``#rrggbb``, or None when absent or malformed
    """
    # Deferred: the theme package imports this module while building itself.
    from StreamDock.ui.theme import color as color_util  # pylint: disable=import-outside-toplevel

    try:
        raw = parser.get(section, key)
    except (configparser.NoSectionError, configparser.NoOptionError):
        return None

    if not raw or not raw.strip():
        return None

    try:
        return color_util.to_hex(color_util.parse(raw))
    except ValueError:
        logger.debug("Ignoring unreadable colour %s/%s=%r", section, key, raw)
        return None


def read_gnome_setting(key: str, schema: str = 'org.gnome.desktop.interface') -> str:
    """
    Ask GSettings for one interface preference.

    Args:
        key: Setting name, e.g. ``color-scheme``
        schema: Schema holding it

    Returns:
        The value with GVariant quoting stripped, or '' when GSettings is
        unavailable or does not know the key
    """
    if not shutil.which('gsettings'):
        return ''

    try:
        finished = subprocess.run(
            ['gsettings', 'get', schema, key],
            capture_output=True, text=True, timeout=_GSETTINGS_TIMEOUT, check=False)
    except (OSError, subprocess.SubprocessError) as e:
        logger.debug("gsettings %s %s failed: %s", schema, key, e)
        return ''

    if finished.returncode != 0:
        return ''
    return finished.stdout.strip().strip("'\"")


def read_gnome_accent() -> Optional[str]:
    """
    The accent colour GNOME 47 and later let the user choose.

    Returns:
        ``#rrggbb``, or None on older GNOME where the accent is always blue
    """
    name = read_gnome_setting('accent-color')
    return GNOME_ACCENTS.get(name)


def detect_scheme(flavor: Flavor) -> Scheme:
    """
    Work out whether the session is in light or dark mode.

    Args:
        flavor: The design in use, which decides where to look first

    Returns:
        The scheme to paint
    """
    from_qt = _scheme_from_qt()
    if from_qt is not None:
        return from_qt

    if flavor is Flavor.KDE:
        colors = read_kde_colors()
        background = colors.get('window_bg')
        if background:
            from StreamDock.ui.theme import color as color_util  # pylint: disable=import-outside-toplevel
            return Scheme.DARK if color_util.is_dark(background) else Scheme.LIGHT

    if 'dark' in read_gnome_setting('color-scheme'):
        return Scheme.DARK

    # Everything the application shipped with until now was dark, so an
    # undetectable session keeps the look its user already knows.
    return Scheme.DARK


def _scheme_from_qt() -> Optional[Scheme]:
    """
    Ask Qt, which reads the cross-desktop portal setting when one is running.

    Returns:
        The scheme, or None when Qt has no opinion or is not started yet
    """
    # Imported here so the rest of this module stays usable, and testable,
    # with no Qt at all.
    try:
        # pylint: disable=import-outside-toplevel
        from PyQt6.QtCore import Qt
        from PyQt6.QtGui import QGuiApplication
    except ImportError:  # pragma: no cover - Qt is a hard dependency of the GUI
        return None

    application = QGuiApplication.instance()
    if application is None:
        return None

    hints = application.styleHints()
    reported = getattr(hints, 'colorScheme', None)
    if reported is None:  # pragma: no cover - Qt below 6.5
        return None

    value = reported()
    if value == Qt.ColorScheme.Dark:
        return Scheme.DARK
    if value == Qt.ColorScheme.Light:
        return Scheme.LIGHT
    return None
