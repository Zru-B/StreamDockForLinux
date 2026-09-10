"""
What the window wants in its chrome, described without saying where it goes.

The main window names its actions and groups them; the KDE chrome turns that
into a menu bar and the GNOME chrome into a header bar with a primary menu.
Neither arrangement leaks back into the window.
"""

from dataclasses import dataclass, field
from typing import List, Optional

from PyQt6.QtGui import QAction

# A None entry in a group is a separator, which both designs draw.
SEPARATOR = None


@dataclass
class MenuSpec:
    """One group of actions: a menu on KDE, a section on GNOME."""

    title: str
    entries: List = field(default_factory=list)


@dataclass
class ChromeModel:
    """Everything a chrome needs to build itself."""

    menus: List[MenuSpec] = field(default_factory=list)
    # Promoted into the GNOME header bar, where a menu bar would otherwise
    # hide the two things people came to do. Both stay in the menus as well.
    open_action: Optional[QAction] = None
    save_action: Optional[QAction] = None
    title: str = ""
