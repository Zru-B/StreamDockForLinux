"""
Edge-case configuration files in the editor.

The window must never die on a file the user hands it. Anything unusual
should render as an error state or be skipped visibly, not raise out of a Qt
slot, where the exception aborts the process rather than showing a dialog.
"""

import os
import tempfile
from unittest.mock import Mock, patch

import pytest
import yaml

from StreamDock.application.config_document import (
    MIN_BRIGHTNESS,
    ConfigDocument,
    KeyDefinition,
)
from StreamDock.ui.dialogs import ActionDialog
from StreamDock.ui.main_window import MainWindow
from StreamDock.ui.widgets import ActionListItem, KeySquare


@pytest.fixture
def workdir():
    with tempfile.TemporaryDirectory() as tmpdir:
        yield tmpdir


@pytest.fixture
def window(qtbot):
    w = MainWindow()
    qtbot.addWidget(w)
    return w


@pytest.fixture
def square(qtbot):
    s = KeySquare(1)
    qtbot.addWidget(s)
    return s


def write_config(workdir, streamdock, name="config.yml"):
    path = os.path.join(workdir, name)
    with open(path, "w", encoding="utf-8") as f:
        yaml.dump({"streamdock": streamdock}, f, sort_keys=False)
    return path


def key(text="A", **extra):
    return {"text": text, "on_press_actions": [{"KEY_PRESS": "a"}], **extra}


BASE = {
    "settings": {"brightness": 30},
    "keys": {"KeyA": key()},
    "layouts": {"Main": {"Default": True, "keys": [{1: "KeyA"}]}},
}


class TestLoadingOddConfigs:
    """load_config must survive whatever the file holds."""

    def test_a_float_brightness_loads(self, window, workdir):
        """The validator accepts it; the slider does not take a float."""
        window.load_config(write_config(workdir, {**BASE, "settings": {"brightness": 50.5}}))

        assert window.brightness_slider.value() == 50
        assert window.brightness_value.text() == "50%"
        assert window.config.settings.brightness == 50.5

    @pytest.mark.parametrize("stored,shown", [(0, MIN_BRIGHTNESS),
                                              (MIN_BRIGHTNESS, MIN_BRIGHTNESS),
                                              (100, 100)])
    def test_brightness_extremes_load(self, window, workdir, stored, shown):
        """A file dimmer than the device honours lands on the slider minimum."""
        window.load_config(
            write_config(workdir, {**BASE, "settings": {"brightness": stored}}))

        assert window.brightness_slider.value() == shown
        assert window.brightness_value.text() == f"{shown}%"

    def test_unicode_names_load(self, window, workdir):
        source = {"keys": {"Ключ 🎹": key("日本")},
                  "layouts": {"Основной 🚀": {"Default": True,
                                              "keys": [{1: "Ключ 🎹"}]}}}

        window.load_config(write_config(workdir, source))

        assert "Основной 🚀" in window.config.layouts

    def test_many_layouts_load(self, window, workdir):
        source = {**BASE,
                  "layouts": {f"Layout{n}": {"keys": [{1: "KeyA"}]} for n in range(50)}}
        source["layouts"]["Layout0"]["Default"] = True

        window.load_config(write_config(workdir, source))

        assert len(window.config.layouts) == 50

    def test_a_config_with_no_window_rules_loads(self, window, workdir):
        window.load_config(write_config(workdir, BASE))

        assert window.config.window_rules == {}

    def test_a_failed_load_keeps_the_previous_document(self, window, workdir):
        """The new document must not be swapped in half way."""
        window.load_config(write_config(workdir, BASE))
        before = window.config

        bad = os.path.join(workdir, "bad.yml")
        with open(bad, "w", encoding="utf-8") as f:
            f.write("streamdock:\n  keys: [unclosed\n")

        with patch('StreamDock.ui.main_window.QMessageBox.critical'):
            window.load_config(bad)

        assert window.config is before
        assert "KeyA" in window.config.keys

    def test_a_malformed_file_reports_rather_than_raises(self, window, workdir):
        bad = os.path.join(workdir, "bad.yml")
        with open(bad, "w", encoding="utf-8") as f:
            f.write("streamdock:\n")

        with patch('StreamDock.ui.main_window.QMessageBox.critical') as critical:
            window.load_config(bad)

        critical.assert_called_once()


