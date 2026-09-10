"""
The generated stylesheet.

Testing QSS by string matching is brittle, so these check the properties that
actually break the window: balanced braces, no unresolved placeholders, and
the handful of selectors the widgets rely on by object name.
"""

import pytest

from StreamDock.ui.theme import palette as palette_module
from StreamDock.ui.theme.detection import Flavor, Scheme
from StreamDock.ui.theme.metrics import build_metrics
from StreamDock.ui.theme.palette import build_palette
from StreamDock.ui.theme.stylesheet import build_stylesheet

# Object names the widgets set, which the sheet has to know about. A rename on
# one side and not the other leaves an unstyled widget nobody notices.
REQUIRED_SELECTORS = (
    '#deviceBar', '#deviceCombo', '#connectionDot', '#connectionStatus',
    '#actionRow', '#segmentedControl', '#sidePanel', '#keyGrid',
    '#headerBar', '#dialogHeader', '#toast', '#toastText',
    '#brightnessValue', '#actionGrip', '#actionIndex', '#actionsEmpty',
    'buttonType="primary"', 'buttonType="danger"', 'buttonType="glyph"',
    'glyphRole="add"', 'barButton="primary"', 'segment="true"',
    'headingLevel="1"', 'headingLevel="2"',
)

EVERY_DESIGN = [(flavor, scheme) for flavor in Flavor for scheme in Scheme]


@pytest.fixture(autouse=True)
def no_desktop(monkeypatch):
    """Build from the stock colours, so the result does not vary by machine."""
    monkeypatch.setattr(palette_module, 'read_kde_colors', dict)
    monkeypatch.setattr(palette_module, 'read_gnome_accent', lambda: None)


def sheet_for(flavor, scheme=Scheme.DARK):
    return build_stylesheet(build_palette(flavor, scheme),
                            build_metrics(flavor), flavor)


@pytest.mark.parametrize('flavor, scheme', EVERY_DESIGN)
class TestWellFormed:
    """Whatever it says, it has to be valid QSS."""

    def test_braces_balance(self, flavor, scheme):
        sheet = sheet_for(flavor, scheme)

        assert sheet.count('{') == sheet.count('}')

    def test_nothing_is_left_unsubstituted(self, flavor, scheme):
        """A stray {p.something} means an f-string brace was doubled."""
        sheet = sheet_for(flavor, scheme)

        assert '{p.' not in sheet
        assert '{m.' not in sheet

    def test_every_object_name_the_widgets_use_is_styled(self, flavor, scheme):
        sheet = sheet_for(flavor, scheme)

        assert not [name for name in REQUIRED_SELECTORS if name not in sheet]

    def test_the_window_colour_reaches_the_sheet(self, flavor, scheme):
        built = build_palette(flavor, scheme)

        assert built.bg_primary in sheet_for(flavor, scheme)


class TestDesignTells:
    """The two designs have to actually look different."""

    def test_they_are_not_the_same_sheet(self):
        assert sheet_for(Flavor.KDE) != sheet_for(Flavor.GNOME)

    def test_breeze_underlines_the_current_tab(self):
        assert 'border-bottom: 2px solid' in sheet_for(Flavor.KDE)

    def test_adwaita_rounds_further_than_breeze(self):
        assert (build_metrics(Flavor.GNOME).radius_card
                > build_metrics(Flavor.KDE).radius_card)

    def test_adwaita_leaves_its_cards_unoutlined(self):
        assert 'QGroupBox {\n    background-color: #2D2D2D;\n    border: none;' \
            in sheet_for(Flavor.GNOME)


class TestQtPalette:
    """The Qt palette, for everything a stylesheet cannot reach."""

    @pytest.mark.parametrize('flavor, scheme', EVERY_DESIGN)
    def test_the_window_and_its_text_come_through(self, flavor, scheme, qapp):
        from PyQt6.QtGui import QPalette

        from StreamDock.ui.theme.manager import qt_palette

        built = build_palette(flavor, scheme)
        translated = qt_palette(built)

        assert translated.color(QPalette.ColorRole.Window).name().upper() \
            == built.bg_primary.upper()
        assert translated.color(QPalette.ColorRole.WindowText).name().upper() \
            == built.text_primary.upper()
