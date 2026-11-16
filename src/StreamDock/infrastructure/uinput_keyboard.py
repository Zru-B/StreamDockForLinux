"""
Virtual keyboard on /dev/uinput, for sending keys on Wayland.

xdotool only reaches X11 (XWayland) windows, so on a Wayland session key
presses and typed text never arrive in native Wayland apps. A uinput device
is a keyboard as far as the kernel is concerned: the compositor delivers its
keys to whichever window has focus, like a real keyboard's.

Keys are sent as key codes, so the active keyboard layout decides which
character they produce. The tables below assume a US layout.

Needs python-evdev and write access to /dev/uinput (the udev rule in
contrib/70-streamdock.rules grants it to the logged-in user).
"""

import logging
import threading
import time
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# The compositor needs a moment to pick up a new input device; keys sent
# before that are lost.
DEVICE_SETTLE_SECONDS = 0.3
# Pause between key events. Without it, some apps drop keys of long texts.
KEY_EVENT_DELAY = 0.006

DEVICE_NAME = "StreamDock virtual keyboard"

# Modifier names as the KEY_PRESS action writes them.
_MODIFIERS = {
    "ctrl": "KEY_LEFTCTRL",
    "alt": "KEY_LEFTALT",
    "shift": "KEY_LEFTSHIFT",
    "super": "KEY_LEFTMETA",
}

# X keysym name -> (evdev key name, needs Shift) on a US layout.
_KEYSYMS: Dict[str, Tuple[str, bool]] = {
    "Return": ("KEY_ENTER", False),
    "Tab": ("KEY_TAB", False),
    "space": ("KEY_SPACE", False),
    "BackSpace": ("KEY_BACKSPACE", False),
    "Delete": ("KEY_DELETE", False),
    "Insert": ("KEY_INSERT", False),
    "Escape": ("KEY_ESC", False),
    "Home": ("KEY_HOME", False),
    "End": ("KEY_END", False),
    "Page_Up": ("KEY_PAGEUP", False),
    "Prior": ("KEY_PAGEUP", False),
    "Page_Down": ("KEY_PAGEDOWN", False),
    "Next": ("KEY_PAGEDOWN", False),
    "Up": ("KEY_UP", False),
    "Down": ("KEY_DOWN", False),
    "Left": ("KEY_LEFT", False),
    "Right": ("KEY_RIGHT", False),
    "Print": ("KEY_SYSRQ", False),
    "Menu": ("KEY_COMPOSE", False),
    "Caps_Lock": ("KEY_CAPSLOCK", False),
    "minus": ("KEY_MINUS", False),
    "equal": ("KEY_EQUAL", False),
    "bracketleft": ("KEY_LEFTBRACE", False),
    "bracketright": ("KEY_RIGHTBRACE", False),
    "backslash": ("KEY_BACKSLASH", False),
    "semicolon": ("KEY_SEMICOLON", False),
    "apostrophe": ("KEY_APOSTROPHE", False),
    "grave": ("KEY_GRAVE", False),
    "comma": ("KEY_COMMA", False),
    "period": ("KEY_DOT", False),
    "slash": ("KEY_SLASH", False),
    "exclam": ("KEY_1", True),
    "at": ("KEY_2", True),
    "numbersign": ("KEY_3", True),
    "dollar": ("KEY_4", True),
    "percent": ("KEY_5", True),
    "asciicircum": ("KEY_6", True),
    "ampersand": ("KEY_7", True),
    "asterisk": ("KEY_8", True),
    "parenleft": ("KEY_9", True),
    "parenright": ("KEY_0", True),
    "underscore": ("KEY_MINUS", True),
    "plus": ("KEY_EQUAL", True),
    "braceleft": ("KEY_LEFTBRACE", True),
    "braceright": ("KEY_RIGHTBRACE", True),
    "bar": ("KEY_BACKSLASH", True),
    "colon": ("KEY_SEMICOLON", True),
    "quotedbl": ("KEY_APOSTROPHE", True),
    "asciitilde": ("KEY_GRAVE", True),
    "less": ("KEY_COMMA", True),
    "greater": ("KEY_DOT", True),
    "question": ("KEY_SLASH", True),
    "KP_Add": ("KEY_KPPLUS", False),
    "KP_Subtract": ("KEY_KPMINUS", False),
    "KP_Multiply": ("KEY_KPASTERISK", False),
    "KP_Divide": ("KEY_KPSLASH", False),
    "KP_Enter": ("KEY_KPENTER", False),
    "KP_Decimal": ("KEY_KPDOT", False),
    "XF86AudioPlay": ("KEY_PLAYPAUSE", False),
    "XF86AudioPause": ("KEY_PAUSECD", False),
    "XF86AudioNext": ("KEY_NEXTSONG", False),
    "XF86AudioPrev": ("KEY_PREVIOUSSONG", False),
    "XF86AudioStop": ("KEY_STOPCD", False),
    "XF86AudioMute": ("KEY_MUTE", False),
    "XF86AudioRaiseVolume": ("KEY_VOLUMEUP", False),
    "XF86AudioLowerVolume": ("KEY_VOLUMEDOWN", False),
    "XF86AudioMicMute": ("KEY_MICMUTE", False),
}
_KEYSYMS.update({f"F{n}": (f"KEY_F{n}", False) for n in range(1, 25)})
_KEYSYMS.update({f"KP_{n}": (f"KEY_KP{n}", False) for n in range(10)})
_KEYSYMS.update({str(n): (f"KEY_{n}", False) for n in range(10)})
_KEYSYMS.update({c: (f"KEY_{c.upper()}", False) for c in "abcdefghijklmnopqrstuvwxyz"})

