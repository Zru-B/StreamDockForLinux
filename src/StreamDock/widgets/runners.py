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
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from dataclasses import dataclass
from typing import Any, Callable, Dict, Mapping, Optional, Tuple

from PIL import Image

import streamdock_sdk
from streamdock_sdk.scheduler import WidgetDriver, check_frame
from StreamDock.widgets.registry import CHANGED_PROBLEM, WidgetSpec

logger = logging.getLogger(__name__)

FrameCallback = Callable[[Image.Image], None]
ErrorCallback = Callable[[str], None]
TextCallback = Callable[[Optional[str]], None]

# A child's stderr line longer than this is cut short in the log.
MAX_LOG_LINE = 2000
# At most this many stderr lines per widget are logged in any LOG_WINDOW
# seconds; the rest are counted, so a widget printing in a loop can't flood the log.
LOG_BURST = 50
LOG_WINDOW = 10.0
# Children speak UTF-8; a stray invalid byte must not kill the reader thread.
CHILD_TEXT = {'encoding': 'utf-8', 'errors': 'replace'}


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
    return [sys.executable, '-B', '-m', 'streamdock_sdk.host', script_path]


def _child_env(cache_dir: str) -> Dict[str, str]:
    """
    The child imports the SDK from wherever this process found it, installed or not.

    Bytecode is looked up only under ``cache_dir``, an empty folder of the
    caller's, and never written: a ``.pyc`` dropped into the widget's folder
    would otherwise run in place of the source whose hash the user approved.
    """
    env = dict(os.environ)
    src = os.path.dirname(os.path.dirname(os.path.abspath(streamdock_sdk.__file__)))
    env['PYTHONPATH'] = os.pathsep.join(filter(None, [src, env.get('PYTHONPATH')]))
    env['PYTHONUNBUFFERED'] = '1'
    env['PYTHONDONTWRITEBYTECODE'] = '1'
    env['PYTHONPYCACHEPREFIX'] = cache_dir
    return env


