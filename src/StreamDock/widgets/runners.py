"""
Run a widget: in the app's process (built-ins) or in a child process (third-party).

Both runners take the same calls and report frames and errors through the
same callbacks, so the host doesn't care which one it holds.
"""

import base64
import io
import json
import logging
import os
import subprocess
import sys
import threading
import time
from dataclasses import dataclass
from typing import Any, Callable, Dict, Mapping, Optional, Tuple

from PIL import Image

import streamdock_sdk
from streamdock_sdk.scheduler import WidgetDriver, check_frame
from StreamDock.widgets.registry import WidgetSpec

logger = logging.getLogger(__name__)

FrameCallback = Callable[[Image.Image], None]
ErrorCallback = Callable[[str], None]
TextCallback = Callable[[Optional[str]], None]


def _ignore(_value) -> None:
    pass


class WidgetRunner:
    """Common interface; see InProcessRunner and SubprocessRunner."""

    def start(self) -> None:
        raise NotImplementedError

    def stop(self) -> None:
        raise NotImplementedError

    def post_event(self, name: str) -> None:
        raise NotImplementedError

    def post_focus(self, app: str, title: str) -> None:
        raise NotImplementedError

    def show(self) -> None:
        raise NotImplementedError

    def hide(self) -> None:
        raise NotImplementedError


class InProcessRunner(WidgetRunner):
    def __init__(self, spec: WidgetSpec, options: Mapping[str, Any], size: Tuple[int, int],
                 on_frame: FrameCallback, on_error: ErrorCallback, data_dir: Optional[str] = None,
                 on_state: TextCallback = _ignore, on_badge: TextCallback = _ignore, draw_frames: bool = True):
        self._driver = WidgetDriver(spec.widget_cls, options, size, on_frame, on_error, data_dir,
                                    on_state=on_state, on_badge=on_badge, draw_frames=draw_frames)

    def start(self) -> None:
        self._driver.start()

    def stop(self) -> None:
        self._driver.stop()

    def post_event(self, name: str) -> None:
        self._driver.post_event(name)

    def post_focus(self, app: str, title: str) -> None:
        self._driver.post_focus(app, title)

    def show(self) -> None:
        self._driver.show()

    def hide(self) -> None:
        self._driver.hide()


def _child_command(script_path: str):
    return [sys.executable, '-m', 'streamdock_sdk.host', script_path]


def _child_env() -> Dict[str, str]:
    """The child imports the SDK from wherever this process found it, installed or not."""
    env = dict(os.environ)
    src = os.path.dirname(os.path.dirname(os.path.abspath(streamdock_sdk.__file__)))
    env['PYTHONPATH'] = os.pathsep.join(filter(None, [src, env.get('PYTHONPATH')]))
    env['PYTHONUNBUFFERED'] = '1'
    return env


def decode_frame(payload: str, size: Tuple[int, int]) -> Image.Image:
    image = Image.open(io.BytesIO(base64.b64decode(payload)))
    image.load()
    return check_frame(image, size)


class WidgetProcessError(RuntimeError):
    """A widget child process failed, hung or said something unexpected."""


@dataclass
class Snapshot:
    """One frame of a widget, with the state and badge it reported while drawing it."""

    manifest: Dict[str, Any]
    frame: Image.Image
    state: Optional[str] = None
    badge: Optional[str] = None


