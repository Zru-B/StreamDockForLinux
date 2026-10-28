"""
Picture sources for the lock-screen slideshow.

A folder on disk, or a free online service. Online pictures are kept in a
small cache under $XDG_CACHE_HOME, so the slideshow keeps going from what it
already downloaded when the network is down - which it often is right after
the computer locks and suspends its connections.
"""

import hashlib
import json
import logging
import os
import random
import urllib.request
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

from PIL import Image

from StreamDock.business_logic.screensaver import (
    SOURCE_ONLINE,
    ImageSource,
    ScreensaverConfig,
)

logger = logging.getLogger(__name__)

IMAGE_EXTENSIONS = ('.jpg', '.jpeg', '.png', '.bmp', '.gif', '.webp')

HTTP_TIMEOUT = 10
# Wallpapers run to a few MB; anything this big is not one.
MAX_DOWNLOAD_BYTES = 20 * 1024 * 1024
MAX_CACHED = 100
USER_AGENT = "StreamDockForLinux-screensaver"

PICSUM_URL = "https://picsum.photos/{width}/{height}"
BING_ROOT = "https://www.bing.com"
# The archive serves at most eight days per request; two requests reach back
# about a fortnight.
BING_ARCHIVE_URLS = tuple(f"{BING_ROOT}/HPImageArchive.aspx?format=js&idx={idx}&n=8&mkt=en-US"
                          for idx in (0, 8))
# Nearly the front panel's proportions (see device_geometry.panel_size), so little is
# cropped away, and still more pixels than the panel has.
BING_RESOLUTION = "_1280x720.jpg"

Fetch = Callable[[str], Tuple[bytes, Dict[str, str]]]


def default_cache_dir() -> Path:
    base = os.environ.get('XDG_CACHE_HOME') or os.path.join(Path.home(), '.cache')
    return Path(base) / 'streamdock' / 'screensaver'


def http_get(url: str) -> Tuple[bytes, Dict[str, str]]:
    """GET over HTTPS; returns the body and the response headers."""
    if not url.startswith('https://'):
        raise ValueError(f"refusing a non-HTTPS URL: {url}")
    request = urllib.request.Request(url, headers={'User-Agent': USER_AGENT})
    with urllib.request.urlopen(request, timeout=HTTP_TIMEOUT) as response:
        data = response.read(MAX_DOWNLOAD_BYTES + 1)
        if len(data) > MAX_DOWNLOAD_BYTES:
            raise ValueError(f"response from {url} is larger than {MAX_DOWNLOAD_BYTES} bytes")
        return data, dict(response.headers.items())


def open_image(path: str, target_size: Optional[Tuple[int, int]] = None) -> Optional[Image.Image]:
    """
    Decode a picture fully, or None if it is not one.

    ``target_size`` lets a JPEG decode at a reduced scale: a 24-megapixel
    photo cut into 112-pixel tiles need not be decoded at full size.
    """
    try:
        with Image.open(path) as image:
            if target_size is not None:
                image.draft('RGB', target_size)
            image.load()
            return image.copy()
    except (OSError, ValueError, Image.DecompressionBombError) as e:
        logger.debug("Skipping %s: %s", path, e)
        return None


class FolderImageSource:
    """
    Pictures from a folder and its subfolders.

    The folder is scanned again after each full pass, so pictures added or
    removed while the screen is locked are picked up.
    """

    def __init__(self, folder: str, shuffle: bool = True,
                 target_size: Optional[Tuple[int, int]] = None,
                 rng: Optional[random.Random] = None):
        self._folder = folder
        self._shuffle = shuffle
        self._target_size = target_size
        self._rng = rng or random.Random()
        self._queue: List[str] = []

    def _scan(self) -> List[str]:
        found = []
        for root, dirs, files in os.walk(self._folder):
            dirs[:] = sorted(d for d in dirs if not d.startswith('.'))
            found.extend(os.path.join(root, name) for name in sorted(files)
                         if name.lower().endswith(IMAGE_EXTENSIONS) and not name.startswith('.'))
        return found

    def next_image(self) -> Optional[Image.Image]:
        if not self._queue:
            if not os.path.isdir(self._folder):
                logger.warning("Screensaver folder does not exist: %s", self._folder)
                return None
            self._queue = self._scan()
            if self._shuffle:
                self._rng.shuffle(self._queue)
            if not self._queue:
                logger.warning("Screensaver folder has no pictures: %s", self._folder)
                return None
        # Unreadable files are skipped, but a folder of nothing but broken
        # files must not spin: at most one pass over it.
        for _ in range(len(self._queue)):
            if not self._queue:
                break
            image = open_image(self._queue.pop(0), self._target_size)
            if image is not None:
                return image
        return None


