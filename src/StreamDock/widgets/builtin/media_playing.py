from streamdock_sdk import Option, Widget
from StreamDock.infrastructure import mpris as _mpris
from StreamDock.widgets.builtin import _common


class MediaPlaying(Widget):
    id = 'media_playing'
    name = 'Media Playing'
    version = '1.0.0'
    description = 'Whether a media player is playing; pressing the key can play or pause it.'
    author = 'StreamDock'
    states = ('playing', 'paused', 'stopped', 'none')
    options = [
        Option.string('player', default='', label='Player', description=_mpris.PLAYER_OPTION_DESCRIPTION),
        Option.bool('toggle_on_press', default=True, label='Press plays / pauses'),
        Option.int('interval', default=2, minimum=1, maximum=60, label='Check every (s)'),
        Option.color('playing_color', default='#1b5e20', label='Playing background'),
        Option.color('idle_color', default='#303030', label='Paused background'),
        Option.color('color', default='#ffffff', label='Icon colour'),
    ]

    def setup(self, ctx):
        self.status = _mpris.current(ctx.options['player'], with_metadata=False)
        ctx.set_state(self.status.status)
        ctx.every(ctx.options['interval'], lambda: self.check(ctx))

    def on_show(self, ctx):
        self.check(ctx)

    def check(self, ctx, poll=True):
        # A check after a press must run even while a poll is in flight: that
        # poll may have read the player before the press.
        ctx.run_in_background(lambda: _mpris.current(ctx.options['player'], with_metadata=False),
                              then=lambda status: self.update(ctx, status), skip_if_running=poll)

    def update(self, ctx, status):
        changed = status.status != self.status.status
        self.status = status
        if changed:
            ctx.set_state(status.status)
            ctx.request_render()

    def on_press(self, ctx):
        if ctx.options['toggle_on_press'] and self.status.player:
            player = self.status.player
            ctx.run_in_background(lambda: _mpris.call(player, 'PlayPause'), then=lambda _: self.check(ctx, poll=False))

    def render(self, ctx):
        options = ctx.options
        status = self.status.status
        playing = status == 'playing'
        caption = {'playing': 'PLAYING', 'paused': 'PAUSED', 'stopped': 'STOPPED'}.get(status, 'NO PLAYER')
        image, canvas, scale, (left, top, right, bottom) = _common.status_tile(
            ctx.size, options['playing_color'] if playing else options['idle_color'], caption, options['color'])
        width, height = right - left, bottom - top
        centre_x = (left + right) / 2
        if playing:
            bar = width * 0.18
            gap = width * 0.14
            for x in (centre_x - gap / 2 - bar, centre_x + gap / 2):
                canvas.rounded_rectangle((x, top + height * 0.05, x + bar, bottom - height * 0.05),
                                         radius=bar / 4, fill=options['color'])
        else:
            triangle_w = height * 0.8
            x0 = centre_x - triangle_w * 0.4
            canvas.polygon([(x0, top + height * 0.05), (x0, bottom - height * 0.05),
                            (x0 + triangle_w, top + height / 2)],
                           fill=options['color'] if status != 'none' else None,
                           outline=options['color'], width=3 * scale)
        return _common.downsample(image, ctx.size)
