"""
The colours each design paints with.

What matters is that the desktop's own scheme comes through, that a forced
design does not inherit the other one's colours, and that nothing produced is
unreadable.
"""

import pytest

from StreamDock.ui.theme import color, palette
from StreamDock.ui.theme.detection import Flavor, Scheme
from StreamDock.ui.theme.palette import build_palette

# Every role the widgets index into by name. Losing one is a KeyError at the
# moment a window opens, so it is worth stating the list.
LEGACY_ROLES = (
    'primary', 'primary_hover', 'primary_dark', 'secondary', 'secondary_hover',
    'success', 'success_hover', 'danger', 'danger_hover', 'warning',
    'warning_hover', 'info', 'info_hover', 'bg_primary', 'bg_secondary',
    'bg_tertiary', 'bg_hover', 'bg_light', 'bg_card', 'text_primary',
    'text_secondary', 'text_light', 'text_dark', 'border', 'border_focus',
)

EVERY_DESIGN = [(flavor, scheme) for flavor in Flavor for scheme in Scheme]


@pytest.fixture(autouse=True)
def no_desktop(monkeypatch):
    """Nothing is read from the running session unless a test asks for it."""
    monkeypatch.setattr(palette, 'read_kde_colors', dict)
    monkeypatch.setattr(palette, 'read_gnome_accent', lambda: None)


@pytest.mark.parametrize('flavor, scheme', EVERY_DESIGN)
class TestEveryDesign:
    """Properties that have to hold whichever design is on."""

    def test_every_role_the_widgets_ask_for_is_present(self, flavor, scheme):
        colors = build_palette(flavor, scheme).as_dict()

        assert not set(LEGACY_ROLES) - set(colors)

    def test_every_colour_is_a_colour(self, flavor, scheme):
        for role, value in build_palette(flavor, scheme).as_dict().items():
            assert color.parse(value), role

    def test_text_contrasts_with_the_window(self, flavor, scheme):
        built = build_palette(flavor, scheme)

        difference = abs(color.luminance(built.text_primary)
                         - color.luminance(built.bg_primary))

        assert difference > 0.5

    def test_the_accent_carries_legible_text(self, flavor, scheme):
        built = build_palette(flavor, scheme)

        assert built.on_primary == color.readable_on(built.primary)

    def test_the_scheme_decides_which_way_round_it_is(self, flavor, scheme):
        built = build_palette(flavor, scheme)

        assert color.is_dark(built.bg_primary) == (scheme is Scheme.DARK)


class TestBreezeToolsArea:
    """The header strip Plasma paints its title bar and toolbar with."""

    def test_the_dark_tools_area_is_lighter_than_the_window(self):
        built = build_palette(Flavor.KDE, Scheme.DARK)

        assert color.luminance(built.bg_header) > color.luminance(built.bg_primary)

    def test_the_light_tools_area_is_darker_than_the_window(self):
        built = build_palette(Flavor.KDE, Scheme.LIGHT)

        assert color.luminance(built.bg_header) < color.luminance(built.bg_primary)

    @pytest.mark.parametrize('scheme', list(Scheme))
    def test_it_falls_back_to_the_window_colour_when_inactive(self, scheme):
        built = build_palette(Flavor.KDE, scheme)

        assert built.bg_header_inactive == built.bg_primary
        assert built.bg_header != built.bg_header_inactive

    def test_the_session_can_say_otherwise(self, monkeypatch):
        monkeypatch.setattr(palette, 'read_kde_colors', lambda: {
            'window_bg': '#202326', 'header_bg': '#303030',
            'header_bg_inactive': '#101010'})

        built = build_palette(Flavor.KDE, Scheme.DARK)

        assert built.bg_header == '#303030'
        assert built.bg_header_inactive == '#101010'

    def test_frames_are_the_window_pulled_towards_the_text(self, monkeypatch):
        """Breeze has no border role; the outline is a blend, at a contrast
        the user can set."""
        monkeypatch.setattr(palette, 'read_kde_colors',
                            lambda: {'window_bg': '#000000', 'window_fg': '#FFFFFF'})
        monkeypatch.setattr(palette, 'read_kde_frame_contrast', lambda: 0.5)

        built = build_palette(Flavor.KDE, Scheme.DARK)

        assert built.border == '#808080'


class TestFollowingKde:
    """The Plasma palette is the user's own colour scheme."""

    def test_the_session_scheme_replaces_the_stock_one(self, monkeypatch):
        monkeypatch.setattr(palette, 'read_kde_colors', lambda: {
            'window_bg': '#101010', 'window_fg': '#EEEEEE',
            'window_fg_inactive': '#999999', 'view_bg': '#080808',
            'selection_bg': '#FF6600', 'positive': '#00FF00',
            'negative': '#FF0000', 'neutral': '#FFFF00', 'link': '#00FFFF',
        })

        built = build_palette(Flavor.KDE, Scheme.DARK)

        assert built.bg_primary == '#101010'
        assert built.primary == '#FF6600'
        assert built.success == '#00FF00'

    def test_an_explicit_accent_beats_the_selection_colour(self, monkeypatch):
        monkeypatch.setattr(palette, 'read_kde_colors', lambda: {
            'window_bg': '#202326', 'window_fg': '#FCFCFC',
            'window_fg_inactive': '#A1A9B1', 'view_bg': '#141618',
            'selection_bg': '#3DAEE9', 'accent': '#924AFF',
            'positive': '#27AE60', 'negative': '#DA4453',
            'neutral': '#F67400', 'link': '#1D99F3',
        })

        assert build_palette(Flavor.KDE, Scheme.DARK).primary == '#924AFF'

    def test_a_dark_session_is_ignored_when_light_was_asked_for(self, monkeypatch):
        """Forcing the light design must not pull in dark colours."""
        monkeypatch.setattr(palette, 'read_kde_colors',
                            lambda: {'window_bg': '#101010'})

        assert not color.is_dark(build_palette(Flavor.KDE, Scheme.LIGHT).bg_primary)

    def test_the_desktop_can_be_ignored_entirely(self, monkeypatch):
        monkeypatch.setattr(palette, 'read_kde_colors',
                            lambda: {'window_bg': '#101010', 'selection_bg': '#FF6600'})

        built = build_palette(Flavor.KDE, Scheme.DARK, follow_desktop=False)

        assert built.primary == '#3DAEE9'


class TestFollowingGnome:
    """Adwaita is fixed apart from the accent."""

    def test_the_chosen_accent_is_used(self, monkeypatch):
        monkeypatch.setattr(palette, 'read_gnome_accent', lambda: '#9141AC')

        assert build_palette(Flavor.GNOME, Scheme.DARK).primary == '#9141AC'

    def test_older_gnome_keeps_adwaita_blue(self):
        assert build_palette(Flavor.GNOME, Scheme.DARK).primary == '#3584E4'

    def test_the_accent_is_ignored_when_the_design_was_forced(self, monkeypatch):
        monkeypatch.setattr(palette, 'read_gnome_accent', lambda: '#9141AC')

        built = build_palette(Flavor.GNOME, Scheme.LIGHT, follow_desktop=False)

        assert built.primary == '#3584E4'
