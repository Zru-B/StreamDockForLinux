"""Third-party widgets in a child process: protocol, crashes, hangs."""

import base64
import importlib.util
import logging
import os
import py_compile
import struct
import sys
import threading
import time
import zlib

import pytest

from StreamDock.widgets import runners
from StreamDock.widgets.registry import CHANGED_PROBLEM, WidgetSpec, file_digests
from StreamDock.widgets.runners import SubprocessRunner, WidgetProcessError, decode_frame, render_in_subprocess

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


WIDGET = """import sys
from streamdock_sdk import Widget, draw
{top}

class W(Widget):
    id = 'fixture_tmp'
    name = 'W'
    version = '1'

    def setup(self, ctx):
{setup}

    def render(self, ctx):
        return draw.text_key('x', size=ctx.size)
"""


def write_widget(folder, top='', setup='pass'):
    path = folder / 'widget.py'
    path.write_text(WIDGET.format(top=top, setup='        ' + setup))
    return str(path)


def tmp_spec(folder, files=None):
    return WidgetSpec(manifest={'id': 'fixture_tmp'}, builtin=False,
                      script_path=str(folder / 'widget.py'), folder=str(folder), files=files)


def fake_child(monkeypatch, tmp_path, body):
    """Replace the widget host with a script that speaks the protocol as ``body`` says."""
    script = tmp_path / 'child.py'
    script.write_text('import json, sys, time\n' + body)
    monkeypatch.setattr(runners, '_child_command', lambda _path: [sys.executable, str(script)])


def png(width, height):
    def chunk(kind, data):
        return struct.pack('>I', len(data)) + kind + data + struct.pack('>I', zlib.crc32(kind + data))
    header = struct.pack('>IIBBBBB', width, height, 8, 2, 0, 0, 0)
    return b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', header) + chunk(b'IEND', b'')


def test_modified_files_are_refused_before_spawning(tmp_path):
    # The registry's hash check is only as fresh as its last refresh; each spawn re-checks.
    write_widget(tmp_path)
    files = file_digests(str(tmp_path))
    (tmp_path / 'widget.py').write_text('raise SystemExit(1)\n')
    collected = Collector()
    runner = SubprocessRunner(tmp_spec(tmp_path, files), {}, (112, 112), collected.frame, collected.error)
    runner.start()
    try:
        assert collected.wait_for(lambda: CHANGED_PROBLEM in collected.errors)
    finally:
        runner.stop()
    assert collected.frames == []


def test_approved_files_run(tmp_path):
    write_widget(tmp_path)
    collected = Collector()
    runner = SubprocessRunner(tmp_spec(tmp_path, file_digests(str(tmp_path))), {}, (112, 112),
                              collected.frame, collected.error)
    runner.start()
    try:
        assert collected.wait_for(lambda: collected.frames)
    finally:
        runner.stop()
    assert not os.path.exists(tmp_path / '__pycache__')


def test_bytecode_next_to_the_source_is_never_used(tmp_path):
    # A .pyc planted in the widget folder would run instead of the hashed source.
    write_widget(tmp_path, top='import helper\nassert helper.VALUE == "god", helper.VALUE\n')
    helper = tmp_path / 'helper.py'
    helper.write_text('VALUE = "bad"\n')
    py_compile.compile(str(helper), cfile=importlib.util.cache_from_source(str(helper)))
    stamp = os.stat(helper).st_mtime_ns
    helper.write_text('VALUE = "god"\n')
    os.utime(helper, ns=(stamp, stamp))

    render_in_subprocess(str(tmp_path / 'widget.py'), {})


def test_non_object_messages_are_ignored(monkeypatch, tmp_path):
    # A bare JSON list used to raise in the reader and leave the supervisor waiting forever.
    fake_child(monkeypatch, tmp_path, f"""
print('[1]', flush=True)
print('"text"', flush=True)
print(json.dumps({{'op': 'ready', 'manifest': {{}}}}), flush=True)
sys.stdin.readline()
print(json.dumps({{'op': 'state', 'state': 'up'}}), flush=True)
time.sleep(30)
""")
    collected = Collector()
    runner = SubprocessRunner(spec('good.py', 'fixture_fake'), {}, (112, 112), collected.frame,
                              collected.error, on_state=collected.state)
    runner.start()
    try:
        assert collected.wait_for(lambda: collected.states == ['up'])
    finally:
        runner.stop()
    assert collected.errors == []


def test_a_failing_callback_kills_the_child_and_counts_as_a_crash(monkeypatch, tmp_path):
    monkeypatch.setattr(SubprocessRunner, 'MAX_CRASHES', 1)
    fake_child(monkeypatch, tmp_path, f"""
print(json.dumps({{'op': 'ready', 'manifest': {{}}}}), flush=True)
print(json.dumps({{'op': 'state', 'state': 'boom'}}), flush=True)
time.sleep(60)
""")
    collected = Collector()

    def state(value):
        raise RuntimeError('callback broke')

    runner = SubprocessRunner(spec('good.py', 'fixture_fake'), {}, (112, 112), collected.frame,
                              collected.error, on_state=state)
    started = time.monotonic()
    runner.start()
    try:
        assert collected.wait_for(lambda: 'stopped after repeated crashes' in collected.errors, timeout=10)
    finally:
        runner.stop()
    assert any('callback broke' in error for error in collected.errors)
    assert time.monotonic() - started < 10


