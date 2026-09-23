"""
Per-key gesture detection: press, release, double press and long press.

Timers are replaced by FakeTimer so a test decides exactly when each one
expires, and the clock is patched so double-press windows are deterministic.
Events go through _handle_key_event, the part of the read loop that owns the
gesture state.
"""

from unittest.mock import MagicMock, patch

import pytest

from StreamDock.devices.stream_dock import StreamDock

KEY = 15
OTHER_KEY = 3


class FakeTimer:
    """Stands in for threading.Timer; fire() runs the callback on demand."""

    def __init__(self, interval, function):
        self.interval = interval
        self.function = function
        self.cancelled = False
        self.daemon = False

    def start(self):
        pass

    def cancel(self):
        self.cancelled = True

    def fire(self):
        if not self.cancelled:
            self.function()


class ConcreteStreamDock(StreamDock):
    def get_serial_number(self):
        return "TEST-SERIAL"

    def set_key_image(self, key, image):
        pass

    def set_brightness(self, percent):
        pass

    def set_touchscreen_image(self, image):
        pass


@pytest.fixture
def device():
    return ConcreteStreamDock(MagicMock(), {'vendor_id': 1, 'product_id': 2, 'path': 'p'})


@pytest.fixture
def timers():
    created = []

    def factory(interval, function):
        timer = FakeTimer(interval, function)
        created.append(timer)
        return timer

    with patch('StreamDock.devices.stream_dock.threading.Timer', side_effect=factory):
        yield created


@pytest.fixture
def clock():
    with patch('StreamDock.devices.stream_dock.time.time') as mock_time:
        mock_time.return_value = 100.0
        yield mock_time


@pytest.fixture
def calls():
    """Ordered log of every callback that ran, as (name, key)."""
    return []


def recorder(calls, name):
    return lambda device, key: calls.append((name, key))


def register(device, calls, key=KEY, *, press=True, release=True, double=False, long=False):
    device.set_per_key_callback(
        key,
        on_press=recorder(calls, 'press') if press else None,
        on_release=recorder(calls, 'release') if release else None,
        on_double_press=recorder(calls, 'double') if double else None,
        on_long_press=recorder(calls, 'long') if long else None,
    )


def run_queue(device):
    while not device._event_queue.empty():
        func, args = device._event_queue.get()
        func(*args)


def down(device, key=KEY):
    device._handle_key_event(key, True)
    run_queue(device)


def up(device, key=KEY):
    device._handle_key_event(key, False)
    run_queue(device)


def fire(device, timer):
    timer.fire()
    run_queue(device)


class TestLongPressAlone:
    """A key with press, release and long-press actions."""

    def test_holding_runs_only_the_long_press(self, device, timers, calls):
        register(device, calls, long=True)

        down(device)
        assert calls == []
        fire(device, timers[-1])
        assert calls == [('long', KEY)]

        up(device)
        assert calls == [('long', KEY)]

    def test_the_hold_time_is_the_configured_duration(self, device, timers, calls):
        device.long_press_duration = 1.5
        register(device, calls, long=True)

        down(device)

        assert timers[-1].interval == 1.5

    def test_a_tap_runs_press_then_release_at_release_time(self, device, timers, calls):
        register(device, calls, long=True)

        down(device)
        assert calls == []
        up(device)

        assert calls == [('press', KEY), ('release', KEY)]
        assert timers[0].cancelled

    def test_a_tap_queues_press_and_release_as_one_item(self, device, timers, calls):
        # Separate items could be reordered by the worker pool.
        register(device, calls, long=True)

        down(device)
        device._handle_key_event(KEY, False)

        assert device._event_queue.qsize() == 1

    def test_a_timer_that_lost_the_race_to_the_release_does_nothing(self, device, timers, calls):
        # The timer thread can call in after the read thread cancelled it.
        register(device, calls, long=True)

        down(device)
        up(device)
        timers[0].function()
        run_queue(device)

        assert calls == [('press', KEY), ('release', KEY)]

    def test_each_hold_is_judged_on_its_own(self, device, timers, calls):
        register(device, calls, long=True)

        down(device)
        fire(device, timers[-1])
        up(device)
        down(device)
        up(device)

        assert calls == [('long', KEY), ('press', KEY), ('release', KEY)]

    def test_a_long_press_only_key_ignores_a_tap(self, device, timers, calls):
        register(device, calls, press=False, release=False, long=True)

        down(device)
        up(device)

        assert calls == []