def render_in_subprocess(script_path: str, options: Mapping[str, Any], size: Tuple[int, int] = (112, 112),
                         timeout: float = 5.0) -> Snapshot:
    """
    Import the script in a throwaway child, draw one frame and exit.

    Used for validation and for editor previews, where nothing of the widget
    should stay running.
    """
    commands = ''.join(json.dumps(message) + '\n' for message in (
        {'op': 'render_once', 'options': dict(options), 'size': list(size)},
        {'op': 'stop'},
    ))
    try:
        result = subprocess.run(_child_command(script_path), input=commands, capture_output=True,
                                text=True, timeout=timeout, env=_child_env(), check=False)
    except subprocess.TimeoutExpired as exc:
        raise WidgetProcessError(f'did not finish within {timeout:g} s') from exc

    manifest = None
    state = badge = None
    for line in result.stdout.splitlines():
        try:
            message = json.loads(line)
        except ValueError as exc:
            raise WidgetProcessError(f'unexpected output: {line[:200]}') from exc
        if message.get('op') == 'ready':
            manifest = message['manifest']
        elif message.get('op') == 'error':
            raise WidgetProcessError(message.get('message', 'unknown error').strip())
        elif message.get('op') == 'state':
            state = message.get('state')
        elif message.get('op') == 'badge':
            badge = message.get('text')
        elif message.get('op') == 'frame':
            if manifest is None:
                break
            try:
                return Snapshot(manifest, decode_frame(message['png'], size), state, badge)
            except (ValueError, TypeError, OSError) as exc:
                raise WidgetProcessError(str(exc)) from exc
    stderr = result.stderr.strip().splitlines()
    raise WidgetProcessError(stderr[-1] if stderr else f'exited with code {result.returncode} without a frame')


