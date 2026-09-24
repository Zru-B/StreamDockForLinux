from streamdock_sdk import Option, Widget, draw
from StreamDock.widgets.builtin import _common

FORMATS = ['weekday_day_month', 'day_month', 'iso', 'numeric']


class DateWidget(Widget):
    id = 'date'
    name = 'Date'
    version = '1.0.0'
    description = "Today's date: weekday, day and month, or a compact format."
    author = 'StreamDock'
    options = [
        Option.choice('format', FORMATS, default='weekday_day_month', label='Format',
                      description='weekday_day_month: Wed / 23 / Sep. day_month: 23 Sep. '
                                  'iso: 2026-09-23. numeric: 23/09.'),
        Option.color('color', default='#ffffff', label='Text colour'),
        Option.color('accent', default='#e53935', label='Weekday colour'),
        Option.color('background', default='#000000', label='Background'),
    ]

    def setup(self, ctx):
        ctx.every(60, align=True)

    def render(self, ctx):
        options = ctx.options
        today = _common.now()
        width, height = ctx.size
        image, canvas = draw.canvas(ctx.size, options['background'])
        fmt = options['format']

        if fmt == 'weekday_day_month':
            band = height // 4
            draw.centered_text(canvas, (8, 6, width - 8, 6 + band), today.strftime('%a').upper(),
                               color=options['accent'])
            draw.centered_text(canvas, (8, 8 + band, width - 8, height - band - 6), str(today.day),
                               color=options['color'])
            draw.centered_text(canvas, (8, height - band - 4, width - 8, height - 6),
                               today.strftime('%b').upper(), color=options['color'], bold=False)
            return image

        text = {
            'day_month': f'{today.day}\n{today.strftime("%b")}',
            'iso': today.strftime('%Y\n%m-%d'),
            'numeric': today.strftime('%d/%m'),
        }[fmt]
        draw.centered_text(canvas, (8, 8, width - 8, height - 8), text, color=options['color'])
        return image
