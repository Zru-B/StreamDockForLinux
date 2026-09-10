"""
The active theme, and switching it.

Resolves what the session is running, what the user has overridden, and turns
that into a palette, a stylesheet and a Qt palette. Everything else in the UI
reads the result through :func:`get_colors` and :func:`current_theme`, so a
switch reaches the whole application by re-reading one object.
"""

import logging
import os
from dataclasses import dataclass
from typing import Dict, Iterator, Mapping, Optional

from PyQt6.QtCore import QObject, pyqtSignal
from PyQt6.QtGui import QColor, QPalette
from PyQt6.QtWidgets import (
    QApplication,
    QDialogButtonBox,
    QProxyStyle,
    QStyle,
    QStyleFactory,
)

from StreamDock.ui.theme.detection import Flavor, Scheme, detect_flavor, detect_scheme
from StreamDock.ui.theme.metrics import Metrics, build_metrics
from StreamDock.ui.theme.palette import Palette, build_palette
from StreamDock.ui.theme.stylesheet import build_stylesheet

logger = logging.getLogger(__name__)

AUTO = "auto"

# Fusion honours a stylesheet predictably. A native style can be forced when
# someone would rather have their desktop's own widget painting underneath.
STYLE_OVERRIDE_ENV = "STREAMDOCK_QT_STYLE"
BASE_STYLE = "Fusion"

_BUTTON_LAYOUT = {
    Flavor.KDE: QDialogButtonBox.ButtonLayout.KdeLayout,
    Flavor.GNOME: QDialogButtonBox.ButtonLayout.GnomeLayout,
}


@dataclass(frozen=True)
class Theme:  # pylint: disable=too-many-instance-attributes
    """One resolved look: which design, which scheme, and everything it paints with."""

    flavor: Flavor
    scheme: Scheme
    palette: Palette
    metrics: Metrics
    stylesheet: str

    @property
    def colors(self) -> Dict[str, str]:
        """
        The palette as the mapping the widgets index into.

        Returns:
            Role name to ``#rrggbb``
        """
        return self.palette.as_dict()

    @property
    def is_gnome(self) -> bool:
        """Whether the GNOME design is in use."""
        return self.flavor is Flavor.GNOME


class _DesignStyle(QProxyStyle):
    """
    A base style that orders dialog buttons the way the design does.

    Qt asks the style where OK and Cancel go, so the built-in dialogs -
    message boxes, file pickers - follow the chosen design without every
    caller arranging them by hand.
    """

    def __init__(self, base: QStyle, button_layout: QDialogButtonBox.ButtonLayout):
        super().__init__(base)
        self._button_layout = int(button_layout.value)

    def styleHint(self, hint, option=None, widget=None, returnData=None) -> int:
        if hint == QStyle.StyleHint.SH_DialogButtonLayout:
            return self._button_layout
        return super().styleHint(hint, option, widget, returnData)


