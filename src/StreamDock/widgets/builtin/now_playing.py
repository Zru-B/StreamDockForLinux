import io
import os
import threading
import urllib.parse
import urllib.request
from collections import OrderedDict
from typing import Optional, Tuple

from PIL import Image, ImageEnhance

from streamdock_sdk import Option, Widget, draw
from StreamDock.infrastructure import mpris as _mpris

ART_TIMEOUT = 5
MAX_ART_BYTES = 5 * 1024 * 1024
# The formats players actually hand out; PIL would otherwise try every plugin it has.
ART_FORMATS = ['PNG', 'JPEG', 'WEBP', 'GIF']
# Art is only ever drawn on a key, so nothing larger is kept.
ART_SIZE = (224, 224)
ART_CACHE_SIZE = 16

_art_cache: 'OrderedDict[str, Image.Image]' = OrderedDict()
_art_lock = threading.Lock()


def _read_art(url: str) -> Optional[bytes]:
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme == 'file':
        path = urllib.parse.unquote(parsed.path)
        # A player may name anything; a FIFO or /dev/zero would block or never end.
        if not os.path.isfile(path) or os.path.getsize(path) > MAX_ART_BYTES:
            return None
        with open(path, 'rb') as handle:
            return handle.read(MAX_ART_BYTES + 1)
    if parsed.scheme in ('http', 'https'):
        with urllib.request.urlopen(url, timeout=ART_TIMEOUT) as response:  # nosec - player-supplied art
            return response.read(MAX_ART_BYTES + 1)
    return None


def _load_art(url: str) -> Optional[Image.Image]:
    try:
        data = _read_art(url)
        if data is None or len(data) > MAX_ART_BYTES:
            return None
        image = Image.open(io.BytesIO(data), formats=ART_FORMATS)
        image.thumbnail(ART_SIZE)
        return image.convert('RGB')
    # PIL's DecompressionBombError is a plain Exception, and a truncated or odd
    # file can raise nearly anything; no art is the answer to all of them.
    except Exception:  # pylint: disable=broad-exception-caught
        return None


def fetch_art(url: str) -> Optional[Image.Image]:
    """
    Album art from a file:// or http(s) URL, scaled down, or None.

    Only successes are cached: art that failed because the player hadn't
    written the file yet, or the network blinked, is tried again next time.
    """
    with _art_lock:
        if url in _art_cache:
            _art_cache.move_to_end(url)
            return _art_cache[url]
    image = _load_art(url)
    if image is not None:
        with _art_lock:
            _art_cache[url] = image
            while len(_art_cache) > ART_CACHE_SIZE:
                _art_cache.popitem(last=False)
    return image


def key_art(art: Image.Image, size: Tuple[int, int], brightness: float) -> Image.Image:
    """The art cropped square, scaled to the key and dimmed for text on top."""
    side = min(art.size)
    art = art.crop(((art.width - side) // 2, (art.height - side) // 2,
                    (art.width + side) // 2, (art.height + side) // 2)).resize(tuple(size), Image.LANCZOS)
    return ImageEnhance.Brightness(art).enhance(brightness)


class NowPlaying(Widget):
    id = 'now_playing'
    name = 'Now Playing'
    version = '1.0.0'
    description = "The playing track's title and artist, over its album art."
    author = 'StreamDock'
    states = ('playing', 'paused', 'stopped', 'none')
    options = [
        Option.string('player', default='', label='Player', description=_mpris.PLAYER_OPTION_DESCRIPTION),
        Option.bool('show_art', default=True, label='Album art background'),
        Option.int('art_brightness', default=45, minimum=0, maximum=100, label='Art brightness (%)'),
        Option.bool('toggle_on_press', default=True, label='Press plays / pauses'),
        Option.int('interval', default=2, minimum=1, maximum=60, label='Check every (s)'),
        Option.color('color', default='#ffffff', label='Text colour'),
        Option.color('background', default='#000000', label='Background'),
    ]

    def setup(self, ctx):
        self.status = _mpris.PlayerStatus()
        self.art: Optional[Image.Image] = None
        self.update(ctx, _mpris.current(ctx.options['player']))
        ctx.every(ctx.options['interval'], lambda: self.check(ctx))

    def on_show(self, ctx):
        self.check(ctx)

    def check(self, ctx, poll=True):
        # A check after a press must run even while a poll is in flight: that
        # poll may have read the player before the press.
        ctx.run_in_background(lambda: _mpris.current(ctx.options['player']),
                              then=lambda status: self.update(ctx, status), skip_if_running=poll)

    def update(self, ctx, status):
        previous, self.status = self.status, status
        ctx.set_state(status.status)
        if status.art_url != previous.art_url:
            self.art = None
            self.request_art(ctx)
        if (status.status, status.title, status.artist) != (previous.status, previous.title, previous.artist):
            ctx.request_render()

    def request_art(self, ctx):
        url = self.status.art_url
        if url and ctx.options['show_art']:
            ctx.run_in_background(lambda: fetch_art(url), then=lambda art: self.set_art(ctx, url, art))

    def set_art(self, ctx, url, art):
        if url != self.status.art_url:
            return
        # Scaled and dimmed once here, not on every frame.
        self.art = None if art is None else key_art(art, ctx.size, ctx.options['art_brightness'] / 100)
        ctx.request_render()

    def on_press(self, ctx):
        if ctx.options['toggle_on_press'] and self.status.player:
            player = self.status.player
            ctx.run_in_background(lambda: _mpris.call(player, 'PlayPause'), then=lambda _: self.check(ctx, poll=False))

    def render(self, ctx):
        options = ctx.options
        width, height = ctx.size
        image, canvas = draw.canvas(ctx.size, options['background'])
        if self.art is not None:
            image.paste(self.art)

        if self.status.status == 'none' or not self.status.title:
            draw.centered_text(canvas, (8, 8, width - 8, height - 8),
                               'Nothing\nplaying' if self.status.status == 'none' else 'No title',
                               color=options['color'], bold=False)
            return image

        pad = 6
        title_font = draw.font(17)
        artist_font = draw.font(13, bold=False)
        artist_lines = draw.wrap(canvas, self.status.artist, artist_font, width - 2 * pad, 1)
        title_lines = draw.wrap(canvas, self.status.title, title_font, width - 2 * pad, 4 - len(artist_lines))
        y = pad
        for line in title_lines:
            canvas.text((width / 2, y), line, font=title_font, fill=options['color'], anchor='mt')
            y += 20
        for line in artist_lines:
            canvas.text((width / 2, height - pad), line, font=artist_font, fill=options['color'], anchor='mb')
        if self.status.status != 'playing':
            canvas.rectangle((width - 18, 6, width - 14, 18), fill=options['color'])
            canvas.rectangle((width - 10, 6, width - 6, 18), fill=options['color'])
        return image
