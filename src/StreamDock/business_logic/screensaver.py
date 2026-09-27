"""
Lock-screen slideshow.

While the computer is locked the deck can show pictures instead of going
dark: each picture is cropped to the whole key grid and cut into one tile per
key. This module holds the settings and the timing loop; where pictures come
from (a folder, an online service) is an ImageSource injected by the
application, and what a picture looks like on the device is the caller's
``show`` callback.
"""

import logging
import threading
import time
from dataclasses import dataclass
from typing import Any, Callable, Dict, Optional, Protocol

logger = logging.getLogger(__name__)

SOURCE_FOLDER = 'folder'
SOURCE_ONLINE = 'online'
SOURCES = (SOURCE_FOLDER, SOURCE_ONLINE)

# Free services that need no account or API key.
ONLINE_PROVIDERS = {
    'picsum': 'Lorem Picsum (random photos)',
    'bing': 'Bing image of the day',
}
DEFAULT_PROVIDER = 'picsum'

DEFAULT_INTERVAL = 10.0
# Every picture is fifteen HID image transfers; much faster than this and the
# deck spends its time mid-redraw.
MIN_INTERVAL = 2.0
MAX_INTERVAL = 3600.0

# Minutes; 0 keeps the slideshow running for as long as the screen is locked.
DEFAULT_TURN_OFF_AFTER = 0.0
MAX_TURN_OFF_AFTER = 1440.0

# How long stop() waits for the loop. An online fetch can take its full
# timeout, and an unlock must not wait for it: a frame the loop draws after
# this is refused by the caller's show callback instead.
STOP_JOIN_TIMEOUT = 0.5

KNOWN_FIELDS = ('enabled', 'source', 'folder', 'provider', 'interval',
                'turn_off_after', 'shuffle', 'brightness')


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def screensaver_problem(data: Any) -> Optional[str]:
    """
    What is wrong with a ``settings.screensaver`` section, or None.

    The message is shown to the user verbatim.
    """
    if not isinstance(data, dict):
        return "screensaver must be a mapping"
    for flag in ('enabled', 'shuffle'):
        if flag in data and not isinstance(data[flag], bool):
            return f"screensaver.{flag} must be true or false"
    source = data.get('source', SOURCE_FOLDER)
    if source not in SOURCES:
        return f"screensaver.source must be one of: {', '.join(SOURCES)}"
    folder = data.get('folder')
    if folder is not None and not isinstance(folder, str):
        return "screensaver.folder must be a path"
    provider = data.get('provider', DEFAULT_PROVIDER)
    if provider not in ONLINE_PROVIDERS:
        return f"screensaver.provider must be one of: {', '.join(ONLINE_PROVIDERS)}"
    interval = data.get('interval', DEFAULT_INTERVAL)
    if not _is_number(interval) or not MIN_INTERVAL <= interval <= MAX_INTERVAL:
        return (f"screensaver.interval must be a number between {MIN_INTERVAL:g} "
                f"and {MAX_INTERVAL:g} (seconds)")
    turn_off = data.get('turn_off_after', DEFAULT_TURN_OFF_AFTER)
    if not _is_number(turn_off) or not 0 <= turn_off <= MAX_TURN_OFF_AFTER:
        return (f"screensaver.turn_off_after must be a number between 0 and "
                f"{MAX_TURN_OFF_AFTER:g} (minutes, 0 = never)")
    brightness = data.get('brightness')
    if brightness is not None and (not _is_number(brightness) or not 0 <= brightness <= 100):
        return "screensaver.brightness must be a number between 0 and 100"
    if data.get('enabled', False) and source == SOURCE_FOLDER and not (folder or '').strip():
        return "screensaver.folder is required when the source is 'folder'"
    return None


