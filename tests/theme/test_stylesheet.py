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
    '#sidebar', '#sidebarHeading', '#sidebarRule', '#sidebarList',
    '#settingsPanel', '#gridCaption', '#statusDocument',
    'QToolBar', 'QToolButton', 'QStatusBar',
    'buttonType="primary"', 'buttonType="danger"', 'buttonType="glyph"',
    'glyphRole="add"', 'barButton="primary"', 'segment="true"',
    'headingLevel="1"', 'headingLevel="2"', 'textRole="caption"',
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

    def test_breeze_joins_the_current_tab_to_its_frame(self):
        """Plasma 6 raises the current tab into the pane, no accent rule."""
        sheet = sheet_for(Flavor.KDE)

        assert 'margin-bottom: -1px' in sheet
        assert 'border-bottom: 2px solid' not in sheet

    def test_breeze_has_a_tools_area_that_dims_with_the_window(self):
        sheet = sheet_for(Flavor.KDE)

        assert 'QToolBar[windowActive="false"]' in sheet
        assert 'QMenuBar[windowActive="false"]' in sheet
        assert 'QToolBar[windowActive="false"]' not in sheet_for(Flavor.GNOME)

    def test_breeze_never_fills_a_button_with_the_accent(self):
        """Pressed and default buttons get a wash of the accent, not a block."""
        built = build_palette(Flavor.KDE, Scheme.DARK)
        sheet = sheet_for(Flavor.KDE)
        buttons = sheet[sheet.index('/* ── buttons'):sheet.index('/* ── text fields')]

        assert f'background-color: {built.primary};' not in buttons
        assert f'border-color: {built.border_focus};' in buttons

    def test_breeze_marks_a_pending_apply_with_the_neutral_colour(self):
        built = build_palette(Flavor.KDE, Scheme.DARK)
        sheet = sheet_for(Flavor.KDE)

        assert f'border-color: {built.warning};' in sheet
        assert 'QPushButton[barButton="primary"]:enabled' in sheet

    def test_adwaita_keeps_its_accent_filled_apply(self):
        built = build_palette(Flavor.GNOME, Scheme.DARK)

        assert (f'QPushButton[barButton="primary"] {{\n    background-color: {built.primary};'
                in sheet_for(Flavor.GNOME))

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
