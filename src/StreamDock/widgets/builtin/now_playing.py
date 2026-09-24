import io
import urllib.parse
import urllib.request
from functools import lru_cache
from typing import Optional

from PIL import Image, ImageEnhance

from streamdock_sdk import Option, Widget, draw
from StreamDock.infrastructure import mpris as _mpris

ART_TIMEOUT = 5
MAX_ART_BYTES = 5 * 1024 * 1024


@lru_cache(maxsize=16)
def fetch_art(url: str) -> Optional[Image.Image]:
    """Album art from a file:// or http(s) URL, or None."""
    try:
        parsed = urllib.parse.urlparse(url)
        if parsed.scheme == 'file':
            image = Image.open(urllib.parse.unquote(parsed.path))
        elif parsed.scheme in ('http', 'https'):
            with urllib.request.urlopen(url, timeout=ART_TIMEOUT) as response:  # nosec - player-supplied art
                image = Image.open(io.BytesIO(response.read(MAX_ART_BYTES)))
        else:
            return None
        image.load()
        return image.convert('RGB')
    except (OSError, ValueError):
        return None


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

    def check(self, ctx):
        ctx.run_in_background(lambda: _mpris.current(ctx.options['player']),
                              then=lambda status: self.update(ctx, status))

    def update(self, ctx, status):
        previous, self.status = self.status, status
        ctx.set_state(status.status)
        if status.art_url != previous.art_url:
            self.art = None
            if status.art_url and ctx.options['show_art']:
                url = status.art_url
                ctx.run_in_background(lambda: fetch_art(url), then=lambda art: self.set_art(ctx, url, art))
        if (status.status, status.title, status.artist) != (previous.status, previous.title, previous.artist):
            ctx.request_render()

    def set_art(self, ctx, url, art):
        if url == self.status.art_url:
            self.art = art
            ctx.request_render()

    def on_press(self, ctx):
        if ctx.options['toggle_on_press'] and self.status.player:
            player = self.status.player
            ctx.run_in_background(lambda: _mpris.call(player, 'PlayPause'), then=lambda _: self.check(ctx))

    def render(self, ctx):
        options = ctx.options
        width, height = ctx.size
        image, canvas = draw.canvas(ctx.size, options['background'])
        if self.art is not None:
            art = self.art.copy()
            art.thumbnail((max(width, height) * 2,) * 2)
            side = min(art.size)
            art = art.crop(((art.width - side) // 2, (art.height - side) // 2,
                            (art.width + side) // 2, (art.height + side) // 2)).resize(ctx.size, Image.LANCZOS)
            image.paste(ImageEnhance.Brightness(art).enhance(options['art_brightness'] / 100))

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