def decode_frame(payload: str, size: Tuple[int, int]) -> Image.Image:
    image = Image.open(io.BytesIO(base64.b64decode(payload)), formats=['PNG'])
    # Checked before load(): the header alone is enough to refuse a huge image.
    if tuple(image.size) != tuple(size):
        raise ValueError(f'frame is {image.size[0]}x{image.size[1]}, expected {size[0]}x{size[1]}')
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
        with tempfile.TemporaryDirectory(prefix='streamdock-pycache-') as cache_dir:
            # The same working directory as SubprocessRunner, so a preview
            # behaves like the widget on the device.
            result = subprocess.run(_child_command(script_path), input=commands, capture_output=True,
                                    text=True, **CHILD_TEXT, timeout=timeout, env=_child_env(cache_dir),
                                    cwd=os.path.dirname(os.path.abspath(script_path)), check=False)
    except subprocess.TimeoutExpired as exc:
        raise WidgetProcessError(f'did not finish within {timeout:g} s') from exc

    manifest = None
    state = badge = None
    for line in result.stdout.splitlines():
        try:
            message = json.loads(line)
        except ValueError as exc:
            raise WidgetProcessError(f'unexpected output: {line[:200]}') from exc
        if not isinstance(message, dict):
            raise WidgetProcessError(f'unexpected output: {line[:200]}')
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
            # PIL's DecompressionBombError is a plain Exception.
            except Exception as exc:  # pylint: disable=broad-exception-caught
                raise WidgetProcessError(f'bad frame: {exc}') from exc
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
        # Set when the child reported why it could not start, so the
        # missing 'ready' is not reported a second time as a hang.
        self._start_error = False
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
            # Checked before every spawn, restarts included: approval covers
            # the files as they were, and they may have changed since the
            # registry last looked.
            if self._spec.changed_since_approval():
                logger.error('widget[%s] not started: %s', self._spec.id, CHANGED_PROBLEM)
                self._on_error(CHANGED_PROBLEM)
                return
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
        cache_dir = tempfile.mkdtemp(prefix='streamdock-pycache-')
        try:
            process = subprocess.Popen(  # pylint: disable=consider-using-with
                _child_command(self._spec.script_path), stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                stderr=subprocess.PIPE, text=True, **CHILD_TEXT, bufsize=1, env=_child_env(cache_dir),
                cwd=self._spec.folder or None)
        except OSError as exc:
            shutil.rmtree(cache_dir, ignore_errors=True)
            self._on_error(f'cannot start: {exc}')
            return
        self._process = process
        self._start_error = False
        threading.Thread(target=self._pump_stderr, args=(process,), daemon=True,
                         name=f'widget-{self._spec.id}-stderr').start()

        ready = threading.Event()
        watchdog = threading.Timer(self.READY_TIMEOUT, lambda: ready.is_set() or process.kill())
        watchdog.daemon = True
        watchdog.start()
        failed = False
        try:
            for line in process.stdout:
                self._handle(line, process, ready)
                if self._stopping.is_set():
                    break
        except Exception as exc:  # pylint: disable=broad-exception-caught
            # Anything escaping here would otherwise leave a live child behind
            # and the supervisor waiting on it forever; treat it as a crash.
            logger.exception('widget[%s] runner failed', self._spec.id)
            self._on_error(f'runner failed: {exc}')
            failed = True
        finally:
            watchdog.cancel()
            self._reap(process, grace=0.0 if failed else 1.0)
            self._process = None
            shutil.rmtree(cache_dir, ignore_errors=True)
        if not ready.is_set() and not failed and not self._start_error and not self._stopping.is_set():
            self._on_error('did not start in time')

    def _reap(self, process: subprocess.Popen, grace: float) -> None:
        """Let the child exit on its own for ``grace`` seconds, then kill it; never wait unbounded."""
        try:
            process.wait(timeout=grace)
        except subprocess.TimeoutExpired:
            process.kill()
            try:
                process.wait(timeout=5.0)
            except subprocess.TimeoutExpired:
                logger.error('widget[%s] did not exit after being killed', self._spec.id)
        for pipe in (process.stdin, process.stdout):
            try:
                pipe.close()
            except (OSError, ValueError):
                pass

    def _handle(self, line: str, process: subprocess.Popen, ready: threading.Event) -> None:
        try:
            message = json.loads(line)
        except ValueError:
            logger.warning('widget[%s] sent garbage: %s', self._spec.id, line[:200].rstrip())
            return
        if not isinstance(message, dict):
            logger.warning('widget[%s] sent a message that is not an object: %s', self._spec.id, line[:200].rstrip())
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
            # PIL's DecompressionBombError is a plain Exception.
            except Exception as exc:  # pylint: disable=broad-exception-caught
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
                self._start_error = True
                process.kill()

    def _pump_stderr(self, process: subprocess.Popen) -> None:
        """
        Log the child's stderr until it closes.

        Must keep reading whatever happens: a child blocked on a full stderr
        pipe stops answering, and would be killed as hung. Lines are read in
        bounded pieces so a widget printing without newlines can't fill memory.
        """
        continuation = False
        window_start, logged, suppressed = time.monotonic(), 0, 0
        while True:
            try:
                chunk = process.stderr.readline(MAX_LOG_LINE)
            except (OSError, ValueError):
                chunk = ''
            except Exception:  # pylint: disable=broad-exception-caught
                logger.exception('widget[%s] stderr could not be read; discarding the rest', self._spec.id)
                _drain(process.stderr)
                chunk = ''
            if not chunk:
                if suppressed:
                    logger.info('widget[%s] suppressed %d more lines of output', self._spec.id, suppressed)
                return
            if not continuation:
                now = time.monotonic()
                if now - window_start >= LOG_WINDOW:
                    if suppressed:
                        logger.info('widget[%s] suppressed %d more lines of output', self._spec.id, suppressed)
                    window_start, logged, suppressed = now, 0, 0
                if logged < LOG_BURST:
                    logged += 1
                    ending = '' if chunk.endswith('\n') else ' [...]'
                    logger.info('widget[%s] %s%s', self._spec.id, chunk.rstrip(), ending)
                else:
                    suppressed += 1
            continuation = not chunk.endswith('\n')


def _drain(stream) -> None:
    try:
        while stream.buffer.read1(65536):
            pass
    except Exception:  # pylint: disable=broad-exception-caught
        pass


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
