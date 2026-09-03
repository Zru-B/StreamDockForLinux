"""
Unit tests for DeviceWatcher.

Removing the udev auto-start left nothing noticing a replug, so this is what
keeps the application usable across an unplug.
"""

import threading
import time
from unittest.mock import Mock, patch

import pytest

from StreamDock.application.device_watcher import DeviceWatcher


def make_device(path, serial=''):
    return Mock(vendor_id=0x6603, product_id=0x1006, serial_number=serial,
                path=path, manufacturer='Test', product='StreamDock')


@pytest.fixture
def scans():
    """Successive results discover_devices() should return."""
    return []


@pytest.fixture
def watcher(scans):
    """A watcher in polling mode, driven by refresh() rather than a thread."""
    def fake_discover(_hardware=None):
        return scans.pop(0) if scans else []

    with patch('StreamDock.application.device_watcher.discover_devices',
               side_effect=fake_discover):
        yield DeviceWatcher


class TestChangeDetection:
    """The watcher reports only real changes."""

    def build(self, scans, on_changed):
        def fake_discover(_hardware=None):
            return scans.pop(0) if scans else scans_last[0]
        scans_last = [[]]

        def discover(_hardware=None):
            if scans:
                scans_last[0] = scans.pop(0)
            return scans_last[0]

        patcher = patch('StreamDock.application.device_watcher.discover_devices',
                        side_effect=discover)
        patcher.start()
        watcher = DeviceWatcher(on_changed)
        return watcher, patcher

    def test_an_unchanged_set_is_not_reported(self):
        device = make_device('/dev/hidraw0')
        seen = []
        watcher, patcher = self.build([[device], [device]], seen.append)
        try:
            watcher._devices = [device]
            watcher._keys = {'6603:1006@/dev/hidraw0'}
            watcher._running = True
            watcher.refresh()
        finally:
            patcher.stop()

        assert seen == []

    def test_a_new_device_is_reported(self):
        first, second = make_device('/dev/hidraw0'), make_device('/dev/hidraw1')
        seen = []
        watcher, patcher = self.build([[first, second]], seen.append)
        try:
            watcher._devices = [first]
            watcher._keys = {'6603:1006@/dev/hidraw0'}
            watcher._running = True
            watcher.refresh()
        finally:
            patcher.stop()

        assert len(seen) == 1
        assert len(seen[0]) == 2

    def test_a_removed_device_is_reported(self):
        device = make_device('/dev/hidraw0')
        seen = []
        watcher, patcher = self.build([[]], seen.append)
        try:
            watcher._devices = [device]
            watcher._keys = {'6603:1006@/dev/hidraw0'}
            watcher._running = True
            watcher.refresh()
        finally:
            patcher.stop()

        assert seen == [[]]

    def test_a_raising_handler_does_not_kill_the_watcher(self):
        def boom(_devices):
            raise RuntimeError("handler exploded")

        watcher, patcher = self.build([[make_device('/dev/hidraw0')]], boom)
        try:
            watcher._running = True
            watcher.refresh()
        finally:
            patcher.stop()

    def test_enumeration_failure_is_survived(self):
        seen = []
        with patch('StreamDock.application.device_watcher.discover_devices',
                   side_effect=OSError("usb exploded")):
            watcher = DeviceWatcher(seen.append)
            watcher._devices = [make_device('/dev/hidraw0')]
            watcher._keys = {'6603:1006@/dev/hidraw0'}
            watcher._running = True
            watcher.refresh()

        # An empty scan still counts as "everything went away".
        assert seen == [[]]


class TestLifecycle:
    """start()/stop()."""

    def test_start_seeds_without_reporting(self):
        seen = []
        with patch('StreamDock.application.device_watcher.discover_devices',
                   return_value=[make_device('/dev/hidraw0')]):
            watcher = DeviceWatcher(seen.append)
            watcher.start()
            try:
                assert len(watcher.devices()) == 1
                assert seen == []
            finally:
                watcher.stop()

    def test_stop_is_safe_before_start(self):
        DeviceWatcher(lambda devices: None).stop()

    def test_polling_is_used_when_pyudev_is_missing(self):
        seen = []
        real_import = __builtins__['__import__'] if isinstance(__builtins__, dict) \
            else __builtins__.__import__

        def no_pyudev(name, *args, **kwargs):
            if name == 'pyudev':
                raise ImportError("no pyudev")
            return real_import(name, *args, **kwargs)

        with patch('StreamDock.application.device_watcher.discover_devices',
                   return_value=[]), \
             patch('builtins.__import__', side_effect=no_pyudev):
            watcher = DeviceWatcher(seen.append, poll_interval=0.1)
            using_udev = watcher.start()
            try:
                assert using_udev is False
            finally:
                watcher.stop()

    def test_polling_notices_a_change(self):
        seen = []
        results = [[], [make_device('/dev/hidraw0')]]
        done = threading.Event()

        def discover(_hardware=None):
            return results[0] if len(results) == 1 else results.pop(0)

        def on_changed(devices):
            seen.append(devices)
            done.set()

        real_import = __builtins__['__import__'] if isinstance(__builtins__, dict) \
            else __builtins__.__import__

        def no_pyudev(name, *args, **kwargs):
            if name == 'pyudev':
                raise ImportError("no pyudev")
            return real_import(name, *args, **kwargs)

        with patch('StreamDock.application.device_watcher.discover_devices',
                   side_effect=discover), \
             patch('builtins.__import__', side_effect=no_pyudev):
            watcher = DeviceWatcher(on_changed, poll_interval=0.1)
            watcher.start()
            try:
                assert done.wait(timeout=10), "polling never reported the change"
            finally:
                watcher.stop()

        assert len(seen[0]) == 1
