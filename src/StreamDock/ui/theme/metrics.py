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

    # Layout
    window_margin: int
    card_padding: int
    spacing: int
    spacing_tight: int
    menu_item_padding: int

    # Type, in points relative to the desktop's interface font
    font_pt: float
    font_small_pt: float
    heading_pt: float
    title_pt: float

    # Design tells
    flat_buttons: bool          # Adwaita fills, Breeze outlines
    underline_tabs: bool        # Breeze marks the current tab with an accent rule
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
        return Metrics(
            radius_small=2, radius=3, radius_large=4, radius_card=6,
            control_height=28, button_min_width=80, button_padding=12,
            border_width=1, focus_width=1, indicator_size=18,
            window_margin=12, card_padding=12, spacing=10, spacing_tight=6,
            menu_item_padding=6,
            font_pt=base, font_small_pt=max(7.0, base - 1),
            heading_pt=base + 1, title_pt=base + 4,
            flat_buttons=False, underline_tabs=True, header_separator=True,
        )

    return Metrics(
        radius_small=6, radius=8, radius_large=12, radius_card=12,
        control_height=32, button_min_width=90, button_padding=16,
        border_width=1, focus_width=2, indicator_size=20,
        window_margin=16, card_padding=14, spacing=12, spacing_tight=8,
        menu_item_padding=8,
        font_pt=base, font_small_pt=max(7.0, base - 1),
        heading_pt=base + 1, title_pt=base + 3,
        flat_buttons=True, underline_tabs=False, header_separator=True,
    )
