"""
The shapes and sizes each design is built from.

Breeze and Adwaita differ far more in geometry than in colour: Breeze is tight
and lightly outlined, Adwaita is round, flat and roomy. Keeping those numbers
in one place is what lets a single stylesheet template produce both.
"""

from dataclasses import dataclass

from StreamDock.ui.theme.detection import Flavor

# What each desktop sets as its interface font size, used when the running
# application has not told us its own.
DEFAULT_POINT_SIZE = {Flavor.KDE: 10, Flavor.GNOME: 11}

# Kirigami's heading scale: level 1 and level 2, relative to the body text.
_KIRIGAMI_TITLE_SCALE = 1.35
_KIRIGAMI_HEADING_SCALE = 1.2


@dataclass(frozen=True)
class Metrics:  # pylint: disable=too-many-instance-attributes
    """Geometry and type scale for one design."""

    # Corners
    radius_small: int      # checkboxes, chips
    radius: int            # buttons, inputs
    radius_large: int      # menus, popovers
    radius_card: int       # cards, group boxes, the key grid

    # Controls
    control_height: int
    button_min_width: int
    button_padding: int
    border_width: int
    focus_width: int
    indicator_size: int
    icon_size: int         # toolbar and list icons
    icon_size_small: int   # menu entries, buttons
    list_row_height: int

    # Layout
    window_margin: int
    card_padding: int
    spacing: int
    spacing_tight: int
    menu_item_padding: int
    sidebar_width: int

    # Type, in points relative to the desktop's interface font
    font_pt: float
    font_small_pt: float
    heading_pt: float
    title_pt: float

    # Design tells
    flat_buttons: bool          # Adwaita fills, Breeze outlines
    underline_tabs: bool        # an accent rule under the current tab
    header_separator: bool      # a hairline under the header strip

    @property
    def radius_pill(self) -> int:
        """
        The radius that rounds a control into a capsule.

        Returns:
            Half the control height, which is what a pill needs
        """
        return self.control_height // 2


def build_metrics(flavor: Flavor, base_point_size: float = 0) -> Metrics:
    """
    Assemble the metrics for one design.

    Args:
        flavor: Which design to build
        base_point_size: The interface font size in points, so headings scale
            with whatever the user set. Zero takes the desktop's default.

    Returns:
        The metrics
    """
    base = base_point_size or DEFAULT_POINT_SIZE[flavor]

    if flavor is Flavor.KDE:
        # Plasma 6 Breeze: 3px frames on every control, a touch more on
        # popups, 22px toolbar icons, and Kirigami's heading scale. Captions
        # use the "smallest readable" size, two points under the body text.
        return Metrics(
            radius_small=3, radius=3, radius_large=5, radius_card=3,
            control_height=32, button_min_width=80, button_padding=14,
            border_width=1, focus_width=1, indicator_size=20,
            icon_size=22, icon_size_small=16, list_row_height=30,
            window_margin=10, card_padding=8, spacing=6, spacing_tight=4,
            menu_item_padding=5, sidebar_width=240,
            font_pt=base, font_small_pt=max(7.0, base - 2),
            heading_pt=round(base * _KIRIGAMI_HEADING_SCALE, 1),
            title_pt=round(base * _KIRIGAMI_TITLE_SCALE, 1),
            flat_buttons=False, underline_tabs=False, header_separator=True,
        )

    return Metrics(
        radius_small=6, radius=8, radius_large=12, radius_card=12,
        control_height=32, button_min_width=90, button_padding=16,
        border_width=1, focus_width=2, indicator_size=20,
        icon_size=16, icon_size_small=16, list_row_height=40,
        window_margin=16, card_padding=14, spacing=12, spacing_tight=8,
        menu_item_padding=8, sidebar_width=300,
        font_pt=base, font_small_pt=max(7.0, base - 1),
        heading_pt=base + 1, title_pt=base + 3,
        flat_buttons=True, underline_tabs=False, header_separator=True,
    )
