"""
Resolving and switching the active theme.
"""

import pytest
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import QDialogButtonBox, QStyle, QStyleFactory

import StreamDock.ui.theme.manager as manager_module
from StreamDock.ui.theme.detection import Flavor, Scheme
from StreamDock.ui.theme.manager import (
    ThemeManager,
    _DesignStyle,
    desktop_font,
    get_colors,
    theme_manager,
)


@pytest.fixture
def theme(monkeypatch):
    """A manager on a session that reports Plasma, dark, with stock colours."""
    monkeypatch.setattr(manager_module, 'detect_flavor', lambda: Flavor.KDE)
    monkeypatch.setattr(manager_module, 'detect_scheme', lambda _flavor: Scheme.DARK)
    from StreamDock.ui.theme import palette as palette_module
    monkeypatch.setattr(palette_module, 'read_kde_colors', dict)
    monkeypatch.setattr(palette_module, 'read_gnome_accent', lambda: None)
    return ThemeManager()


class TestResolving:
    """What the session says, unless the user said otherwise."""

    def test_it_follows_the_session_by_default(self, theme):
        assert theme.theme.flavor is Flavor.KDE
        assert theme.theme.scheme is Scheme.DARK

    def test_a_forced_design_overrides_the_session(self, theme):
        theme.set_preferences(flavor='gnome')

        assert theme.theme.flavor is Flavor.GNOME

    def test_a_forced_scheme_overrides_the_session(self, theme):
        theme.set_preferences(scheme='light')

        assert theme.theme.scheme is Scheme.LIGHT
        assert theme.theme.flavor is Flavor.KDE

    def test_an_unknown_preference_falls_back_to_following(self, theme):
        """A settings file is a text file someone can mistype."""
        theme.set_preferences(flavor='aqua', scheme='sepia')

        assert theme.theme.flavor is Flavor.KDE
        assert theme.theme.scheme is Scheme.DARK

    def test_a_forced_design_does_not_borrow_the_session_colours(
            self, theme, monkeypatch):
        from StreamDock.ui.theme import palette as palette_module
        monkeypatch.setattr(palette_module, 'read_kde_colors',
                            lambda: {'window_bg': '#101010', 'selection_bg': '#FF6600'})

        theme.set_preferences(flavor='gnome')

        assert theme.theme.palette.primary == '#3584E4'


class TestSwitching:
    """Telling everyone the look has changed."""

    def test_a_change_is_announced_once(self, theme, qtbot):
        theme.theme  # resolve first, so the switch is a change

        with qtbot.waitSignal(theme.changed, timeout=1000):
            assert theme.set_preferences(flavor='gnome') is True

    def test_choosing_what_is_already_on_changes_nothing(self, theme):
        theme.set_preferences(flavor='kde')

        assert theme.set_preferences(flavor='kde') is False

    def test_applying_paints_the_application(self, theme, qapp):
        theme.apply(qapp)

        assert qapp.styleSheet() == theme.theme.stylesheet
        assert theme.theme.palette.bg_primary in qapp.styleSheet()


class TestLiveColors:
    """The mapping every widget module captures at import."""

    def test_it_reports_the_active_palette(self):
        colors = get_colors()

        assert colors['primary'] == manager_module.current_theme().palette.primary

    def test_it_follows_a_switch_without_being_re_imported(self, monkeypatch):
        colors = get_colors()
        active = theme_manager()
        before = colors['bg_primary']

        try:
            active.set_preferences(flavor='gnome', scheme='light')

            assert colors['bg_primary'] != before
        finally:
            active.set_preferences(flavor='auto', scheme='auto')

    def test_it_behaves_like_a_mapping(self):
        colors = get_colors()

        assert 'primary' in colors
        assert len(colors) == len(manager_module.current_theme().colors)


class TestDesignStyle:
    """The base style answers Qt's questions the way the design would."""

    @pytest.fixture
    def style_for(self, qapp):
        return lambda flavor: _DesignStyle(QStyleFactory.create('Fusion'), flavor)

    def test_plasma_orders_buttons_ok_then_cancel(self, style_for):
        hint = style_for(Flavor.KDE).styleHint(QStyle.StyleHint.SH_DialogButtonLayout)

        assert hint == int(QDialogButtonBox.ButtonLayout.KdeLayout.value)

    def test_gnome_orders_buttons_cancel_then_ok(self, style_for):
        hint = style_for(Flavor.GNOME).styleHint(QStyle.StyleHint.SH_DialogButtonLayout)

        assert hint == int(QDialogButtonBox.ButtonLayout.GnomeLayout.value)

    def test_plasma_puts_icons_on_dialog_buttons_and_gnome_does_not(self, style_for):
        hint = QStyle.StyleHint.SH_DialogButtonBox_ButtonsHaveIcons

        assert style_for(Flavor.KDE).styleHint(hint) == 1
        assert style_for(Flavor.GNOME).styleHint(hint) == 0

    def test_plasma_lines_form_labels_up_on_the_right(self, style_for):
        hint = style_for(Flavor.KDE).styleHint(QStyle.StyleHint.SH_FormLayoutLabelAlignment)

        assert hint & int(Qt.AlignmentFlag.AlignRight.value)

    def test_plasma_uses_22px_toolbar_icons(self, style_for):
        assert style_for(Flavor.KDE).pixelMetric(QStyle.PixelMetric.PM_ToolBarIconSize) == 22

    def test_gnome_keeps_the_base_styles_metrics(self, style_for):
        base = QStyleFactory.create('Fusion')
        metric = QStyle.PixelMetric.PM_ToolBarIconSize

        assert style_for(Flavor.GNOME).pixelMetric(metric) == base.pixelMetric(metric)


class TestDesktopFont:
    """What Plasma would have handed a window that Qt could not ask it for."""

    def test_gnome_is_left_to_its_platform(self, qapp):
        assert desktop_font(Flavor.GNOME, QFont('Sans Serif', 9)) is None

    def test_a_font_from_kdeglobals_wins(self, qapp, monkeypatch):
        monkeypatch.setattr(manager_module, 'read_kde_font',
                            lambda key='font': 'DejaVu Sans,11,-1,5,400,0,0,0,0,0,0,0,0,0,0,1')

        font = desktop_font(Flavor.KDE, QFont('Sans Serif', 9))

        assert font.family() == 'DejaVu Sans'
        assert font.pointSize() == 11

    def test_a_font_the_platform_set_is_kept(self, qapp, monkeypatch):
        monkeypatch.setattr(manager_module, 'read_kde_font', lambda key='font': '')

        assert desktop_font(Flavor.KDE, QFont('Cantarell', 11)) is None

    def test_qts_fallback_is_replaced_by_plasmas_default(self, qapp, monkeypatch):
        monkeypatch.setattr(manager_module, 'read_kde_font', lambda key='font': '')
        monkeypatch.setattr(manager_module.QFontDatabase, 'families',
                            staticmethod(lambda *args: ['Noto Sans', 'DejaVu Sans']))

        font = desktop_font(Flavor.KDE, QFont('Sans Serif', 9))

        assert font.family() == 'Noto Sans'
        assert font.pointSize() == 10

    def test_nothing_is_forced_when_the_default_is_not_installed(self, qapp, monkeypatch):
        monkeypatch.setattr(manager_module, 'read_kde_font', lambda key='font': '')
        monkeypatch.setattr(manager_module.QFontDatabase, 'families',
                            staticmethod(lambda *args: ['DejaVu Sans']))

        assert desktop_font(Flavor.KDE, QFont('Sans Serif', 9)) is None
