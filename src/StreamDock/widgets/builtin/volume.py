from streamdock_sdk import Option, draw
from StreamDock.widgets.builtin import _common, _volume

# The gauge is a 270-degree arc open at the bottom; Pillow counts degrees
# clockwise from three o'clock.
GAUGE_START, GAUGE_SWEEP = 135, 270


class Volume(_volume.VolumeWidget):
    """The default speaker's volume on one key: press raises, double press lowers, hold mutes."""

    id = 'volume'
    name = 'Volume'
    version = '1.0.0'
    description = ('The speaker volume on one key, as a gauge. Press to raise it by the step, double press '
                   'to lower it, hold to mute or unmute.')
    author = 'StreamDock'
    states = _volume.STATES
    supports_badge = True
    options = [
        *_volume.STEP_OPTIONS,
        Option.color('color', default='#ffffff', label='Icon colour'),
        Option.color('gauge_color', default='#29b6f6', label='Gauge colour'),
        Option.color('muted_color', default='#e53935', label='Gauge colour when muted'),
        Option.color('background', default='#000000', label='Background'),
    ]

    def on_press(self, ctx):
        self.change_volume(ctx, ctx.options['step'])

    def on_double_press(self, ctx):
        self.change_volume(ctx, -ctx.options['step'])

    def on_long_press(self, ctx):
        self.toggle_mute(ctx)

    def render(self, ctx):
        options = ctx.options
        image, canvas, scale = _common.supersampled(ctx.size, options['background'])
        width, height = image.size
        volume, muted = self.level.volume, self.level.muted
        color = options['color']

        ring = (8 * scale, 8 * scale, width - 8 * scale, height - 8 * scale)
        thickness = 9 * scale
        canvas.arc(ring, GAUGE_START, GAUGE_START + GAUGE_SWEEP, fill='#37474f', width=thickness)
        if volume:
            fraction = min(volume / options['max_volume'], 1.0)
            canvas.arc(ring, GAUGE_START, GAUGE_START + GAUGE_SWEEP * fraction,
                       fill=options['muted_color'] if muted else options['gauge_color'], width=thickness)

        icon = (34 * scale, 26 * scale, 80 * scale, 62 * scale)
        _volume.draw_speaker(canvas, icon, color, scale, waves=0 if muted else 2)
        if muted:
            _common.slash(canvas, icon, options['muted_color'], 5 * scale)
        caption = '?' if volume is None else 'MUTE' if muted else f'{volume}%'
        draw.centered_text(canvas, (32 * scale, 66 * scale, width - 32 * scale, 88 * scale), caption, color=color)
        return _common.downsample(image, ctx.size)
