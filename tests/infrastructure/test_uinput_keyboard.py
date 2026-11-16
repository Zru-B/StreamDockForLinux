"""
Unit tests for the uinput virtual keyboard.

python-evdev is replaced by a fake module, so the tests need neither the
package nor access to /dev/uinput.
"""

import sys
import types

import pytest
from unittest.mock import MagicMock

from StreamDock.infrastructure import uinput_keyboard
from StreamDock.infrastructure.uinput_keyboard import (
    UinputKeyboard, UinputUnavailable, parse_combo, unsupported_chars,
)

EV_KEY = 1
DOWN, UP = 1, 0


@pytest.fixture
def fake_evdev(monkeypatch):
    """A fake evdev module whose key codes are their own names."""
    codes = {name: name for name in uinput_keyboard._all_key_names()}
    ecodes = types.SimpleNamespace(EV_KEY=EV_KEY, **codes)
    device = MagicMock()
    module = types.SimpleNamespace(UInput=MagicMock(return_value=device), ecodes=ecodes)
    monkeypatch.setitem(sys.modules, "evdev", module)
    monkeypatch.setattr(uinput_keyboard.time, "sleep", lambda _seconds: None)
    return module


def key_events(device):
    """The (key, value) pairs written to the device, in order."""
    return [(c.args[1], c.args[2]) for c in device.write.call_args_list]


class TestParseCombo:

    def test_modifiers_and_key(self):
        assert parse_combo("ctrl+shift+t") == [
            ("KEY_LEFTCTRL", False), ("KEY_LEFTSHIFT", False), ("KEY_T", False)]

    def test_shifted_symbol(self):
        assert parse_combo("ctrl+parenleft") == [("KEY_LEFTCTRL", False), ("KEY_9", True)]

    def test_named_keys(self):
        assert parse_combo("alt+Page_Down") == [("KEY_LEFTALT", False), ("KEY_PAGEDOWN", False)]
        assert parse_combo("F12") == [("KEY_F12", False)]
        assert parse_combo("XF86AudioPlay") == [("KEY_PLAYPAUSE", False)]

    def test_unknown_key(self):
        assert parse_combo("ctrl+XF86Calculator") is None


class TestSendCombo:

    def test_presses_in_order_and_releases_in_reverse(self, fake_evdev):
        keyboard = UinputKeyboard()
        assert keyboard.send_combo("ctrl+t") is True
        device = fake_evdev.UInput.return_value
        assert key_events(device) == [
            ("KEY_LEFTCTRL", DOWN), ("KEY_T", DOWN), ("KEY_T", UP), ("KEY_LEFTCTRL", UP)]
        assert device.syn.call_count == 4

    def test_shifted_symbol_adds_shift_before_the_key(self, fake_evdev):
        UinputKeyboard().send_combo("ctrl+parenleft")
        assert key_events(fake_evdev.UInput.return_value) == [
            ("KEY_LEFTCTRL", DOWN), ("KEY_LEFTSHIFT", DOWN), ("KEY_9", DOWN),
            ("KEY_9", UP), ("KEY_LEFTSHIFT", UP), ("KEY_LEFTCTRL", UP)]

    def test_shift_written_in_the_combo_is_not_doubled(self, fake_evdev):
        UinputKeyboard().send_combo("shift+plus")
        assert key_events(fake_evdev.UInput.return_value) == [
            ("KEY_LEFTSHIFT", DOWN), ("KEY_EQUAL", DOWN), ("KEY_EQUAL", UP), ("KEY_LEFTSHIFT", UP)]

    def test_unknown_key_sends_nothing(self, fake_evdev):
        assert UinputKeyboard().send_combo("XF86Calculator") is False
        fake_evdev.UInput.assert_not_called()

    def test_device_is_created_once(self, fake_evdev):
        keyboard = UinputKeyboard()
        keyboard.send_combo("a")
        keyboard.send_combo("b")
        fake_evdev.UInput.assert_called_once()
        assert fake_evdev.UInput.call_args.kwargs["name"] == uinput_keyboard.DEVICE_NAME


class TestTypeText:

    def test_types_with_shift_and_newline(self, fake_evdev):
        assert UinputKeyboard().type_text("Hi!\n") is True
        assert key_events(fake_evdev.UInput.return_value) == [
            ("KEY_LEFTSHIFT", DOWN), ("KEY_H", DOWN), ("KEY_H", UP), ("KEY_LEFTSHIFT", UP),
            ("KEY_I", DOWN), ("KEY_I", UP),
            ("KEY_LEFTSHIFT", DOWN), ("KEY_1", DOWN), ("KEY_1", UP), ("KEY_LEFTSHIFT", UP),
            ("KEY_ENTER", DOWN), ("KEY_ENTER", UP)]

    def test_unsupported_characters_type_nothing(self, fake_evdev):
        assert UinputKeyboard().type_text("Hi שלום") is False
        fake_evdev.UInput.assert_not_called()

    def test_unsupported_chars_lists_each_once(self):
        assert unsupported_chars("aé b é ü") == "éü"
        assert unsupported_chars("Hi, how are you doing today?") == ""


class TestUnavailable:

    def test_no_access_to_uinput(self, fake_evdev):
        fake_evdev.UInput.side_effect = PermissionError(13, "Permission denied")
        with pytest.raises(UinputUnavailable, match="Permission denied"):
            UinputKeyboard().send_combo("a")

    def test_no_evdev(self, monkeypatch):
        monkeypatch.setitem(sys.modules, "evdev", None)
        with pytest.raises(UinputUnavailable, match="python-evdev"):
            UinputKeyboard().type_text("a")

    def test_close_removes_the_device(self, fake_evdev):
        keyboard = UinputKeyboard()
        keyboard.send_combo("a")
        keyboard.close()
        fake_evdev.UInput.return_value.close.assert_called_once()
        keyboard.send_combo("a")
        assert fake_evdev.UInput.call_count == 2