# Characters TYPE_TEXT can type -> keysym name.
_CHARS: Dict[str, str] = {
    "\n": "Return", "\t": "Tab", " ": "space",
    "-": "minus", "=": "equal", "[": "bracketleft", "]": "bracketright",
    "\\": "backslash", ";": "semicolon", "'": "apostrophe", "`": "grave",
    ",": "comma", ".": "period", "/": "slash",
    "!": "exclam", "@": "at", "#": "numbersign", "$": "dollar", "%": "percent",
    "^": "asciicircum", "&": "ampersand", "*": "asterisk", "(": "parenleft",
    ")": "parenright", "_": "underscore", "+": "plus", "{": "braceleft",
    "}": "braceright", "|": "bar", ":": "colon", '"': "quotedbl",
    "~": "asciitilde", "<": "less", ">": "greater", "?": "question",
}
_CHARS.update({c: c for c in "abcdefghijklmnopqrstuvwxyz0123456789"})


class UinputUnavailable(Exception):
    """The virtual keyboard can't be created (no python-evdev, no access)."""


def _lookup_keysym(name: str) -> Optional[Tuple[str, bool]]:
    if name in _KEYSYMS:
        return _KEYSYMS[name]
    # A single upper-case letter is the shifted letter.
    if len(name) == 1 and name.isalpha() and name.isascii():
        return (f"KEY_{name.upper()}", name.isupper())
    return None


def parse_combo(combo: str) -> Optional[List[Tuple[str, bool]]]:
    """
    Split an xdotool-style combo ("ctrl+shift+t") into (evdev key name,
    needs Shift) pairs, modifiers first. None if a key isn't known.
    """
    keys: List[Tuple[str, bool]] = []
    for part in combo.split("+"):
        if part.lower() in _MODIFIERS:
            keys.append((_MODIFIERS[part.lower()], False))
            continue
        key = _lookup_keysym(part)
        if key is None:
            return None
        keys.append(key)
    return keys or None


def unsupported_chars(text: str) -> str:
    """The characters of *text* TYPE_TEXT can't type, in order, without repeats."""
    seen = []
    for char in text:
        if char not in _CHARS and _lookup_keysym(char) is None and char not in seen:
            seen.append(char)
    return "".join(seen)


def _all_key_names() -> List[str]:
    names = set(_MODIFIERS.values())
    names.update(name for name, _ in _KEYSYMS.values())
    return sorted(names)


class UinputKeyboard:
    """A virtual keyboard, created on first use and kept open."""

    def __init__(self) -> None:
        self._device = None
        self._ecodes = None
        self._lock = threading.Lock()

    def _open(self):
        """Create the device; raises UinputUnavailable."""
        if self._device is not None:
            return self._device
        try:
            # pylint: disable=import-outside-toplevel
            from evdev import UInput, ecodes
        except ImportError as exc:
            raise UinputUnavailable("python-evdev is not installed") from exc
        try:
            codes = [getattr(ecodes, name) for name in _all_key_names()]
            self._device = UInput({ecodes.EV_KEY: codes}, name=DEVICE_NAME)
        except Exception as exc:  # pylint: disable=broad-exception-caught
            # OSError without access; evdev's UInputError without /dev/uinput.
            raise UinputUnavailable(f"cannot open /dev/uinput: {exc}") from exc
        self._ecodes = ecodes
        time.sleep(DEVICE_SETTLE_SECONDS)
        logger.info("Created the %s", DEVICE_NAME)
        return self._device

    def _emit(self, device, name: str, value: int) -> None:
        device.write(self._ecodes.EV_KEY, getattr(self._ecodes, name), value)
        device.syn()
        time.sleep(KEY_EVENT_DELAY)

    def _tap(self, device, held: List[str]) -> None:
        """Press *held* in order, then release them in reverse."""
        for name in held:
            self._emit(device, name, 1)
        for name in reversed(held):
            self._emit(device, name, 0)

    @staticmethod
    def _with_shift(keys: List[Tuple[str, bool]]) -> List[str]:
        names = [name for name, _ in keys]
        if any(shift for _, shift in keys) and _MODIFIERS["shift"] not in names:
            # Shift goes down after the other modifiers, before the key.
            names.insert(len(names) - 1, _MODIFIERS["shift"])
        return names

    def send_combo(self, combo: str) -> bool:
        """
        Press an xdotool-style combo. Raises UinputUnavailable; returns False
        for a key it doesn't know.
        """
        keys = parse_combo(combo)
        if keys is None:
            logger.error("Key combination '%s' has a key the uinput keyboard doesn't know",
                         combo)
            return False
        with self._lock:
            device = self._open()
            self._tap(device, self._with_shift(keys))
        return True

    def type_text(self, text: str) -> bool:
        """
        Type *text*. Raises UinputUnavailable; returns False, typing nothing,
        if it has a character the US layout can't type.
        """
        missing = unsupported_chars(text)
        if missing:
            logger.error("TYPE_TEXT can't type %r on the uinput keyboard (US layout only)",
                         missing)
            return False
        with self._lock:
            device = self._open()
            for char in text:
                key = _lookup_keysym(_CHARS.get(char, char))
                self._tap(device, self._with_shift([key]))
        return True

    def close(self) -> None:
        """Remove the device."""
        with self._lock:
            if self._device is not None:
                try:
                    self._device.close()
                except Exception:  # pylint: disable=broad-exception-caught
                    pass
                self._device = None