class ThemeManager(QObject):
    """Holds the active theme and rebuilds it when the preferences change."""

    changed = pyqtSignal()

    def __init__(self):
        super().__init__()
        self._flavor_pref: str = AUTO
        self._scheme_pref: str = AUTO
        self._theme: Optional[Theme] = None
        self._style: Optional[QStyle] = None

    # ── reading ───────────────────────────────────────────────────────────

    @property
    def theme(self) -> Theme:
        """
        The active theme, resolving it on first use.

        Returns:
            The theme
        """
        if self._theme is None:
            self._theme = self._resolve()
        return self._theme

    @property
    def flavor_preference(self) -> str:
        """The stored design preference: 'auto', 'kde' or 'gnome'."""
        return self._flavor_pref

    @property
    def scheme_preference(self) -> str:
        """The stored scheme preference: 'auto', 'light' or 'dark'."""
        return self._scheme_pref

    # ── changing ──────────────────────────────────────────────────────────

    def set_preferences(self, flavor: Optional[str] = None,
                        scheme: Optional[str] = None) -> bool:
        """
        Choose the design and scheme, overriding what the session reports.

        Args:
            flavor: 'auto', 'kde' or 'gnome'; None leaves it alone
            scheme: 'auto', 'light' or 'dark'; None leaves it alone

        Returns:
            True when the resulting theme actually differs from the current one
        """
        if flavor is not None:
            self._flavor_pref = flavor
        if scheme is not None:
            self._scheme_pref = scheme

        rebuilt = self._resolve()
        if self._theme is not None and (
                rebuilt.flavor == self._theme.flavor
                and rebuilt.scheme == self._theme.scheme
                and rebuilt.stylesheet == self._theme.stylesheet):
            return False

        self._theme = rebuilt
        application = QApplication.instance()
        if application is not None:
            self._paint(application)
        self.changed.emit()
        return True

    def apply(self, application: QApplication) -> Theme:
        """
        Put the theme on a running application.

        Args:
            application: The QApplication to paint

        Returns:
            The theme that was applied
        """
        # Rebuilt here rather than reused: only now is there an application
        # font to scale the type against.
        self._theme = self._resolve()
        self._paint(application)
        self.changed.emit()
        return self._theme

    def refresh(self) -> bool:
        """
        Re-read the desktop and repaint if anything about it moved.

        Called when the session reports a light/dark switch.

        Returns:
            True when the theme changed
        """
        return self.set_preferences()

    # ── internals ─────────────────────────────────────────────────────────

    def _resolve(self) -> Theme:
        """
        Work out the theme from the preferences and the session.

        Returns:
            A freshly built theme
        """
        forced_flavor = _as_flavor(self._flavor_pref)
        flavor = forced_flavor or detect_flavor()

        forced_scheme = _as_scheme(self._scheme_pref)
        scheme = forced_scheme or detect_scheme(flavor)

        # A design the user forced against the session's own has nothing to
        # follow: reading KDE's colours to paint an Adwaita window would put
        # Breeze blue on a GNOME layout.
        follow_desktop = forced_flavor is None or forced_flavor == detect_flavor()

        palette = build_palette(flavor, scheme, follow_desktop)
        metrics = build_metrics(flavor, _application_point_size())
        return Theme(flavor=flavor, scheme=scheme, palette=palette, metrics=metrics,
                     stylesheet=build_stylesheet(palette, metrics, flavor))

    def _paint(self, application: QApplication) -> None:
        """
        Push the theme onto the application.

        Args:
            application: The QApplication to paint
        """
        theme = self._theme
        self._style = _make_style(theme.flavor)
        if self._style is not None:
            application.setStyle(self._style)
        application.setPalette(qt_palette(theme.palette))
        application.setStyleSheet(theme.stylesheet)
        logger.info("Using the %s design, %s scheme",
                    theme.flavor.value, theme.scheme.value)


def qt_palette(palette: Palette) -> QPalette:
    """
    Translate a palette into the one Qt hands to unstyled widgets.

    The stylesheet cannot reach everything - a native file dialog, the text
    cursor, a message box icon - so Qt needs the same colours by role.

    Args:
        palette: The colours to translate

    Returns:
        A QPalette carrying them
    """
    qt = QPalette()
    role = QPalette.ColorRole
    group = QPalette.ColorGroup

    for target, value in (
            (role.Window, palette.bg_primary),
            (role.WindowText, palette.text_primary),
            (role.Base, palette.bg_input),
            (role.AlternateBase, palette.bg_alternate),
            (role.Text, palette.text_primary),
            (role.Button, palette.bg_tertiary),
            (role.ButtonText, palette.text_primary),
            (role.BrightText, palette.danger),
            (role.Highlight, palette.bg_selection),
            (role.HighlightedText, palette.text_selection),
            (role.ToolTipBase, palette.bg_tooltip),
            (role.ToolTipText, palette.text_tooltip),
            (role.Link, palette.info),
            (role.LinkVisited, palette.secondary),
            (role.PlaceholderText, palette.text_secondary),
            (role.Mid, palette.border),
            (role.Dark, palette.border_strong),
            (role.Light, palette.bg_hover),
    ):
        qt.setColor(target, QColor(value))

    for target in (role.WindowText, role.Text, role.ButtonText):
        qt.setColor(group.Disabled, target, QColor(palette.text_disabled))
    qt.setColor(group.Disabled, role.Highlight, QColor(palette.bg_tertiary))
    qt.setColor(group.Disabled, role.HighlightedText, QColor(palette.text_disabled))

    return qt


