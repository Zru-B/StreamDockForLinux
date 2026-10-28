"""
The lock-screen slideshow: its settings and its timing loop.
"""

import threading
import time

import pytest

from StreamDock.business_logic.screensaver import (
    Screensaver,
    ScreensaverConfig,
    screensaver_problem,
)


class ListSource:
    """Hands out the given items in turn, then None."""

    def __init__(self, items):
        self.items = list(items)
        self.calls = 0

    def next_image(self):
        self.calls += 1
        return self.items.pop(0) if self.items else None


class Recorder:
    def __init__(self):
        self.shown = []
        self.expired = threading.Event()
        self.first_shown = threading.Event()

    def show(self, saver, image):
        self.shown.append(image)
        self.first_shown.set()

    def expire(self, saver):
        self.expired.set()


def fast_config(**overrides):
    # Below MIN_INTERVAL on purpose: the runner trusts validated settings.
    values = dict(enabled=True, interval=0.02, turn_off_after=0)
    values.update(overrides)
    return ScreensaverConfig(**values)


class TestScreensaverProblem:

    def test_a_complete_section_is_valid(self):
        assert screensaver_problem({'enabled': True, 'source': 'online', 'provider': 'bing',
                                    'interval': 30, 'turn_off_after': 15}) is None

    def test_an_empty_section_is_valid(self):
        assert screensaver_problem({}) is None

    @pytest.mark.parametrize('section, fragment', [
        ([], 'mapping'),
        ({'enabled': 'yes'}, 'enabled'),
        ({'source': 'camera'}, 'source'),
        ({'provider': 'unsplash'}, 'provider'),
        ({'interval': 1}, 'interval'),
        ({'interval': True}, 'interval'),
        ({'turn_off_after': -1}, 'turn_off_after'),
        ({'folder': 42}, 'folder'),
        ({'brightness': 150}, 'brightness'),
        ({'brightness': 'bright'}, 'brightness'),
        ({'enabled': True, 'source': 'folder'}, 'folder is required'),
    ])
    def test_it_names_what_is_wrong(self, section, fragment):
        assert fragment in screensaver_problem(section)

    def test_a_disabled_folder_screensaver_needs_no_folder(self):
        assert screensaver_problem({'enabled': False, 'source': 'folder'}) is None


class TestScreensaverConfig:

    def test_no_section_means_disabled(self):
        assert ScreensaverConfig.from_dict(None).enabled is False

    def test_the_folder_is_resolved(self):
        config = ScreensaverConfig.from_dict({'enabled': True, 'folder': 'pics'},
                                             lambda path: '/base/' + path)
        assert config.folder == '/base/pics'

    def test_brightness_is_optional(self):
        assert ScreensaverConfig.from_dict({'enabled': True}).brightness is None
        assert ScreensaverConfig.from_dict({'brightness': 30}).brightness == 30
        assert screensaver_problem({'brightness': None}) is None

    def test_turn_off_after_is_minutes(self):
        assert ScreensaverConfig(turn_off_after=2).turn_off_seconds == 120
        assert ScreensaverConfig(turn_off_after=0).turn_off_seconds is None


class TestScreensaver:

    def test_it_shows_pictures_in_turn(self):
        recorder = Recorder()
        saver = Screensaver(fast_config(), ListSource(['a', 'b', 'c']),
                            recorder.show, recorder.expire)
        saver.start()
        deadline = time.monotonic() + 2
        while len(recorder.shown) < 3 and time.monotonic() < deadline:
            time.sleep(0.01)
        saver.stop()

        assert recorder.shown[:3] == ['a', 'b', 'c']
        assert not recorder.expired.is_set()

    def test_it_keeps_the_last_picture_when_the_source_runs_dry(self):
        recorder = Recorder()
        saver = Screensaver(fast_config(), ListSource(['a']), recorder.show, recorder.expire)
        saver.start()
        deadline = time.monotonic() + 2
        while len(recorder.shown) < 3 and time.monotonic() < deadline:
            time.sleep(0.01)
        saver.stop()

        assert set(recorder.shown) == {'a'}

    def test_no_picture_at_all_expires_at_once(self):
        """The deck must go dark rather than stay blank-but-lit."""
        recorder = Recorder()
        saver = Screensaver(fast_config(), ListSource([]), recorder.show, recorder.expire)
        saver.start()

        assert recorder.expired.wait(2)
        assert recorder.shown == []

    def test_it_expires_after_turn_off_after(self):
        recorder = Recorder()
        # 0.001 min = 60 ms
        saver = Screensaver(fast_config(interval=10, turn_off_after=0.001),
                            ListSource(['a', 'b']), recorder.show, recorder.expire)
        started = time.monotonic()
        saver.start()

        assert recorder.expired.wait(2)
        # The long interval did not hold the turn-off back.
        assert time.monotonic() - started < 1
        assert recorder.shown == ['a']

    def test_stop_does_not_expire(self):
        """Unlocking ends the slideshow; the unlock path, not expire, restores the deck."""
        recorder = Recorder()
        saver = Screensaver(fast_config(interval=10), ListSource(['a', 'b']),
                            recorder.show, recorder.expire)
        saver.start()
        assert recorder.first_shown.wait(2)

        saver.stop()

        assert saver.stopped
        assert not recorder.expired.wait(0.1)

    def test_a_failing_source_counts_as_no_picture(self):
        class Broken:
            def next_image(self):
                raise RuntimeError("boom")

        recorder = Recorder()
        saver = Screensaver(fast_config(), Broken(), recorder.show, recorder.expire)
        saver.start()

        assert recorder.expired.wait(2)
