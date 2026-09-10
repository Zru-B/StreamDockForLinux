"""
Desktop-native theming.

The application wears one of two designs. On a Qt desktop it is Breeze, built
from the colour scheme the user picked in System Settings; on a GTK desktop it
is Adwaita, with GNOME's own accent. Which one is chosen follows the running
session unless the user overrides it.

Import from here rather than from the modules underneath: the split between
detection, palette, metrics and stylesheet is an implementation detail.
"""

from StreamDock.ui.theme.assets import glyph_path as assets_glyph
from StreamDock.ui.theme.detection import Flavor, Scheme, detect_flavor, detect_scheme
from StreamDock.ui.theme.manager import (
    AUTO,
    Theme,
    ThemeManager,
    apply_theme,
    current_theme,
    get_colors,
    get_stylesheet,
    theme_manager,
    qt_palette,
)
from StreamDock.ui.theme.metrics import Metrics, build_metrics
from StreamDock.ui.theme.palette import Palette, build_palette
from StreamDock.ui.theme.stylesheet import build_stylesheet

__all__ = [
    'AUTO',
    'Flavor',
    'Metrics',
    'Palette',
    'Scheme',
    'Theme',
    'ThemeManager',
    'apply_theme',
    'assets_glyph',
    'build_metrics',
    'build_palette',
    'build_stylesheet',
    'current_theme',
    'detect_flavor',
    'detect_scheme',
    'get_colors',
    'get_stylesheet',
    'theme_manager',
    'qt_palette',
]
