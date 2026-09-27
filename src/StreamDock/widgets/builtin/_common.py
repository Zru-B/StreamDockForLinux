"""Helpers shared by the built-in widgets."""

import logging
import subprocess
import threading
from datetime import datetime, tzinfo
from typing import Any, Callable, List, Optional, Sequence, Tuple
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from PIL import Image, ImageDraw

from streamdock_sdk import draw

logger = logging.getLogger(__name__)

# Draw at this multiple of the key size and scale down, for smooth edges.
SUPERSAMPLE = 4


def now(zone: Optional[tzinfo] = None) -> datetime:
    """The current time; tests replace this to freeze the clock."""
    return datetime.now(zone)


def parse_zone(name: str) -> Optional[tzinfo]:
    """The zone called ``name``, or None (local time) when it's empty or unknown."""
    if not name.strip():
        return None
    try:
        return ZoneInfo(name.strip())
    except (ZoneInfoNotFoundError, ValueError):
        logger.warning('Unknown time zone %r; showing local time', name)
        return None


def supersampled(size: Tuple[int, int], background: str) -> Tuple[Image.Image, ImageDraw.ImageDraw, int]:
    image = Image.new('RGB', (size[0] * SUPERSAMPLE, size[1] * SUPERSAMPLE), background)
    return image, ImageDraw.Draw(image), SUPERSAMPLE


def downsample(image: Image.Image, size: Tuple[int, int]) -> Image.Image:
    return image.resize(tuple(size), Image.LANCZOS)


def status_tile(size: Tuple[int, int], background: str, caption: str, caption_color: str = 'white'):
    """
    A supersampled canvas for an icon-plus-caption status key.

    Returns (image, draw, scale, icon_box), where icon_box is the area above
    the caption in supersampled pixels. Pass the image to ``finish_status_tile``.
    """
    image, canvas, scale = supersampled(size, background)
    width, height = image.size
    caption_top = int(height * 0.70)
    draw.centered_text(canvas, (6 * scale, caption_top, width - 6 * scale, height - 6 * scale),
                       caption, color=caption_color)
    icon_box = (int(width * 0.22), int(height * 0.10), int(width * 0.78), caption_top - 4 * scale)
    return image, canvas, scale, icon_box


def slash(canvas: ImageDraw.ImageDraw, box, color: str, width: int) -> None:
    """The diagonal 'off' stroke across an icon."""
    left, top, right, bottom = box
    canvas.line((left, bottom, right, top), fill=color, width=width)


class ProcessHub:
    """
    One long-running command, such as a bus monitor, shared by every subscriber in the process.

    Started by the first subscriber and stopped with the last. Each start is
    a generation with its own stop event: a reader thread of a stopped
    generation that is still winding down never publishes to the next one's
    subscribers, and a process it spawns after the stop is killed at once.
    ``parse(line)`` turns an output line into an event, or None to skip it;
    subscribers get ``None`` itself when the command can't run.
    """

    RESTART_DELAY = 5.0

    def __init__(self, command: Sequence[str], name: str, parse: Callable[[str], Any] = lambda line: line):
        self._command = list(command)
        self._name = name
        self._parse = parse
        self._lock = threading.Lock()
        self._subscribers: List[Callable[[Any], None]] = []
        self._stopping: Optional[threading.Event] = None
        self._process: Optional[subprocess.Popen] = None

    def subscribe(self, callback: Callable[[Any], None]) -> None:
        with self._lock:
            self._subscribers.append(callback)
            if self._stopping is None:
                self._stopping = threading.Event()
                threading.Thread(target=self._run, args=(self._stopping,), name=self._name, daemon=True).start()

    def unsubscribe(self, callback: Callable[[Any], None]) -> None:
        with self._lock:
            if callback in self._subscribers:
                self._subscribers.remove(callback)
            if self._subscribers or self._stopping is None:
                return
            self._stopping.set()
            self._stopping = None
            process, self._process = self._process, None
        if process is not None:
            process.terminate()

    def _publish(self, stopping: threading.Event, event: Any) -> None:
        with self._lock:
            if stopping is not self._stopping:
                return
            subscribers = list(self._subscribers)
        for callback in subscribers:
            try:
                callback(event)
            except Exception:  # pylint: disable=broad-exception-caught
                logger.exception('%s subscriber failed', self._name)

    def _run(self, stopping: threading.Event) -> None:
        while not stopping.is_set():
            try:
                process = subprocess.Popen(self._command, stdout=subprocess.PIPE,  # pylint: disable=consider-using-with
                                           stderr=subprocess.DEVNULL, text=True, errors='replace')
            except OSError:
                logger.warning('%s: %s not found', self._name, self._command[0])
                self._publish(stopping, None)
                return
            with self._lock:
                # unsubscribe() may have run while Popen did; it saw no process to stop.
                stopped = stopping.is_set()
                if not stopped:
                    self._process = process
            if stopped:
                process.terminate()
                process.wait()
                return
            try:
                for line in process.stdout:
                    try:
                        event = self._parse(line)
                    except Exception:  # pylint: disable=broad-exception-caught
                        logger.exception('%s: cannot parse %r', self._name, line[:200])
                        continue
                    if event is not None:
                        self._publish(stopping, event)
            except Exception:  # pylint: disable=broad-exception-caught
                # The thread must outlive anything one line does; the process restarts.
                logger.exception('%s reader failed', self._name)
                process.kill()
            finally:
                with self._lock:
                    if self._process is process:
                        self._process = None
            if process.wait() != 0 and not stopping.is_set():
                self._publish(stopping, None)
            stopping.wait(self.RESTART_DELAY)
