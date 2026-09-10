"""
Resolving and switching the active theme.
"""

import pytest

import StreamDock.ui.theme.manager as manager_module
from StreamDock.ui.theme.detection import Flavor, Scheme
from StreamDock.ui.theme.manager import ThemeManager, get_colors, theme_manager


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
