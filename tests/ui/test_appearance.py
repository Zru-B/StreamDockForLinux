"""
Choosing and switching the interface design from the window.

The design follows the running desktop by default. What these cover is the
override: that choosing one rearranges the window rather than only recolouring
it, that the choice is remembered, and that the window survives being
rearranged while a configuration is open.
"""

import pytest
from PyQt6.QtWidgets import QMenuBar, QStatusBar

from StreamDock.ui import settings_store
from StreamDock.ui.chrome import GnomeChrome, KdeChrome
from StreamDock.ui.main_window import DESIGN_CHOICES, SCHEME_CHOICES, MainWindow
from StreamDock.ui.theme import Flavor, Scheme
from StreamDock.ui.theme.manager import theme_manager


@pytest.fixture
def remembered(monkeypatch):
    """Preferences that live for one test rather than in the user's settings."""
    store = {'design': 'auto', 'scheme': 'auto'}
    monkeypatch.setattr(settings_store, 'set_design',
                        lambda value: store.update(design=value))
    monkeypatch.setattr(settings_store, 'set_scheme',
                        lambda value: store.update(scheme=value))
    import StreamDock.ui.main_window as main_window
    monkeypatch.setattr(main_window, 'set_design',
                        lambda value: store.update(design=value))
    monkeypatch.setattr(main_window, 'set_scheme',
                        lambda value: store.update(scheme=value))
    return store


@pytest.fixture
def window(qtbot, remembered):
    theme_manager().set_preferences(flavor='kde', scheme='dark')
    built = MainWindow()
    qtbot.addWidget(built)
    yield built
    theme_manager().set_preferences(flavor='auto', scheme='auto')


class TestTheAppearanceMenu:
    """What the window offers under Settings."""

    def test_every_design_is_on_offer(self, window):
        values = [value for _label, value in DESIGN_CHOICES]

        assert values == ['auto', 'kde', 'gnome']

    def test_every_scheme_is_on_offer(self, window):
        values = [value for _label, value in SCHEME_CHOICES]

        assert values == ['auto', 'light', 'dark']

    def test_choosing_a_design_is_remembered(self, window, remembered):
        window.on_design_chosen('gnome')

        assert remembered['design'] == 'gnome'

    def test_choosing_a_scheme_is_remembered(self, window, remembered):
        window.on_scheme_chosen('light')

        assert remembered['scheme'] == 'light'


class TestSwitchingDesign:
    """A design change moves the furniture, not only the colours."""

    def test_it_starts_on_the_plasma_arrangement(self, window):
        assert isinstance(window._chrome, KdeChrome)
        assert window.findChild(QMenuBar) is not None

    def test_choosing_gnome_replaces_the_menu_bar_with_a_header(self, window):
        window.on_design_chosen('gnome')

        assert isinstance(window._chrome, GnomeChrome)
        assert window.findChild(QMenuBar) is None
        assert window.menuWidget().objectName() == "headerBar"

    def test_choosing_gnome_takes_the_status_bar_away(self, window):
        window.on_design_chosen('gnome')

        assert window.findChild(QStatusBar) is None

    def test_going_back_restores_the_menu_bar(self, window):
        window.on_design_chosen('gnome')

        window.on_design_chosen('kde')

        assert isinstance(window._chrome, KdeChrome)
        assert [action.text() for action in window.menuBar().actions()] == [
            "&File", "&Keys", "&Settings"]

    def test_messages_keep_working_across_the_switch(self, window):
        window.on_design_chosen('gnome')

        window.show_status("Configuration applied to device", 0)

        assert window.current_status() == "Configuration applied to device"

    def test_the_open_configuration_survives(self, window, tmp_path):
        path = tmp_path / "config.yml"
        path.write_text(
            "streamdock:\n"
            "  keys:\n"
            "    KeyA:\n"
            "      text: \"A\"\n"
            "  layouts:\n"
            "    Main:\n"
            "      Default: true\n"
            "      keys:\n"
            "        - 1: \"KeyA\"\n", encoding='utf-8')
        window.load_config(str(path))

        window.on_design_chosen('gnome')

        assert window.current_layout.name == "Main"
        assert window.key_squares[0].key_name == "KeyA"

    def test_the_grid_repaints_in_the_new_colours(self, window):
        empty = window.key_squares[-1]
        before = empty.styleSheet()

        window.on_scheme_chosen('light')

        assert empty.styleSheet() != before


class TestSwitchingScheme:
    """Light and dark, independently of the design."""

    def test_the_design_is_left_alone(self, window):
        window.on_scheme_chosen('light')

        assert theme_manager().theme.flavor is Flavor.KDE
        assert theme_manager().theme.scheme is Scheme.LIGHT

    def test_the_arrangement_is_left_alone(self, window):
        window.on_scheme_chosen('light')

        assert isinstance(window._chrome, KdeChrome)
