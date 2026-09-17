"""
The two window arrangements.

Plasma gets a toolbar with a menu button, a status bar, and a menu bar that
stays hidden until Ctrl+M; GNOME gets a header bar with one primary menu and
toasts. The window itself only names its actions, so what these check is
that the same model produces both, and that switching between them leaves
nothing behind.
"""

import pytest
from PyQt6.QtGui import QAction, QIcon, QPixmap
from PyQt6.QtWidgets import (
    QDialog,
    QLabel,
    QMainWindow,
    QMenuBar,
    QStatusBar,
    QToolBar,
    QWidgetAction,
)

from StreamDock.ui.chrome import (
    SEPARATOR,
    SHOW_MENUBAR_SHORTCUT,
    ChromeModel,
    GnomeChrome,
    KdeChrome,
    MenuSpec,
    ThemedDialog,
    make_chrome,
)
from StreamDock.ui.chrome import dialog as dialog_module
from StreamDock.ui.chrome import window as window_module
from StreamDock.ui.theme.manager import theme_manager


@pytest.fixture
def restore_theme():
    """Put the process-wide theme back however the test left it."""
    yield
    theme_manager().set_preferences(flavor='auto', scheme='auto')


@pytest.fixture(autouse=True)
def forgotten_menubar(monkeypatch):
    """The menu-bar preference lives for one test, and starts hidden."""
    store = {'visible': False}
    monkeypatch.setattr(window_module, 'get_menubar_visible', lambda: store['visible'])
    monkeypatch.setattr(window_module, 'set_menubar_visible',
                        lambda value: store.update(visible=value))
    return store


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
    quit_action = QAction("&Quit", window)
    quit_action.setMenuRole(QAction.MenuRole.QuitRole)
    settings_action = QAction("&Advanced...", window)

    return ChromeModel(
        menus=[
            MenuSpec("&File", [open_action, save_action, SEPARATOR, quit_action]),
            MenuSpec("&Settings", [settings_action]),
        ],
        open_action=open_action,
        save_action=save_action,
        title="StreamDock",
        toolbar_actions=[open_action, save_action],
    )


def labels(menu) -> list:
    return [action.text() for action in menu.actions() if not action.isSeparator()]


class TestChoosingTheArrangement:
    """make_chrome() follows the active design."""

    def test_the_plasma_design_gets_a_toolbar(self, window, model, restore_theme):
        theme_manager().set_preferences(flavor='kde')

        assert isinstance(make_chrome(window, model), KdeChrome)

    def test_the_gnome_design_gets_a_header_bar(self, window, model, restore_theme):
        theme_manager().set_preferences(flavor='gnome')

        assert isinstance(make_chrome(window, model), GnomeChrome)


class TestPlasmaArrangement:
    """A toolbar and a menu button above, a status bar below."""

    @pytest.fixture
    def chrome(self, window, model, restore_theme):
        theme_manager().set_preferences(flavor='kde')
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

    def test_the_menu_bar_starts_hidden(self, chrome, window):
        """Plasma 6 applications keep it out of sight until asked."""
        assert window.menuBar().isHidden()
        assert chrome.menubar_visible is False

    def test_the_toolbar_carries_the_promoted_actions(self, chrome, window):
        toolbar = window.findChild(QToolBar)

        assert toolbar is chrome.toolbar
        assert [a.text() for a in toolbar.actions()[:2]] == ["&Open...", "&Save"]

    def test_the_menu_button_holds_every_command(self, chrome):
        assert chrome.menu_button is not None
        menu = chrome.menu_button.menu()

        assert "&Open..." in labels(menu)
        assert "&Advanced..." in labels(menu)

    def test_the_menu_button_files_quit_last(self, chrome):
        """After the menu-bar toggle, the way KDE's hamburger menus end."""
        entries = labels(chrome.menu_button.menu())

        assert entries[-1] == "&Quit"
        assert entries[-2] == chrome.menubar_action.text()

    def test_the_groups_are_sections_rather_than_submenus(self, chrome):
        menu = chrome.menu_button.menu()

        assert all(action.menu() is None for action in menu.actions())
        assert sum(action.isSeparator() for action in menu.actions()) >= 2

    def test_ctrl_m_toggles_the_menu_bar(self, chrome, window):
        assert chrome.menubar_action.shortcut().toString() == SHOW_MENUBAR_SHORTCUT

        chrome.menubar_action.trigger()

        assert not window.menuBar().isHidden()
        assert chrome.menubar_visible is True

    def test_the_choice_is_remembered(self, chrome, forgotten_menubar):
        chrome.menubar_action.trigger()

        assert forgotten_menubar['visible'] is True

    def test_a_remembered_menu_bar_comes_back(self, window, model, restore_theme,
                                              forgotten_menubar):
        forgotten_menubar['visible'] = True
        theme_manager().set_preferences(flavor='kde')

        chrome = KdeChrome(window, model)
        chrome.install()

        assert not window.menuBar().isHidden()
        assert chrome.menubar_action.isChecked()

    def test_the_toggle_is_filed_under_settings(self, chrome, window):
        settings = window.menuBar().actions()[1].menu()

        assert chrome.menubar_action in settings.actions()

    def test_hiding_the_menu_bar_says_how_to_get_it_back(self, chrome, window):
        chrome.menubar_action.trigger()
        chrome.menubar_action.trigger()

        assert "Ctrl+M" in window.statusBar().currentMessage()

    def test_messages_go_to_the_status_bar(self, chrome, window):
        chrome.show_status("Configuration applied", 0)

        assert window.statusBar().currentMessage() == "Configuration applied"
        assert chrome.current_status() == "Configuration applied"

    def test_the_status_bar_names_the_open_file(self, chrome, window):
        chrome.set_document("config.yml", modified=False, path="/srv/decks/config.yml")

        label = window.statusBar().findChild(QLabel, "statusDocument")
        assert label.text() == "/srv/decks/config.yml"

    def test_removing_it_takes_everything_away(self, chrome, window):
        chrome.remove()

        assert window.findChild(QMenuBar) is None
        assert window.findChild(QStatusBar) is None
        assert window.findChild(QToolBar) is None
        assert chrome.menubar_action is None


