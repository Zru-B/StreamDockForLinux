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
from typing import Dict, List, Optional

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

# What Plasma paints frames with when the user has not said otherwise: the
# outline is the window colour pulled this far towards the text colour.
DEFAULT_FRAME_CONTRAST = 0.2

# Plasma's interface font, used when kdeglobals does not name one. Qt's own
# fallback is a 9pt "Sans Serif", which is what makes an unthemed Qt window
# look subtly wrong beside every KDE application around it.
KDE_DEFAULT_FONT_FAMILY = "Noto Sans"
KDE_DEFAULT_FONT_SIZE = 10

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


def is_plasma_session() -> bool:
    """
    Whether the session is actually Plasma, rather than merely not GNOME.

    :func:`detect_flavor` answers "which design", and an unrecognised
    session gets Breeze; this answers whether KDE's own services - its
    portal, its dialogs - can be expected to be running.

    Returns:
        True on a Plasma session
    """
    if os.environ.get('KDE_FULL_SESSION'):
        return True
    return any(name in ('kde', 'plasma', 'plasma5', 'plasma6') for name in _session_names())


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


# ── the desktop's own settings ───────────────────────────────────────────────


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
    parser = _parse_kde_config(_kdeglobals_path())
    if parser is None:
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
            # kdeglobals writes "[Colors:Header][Inactive]"; configparser
            # keeps everything between the outer brackets as the name.
            ('header_bg_inactive', 'Colors:Header][Inactive', 'BackgroundNormal'),
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


def read_kde_setting(section: str, key: str) -> str:
    """
    One plain value from the user's KDE configuration.

    ``kdeglobals`` holds what the user changed; ``kdedefaults/kdeglobals``
    holds what the global theme set, which is where the icon theme and the
    widget style usually live on a stock Plasma session.

    Args:
        section: INI section, e.g. ``General``
        key: Key within it

    Returns:
        The raw value, or '' when neither file defines it
    """
    for path in (_kdeglobals_path(), _kdedefaults_path()):
        parser = _parse_kde_config(path)
        if parser is None:
            continue
        try:
            value = parser.get(section, key)
        except (configparser.NoSectionError, configparser.NoOptionError):
            continue
        if value and value.strip():
            return value.strip()
    return ''


def read_kde_font(key: str = 'font') -> str:
    """
    A font the user set in System Settings, in Qt's own serialised form.

    Args:
        key: ``font``, ``menuFont``, ``toolBarFont`` or ``smallestReadableFont``

    Returns:
        A string ``QFont.fromString`` accepts, or '' when unset
    """
    return read_kde_setting('General', key)


def read_kde_icon_theme() -> str:
    """
    The icon theme the session uses.

    Returns:
        Its name, or '' when the configuration does not say
    """
    return read_kde_setting('Icons', 'Theme')


def read_kde_frame_contrast() -> float:
    """
    How far Plasma pulls a frame's outline from its background.

    Returns:
        A ratio between 0 and 1, Breeze's own default when unset or unreadable
    """
    raw = read_kde_setting('KDE', 'frameContrast')
    try:
        value = float(raw)
    except ValueError:
        return DEFAULT_FRAME_CONTRAST
    if not 0.0 <= value <= 1.0:
        return DEFAULT_FRAME_CONTRAST
    return value


def _kdeglobals_path() -> Optional[Path]:
    """
    Locate the user's ``kdeglobals``.

    Returns:
        The path, or None when there is none to read
    """
    path = Path(_config_home()) / 'kdeglobals'
    return path if path.is_file() else None


def _kdedefaults_path() -> Optional[Path]:
    """
    Locate the defaults the current global theme wrote.

    Returns:
        The path, or None when there is none to read
    """
    path = Path(_config_home()) / 'kdedefaults' / 'kdeglobals'
    return path if path.is_file() else None


def _config_home() -> str:
    return os.environ.get('XDG_CONFIG_HOME') or os.path.join(Path.home(), '.config')


def _parse_kde_config(path: Optional[Path]) -> Optional[configparser.RawConfigParser]:
    """
    Parse one KDE INI file.

    Args:
        path: The file, or None when there is none

    Returns:
        The parser, or None when the file is missing or unreadable
    """
    if path is None:
        return None

    parser = configparser.RawConfigParser(strict=False)
    # kdeglobals keys are case sensitive; the default lowercases them.
    parser.optionxform = str
    try:
        with open(path, 'r', encoding='utf-8', errors='replace') as handle:
            parser.read_file(handle)
    except (OSError, configparser.Error) as e:
        logger.debug("Could not read %s: %s", path, e)
        return None
    return parser


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


def icon_theme_directories() -> List[str]:
    """
    Where icon themes live on a freedesktop system.

    Qt normally finds these itself through the platform theme; a PyQt wheel
    running under a platform it has no theme plugin for does not, and then
    every ``QIcon.fromTheme`` comes back empty.

    Returns:
        Directories, the user's own first
    """
    data_home = os.environ.get('XDG_DATA_HOME') or os.path.join(Path.home(), '.local', 'share')
    data_dirs = os.environ.get('XDG_DATA_DIRS') or '/usr/local/share:/usr/share'
    candidates = [os.path.join(data_home, 'icons')]
    candidates += [os.path.join(base, 'icons') for base in data_dirs.split(':') if base]
    candidates.append(os.path.join(Path.home(), '.icons'))
    return [directory for directory in candidates if os.path.isdir(directory)]


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
