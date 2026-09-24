"""
Runs one widget: its thread, timers, key events and frames.

Shared by both ways a widget runs - inside the app for built-ins and inside
the child process for third-party scripts - so a widget behaves the same
either way.
"""

import logging
import math
import queue
import tempfile
import threading
import time
from typing import Any, Callable, List, Mapping, Optional, Tuple, Type

from PIL import Image

from streamdock_sdk.context import WidgetContext
from streamdock_sdk.widget import KEY_EVENTS, Widget

logger = logging.getLogger(__name__)

_STOP = object()


class _Timer:
    __slots__ = ('interval', 'fn', 'align', 'due')

    def __init__(self, interval: float, fn: Optional[Callable[[], None]], align: bool):
        self.interval = interval
        self.fn = fn
        self.align = align
        self.due = 0.0


def check_frame(image: Any, size: Tuple[int, int]) -> Image.Image:
    """Return ``image`` as RGB, or raise if it isn't a PIL image of ``size``."""
    if not isinstance(image, Image.Image):
        raise TypeError(f'render() returned {type(image).__name__}, not a PIL image')
    if tuple(image.size) != tuple(size):
        raise ValueError(f'render() returned a {image.size[0]}x{image.size[1]} image, '
                         f'expected {size[0]}x{size[1]}')
    return image if image.mode == 'RGB' else image.convert('RGB')


