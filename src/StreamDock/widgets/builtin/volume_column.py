from streamdock_sdk import Option, draw
from StreamDock.widgets.builtin import _common, _volume

# Which third of the column's level bar each button shows, counted from the bottom.
SEGMENTS = {'down': 0, 'mute': 1, 'up': 2}


class VolumeColumn(_volume.VolumeWidget):
    """
    One button of a three-key volume column: volume up, mute, volume down.

    Put three keys with this widget in one column of the device, top to
    bottom 'up', 'mute', 'down'. Each shows its third of a shared level bar,
    so the column reads as one tall meter.
    """

    id = 'volume_column'
    name = 'Volume Column (1x3)'
    version = '1.0.0'
    description = ('One button of a 1x3 volume column: up, mute or down. Use three keys stacked in one '
                   'column - up on top, mute in the middle, down below - and they share one level bar.')
    author = 'StreamDock'
    states = _volume.STATES
    supports_badge = True
    options = [
        Option.choice('button', ['up', 'mute', 'down'], default='mute', label='Button',
                      description='up for the top key of the column, mute for the middle, down for the bottom.'),
        *_volume.STEP_OPTIONS,
        Option.bool('show_level_bar', default=True, label='Show level bar'),
        Option.color('color', default='#ffffff', label='Icon colour'),
        Option.color('bar_color', default='#29b6f6', label='Level bar colour'),
        Option.color('muted_color', default='#b71c1c', label='Muted background'),
        Option.color('background', default='#1c262b', label='Background'),
    ]

    def on_press(self, ctx):
        button = ctx.options['button']
        if button == 'mute':
            self.toggle_mute(ctx)
        else:
            step = ctx.options['step']
            self.change_volume(ctx, step if button == 'up' else -step)

    def render(self, ctx):
        options = ctx.options
        button = options['button']
        muted = self.level.muted
        background = options['muted_color'] if button == 'mute' and muted else options['background']
        image, canvas, scale = _common.supersampled(ctx.size, background)
        width, height = image.size
        left = 8 * scale
        if options['show_level_bar']:
            self.draw_bar(canvas, options, scale, height)
            left = 26 * scale
        right = width - 8 * scale
        color = options['color']

        if button == 'mute':
            icon = (left + 8 * scale, 12 * scale, right - 8 * scale, 70 * scale)
            _volume.draw_speaker(canvas, icon, color, scale, waves=0 if muted else 2)
            if muted:
                _common.slash(canvas, icon, color, 5 * scale)
            volume = self.level.volume
            caption = 'MUTED' if muted else '?' if volume is None else f'{volume}%'
            draw.centered_text(canvas, (left, 76 * scale, right, height - 8 * scale), caption, color=color)
        else:
            middle = height / 2
            speaker = (left, middle - 30 * scale, left + (right - left) * 0.62, middle + 30 * scale)
            _volume.draw_speaker(canvas, speaker, color, scale, waves=0)
            sign_left = left + (right - left) * 0.52
            _volume.draw_sign(canvas, (sign_left, middle - 17 * scale, right, middle + 17 * scale),
                              '+' if button == 'up' else '-', color, scale)
        return _common.downsample(image, ctx.size)

    def draw_bar(self, canvas, options, scale, height):
        """This key's third of the column's level bar, filled from the bottom."""
        left, right = 8 * scale, 18 * scale
        top, bottom = 6 * scale, height - 6 * scale
        canvas.rounded_rectangle((left, top, right, bottom), radius=3 * scale, fill='#37474f')
        volume = self.level.volume
        if volume is None:
            return
        segment = SEGMENTS[options['button']]
        fraction = min(max(volume / options['max_volume'] * 3 - segment, 0.0), 1.0)
        if fraction > 0:
            fill = '#78909c' if self.level.muted else options['bar_color']
            canvas.rounded_rectangle((left, bottom - (bottom - top) * fraction, right, bottom),
                                     radius=3 * scale, fill=fill)
