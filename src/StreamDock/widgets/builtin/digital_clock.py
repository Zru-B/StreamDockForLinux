from streamdock_sdk import Option, Widget, draw
from StreamDock.widgets.builtin import _common


class DigitalClock(Widget):
    id = 'digital_clock'
    name = 'Digital Clock'
    version = '1.0.0'
    description = 'The time as hours and minutes, optionally with seconds.'
    author = 'StreamDock'
    options = [
        Option.choice('format', ['24h', '12h'], default='24h', label='Format'),
        Option.bool('show_seconds', default=False, label='Show seconds'),
        Option.string('timezone', default='', label='Time zone',
                      description='For example Europe/London. Empty for local time.'),
        Option.color('color', default='#ffffff', label='Text colour'),
        Option.color('background', default='#000000', label='Background'),
    ]

    def setup(self, ctx):
        self.zone = _common.parse_zone(ctx.options['timezone'])
        ctx.every(1 if ctx.options['show_seconds'] else 60, align=True)

    def render(self, ctx):
        options = ctx.options
        moment = _common.now(self.zone)
        twelve_hour = options['format'] == '12h'
        hour = (moment.hour % 12 or 12) if twelve_hour else moment.hour
        text = f'{hour}:{moment.minute:02d}' if twelve_hour else f'{hour:02d}:{moment.minute:02d}'
        if options['show_seconds']:
            text += f':{moment.second:02d}'

        width, height = ctx.size
        image, canvas = draw.canvas(ctx.size, options['background'])
        main_bottom = int(height * 0.68) if twelve_hour else height - 8
        draw.centered_text(canvas, (6, 8, width - 6, main_bottom), text, color=options['color'])
        if twelve_hour:
            draw.centered_text(canvas, (10, main_bottom + 2, width - 10, height - 8),
                               'AM' if moment.hour < 12 else 'PM', color=options['color'], bold=False)
        return image