class WidgetDriver:
    """
    Owns one widget instance and the single thread all its hooks run on.

    Timers are measured against the wall clock and the loop never sleeps more
    than ``MAX_SLEEP``, so after a suspend or a clock change a clock widget
    catches up within seconds instead of drifting until the next tick.
    """

    MAX_SLEEP = 5.0
    # Fire aligned ticks just after the boundary, so a clock never renders
    # 11:59 at 11:59:59.999.
    ALIGN_SLACK = 0.05

    def __init__(self, widget_cls: Type[Widget], options: Mapping[str, Any],
                 size: Tuple[int, int] = (112, 112),
                 on_frame: Optional[Callable[[Image.Image], None]] = None,
                 on_error: Optional[Callable[[str], None]] = None,
                 data_dir: Optional[str] = None,
                 clock: Callable[[], float] = time.time,
                 on_state: Optional[Callable[[Optional[str]], None]] = None,
                 on_badge: Optional[Callable[[Optional[str]], None]] = None,
                 draw_frames: bool = True):
        self.widget_cls = widget_cls
        self._on_frame = on_frame or (lambda image: None)
        self._on_error = on_error or (lambda message: None)
        self._on_state = on_state or (lambda state: None)
        self._on_badge = on_badge or (lambda text: None)
        # Off when the key shows the user's images: nothing would use a frame.
        self._draw_frames = draw_frames
        self.state: Optional[str] = None
        self.badge: Optional[str] = None
        self._clock = clock
        self._queue: 'queue.Queue[Any]' = queue.Queue()
        self._timers: List[_Timer] = []
        self._render_lock = threading.Lock()
        self._render_pending = False
        self._visible = False
        self._failed = False
        self._thread: Optional[threading.Thread] = None
        self.widget: Optional[Widget] = None
        self.ctx = WidgetContext(self, options, size, data_dir,
                                 logging.getLogger(f'widget.{widget_cls.id}'))

    @property
    def visible(self) -> bool:
        return self._visible

    # ------------------------------------------------------------------
    # Thread-safe API
    # ------------------------------------------------------------------

    def start(self) -> None:
        self._thread = threading.Thread(target=self._run, name=f'widget-{self.widget_cls.id}', daemon=True)
        self._thread.start()

    def stop(self, timeout: float = 1.0) -> None:
        self._queue.put(_STOP)
        if self._thread is not None and self._thread is not threading.current_thread():
            self._thread.join(timeout)

    def post_event(self, name: str) -> None:
        if name not in KEY_EVENTS:
            raise ValueError(f'unknown key event {name!r}')
        self._queue.put(lambda: getattr(self.widget, f'on_{name}')(self.ctx))

    def post_focus(self, app: str, title: str) -> None:
        self._queue.put(lambda: self.widget.on_window_focus(self.ctx, app, title))

    def show(self) -> None:
        self._queue.put(self._show)

    def hide(self) -> None:
        self._queue.put(self._hide)

    def request_render(self) -> None:
        if not self._draw_frames:
            return
        with self._render_lock:
            if self._render_pending:
                return
            self._render_pending = True
        self._queue.put(self._render)

    def set_state(self, state: Optional[str]) -> None:
        if state is not None and state not in self.widget_cls.states:
            raise ValueError(f'{state!r} is not one of the declared states {self.widget_cls.states}')
        if state != self.state:
            self.state = state
            self._on_state(state)

    def set_badge(self, text: Optional[str]) -> None:
        text = None if text is None or str(text) == '' else str(text)[:8]
        if text != self.badge:
            self.badge = text
            self._on_badge(text)

    def call_soon(self, fn: Callable[[], None]) -> None:
        self._queue.put(fn)

    def add_timer(self, seconds: float, fn: Optional[Callable[[], None]], align: bool) -> None:
        timer = _Timer(seconds, fn, align)
        timer.due = self._next_due(timer, self._clock())
        if self._on_widget_thread():
            self._timers.append(timer)
        else:
            self._queue.put(lambda: self._timers.append(timer))

    def run_in_background(self, fn: Callable[[], Any], then: Optional[Callable[[Any], None]]) -> None:
        def job():
            try:
                result = fn()
            except Exception:  # pylint: disable=broad-exception-caught
                self.ctx.log.exception('background job failed')
                return
            if then is not None:
                self.call_soon(lambda: then(result))

        threading.Thread(target=job, name=f'widget-{self.widget_cls.id}-bg', daemon=True).start()

    def render_once(self) -> Image.Image:
        """
        Set the widget up, draw one frame and tear it down, on the caller's thread.

        For previews and validation: exceptions propagate instead of being
        reported, and no timers run. Without a data directory of its own the
        widget gets a throwaway one, so ``ctx.data_dir`` works here too
        without touching the widget's real files.
        """
        with tempfile.TemporaryDirectory(prefix='streamdock-widget-') as scratch:
            if self.ctx._data_dir is None:  # pylint: disable=protected-access
                self.ctx._data_dir = scratch  # pylint: disable=protected-access
            self.widget = self.widget_cls()
            self.widget.setup(self.ctx)
            try:
                return check_frame(self.widget.render(self.ctx), self.ctx.size)
            finally:
                self.widget.teardown(self.ctx)

    # ------------------------------------------------------------------
    # Widget thread
    # ------------------------------------------------------------------

    def _on_widget_thread(self) -> bool:
        return self._thread is None or self._thread is threading.current_thread()

    def _run(self) -> None:
        try:
            self.widget = self.widget_cls()
            self.widget.setup(self.ctx)
        except Exception as exc:  # pylint: disable=broad-exception-caught
            self.ctx.log.exception('setup failed')
            self._on_error(f'setup failed: {exc}')
            self._failed = True
        else:
            self.request_render()

        while True:
            try:
                item = self._queue.get(timeout=self._next_timeout(self._clock()))
            except queue.Empty:
                item = None
            if item is _STOP:
                break
            if item is not None and not self._failed:
                self._guard(item)
            if not self._failed:
                self._run_due_timers(self._clock())

        if self.widget is not None and not self._failed:
            self._guard(lambda: self.widget.teardown(self.ctx))

    def _guard(self, fn: Callable[[], None]) -> None:
        try:
            fn()
        except Exception:  # pylint: disable=broad-exception-caught
            self.ctx.log.exception('widget hook failed')

    def _next_timeout(self, now: float) -> Optional[float]:
        if not self._visible or not self._timers:
            return None
        return max(0.0, min(min(t.due for t in self._timers) - now, self.MAX_SLEEP))

    def _run_due_timers(self, now: float) -> None:
        if not self._visible:
            return
        for timer in list(self._timers):
            if now >= timer.due:
                timer.due = self._next_due(timer, now)
                self._guard(timer.fn or self.request_render)

    def _next_due(self, timer: _Timer, now: float) -> float:
        if timer.align:
            return (math.floor(now / timer.interval) + 1) * timer.interval + self.ALIGN_SLACK
        return now + timer.interval

    def _show(self) -> None:
        if self._visible:
            return
        self._visible = True
        now = self._clock()
        for timer in self._timers:
            timer.due = self._next_due(timer, now)
        self.widget.on_show(self.ctx)
        self.request_render()

    def _hide(self) -> None:
        if not self._visible:
            return
        self._visible = False
        self.widget.on_hide(self.ctx)

    def _render(self) -> None:
        with self._render_lock:
            self._render_pending = False
        try:
            frame = check_frame(self.widget.render(self.ctx), self.ctx.size)
        except Exception as exc:  # pylint: disable=broad-exception-caught
            self.ctx.log.exception('render failed')
            self._on_error(f'render failed: {exc}')
            return
        self._on_frame(frame)