class TestDisplayLayout:
    """Rendering a layout onto the 15-square grid."""

    def show(self, window, workdir, layout_keys, keys=None):
        source = {**BASE,
                  "keys": keys or BASE["keys"],
                  "layouts": {"Main": {"Default": True, "keys": layout_keys}}}
        window.load_config(write_config(workdir, source))
        window.on_layout_selected("Main")
        return window

    def test_an_empty_layout_leaves_the_grid_blank(self, window, workdir):
        self.show(window, workdir, [{1: None}])

        assert all(square.is_empty() for square in window.key_squares)

    def test_a_null_slot_is_skipped(self, window, workdir):
        self.show(window, workdir, [{1: None}, {2: "KeyA"}])

        assert window.key_squares[0].is_empty()
        assert not window.key_squares[1].is_empty()

    def test_a_dangling_key_reference_leaves_the_square_empty(self, window, workdir):
        """The reference survives in the document; the square shows nothing."""
        window.config = ConfigDocument.from_dict({
            **BASE,
            "layouts": {"Main": {"Default": True, "keys": [{1: "Missing"}]}}})
        window.display_layout(window.config.layouts["Main"])

        assert window.key_squares[0].is_empty()

    def test_an_out_of_range_position_is_skipped_but_kept(self, window, workdir):
        """It cannot be edited away in the UI, and it blocks Apply."""
        window.config = ConfigDocument.from_dict({
            **BASE,
            "layouts": {"Main": {"Default": True,
                                 "keys": [{1: "KeyA"}, {99: "KeyA"}]}}})

        window.display_layout(window.config.layouts["Main"])

        assert not window.key_squares[0].is_empty()
        assert 99 in window.config.layouts["Main"].keys
        assert window.config.validate() != []

    def test_a_full_deck_fills_every_square(self, window, workdir):
        keys = {f"K{n}": key(str(n)) for n in range(1, 16)}
        self.show(window, workdir, [{n: f"K{n}"} for n in range(1, 16)], keys)

        assert all(not square.is_empty() for square in window.key_squares)

    def test_selecting_a_layout_never_raises(self, window, workdir):
        """on_layout_selected is a Qt slot with no try, so a raise kills the app."""
        keys = {"Weird": {"text": "A", "font_size": 20,
                          "on_press_actions": [{"KEY_PRESS": "a"}]}}
        self.show(window, workdir, [{1: "Weird"}], keys)

        assert not window.key_squares[0].is_empty()


class TestKeySquare:
    """The grid cell, which renders whatever the document holds."""

    @pytest.mark.parametrize("font_size", [20.5, "20", None, 0, -5])
    def test_a_bad_font_size_does_not_raise(self, square, font_size):
        """This used to raise TypeError out of a Qt slot."""
        square.set_key("K", KeyDefinition("K", {"text": "A", "font_size": font_size}))

        assert square.label.text() == "A"

    def test_a_bogus_colour_does_not_raise(self, square):
        square.set_key("K", KeyDefinition("K", {
            "text": "A", "text_color": "not-a-colour",
            "background_color": "#ZZZZZZ"}))

        assert square.label.text() == "A"

    def test_a_key_with_neither_icon_nor_text_shows_an_error(self, square):
        """It used to look empty while is_empty() said otherwise."""
        square.set_key("K", KeyDefinition("K", {}))

        assert "No icon" in square.label.text()

    def test_a_key_with_both_icon_and_text_still_renders(self, square, workdir):
        icon = os.path.join(workdir, "icon.png")
        with open(icon, "wb") as f:
            f.write(b"\x89PNG\r\n\x1a\n")
        square.config_dir = workdir

        square.set_key("K", KeyDefinition("K", {"icon": "icon.png", "text": "A"}))

        assert not square.is_empty()

    def test_a_missing_icon_shows_not_found(self, square, workdir):
        square.config_dir = workdir

        square.set_key("K", KeyDefinition("K", {"icon": "gone.png"}))

        assert "Not Found" in square.label.text()

    def test_a_file_that_is_not_an_image_shows_an_error(self, square, workdir):
        path = os.path.join(workdir, "fake.png")
        with open(path, "w") as f:
            f.write("this is not a png")
        square.config_dir = workdir

        square.set_key("K", KeyDefinition("K", {"icon": "fake.png"}))

        assert "Error" in square.label.text()

    def test_a_zero_byte_icon_shows_an_error(self, square, workdir):
        path = os.path.join(workdir, "empty.png")
        open(path, "wb").close()
        square.config_dir = workdir

        square.set_key("K", KeyDefinition("K", {"icon": "empty.png"}))

        assert "Error" in square.label.text()

    def test_very_long_text_renders(self, square):
        square.set_key("K", KeyDefinition("K", {"text": "x" * 500}))

        assert square.label.text() == "x" * 500

    def test_emoji_text_renders(self, square):
        square.set_key("K", KeyDefinition("K", {"text": "🚀🎹"}))

        assert square.label.text() == "🚀🎹"


