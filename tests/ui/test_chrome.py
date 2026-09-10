"""
The two window arrangements.

Plasma gets a menu bar and a status bar; GNOME gets a header bar with one
primary menu and toasts. The window itself only names its actions, so what
these check is that the same model produces both, and that switching between
them leaves nothing behind.
"""

import pytest
from PyQt6.QtGui import QAction
from PyQt6.QtWidgets import QDialog, QMainWindow, QMenuBar, QStatusBar

from StreamDock.ui.chrome import (
    SEPARATOR,
    ChromeModel,
    GnomeChrome,
    KdeChrome,
    MenuSpec,
    ThemedDialog,
    make_chrome,
)
from StreamDock.ui.theme import Flavor
from StreamDock.ui.theme.manager import theme_manager


@pytest.fixture
def restore_theme():
    """Put the process-wide theme back however the test left it."""
    yield
    theme_manager().set_preferences(flavor='auto', scheme='auto')


@pytest.fixture
def window(qtbot):
    frame = QMainWindow()
    qtbot.addWidget(frame)
    return frame


@pytest.fixture
def model(window):
    """A File menu, a Settings menu, and two actions worth promoting."""
    open_action = QAction("&Open...", window)
    save_action = QAction("&Save", window)
    quit_action = QAction("E&xit", window)
    settings_action = QAction("&Advanced...", window)

    return ChromeModel(
        menus=[
            MenuSpec("&File", [open_action, save_action, SEPARATOR, quit_action]),
            MenuSpec("&Settings", [settings_action]),
        ],
        open_action=open_action,
        save_action=save_action,
        title="StreamDock",
    )


class TestChoosingTheArrangement:
    """make_chrome() follows the active design."""

    def test_the_plasma_design_gets_a_menu_bar(self, window, model, restore_theme):
        theme_manager().set_preferences(flavor='kde')

        assert isinstance(make_chrome(window, model), KdeChrome)

    def test_the_gnome_design_gets_a_header_bar(self, window, model, restore_theme):
        theme_manager().set_preferences(flavor='gnome')

        assert isinstance(make_chrome(window, model), GnomeChrome)


class TestPlasmaArrangement:
    """A menu bar above, a status bar below."""

    @pytest.fixture
    def chrome(self, window, model):
        installed = KdeChrome(window, model)
        installed.install()
        return installed

    def test_each_group_becomes_a_menu(self, chrome, window):
        titles = [action.text() for action in window.menuBar().actions()]

        assert titles == ["&File", "&Settings"]

    def test_a_separator_survives_the_trip(self, chrome, window):
        entries = window.menuBar().actions()[0].menu().actions()

        assert [entry.isSeparator() for entry in entries] == [
            False, False, True, False]

    def test_messages_go_to_the_status_bar(self, chrome, window):
        chrome.show_status("Configuration applied", 0)

        assert window.statusBar().currentMessage() == "Configuration applied"
        assert chrome.current_status() == "Configuration applied"

    def test_removing_it_takes_both_bars_away(self, chrome, window):
        chrome.remove()

        assert window.findChild(QMenuBar) is None
        assert window.findChild(QStatusBar) is None


class TestGnomeArrangement:
    """A header bar, one primary menu, and toasts."""

    @pytest.fixture
    def chrome(self, window, model, restore_theme):
        theme_manager().set_preferences(flavor='gnome')
        installed = GnomeChrome(window, model)
        installed.install()
        return installed

    def test_there_is_no_menu_bar_at_all(self, chrome, window):
        assert window.findChild(QMenuBar) is None
        assert window.menuWidget().objectName() == "headerBar"

    def test_there_is_no_status_bar_either(self, chrome, window):
        assert window.findChild(QStatusBar) is None

    def test_every_command_reaches_the_primary_menu(self, chrome):
        labels = [action.text() for action in chrome._menu.actions()
                  if not action.isSeparator()]

        assert labels == ["&Open...", "&Save", "E&xit", "&Advanced..."]

    def test_the_groups_are_separated_rather_than_nested(self, chrome):
        """One popover, sectioned - not a menu bar folded into a button."""
        entries = chrome._menu.actions()

        assert sum(entry.isSeparator() for entry in entries) == 2

    def test_messages_arrive_as_a_toast(self, chrome):
        chrome.show_status("Device unplugged", 0)

        assert chrome.current_status() == "Device unplugged"

    def test_the_promoted_actions_become_header_buttons(self, chrome, window):
        from PyQt6.QtWidgets import QPushButton

        labels = [button.text() for button
                  in window.menuWidget().findChildren(QPushButton)]

        assert "Open" in labels
        assert "Save" in labels

    def test_a_header_button_fires_the_action_behind_it(self, chrome, window,
                                                        model, qtbot):
        from PyQt6.QtWidgets import QPushButton

        fired = []
        model.open_action.triggered.connect(lambda: fired.append(True))
        button = next(child for child in window.menuWidget().findChildren(QPushButton)
                      if child.text() == "Open")

        button.click()

        assert fired == [True]

    def test_the_open_document_shows_in_the_header(self, chrome):
        chrome.set_document("config.yml", modified=True)

        assert "config.yml" in chrome._subtitle.text()
        assert "Unsaved" in chrome._subtitle.text()


class TestSwitchingBetweenThem:
    """A design change has to leave nothing of the previous one behind."""

    def test_plasma_to_gnome_and_back(self, window, model, restore_theme):
        first = KdeChrome(window, model)
        first.install()
        first.remove()

        second = GnomeChrome(window, model)
        second.install()
        assert window.findChild(QMenuBar) is None

        second.remove()
        third = KdeChrome(window, model)
        third.install()

        assert [action.text() for action in window.menuBar().actions()] == [
            "&File", "&Settings"]
        assert window.findChild(QStatusBar) is not None


class TestThemedDialogs:
    """Where a dialog's decisions land."""

    def build(self, qtbot):
        dialog = ThemedDialog("Edit Key")
        qtbot.addWidget(dialog)
        dialog.add_actions("Save", dialog.accept)
        return dialog

    def test_plasma_puts_them_in_a_row_under_the_content(self, qtbot, restore_theme):
        theme_manager().set_preferences(flavor='kde')

        dialog = self.build(qtbot)

        assert dialog._outer.count() == 2
        assert dialog._outer.itemAt(1).layout() is not None

    def test_gnome_puts_them_in_a_header_above_it(self, qtbot, restore_theme):
        theme_manager().set_preferences(flavor='gnome')

        dialog = self.build(qtbot)

        assert dialog._outer.itemAt(0).widget().objectName() == "dialogHeader"

    def test_both_carry_the_same_buttons(self, qtbot, restore_theme):
        for design in ('kde', 'gnome'):
            theme_manager().set_preferences(flavor=design)

            dialog = self.build(qtbot)

            assert dialog.affirmative_button.text() == "Save"
            assert dialog.cancel_button.text() == "Cancel"

    def test_a_dialog_with_no_way_back_has_no_cancel(self, qtbot, restore_theme):
        theme_manager().set_preferences(flavor='gnome')

        dialog = ThemedDialog("Manage Keys")
        qtbot.addWidget(dialog)
        dialog.add_actions("Close", dialog.accept, cancel=None)

        assert dialog.cancel_button is None
        assert dialog.affirmative_button.text() == "Close"

    def test_the_content_layout_is_where_widgets_go(self, qtbot, restore_theme):
        dialog = ThemedDialog("Edit Key")
        qtbot.addWidget(dialog)

        assert dialog.content_layout is not dialog._outer
        assert isinstance(dialog, QDialog)
