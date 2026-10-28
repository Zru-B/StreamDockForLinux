"""
The orchestrator's lock handling with the screensaver on: the deck stays open
and lit but inert, shows pictures, and goes dark when the slideshow ends.
"""

import threading
import time
from unittest.mock import Mock

import pytest
from PIL import Image

from StreamDock.business_logic import LayoutManager, SystemEvent, SystemEventMonitor
from StreamDock.business_logic.screensaver import ScreensaverConfig
from StreamDock.infrastructure import HardwareInterface, SystemInterface
from StreamDock.infrastructure.window_interface import WindowInterface
from StreamDock.orchestration.device_orchestrator import DeviceOrchestrator


class PictureSource:
    def __init__(self, count=100):
        self.remaining = count

    def next_image(self):
        if self.remaining <= 0:
            return None
        self.remaining -= 1
        return Image.new('RGB', (560, 336), (10, 20, 30))


def wait_for(condition, timeout=2.0):
    deadline = time.monotonic() + timeout
    while not condition():
        if time.monotonic() > deadline:
            return False
        time.sleep(0.01)
    return True


@pytest.fixture
def device():
    device = Mock()
    device._current_brightness = 60
    device.open.return_value = True
    return device


@pytest.fixture
def layout():
    return Mock()


@pytest.fixture
def orchestrator(device, layout):
    system = Mock(spec=SystemInterface)
    system.poll_lock_state.return_value = False
    monitor = Mock(spec=SystemEventMonitor)
    monitor.current_window = None
    manager = Mock(spec=LayoutManager)
    orch = DeviceOrchestrator(
        hardware=Mock(spec=HardwareInterface), system=system,
        window_manager=Mock(spec=WindowInterface), registry=None,
        event_monitor=monitor, layout_manager=manager)
    orch.register_layout('Main', layout)
    orch.attach_device('device_0', device, current_layout='Main')
    yield orch
    orch._stop_screensaver()


def enable(orch, source=None, **overrides):
    values = dict(enabled=True, interval=0.05, turn_off_after=0)
    values.update(overrides)
    orch.set_screensaver(ScreensaverConfig(**values), source or PictureSource())


class TestLockWithScreensaver:

    def test_the_device_stays_open_but_inert(self, orchestrator, device):
        enable(orchestrator)

        orchestrator._on_lock(SystemEvent.LOCK)

        device.suspend_input.assert_called_once()
        device.close.assert_not_called()
        device.screen_off.assert_not_called()
        assert orchestrator.is_locked()

    def test_the_layout_is_blanked_before_any_picture(self, orchestrator, device):
        # A slow first download must not leave the layout readable on a
        # locked computer.
        enable(orchestrator, source=Mock(next_image=Mock(side_effect=lambda: time.sleep(5))))

        orchestrator._on_lock(SystemEvent.LOCK)

        device.clear_all_icons.assert_called_once()

    def test_each_picture_fills_all_fifteen_keys(self, orchestrator, device):
        enable(orchestrator)

        orchestrator._on_lock(SystemEvent.LOCK)

        assert wait_for(lambda: device.set_key_pil_image.call_count >= 15)
        keys = [c.args[0] for c in device.set_key_pil_image.call_args_list[:15]]
        assert keys == list(range(1, 16))
        assert {c.args[1].size for c in device.set_key_pil_image.call_args_list[:15]} \
            == {(112, 112)}

    def test_unlock_restores_without_reopening(self, orchestrator, device, layout):
        enable(orchestrator)
        orchestrator._on_lock(SystemEvent.LOCK)
        assert wait_for(lambda: device.set_key_pil_image.called)

        orchestrator._on_unlock(SystemEvent.UNLOCK)

        device.open.assert_not_called()
        device.resume_input.assert_called()
        device.init.assert_called_once_with(60)
        layout.apply.assert_called()
        assert not orchestrator.is_locked()

    def test_no_picture_lands_after_unlock(self, orchestrator, device):
        enable(orchestrator)
        orchestrator._on_lock(SystemEvent.LOCK)
        assert wait_for(lambda: device.set_key_pil_image.called)

        orchestrator._on_unlock(SystemEvent.UNLOCK)
        drawn = device.set_key_pil_image.call_count
        time.sleep(0.2)

        assert device.set_key_pil_image.call_count == drawn

    def test_turn_off_after_closes_the_device(self, orchestrator, device):
        enable(orchestrator, interval=10, turn_off_after=0.001)

        orchestrator._on_lock(SystemEvent.LOCK)

        assert wait_for(lambda: device.close.called)
        device.screen_off.assert_called_once()

    def test_unlock_after_turn_off_reopens_and_resumes_input(self, orchestrator, device):
        enable(orchestrator, interval=10, turn_off_after=0.001)
        orchestrator._on_lock(SystemEvent.LOCK)
        assert wait_for(lambda: device.close.called)

        orchestrator._on_unlock(SystemEvent.UNLOCK)

        device.open.assert_called_once()
        device.resume_input.assert_called()

    def test_no_pictures_turns_the_device_off(self, orchestrator, device):
        enable(orchestrator, source=PictureSource(count=0))

        orchestrator._on_lock(SystemEvent.LOCK)

        assert wait_for(lambda: device.close.called)

    def test_a_repeated_lock_after_turn_off_stays_dark(self, orchestrator, device):
        enable(orchestrator, interval=10, turn_off_after=0.001)
        orchestrator._on_lock(SystemEvent.LOCK)
        assert wait_for(lambda: device.close.called)

        orchestrator._on_lock(SystemEvent.LOCK)

        device.suspend_input.assert_called_once()

    def test_its_own_brightness_is_used_and_undone_on_unlock(self, orchestrator, device):
        enable(orchestrator, brightness=25)

        orchestrator._on_lock(SystemEvent.LOCK)
        device.set_brightness.assert_called_once_with(25)

        orchestrator._on_unlock(SystemEvent.UNLOCK)
        # The brightness the deck had before the lock, not the screensaver's.
        device.init.assert_called_once_with(60)
        assert device.set_brightness.call_args_list[-1].args == (60,)

    def test_without_its_own_brightness_it_is_left_alone(self, orchestrator, device):
        enable(orchestrator)

        orchestrator._on_lock(SystemEvent.LOCK)

        device.set_brightness.assert_not_called()

    def test_disabled_screensaver_turns_off_as_before(self, orchestrator, device):
        orchestrator.set_screensaver(ScreensaverConfig(enabled=False), PictureSource())

        orchestrator._on_lock(SystemEvent.LOCK)

        device.screen_off.assert_called_once()
        device.close.assert_called_once()
        device.suspend_input.assert_not_called()

    def test_stop_ends_the_slideshow(self, orchestrator, device):
        enable(orchestrator)
        orchestrator._on_lock(SystemEvent.LOCK)
        assert wait_for(lambda: device.set_key_pil_image.called)

        orchestrator.stop(release_devices=False)
        drawn = device.set_key_pil_image.call_count
        time.sleep(0.2)

        assert device.set_key_pil_image.call_count == drawn

    def test_unlock_does_not_wait_for_a_slow_download(self, orchestrator, device):
        release = threading.Event()

        class Slow:
            first = True

            def next_image(self):
                if self.first:
                    self.first = False
                    return Image.new('RGB', (10, 10))
                release.wait(5)
                return None

        enable(orchestrator, source=Slow())
        orchestrator._on_lock(SystemEvent.LOCK)
        assert wait_for(lambda: device.set_key_pil_image.called)

        started = time.monotonic()
        orchestrator._on_unlock(SystemEvent.UNLOCK)
        release.set()

        assert time.monotonic() - started < 2
