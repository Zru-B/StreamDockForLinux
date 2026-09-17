"""
Compatibility surface for the theme package.

The stylesheet used to be a single hand-written dark sheet living here. It is
now generated per desktop by :mod:`StreamDock.ui.theme`; these three names are
kept because most of the UI asks for its colours through them.
"""

from typing import Mapping

from StreamDock.ui.theme import current_theme, get_colors, get_stylesheet

# Indexed at import by several UI modules. It reads through to the active
# theme, so a switch reaches widgets built after it without re-importing.
COLORS: Mapping = get_colors()

__all__ = ['COLORS', 'current_theme', 'get_colors', 'get_stylesheet']
