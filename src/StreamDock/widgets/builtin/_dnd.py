"""
Do Not Disturb on the desktops and notification daemons Linux commonly runs.

Every backend answers ``read()`` with True (notifications silenced), False,
or None when it can't tell, and ``write(on)`` turns Do Not Disturb on or off.

- **KDE Plasma** has no command-line switch, so the app asks the notification
  server to hold notifications back (``org.freedesktop.Notifications.Inhibit``)
  and keeps the D-Bus connection open for as long as that should last. Plasma
  shows it as Do Not Disturb in the tray. It ends when the app quits.
- **GNOME** turns off notification banners (``show-banners``), which is what
  its own Do Not Disturb switch does.
- **XFCE**, **dunst** and **SwayNotificationCenter** have their own switches.
"""

import logging
import os
import shutil
import subprocess
import threading
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

BACKENDS = ('auto', 'kde', 'gnome', 'xfce', 'dunst', 'swaync')


def _run(*command: str) -> Optional[str]:
    """The command's stripped output, or None if it's missing or failed."""
    try:
        result = subprocess.run(list(command), capture_output=True, text=True, timeout=3, check=False)
    except (OSError, subprocess.TimeoutExpired):
        return None
    return result.stdout.strip() if result.returncode == 0 else None


def _boolean(text: Optional[str]) -> Optional[bool]:
    if text is None:
        return None
    word = text.strip().lower()
    return True if word == 'true' else False if word == 'false' else None


class CommandBackend:
    """A backend driven by a command that prints true/false and commands that set it."""

    read_command: List[str] = []
    on_command: List[str] = []
    off_command: List[str] = []
    # True when the command reports notifications shown, the opposite of DND.
    inverted = False

    def read(self) -> Optional[bool]:
        value = _boolean(_run(*self.read_command))
        return None if value is None else value != self.inverted

    def write(self, on: bool) -> None:
        _run(*(self.on_command if on else self.off_command))


class GnomeBackend(CommandBackend):
    read_command = ['gsettings', 'get', 'org.gnome.desktop.notifications', 'show-banners']
    on_command = ['gsettings', 'set', 'org.gnome.desktop.notifications', 'show-banners', 'false']
    off_command = ['gsettings', 'set', 'org.gnome.desktop.notifications', 'show-banners', 'true']
    inverted = True


class XfceBackend(CommandBackend):
    read_command = ['xfconf-query', '-c', 'xfce4-notifyd', '-p', '/do-not-disturb']
    on_command = ['xfconf-query', '-c', 'xfce4-notifyd', '-p', '/do-not-disturb', '-n', '-t', 'bool', '-s', 'true']
    off_command = ['xfconf-query', '-c', 'xfce4-notifyd', '-p', '/do-not-disturb', '-n', '-t', 'bool', '-s', 'false']

    def read(self) -> Optional[bool]:
        # The property doesn't exist until DND was first switched on.
        if shutil.which('xfconf-query') is None:
            return None
        value = super().read()
        return False if value is None else value


class DunstBackend(CommandBackend):
    read_command = ['dunstctl', 'is-paused']
    on_command = ['dunstctl', 'set-paused', 'true']
    off_command = ['dunstctl', 'set-paused', 'false']


class SwayncBackend(CommandBackend):
    read_command = ['swaync-client', '--get-dnd', '--skip-wait']
    on_command = ['swaync-client', '--dnd-on', '--skip-wait']
    off_command = ['swaync-client', '--dnd-off', '--skip-wait']


class KdeBackend:
    """
    Holds a notification inhibition on a private session-bus connection.

    Plasma lifts an inhibition when the connection that asked for it closes,
    so the connection stays open, shared by every key using this backend.
    """

    SERVICE = 'org.freedesktop.Notifications'
    PATH = '/org/freedesktop/Notifications'

    def __init__(self):
        self._lock = threading.Lock()
        self._bus = None
        self._cookie: Optional[int] = None

    def _interface(self):
        import dbus  # pylint: disable=import-outside-toplevel
        if self._bus is None:
            self._bus = dbus.bus.BusConnection(dbus.bus.BUS_SESSION)
        return dbus, self._bus.get_object(self.SERVICE, self.PATH)

    def read(self) -> Optional[bool]:
        with self._lock:
            if self._cookie is not None:
                return True
            try:
                dbus, proxy = self._interface()
                return bool(proxy.Get(self.SERVICE, 'Inhibited', dbus_interface='org.freedesktop.DBus.Properties'))
            except ImportError:
                logger.warning('dbus-python is not installed; Do Not Disturb is unavailable on KDE')
                return None
            except Exception:  # pylint: disable=broad-exception-caught
                logger.debug('cannot read the notification inhibition', exc_info=True)
                return None

    def write(self, on: bool) -> None:
        with self._lock:
            try:
                dbus, proxy = self._interface()
                interface = dbus.Interface(proxy, self.SERVICE)
                if on and self._cookie is None:
                    self._cookie = int(interface.Inhibit('streamdock', 'Do Not Disturb key',
                                                         dbus.Dictionary({}, signature='sv')))
                elif not on and self._cookie is not None:
                    interface.UnInhibit(dbus.UInt32(self._cookie))
                    self._cookie = None
            except ImportError:
                logger.warning('dbus-python is not installed; Do Not Disturb is unavailable on KDE')
            except Exception:  # pylint: disable=broad-exception-caught
                logger.warning('cannot change the notification inhibition', exc_info=True)


_BACKENDS: Dict[str, object] = {
    'kde': KdeBackend(),
    'gnome': GnomeBackend(),
    'xfce': XfceBackend(),
    'dunst': DunstBackend(),
    'swaync': SwayncBackend(),
}


def detect(desktop: Optional[str] = None) -> Optional[str]:
    """The backend for this session: by desktop first, then by a running notification daemon."""
    desktop = (os.environ.get('XDG_CURRENT_DESKTOP', '') if desktop is None else desktop).lower()
    names = desktop.split(':')
    if 'kde' in names:
        return 'kde'
    if 'gnome' in names or 'unity' in names:
        return 'gnome'
    if 'xfce' in names:
        return 'xfce'
    for name in ('swaync', 'dunst'):
        if _BACKENDS[name].read() is not None:
            return name
    return None


def backend(name: str):
    """The backend called ``name``; 'auto' detects it. None when there's none to use."""
    if name == 'auto':
        name = detect()
    return _BACKENDS.get(name) if name else None