class TestActionListItem:
    """One row of the action list."""

    def test_a_bare_string_action(self, qtbot):
        """`- DEVICE_BRIGHTNESS_UP` passes validation, so it reaches the UI."""
        item = ActionListItem(0, "DEVICE_BRIGHTNESS_UP")
        qtbot.addWidget(item)

        assert "DEVICE_BRIGHTNESS_UP" in item._format_action()

    def test_a_non_string_type_text_payload(self, qtbot):
        item = ActionListItem(0, {"TYPE_TEXT": 42})
        qtbot.addWidget(item)

        assert "42" in item._format_action()

    def test_a_very_long_type_text_payload_is_truncated(self, qtbot):
        item = ActionListItem(0, {"TYPE_TEXT": "x" * 200})
        qtbot.addWidget(item)

        assert item._format_action().endswith("...")

    def test_a_list_key_press_payload(self, qtbot):
        item = ActionListItem(0, {"KEY_PRESS": ["ctrl", "c"]})
        qtbot.addWidget(item)

        assert item._format_action()

    def test_an_empty_action(self, qtbot):
        item = ActionListItem(0, {})
        qtbot.addWidget(item)

        assert item._format_action() == "Empty action"


class TestActionDialogEditing:
    """Loading an existing action - the path the parity test never took."""

    @pytest.mark.parametrize("action", [
        {"KEY_PRESS": "ctrl+c"},
        {"TYPE_TEXT": "hello"},
        {"EXECUTE_COMMAND": "ls"},
        {"LAUNCH_APPLICATION": "firefox"},
        {"WAIT": 2},
        {"CHANGE_KEY_IMAGE": "a.png"},
        {"CHANGE_KEY_TEXT": {"text": "Hi"}},
        {"CHANGE_KEY": "OtherKey"},
        {"CHANGE_LAYOUT": "Other"},
        {"DBUS": "org.example"},
        {"DEVICE_BRIGHTNESS_UP": None},
        {"DEVICE_BRIGHTNESS_DOWN": None},
    ])
    def test_every_action_type_can_be_reopened(self, qtbot, action):
        """CHANGE_KEY sorts first, so its fields were never built."""
        dialog = ActionDialog(action, available_layouts=["Other"],
                              available_keys=["OtherKey"], config_dir="/tmp")
        qtbot.addWidget(dialog)

        assert dialog.get_action() is not None

    @pytest.mark.parametrize("action", [
        {"KEY_PRESS": None},
        {"TYPE_TEXT": None},
        {"CHANGE_KEY_IMAGE": None},
        {"WAIT": "abc"},
        {"WAIT": None},
        {"CHANGE_KEY_TEXT": {"text": "Hi", "font_size": "big"}},
        {"CHANGE_KEY_TEXT": "plain string"},
    ])
    def test_a_bad_payload_does_not_raise(self, qtbot, action):
        dialog = ActionDialog(action, available_layouts=["Other"],
                              available_keys=["OtherKey"], config_dir="/tmp")
        qtbot.addWidget(dialog)

    def test_a_dangling_layout_reference_is_reported_not_silently_kept(self, qtbot):
        """Known behaviour: the combo falls back to its first entry."""
        dialog = ActionDialog({"CHANGE_LAYOUT": "Gone"},
                              available_layouts=["Real"], config_dir="/tmp")
        qtbot.addWidget(dialog)

        assert dialog.get_action() is not None


class TestValidationInTheUI:
    """What the user is told about a bad configuration."""

    def test_a_valid_config_passes(self, window, workdir):
        window.load_config(write_config(workdir, BASE))

        assert window.validate_current_config() is True

    def test_an_invalid_config_is_reported(self, window, workdir):
        window.config = ConfigDocument.from_dict({**BASE,
                                                  "settings": {"brightness": 500}})

        with patch('StreamDock.ui.main_window.QMessageBox') as box:
            box.Icon.Critical = 0
            assert window.validate_current_config() is False

    def test_apply_is_blocked_by_an_invalid_config(self, window, workdir):
        window.config = ConfigDocument.from_dict({**BASE,
                                                  "settings": {"brightness": 500}})
        emitted = []
        window.apply_config_requested.connect(lambda d, p: emitted.append(d))

        with patch('StreamDock.ui.main_window.QMessageBox'):
            window.on_apply_requested()

        assert emitted == []

    def test_save_anyway_writes_an_invalid_config(self, window, workdir):
        """Work in progress is worth keeping, and it must reload afterwards."""
        window.config = ConfigDocument.from_dict({**BASE,
                                                  "settings": {"brightness": 500}})
        target = os.path.join(workdir, "wip.yml")

        with patch.object(MainWindow, 'validate_current_config', return_value=True):
            window.save_config_to_file(target)

        assert os.path.exists(target)
        assert ConfigDocument.load(target).validate() != []