def _make_style(flavor: Flavor) -> Optional[QStyle]:
    """
    Build the base widget style for a design.

    Args:
        flavor: The design in use

    Returns:
        The style, or None when Qt cannot provide one
    """
    name = os.environ.get(STYLE_OVERRIDE_ENV) or BASE_STYLE
    base = QStyleFactory.create(name)
    if base is None:
        logger.warning("Qt style %r is unavailable; keeping the default", name)
        return None
    return _DesignStyle(base, _BUTTON_LAYOUT[flavor])


def _as_flavor(preference: str) -> Optional[Flavor]:
    """
    Read a stored design preference.

    Args:
        preference: 'auto', 'kde' or 'gnome'

    Returns:
        The forced design, or None to follow the session
    """
    try:
        return Flavor(preference)
    except ValueError:
        return None


def _as_scheme(preference: str) -> Optional[Scheme]:
    """
    Read a stored scheme preference.

    Args:
        preference: 'auto', 'light' or 'dark'

    Returns:
        The forced scheme, or None to follow the session
    """
    try:
        return Scheme(preference)
    except ValueError:
        return None


def _application_point_size() -> float:
    """
    The interface font size, so the type scale follows the desktop's.

    Returns:
        A point size, or 0 when there is no application to ask yet
    """
    application = QApplication.instance()
    if application is None:
        return 0.0
    size = application.font().pointSizeF()
    return size if size > 0 else 0.0


class _LiveColors(Mapping):
    """
    A colour mapping that always reads the active theme.

    Modules capture ``COLORS = get_colors()`` at import, long before the theme
    is resolved and again after a switch; a plain dict would freeze whichever
    palette happened to exist first.
    """

    def __getitem__(self, key: str) -> str:
        return theme_manager().theme.colors[key]

    def __iter__(self) -> Iterator[str]:
        return iter(theme_manager().theme.colors)

    def __len__(self) -> int:
        return len(theme_manager().theme.colors)

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"LiveColors({theme_manager().theme.flavor.value})"


_ACTIVE: Optional[ThemeManager] = None
_live_colors = _LiveColors()


def theme_manager() -> ThemeManager:
    """
    The process-wide theme manager.

    Named for the object rather than the module so that
    ``from StreamDock.ui.theme import theme_manager`` cannot shadow
    :mod:`StreamDock.ui.theme.manager` itself.

    Returns:
        The manager, created on first use
    """
    global _ACTIVE  # pylint: disable=global-statement
    if _ACTIVE is None:
        _ACTIVE = ThemeManager()
    return _ACTIVE


def current_theme() -> Theme:
    """
    The active theme.

    Returns:
        The theme
    """
    return theme_manager().theme


def get_colors() -> Mapping:
    """
    The palette, as a mapping that tracks theme changes.

    Returns:
        Role name to ``#rrggbb``
    """
    return _live_colors


def get_stylesheet() -> str:
    """
    The active stylesheet.

    Returns:
        QSS for the whole application
    """
    return theme_manager().theme.stylesheet


def apply_theme(application: QApplication, flavor: Optional[str] = None,
                scheme: Optional[str] = None) -> Theme:
    """
    Resolve and apply the theme to a running application.

    Args:
        application: The QApplication to paint
        flavor: 'auto', 'kde' or 'gnome'
        scheme: 'auto', 'light' or 'dark'

    Returns:
        The theme that was applied
    """
    active = theme_manager()
    if flavor is not None:
        active._flavor_pref = flavor     # pylint: disable=protected-access
    if scheme is not None:
        active._scheme_pref = scheme     # pylint: disable=protected-access
    return active.apply(application)