class TestHostingTheDeviceBar:
    """The Plasma toolbar takes the device controls; GNOME leaves them."""

    @pytest.fixture
    def device_bar(self, window):
        return QLabel("device controls")

    @pytest.fixture
    def hosted_model(self, model, window, device_bar):
        action = QWidgetAction(window)
        action.setDefaultWidget(device_bar)
        model.device_action = action
        return model

    def test_plasma_puts_them_in_the_toolbar(self, window, hosted_model, device_bar,
                                             restore_theme):
        theme_manager().set_preferences(flavor='kde')
        chrome = KdeChrome(window, hosted_model)

        chrome.install()

        assert chrome.hosts_device_bar()
        assert device_bar.parent() is chrome.toolbar

    def test_removing_the_chrome_hands_them_back(self, window, hosted_model, device_bar,
                                                 restore_theme):
        theme_manager().set_preferences(flavor='kde')
        chrome = KdeChrome(window, hosted_model)
        chrome.install()

        chrome.remove()

        assert device_bar.parent() is None
        assert not chrome.hosts_device_bar()

    def test_gnome_leaves_them_to_the_window(self, window, hosted_model, restore_theme):
        theme_manager().set_preferences(flavor='gnome')
        chrome = GnomeChrome(window, hosted_model)

        chrome.install()

        assert not chrome.hosts_device_bar()


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

    def test_there_is_no_status_bar_or_toolbar_either(self, chrome, window):
        assert window.findChild(QStatusBar) is None
        assert window.findChild(QToolBar) is None

    def test_every_command_reaches_the_primary_menu(self, chrome):
        assert labels(chrome._menu) == ["&Open...", "&Save", "&Quit", "&Advanced..."]

    def test_the_groups_are_separated_rather_than_nested(self, chrome):
        """One popover, sectioned - not a menu bar folded into a button."""
        entries = chrome._menu.actions()

        assert sum(entry.isSeparator() for entry in entries) == 2

    def test_messages_arrive_as_a_toast(self, chrome):
        chrome.show_status("Device unplugged", 0)

        assert chrome.current_status() == "Device unplugged"

    def test_the_promoted_actions_become_header_buttons(self, chrome, window):
        from PyQt6.QtWidgets import QPushButton

        labels_ = [button.text() for button
                   in window.menuWidget().findChildren(QPushButton)]

        assert "Open" in labels_
        assert "Save" in labels_

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
        theme_manager().set_preferences(flavor='kde')
        first = KdeChrome(window, model)
        first.install()
        first.remove()

        theme_manager().set_preferences(flavor='gnome')
        second = GnomeChrome(window, model)
        second.install()
        assert window.findChild(QMenuBar) is None
        assert window.findChild(QToolBar) is None

        second.remove()
        theme_manager().set_preferences(flavor='kde')
        third = KdeChrome(window, model)
        third.install()

        assert [action.text() for action in window.menuBar().actions()] == [
            "&File", "&Settings"]
        assert window.findChild(QStatusBar) is not None
        assert window.findChild(QToolBar) is not None


def stub_icon(*names) -> QIcon:
    pixmap = QPixmap(4, 4)
    pixmap.fill()
    return QIcon(pixmap)


class TestThemedDialogs:
    """Where a dialog's decisions land, and what they wear."""

    @pytest.fixture(autouse=True)
    def icons_available(self, monkeypatch):
        """Pretend the theme has an icon for every standard button."""
        monkeypatch.setattr(dialog_module, 'button_icon', lambda text: stub_icon())

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

    def test_plasma_leads_with_the_action_and_ends_with_cancel(self, qtbot, restore_theme):
        theme_manager().set_preferences(flavor='kde')

        dialog = self.build(qtbot)
        row = dialog._outer.itemAt(1).layout()
        buttons = [row.itemAt(i).widget() for i in range(row.count())
                   if row.itemAt(i).widget() is not None]

        assert buttons == [dialog.affirmative_button, dialog.cancel_button]

    def test_plasma_puts_icons_on_the_buttons(self, qtbot, restore_theme):
        theme_manager().set_preferences(flavor='kde')

        dialog = self.build(qtbot)

        assert not dialog.affirmative_button.icon().isNull()
        assert not dialog.cancel_button.icon().isNull()

    def test_gnome_puts_them_in_a_header_above_it(self, qtbot, restore_theme):
        theme_manager().set_preferences(flavor='gnome')

        dialog = self.build(qtbot)

        assert dialog._outer.itemAt(0).widget().objectName() == "dialogHeader"

    def test_gnome_keeps_its_buttons_plain(self, qtbot, restore_theme):
        theme_manager().set_preferences(flavor='gnome')

        dialog = self.build(qtbot)

        assert dialog.affirmative_button.icon().isNull()

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
