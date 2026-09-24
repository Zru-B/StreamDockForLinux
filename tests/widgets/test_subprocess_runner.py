"""Third-party widgets in a child process: protocol, crashes, hangs."""

import os
import threading
import time

from StreamDock.widgets.registry import WidgetSpec
from StreamDock.widgets.runners import SubprocessRunner, render_in_subprocess

FIXTURES = os.path.join(os.path.dirname(__file__), 'fixtures')


def spec(name, widget_id):
    return WidgetSpec(manifest={'id': widget_id}, builtin=False,
                      script_path=os.path.join(FIXTURES, name), folder=FIXTURES)


class Collector:
    def __init__(self):
        self.frames = []
        self.errors = []
        self.states = []
        self.badges = []
        self.changed = threading.Condition()

    def frame(self, image):
        with self.changed:
            self.frames.append(image)
            self.changed.notify_all()

    def error(self, message):
        with self.changed:
            self.errors.append(message)
            self.changed.notify_all()

    def state(self, value):
        with self.changed:
            self.states.append(value)
            self.changed.notify_all()

    def badge(self, value):
        with self.changed:
            self.badges.append(value)
            self.changed.notify_all()

    def wait_for(self, predicate, timeout=10):
        with self.changed:
            return self.changed.wait_for(predicate, timeout)


def test_events_reach_the_child_and_frames_come_back():
    collected = Collector()
    runner = SubprocessRunner(spec('good.py', 'fixture_good'), {'label': 'n', 'start': 0}, (112, 112),
                              collected.frame, collected.error)
    runner.start()
    try:
        assert collected.wait_for(lambda: collected.frames)
        runner.post_event('press')
        assert collected.wait_for(lambda: len(collected.frames) >= 2)
    finally:
        runner.stop()
    assert collected.errors == []
    assert collected.frames[-1].size == (112, 112)


def test_stray_prints_do_not_corrupt_frames():
    collected = Collector()
    runner = SubprocessRunner(spec('printing.py', 'fixture_printing'), {}, (112, 112),
                              collected.frame, collected.error)
    runner.start()
    try:
        assert collected.wait_for(lambda: collected.frames)
    finally:
        runner.stop()
    assert collected.errors == []


def test_crashing_widget_restarts_then_gives_up(monkeypatch):
    # Guards against a broken widget respawning forever.
    monkeypatch.setattr(SubprocessRunner, 'MAX_CRASHES', 3)
    monkeypatch.setattr(SubprocessRunner, 'BACKOFF_CAP', 0.05)
    collected = Collector()
    runner = SubprocessRunner(spec('crashing.py', 'fixture_crashing'), {}, (112, 112),
                              collected.frame, collected.error)
    runner.start()
    try:
        assert collected.wait_for(lambda: 'stopped after repeated crashes' in collected.errors, timeout=20)
    finally:
        runner.stop()
    assert runner.crashes == 3


def test_child_that_never_says_ready_is_killed(monkeypatch):
    monkeypatch.setattr(SubprocessRunner, 'READY_TIMEOUT', 0.5)
    monkeypatch.setattr(SubprocessRunner, 'MAX_CRASHES', 1)
    collected = Collector()
    runner = SubprocessRunner(spec('hang_import.py', 'fixture_hang'), {}, (112, 112),
                              collected.frame, collected.error)
    started = time.monotonic()
    runner.start()
    try:
        assert collected.wait_for(lambda: 'did not start in time' in collected.errors, timeout=10)
    finally:
        runner.stop()
    assert time.monotonic() - started < 10


def test_render_once_returns_manifest_and_frame():
    snapshot = render_in_subprocess(os.path.join(FIXTURES, 'good.py'), {'label': 'x', 'start': 2})
    assert snapshot.manifest['id'] == 'fixture_good'
    assert snapshot.frame.size == (112, 112)


def test_state_and_badge_cross_the_process_boundary():
    collected = Collector()
    runner = SubprocessRunner(spec('stateful.py', 'fixture_stateful'), {}, (112, 112),
                              collected.frame, collected.error, on_state=collected.state,
                              on_badge=collected.badge, draw_frames=False)
    runner.start()
    try:
        assert collected.wait_for(lambda: collected.states == ['on'] and collected.badges == ['5'])
        runner.show()
        runner.post_event('press')
        assert collected.wait_for(lambda: collected.states == ['on', 'off'])
        assert collected.wait_for(lambda: collected.badges == ['5', None])
        runner.post_focus('slack', 'general')
        assert collected.wait_for(lambda: collected.badges == ['5', None, 'sla'])
    finally:
        runner.stop()
    assert collected.frames == []


def test_render_once_reports_state_and_badge():
    snapshot = render_in_subprocess(os.path.join(FIXTURES, 'stateful.py'), {})
    assert (snapshot.state, snapshot.badge) == ('on', '5')
