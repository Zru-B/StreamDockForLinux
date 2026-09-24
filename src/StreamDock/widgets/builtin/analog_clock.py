import math

from streamdock_sdk import Option, Widget
from StreamDock.widgets.builtin import _common


def _hand(canvas, center, angle_deg, length, width, color):
    radians = math.radians(angle_deg - 90)
    end = (center[0] + length * math.cos(radians), center[1] + length * math.sin(radians))
    canvas.line((center, end), fill=color, width=width)
    radius = width / 2
    canvas.ellipse((end[0] - radius, end[1] - radius, end[0] + radius, end[1] + radius), fill=color)


class AnalogClock(Widget):
    id = 'analog_clock'
    name = 'Analog Clock'
    version = '1.0.0'
    description = 'A clock face with hour and minute hands, optionally a second hand.'
    author = 'StreamDock'
    options = [
        Option.bool('show_seconds', default=False, label='Second hand'),
        Option.string('timezone', default='', label='Time zone',
                      description='For example Asia/Tokyo. Empty for local time.'),
        Option.color('face_color', default='#ffffff', label='Face and ticks'),
        Option.color('hand_color', default='#ffffff', label='Hands'),
        Option.color('second_hand_color', default='#e53935', label='Second hand'),
        Option.color('background', default='#000000', label='Background'),
    ]

    def setup(self, ctx):
        self.zone = _common.parse_zone(ctx.options['timezone'])
        ctx.every(1 if ctx.options['show_seconds'] else 60, align=True)

    def render(self, ctx):
        options = ctx.options
        moment = _common.now(self.zone)
        image, canvas, scale = _common.supersampled(ctx.size, options['background'])
        width, height = image.size
        center = (width / 2, height / 2)
        radius = min(width, height) / 2 - 5 * scale

        canvas.ellipse((center[0] - radius, center[1] - radius, center[0] + radius, center[1] + radius),
                       outline=options['face_color'], width=2 * scale)
        for tick in range(12):
            radians = math.radians(tick * 30)
            inner = radius * (0.78 if tick % 3 == 0 else 0.86)
            outer = radius * 0.94
            canvas.line(
                (center[0] + inner * math.sin(radians), center[1] - inner * math.cos(radians),
                 center[0] + outer * math.sin(radians), center[1] - outer * math.cos(radians)),
                fill=options['face_color'], width=(3 if tick % 3 == 0 else 2) * scale)

        minutes = moment.minute + moment.second / 60
        hours = (moment.hour % 12) + minutes / 60
        _hand(canvas, center, hours * 30, radius * 0.50, 5 * scale, options['hand_color'])
        _hand(canvas, center, minutes * 6, radius * 0.76, 3 * scale, options['hand_color'])
        if options['show_seconds']:
            _hand(canvas, center, moment.second * 6, radius * 0.84, 1 * scale, options['second_hand_color'])
        dot = 4 * scale
        canvas.ellipse((center[0] - dot, center[1] - dot, center[0] + dot, center[1] + dot),
                       fill=options['second_hand_color'] if options['show_seconds'] else options['hand_color'])
        return _common.downsample(image, ctx.size)