class OnlineImageSource:
    """
    Pictures downloaded from a free service, cached on disk.

    - ``picsum``: a new random photo from picsum.photos on every call, sized
      for the key grid.
    - ``bing``: Bing's picture of the day for the last couple of weeks, in
      turn; each is downloaded once.

    When a download fails a cached picture stands in, so the slideshow
    survives the network going away.
    """

    def __init__(self, provider: str, target_size: Tuple[int, int],
                 cache_dir: Optional[Path] = None, fetch: Fetch = http_get,
                 max_cached: int = MAX_CACHED, rng: Optional[random.Random] = None):
        self._provider = provider
        self._target_size = target_size
        self._cache_dir = Path(cache_dir or default_cache_dir()) / provider
        self._fetch = fetch
        self._max_cached = max_cached
        self._rng = rng or random.Random()
        self._bing_queue: List[Tuple[str, str]] = []
        self._failing = False
        self._last_path: Optional[Path] = None

    def next_image(self) -> Optional[Image.Image]:
        path = None
        try:
            path = self._download_next()
            if self._failing:
                logger.info("Screensaver downloads from %s are working again", self._provider)
            self._failing = False
        except (OSError, ValueError) as e:
            if not self._failing:
                logger.warning("Screensaver could not download from %s, using cached pictures: %s",
                               self._provider, e)
            self._failing = True
        if path is None:
            path = self._cached_fallback()
        if path is None:
            return None
        image = open_image(str(path), self._target_size)
        if image is None:
            path.unlink(missing_ok=True)
            return None
        self._last_path = path
        return image

    def _download_next(self) -> Optional[Path]:
        if self._provider == 'picsum':
            return self._download_picsum()
        if self._provider == 'bing':
            return self._download_bing()
        raise ValueError(f"unknown screensaver provider: {self._provider}")

    def _download_picsum(self) -> Path:
        width, height = self._target_size
        data, headers = self._fetch(PICSUM_URL.format(width=width, height=height))
        picture_id = headers.get('Picsum-ID') or headers.get('picsum-id')
        if picture_id and picture_id.isdigit():
            name = f"picsum-{picture_id}-{width}x{height}.jpg"
        else:
            name = f"picsum-{hashlib.sha1(data).hexdigest()[:16]}.jpg"
        return self._store(name, data)

    def _download_bing(self) -> Optional[Path]:
        if not self._bing_queue:
            self._bing_queue = self._bing_archive()
        if not self._bing_queue:
            return None
        name, url = self._bing_queue.pop(0)
        cached = self._cache_dir / name
        if cached.is_file():
            return cached
        data, _headers = self._fetch(url)
        return self._store(name, data)

    def _bing_archive(self) -> List[Tuple[str, str]]:
        entries: Dict[str, str] = {}
        for archive_url in BING_ARCHIVE_URLS:
            data, _headers = self._fetch(archive_url)
            try:
                images = json.loads(data.decode('utf-8')).get('images', [])
            except (UnicodeDecodeError, json.JSONDecodeError, AttributeError) as e:
                raise ValueError(f"unexpected Bing archive response: {e}") from e
            for entry in images:
                urlbase = entry.get('urlbase') if isinstance(entry, dict) else None
                if not isinstance(urlbase, str) or not urlbase.startswith('/'):
                    continue
                digest = hashlib.sha1(urlbase.encode('utf-8')).hexdigest()[:16]
                entries.setdefault(f"bing-{digest}.jpg", f"{BING_ROOT}{urlbase}{BING_RESOLUTION}")
        return list(entries.items())

    def _store(self, name: str, data: bytes) -> Path:
        self._cache_dir.mkdir(parents=True, exist_ok=True)
        path = self._cache_dir / name
        partial = path.with_suffix(path.suffix + '.part')
        partial.write_bytes(data)
        os.replace(partial, path)
        self._prune()
        return path

    def _cached(self) -> List[Path]:
        if not self._cache_dir.is_dir():
            return []
        return [path for path in self._cache_dir.iterdir()
                if path.is_file() and path.suffix.lower() in IMAGE_EXTENSIONS]

    def _prune(self) -> None:
        cached = sorted(self._cached(), key=lambda path: path.stat().st_mtime, reverse=True)
        for stale in cached[self._max_cached:]:
            stale.unlink(missing_ok=True)

    def _cached_fallback(self) -> Optional[Path]:
        cached = self._cached()
        if len(cached) > 1 and self._last_path in cached:
            cached.remove(self._last_path)
        return self._rng.choice(cached) if cached else None


def make_image_source(config: ScreensaverConfig, target_size: Tuple[int, int]) -> ImageSource:
    """
    The source a screensaver configuration asks for.

    Args:
        target_size: Pixel size of the whole key grid
    """
    if config.source == SOURCE_ONLINE:
        return OnlineImageSource(config.provider, target_size)
    return FolderImageSource(config.folder, config.shuffle, target_size)