class SubprocessRunner(WidgetRunner):
    """
    Keeps a third-party widget alive in its own process.

    A crash restarts the child after a growing delay; after MAX_CRASHES in a
    row without a healthy run the runner gives up and reports an error, so a
    broken widget can't spin the CPU restarting forever.
    """

    READY_TIMEOUT = 5.0
    MAX_CRASHES = 5
    BACKOFF_CAP = 30.0
    # A child that ran this long counts as healthy and clears the crash count.
    HEALTHY_AFTER = 60.0

    def __init__(self, spec: WidgetSpec, options: Mapping[str, Any], size: Tuple[int, int],
                 on_frame: FrameCallback, on_error: ErrorCallback, data_dir: Optional[str] = None,
                 on_state: TextCallback = _ignore, on_badge: TextCallback = _ignore, draw_frames: bool = True):
        self._spec = spec
        self._on_state = on_state
        self._on_badge = on_badge
        self._draw_frames = draw_frames
        self._options = dict(options)
        self._size = tuple(size)
        self._on_frame = on_frame
        self._on_error = on_error
        self._data_dir = data_dir
        self._stopping = threading.Event()
        self._write_lock = threading.Lock()
        self._process: Optional[subprocess.Popen] = None
        self._visible = False
        self._supervisor: Optional[threading.Thread] = None
        self.crashes = 0

    def start(self) -> None:
        self._supervisor = threading.Thread(target=self._supervise, name=f'widget-{self._spec.id}-proc', daemon=True)
        self._supervisor.start()

    def stop(self) -> None:
        self._stopping.set()
        self._send({'op': 'stop'})
        process = self._process
        if process is not None:
            try:
                process.wait(timeout=1.0)
            except subprocess.TimeoutExpired:
                process.kill()
        if self._supervisor is not None and self._supervisor is not threading.current_thread():
            self._supervisor.join(2.0)

    def post_event(self, name: str) -> None:
        self._send({'op': 'event', 'name': name})

    def post_focus(self, app: str, title: str) -> None:
        self._send({'op': 'focus', 'app': app, 'title': title})

    def show(self) -> None:
        self._visible = True
        self._send({'op': 'show'})

    def hide(self) -> None:
        self._visible = False
        self._send({'op': 'hide'})

    def _send(self, message: Dict[str, Any]) -> None:
        process = self._process
        if process is None or process.stdin is None:
            return
        with self._write_lock:
            try:
                process.stdin.write(json.dumps(message) + '\n')
                process.stdin.flush()
            except (BrokenPipeError, ValueError, OSError):
                pass

    def _supervise(self) -> None:
        while not self._stopping.is_set():
            started = time.monotonic()
            self._run_child()
            if self._stopping.is_set():
                return
            if time.monotonic() - started >= self.HEALTHY_AFTER:
                self.crashes = 0
            self.crashes += 1
            if self.crashes >= self.MAX_CRASHES:
                logger.error('widget[%s] crashed %d times in a row; giving up', self._spec.id, self.crashes)
                self._on_error('stopped after repeated crashes')
                return
            delay = min(2 ** (self.crashes - 1), self.BACKOFF_CAP)
            logger.warning('widget[%s] exited; restarting in %g s', self._spec.id, delay)
            self._stopping.wait(delay)

    def _run_child(self) -> None:
        try:
            process = subprocess.Popen(  # pylint: disable=consider-using-with
                _child_command(self._spec.script_path), stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                stderr=subprocess.PIPE, text=True, bufsize=1, env=_child_env(),
                cwd=self._spec.folder or None)
        except OSError as exc:
            self._on_error(f'cannot start: {exc}')
            return
        self._process = process
        threading.Thread(target=self._pump_stderr, args=(process,), daemon=True,
                         name=f'widget-{self._spec.id}-stderr').start()

        ready = threading.Event()
        watchdog = threading.Timer(self.READY_TIMEOUT, lambda: ready.is_set() or process.kill())
        watchdog.daemon = True
        watchdog.start()
        try:
            for line in process.stdout:
                self._handle(line, process, ready)
                if self._stopping.is_set():
                    break
        finally:
            watchdog.cancel()
            if process.poll() is None and self._stopping.is_set():
                try:
                    process.wait(timeout=1.0)
                except subprocess.TimeoutExpired:
                    process.kill()
            process.wait()
            self._process = None
        if not ready.is_set() and not self._stopping.is_set():
            self._on_error('did not start in time')

    def _handle(self, line: str, process: subprocess.Popen, ready: threading.Event) -> None:
        try:
            message = json.loads(line)
        except ValueError:
            logger.warning('widget[%s] sent garbage: %s', self._spec.id, line[:200].rstrip())
            return
        op = message.get('op')
        if op == 'ready':
            ready.set()
            self._send({'op': 'start', 'options': self._options, 'size': list(self._size),
                        'data_dir': self._data_dir, 'frames': self._draw_frames})
            if self._visible:
                self._send({'op': 'show'})
        elif op == 'frame':
            try:
                frame = decode_frame(message['png'], self._size)
            except (ValueError, TypeError, OSError, KeyError) as exc:
                self._on_error(f'bad frame: {exc}')
                return
            self._on_frame(frame)
        elif op == 'state':
            self._on_state(_short_text(message.get('state')))
        elif op == 'badge':
            self._on_badge(_short_text(message.get('text')))
        elif op == 'error':
            text = str(message.get('message', '')).strip()
            logger.error('widget[%s] %s', self._spec.id, text)
            self._on_error(text.splitlines()[-1] if text else 'error')
            if not ready.is_set():
                process.kill()

    def _pump_stderr(self, process: subprocess.Popen) -> None:
        for line in process.stderr:
            logger.info('widget[%s] %s', self._spec.id, line.rstrip())


def _short_text(value) -> Optional[str]:
    """A child's state or badge, trusted no further than a short string."""
    return None if value is None else str(value)[:40]


def create_runner(spec: WidgetSpec, options: Mapping[str, Any], size: Tuple[int, int],
                  on_frame: FrameCallback, on_error: ErrorCallback,
                  data_dir: Optional[str] = None, on_state: TextCallback = _ignore,
                  on_badge: TextCallback = _ignore, draw_frames: bool = True) -> WidgetRunner:
    runner_cls = InProcessRunner if spec.builtin else SubprocessRunner
    return runner_cls(spec, options, size, on_frame, on_error, data_dir,
                      on_state=on_state, on_badge=on_badge, draw_frames=draw_frames)
