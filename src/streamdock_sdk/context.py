"""What a widget's hooks receive: its options and the ways to ask for work."""

import logging
import os
from types import MappingProxyType
from typing import Any, Callable, Mapping, Optional, Tuple


class WidgetContext:
    """
    The widget's handle on the app.

    Created by the driver; every method is safe to call from any thread, so a
    background job can hand results back with ``call_soon`` or ask for a new
    frame with ``request_render``.
    """

    def __init__(self, driver, options: Mapping[str, Any], size: Tuple[int, int],
                 data_dir: Optional[str], logger: logging.Logger):
        self._driver = driver
        self.options: Mapping[str, Any] = MappingProxyType(dict(options))
        self.size: Tuple[int, int] = tuple(size)
        self.log = logger
        self._data_dir = data_dir

    @property
    def visible(self) -> bool:
        return self._driver.visible

    @property
    def data_dir(self) -> str:
        """A directory this widget may keep files in; created on first use."""
        if not self._data_dir:
            raise RuntimeError('this widget has no data directory')
        os.makedirs(self._data_dir, exist_ok=True)
        return self._data_dir

    def request_render(self) -> None:
        """Draw a new frame soon. Repeated requests before it runs collapse into one."""
        self._driver.request_render()

    def set_state(self, state: str) -> None:
        """
        Report the widget's condition, one of its declared ``states``.

        A key configured with ``state_icons`` shows the matching image instead
        of what ``render`` draws.
        """
        self._driver.set_state(state)

    def set_badge(self, text: Optional[str]) -> None:
        """Report a short badge text (e.g. an unread count), or None for no badge."""
        self._driver.set_badge(text)

    def every(self, seconds: float, fn: Optional[Callable[[], None]] = None, align: bool = False) -> None:
        """
        Run ``fn`` (default: a re-render) every ``seconds`` while the key is shown.

        ``align=True`` fires on wall-clock multiples of ``seconds`` - a clock with
        ``every(60, align=True)`` turns over at :00, not a minute after it started.
        """
        if seconds <= 0:
            raise ValueError('interval must be positive')
        self._driver.add_timer(seconds, fn, align)

    def call_soon(self, fn: Callable[[], None]) -> None:
        """Run ``fn`` on the widget's thread."""
        self._driver.call_soon(fn)

    def run_in_background(self, fn: Callable[[], Any],
                          then: Optional[Callable[[Any], None]] = None, *,
                          skip_if_running: bool = False) -> None:
        """
        Run blocking ``fn`` off the widget's thread.

        ``then(result)`` runs back on the widget's thread; an exception in
        ``fn`` is logged and ``then`` is skipped.

        ``skip_if_running=True`` is for periodic polls: the call does nothing
        while a job started from the same place in the code (the same lambda
        or function) is still running, so a slow poll never stacks up. Leave
        it off for work the user asked for, such as a toggle on a key press.
        """
        self._driver.run_in_background(fn, then, skip_if_running)