@dataclass(frozen=True)
class ScreensaverConfig:
    """
    The runtime's view of ``settings.screensaver``, with the folder resolved.

    Built from an already validated section; see screensaver_problem.
    """
    enabled: bool = False
    source: str = SOURCE_FOLDER
    folder: str = ''
    provider: str = DEFAULT_PROVIDER
    interval: float = DEFAULT_INTERVAL
    turn_off_after: float = DEFAULT_TURN_OFF_AFTER
    shuffle: bool = True
    # None keeps the brightness the deck had when the computer locked.
    brightness: Optional[int] = None

    @classmethod
    def from_dict(cls, data: Optional[Dict[str, Any]],
                  resolve_path: Callable[[str], str] = lambda path: path) -> 'ScreensaverConfig':
        """
        Args:
            data: The section, or None when the file has none
            resolve_path: Turns the folder as written into an absolute path,
                the way key icons are resolved against the config file
        """
        if not data:
            return cls()
        folder = data.get('folder') or ''
        return cls(
            enabled=bool(data.get('enabled', False)),
            source=data.get('source', SOURCE_FOLDER),
            folder=resolve_path(folder) if folder.strip() else '',
            provider=data.get('provider', DEFAULT_PROVIDER),
            interval=float(data.get('interval', DEFAULT_INTERVAL)),
            turn_off_after=float(data.get('turn_off_after', DEFAULT_TURN_OFF_AFTER)),
            shuffle=bool(data.get('shuffle', True)),
            brightness=None if data.get('brightness') is None else int(data['brightness']),
        )

    @property
    def turn_off_seconds(self) -> Optional[float]:
        """Seconds until the deck goes dark, or None to keep running."""
        return self.turn_off_after * 60 if self.turn_off_after > 0 else None


class ImageSource(Protocol):
    """Where the slideshow's pictures come from."""

    def next_image(self) -> Any:
        """The next picture as a PIL image, or None when there is none to give."""


class Screensaver:
    """
    Runs one slideshow on its own thread, from start() until stop().

    Both callbacks run on that thread and receive this Screensaver first, so
    the caller can tell a live slideshow from one it has already replaced:

    - ``show(saver, image)`` draws a picture. The next one is fetched while
      the current one is on screen, so a slow download does not stretch the
      interval.
    - ``expire(saver)`` is called once when the slideshow ends by itself:
      ``turn_off_after`` has passed, or the source never produced a picture.
      The caller turns the deck off, as it would have without a screensaver.
    """

    def __init__(self, config: ScreensaverConfig, source: ImageSource,
                 show: Callable[['Screensaver', Any], None],
                 expire: Callable[['Screensaver'], None],
                 clock: Callable[[], float] = time.monotonic):
        self._config = config
        self._source = source
        self._show = show
        self._expire = expire
        self._clock = clock
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None

    def start(self) -> None:
        if self._thread is not None:
            return
        self._thread = threading.Thread(target=self._run, name="screensaver", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        """
        End the slideshow without calling ``expire``.

        Never call this holding a lock ``show`` takes: the loop may be
        waiting for it.
        """
        self._stop.set()
        thread = self._thread
        if thread is not None and thread is not threading.current_thread():
            thread.join(timeout=STOP_JOIN_TIMEOUT)

    @property
    def stopped(self) -> bool:
        return self._stop.is_set()

    def _next_image(self) -> Any:
        try:
            return self._source.next_image()
        except Exception:  # pylint: disable=broad-exception-caught
            logger.exception("Screensaver image source failed")
            return None

    def _run(self) -> None:
        turn_off = self._config.turn_off_seconds
        deadline = None if turn_off is None else self._clock() + turn_off
        try:
            image = self._next_image()
            if image is None:
                logger.warning("Screensaver has no pictures to show - turning the deck off")
                self._finish()
                return
            logger.info("Screensaver started (every %gs%s)", self._config.interval,
                        "" if turn_off is None else f", off after {self._config.turn_off_after:g} min")
            while not self._stop.is_set():
                shown_at = self._clock()
                self._show(self, image)
                upcoming = self._next_image()
                if upcoming is not None:
                    image = upcoming
                wait = self._config.interval - (self._clock() - shown_at)
                if deadline is not None:
                    wait = min(wait, deadline - self._clock())
                if self._stop.wait(max(0.0, wait)):
                    return
                if deadline is not None and self._clock() >= deadline:
                    logger.info("Screensaver time is up - turning the deck off")
                    self._finish()
                    return
        except Exception:  # pylint: disable=broad-exception-caught
            logger.exception("Screensaver stopped by an error - turning the deck off")
            self._finish()

    def _finish(self) -> None:
        if not self._stop.is_set():
            self._stop.set()
            self._expire(self)