class TestLongPressWithDoublePress:
    """All four slots on one key."""

    @pytest.fixture(autouse=True)
    def four_slots(self, device, calls):
        register(device, calls, double=True, long=True)

    def test_a_double_tap_runs_only_the_double_press(self, device, timers, calls, clock):
        down(device)
        clock.return_value = 100.1
        up(device)
        clock.return_value = 100.2
        down(device)
        clock.return_value = 100.3
        up(device)

        for timer in timers:
            fire(device, timer)

        assert calls == [('double', KEY)]

    def test_a_single_tap_waits_out_the_double_press_window(self, device, timers, calls, clock):
        down(device)
        up(device)
        assert calls == []

        tap_timer = timers[-1]
        assert tap_timer.interval == pytest.approx(device.double_press_interval + 0.01)
        fire(device, tap_timer)

        assert calls == [('press', KEY), ('release', KEY)]

    def test_a_tap_right_after_a_hold_is_not_a_double_press(self, device, timers, calls, clock):
        down(device)
        fire(device, timers[-1])
        clock.return_value = 101.0
        up(device)
        clock.return_value = 101.1
        down(device)
        clock.return_value = 101.2
        up(device)
        fire(device, timers[-1])

        assert calls == [('long', KEY), ('press', KEY), ('release', KEY)]

    def test_holding_the_second_press_of_a_double_tap_is_still_a_double(self, device, timers,
                                                                          calls, clock):
        down(device)
        up(device)
        clock.return_value = 100.1
        down(device)
        # No long-press timer is started for the second press
        assert all(t.cancelled or t.interval != device.long_press_duration for t in timers)
        up(device)

        assert calls == [('double', KEY)]


class TestKeysWithoutLongPress:
    """Keys without a long-press action behave as before."""

    def test_press_still_fires_immediately(self, device, timers, calls):
        register(device, calls)

        down(device)
        assert calls == [('press', KEY)]
        up(device)

        assert calls == [('press', KEY), ('release', KEY)]
        assert timers == []

    def test_double_press_setup_still_delays_press_from_the_press(self, device, timers, calls):
        register(device, calls, double=True)

        down(device)

        assert len(timers) == 1
        fire(device, timers[0])
        assert calls == [('press', KEY)]


class TestInterleavedKeys:
    """Delayed callbacks used to read the loop's latest key, not their own."""

    def test_each_delayed_press_fires_for_its_own_key(self, device, timers, calls):
        register(device, calls, KEY, double=True)
        register(device, calls, OTHER_KEY, double=True)

        down(device, KEY)
        down(device, OTHER_KEY)
        first, second = timers

        fire(device, first)
        fire(device, second)

        assert calls == [('press', KEY), ('press', OTHER_KEY)]

    def test_each_long_press_fires_for_its_own_key(self, device, timers, calls):
        register(device, calls, KEY, long=True)
        register(device, calls, OTHER_KEY, long=True)

        down(device, KEY)
        down(device, OTHER_KEY)
        up(device, OTHER_KEY)
        fire(device, timers[0])

        assert calls == [('press', OTHER_KEY), ('release', OTHER_KEY), ('long', KEY)]


class TestClearing:
    """Reload clears callbacks; a pending hold must not fire afterwards."""

    def test_clear_all_callbacks_cancels_a_pending_long_press(self, device, timers, calls):
        register(device, calls, long=True)
        down(device)

        device.clear_all_callbacks()
        fire(device, timers[0])

        assert timers[0].cancelled
        assert calls == []

    def test_clear_key_callback_cancels_a_pending_long_press(self, device, timers, calls):
        register(device, calls, long=True)
        down(device)

        device.clear_key_callback(KEY)
        fire(device, timers[0])

        assert calls == []
        assert KEY not in device.per_key_callbacks

    def test_a_cleared_hold_does_not_swallow_the_next_release(self, device, timers, calls):
        register(device, calls, long=True)
        down(device)
        fire(device, timers[0])

        device.clear_all_callbacks()
        register(device, calls, long=True)
        calls.clear()
        down(device)
        up(device)

        assert calls == [('press', KEY), ('release', KEY)]