def test_oversized_frames_are_refused_before_decoding():
    # Under PIL's bomb limit, so only the header size check stops a 300 MB decode.
    with pytest.raises(ValueError, match='9000x9000'):
        decode_frame(base64.b64encode(png(9000, 9000)).decode(), (112, 112))


def test_a_bad_frame_is_an_error_not_a_crash(monkeypatch, tmp_path):
    payload = base64.b64encode(png(20000, 20000)).decode()
    fake_child(monkeypatch, tmp_path, f"""
print(json.dumps({{'op': 'ready', 'manifest': {{}}}}), flush=True)
print(json.dumps({{'op': 'frame', 'png': {payload!r}}}), flush=True)
time.sleep(30)
""")
    collected = Collector()
    runner = SubprocessRunner(spec('good.py', 'fixture_fake'), {}, (112, 112), collected.frame, collected.error)
    runner.start()
    try:
        assert collected.wait_for(lambda: collected.errors)
    finally:
        runner.stop()
    # PIL's DecompressionBombError is not an OSError/ValueError and used to escape the reader.
    assert len(collected.errors) == 1 and collected.errors[0].startswith('bad frame:')


def test_invalid_utf8_and_long_lines_on_stderr_are_survived(tmp_path, caplog):
    write_widget(tmp_path, setup="sys.stderr.buffer.write(b'\\xff bad\\n' + b'y' * 10000 + b'\\nafter-marker\\n'); "
                                 "sys.stderr.flush()")
    collected = Collector()
    with caplog.at_level(logging.INFO, logger='StreamDock.widgets.runners'):
        runner = SubprocessRunner(tmp_spec(tmp_path), {}, (112, 112), collected.frame, collected.error)
        runner.start()
        try:
            assert collected.wait_for(lambda: collected.frames)
            deadline = time.monotonic() + 5
            while 'after-marker' not in caplog.text and time.monotonic() < deadline:
                time.sleep(0.05)
        finally:
            runner.stop()
    assert 'after-marker' in caplog.text
    assert max(len(record.getMessage()) for record in caplog.records) < 2100


def test_render_once_survives_invalid_utf8_on_stderr(tmp_path):
    path = write_widget(tmp_path, setup="sys.stderr.buffer.write(b'\\xff\\xfe\\n'); sys.stderr.flush()")
    assert render_in_subprocess(path, {}).frame.size == (112, 112)


def test_render_once_rejects_non_object_output(monkeypatch, tmp_path):
    fake_child(monkeypatch, tmp_path, "print('[1]', flush=True)\n")
    with pytest.raises(WidgetProcessError):
        render_in_subprocess(str(tmp_path / 'x.py'), {})


def test_a_start_error_is_reported_once(monkeypatch, tmp_path):
    # An import error before 'ready' was also reported as "did not start in time".
    monkeypatch.setattr(SubprocessRunner, 'MAX_CRASHES', 1)
    fake_child(monkeypatch, tmp_path, f"""
print(json.dumps({{'op': 'error', 'message': 'ImportError: no module named foo'}}), flush=True)
time.sleep(30)
""")
    collected = Collector()
    runner = SubprocessRunner(spec('good.py', 'fixture_fake'), {}, (112, 112), collected.frame, collected.error)
    runner.start()
    try:
        assert collected.wait_for(lambda: 'stopped after repeated crashes' in collected.errors, timeout=10)
    finally:
        runner.stop()
    assert 'did not start in time' not in collected.errors
    assert collected.errors[0] == 'ImportError: no module named foo'


def test_a_chatty_widget_is_rate_limited_in_the_log(tmp_path, caplog):
    write_widget(tmp_path, setup="[print('spam', i, file=sys.stderr) for i in range(500)]; "
                                 "print('end-marker', file=sys.stderr); sys.stderr.flush()")
    collected = Collector()
    with caplog.at_level(logging.INFO, logger='StreamDock.widgets.runners'):
        runner = SubprocessRunner(tmp_spec(tmp_path), {}, (112, 112), collected.frame, collected.error)
        runner.start()
        try:
            assert collected.wait_for(lambda: collected.frames)
        finally:
            runner.stop()
        deadline = time.monotonic() + 5
        while 'suppressed' not in caplog.text and time.monotonic() < deadline:
            time.sleep(0.05)
    spam = [record for record in caplog.records if 'spam' in record.getMessage()]
    assert len(spam) == runners.LOG_BURST
    assert 'suppressed 451 more lines' in caplog.text


def test_render_once_runs_in_the_widget_folder(tmp_path):
    # A preview used to run in the app's working directory, unlike the device.
    path = write_widget(tmp_path, top="import os\nassert os.getcwd() == os.path.dirname(os.path.abspath(__file__))\n")
    assert render_in_subprocess(path, {}).frame.size == (112, 112)
