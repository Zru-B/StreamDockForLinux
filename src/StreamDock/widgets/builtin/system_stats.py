import time
from typing import Optional, Tuple

from streamdock_sdk import Option, Widget, draw


def read_cpu_times(path: str = '/proc/stat') -> Tuple[int, int]:
    """(busy, total) jiffies from the aggregate cpu line."""
    with open(path, encoding='ascii') as handle:
        fields = [int(value) for value in handle.readline().split()[1:]]
    idle = fields[3] + (fields[4] if len(fields) > 4 else 0)
    total = sum(fields[:8])
    return total - idle, total


def read_memory_percent(path: str = '/proc/meminfo') -> float:
    values = {}
    with open(path, encoding='ascii') as handle:
        for line in handle:
            name, _, rest = line.partition(':')
            values[name] = int(rest.split()[0])
    total = values['MemTotal']
    return 100.0 * (total - values['MemAvailable']) / total


class SystemStats(Widget):
    id = 'system_stats'
    name = 'System Stats'
    version = '1.0.0'
    description = 'CPU load and memory use, as a percentage with a bar.'
    author = 'StreamDock'
    # 'high' once any shown figure passes 85%; the badge carries the first one.
    states = ('normal', 'high')
    supports_badge = True
    options = [
        Option.choice('metric', ['cpu', 'ram', 'both'], default='both', label='Show'),
        Option.int('interval', default=2, minimum=1, maximum=60, label='Update every (s)'),
        Option.color('color', default='#ffffff', label='Text colour'),
        Option.color('bar_color', default='#43a047', label='Bar colour'),
        Option.color('alert_color', default='#e53935', label='Bar colour above 85%'),
        Option.color('background', default='#000000', label='Background'),
    ]

    def setup(self, ctx):
        self.previous: Optional[Tuple[int, int]] = None
        self.cpu: Optional[float] = None
        self.ram: Optional[float] = None
        self.last_displayed = None
        # CPU load is a difference of two readings; take both now so the
        # first frame has a number rather than waiting a whole interval.
        self.sample(ctx)
        time.sleep(0.2)
        self.sample(ctx)
        ctx.every(ctx.options['interval'], lambda: self.sample(ctx))

    def on_show(self, ctx):
        self.sample(ctx)

    def sample(self, ctx):
        try:
            busy, total = read_cpu_times()
            if self.previous is not None and total > self.previous[1]:
                self.cpu = 100.0 * (busy - self.previous[0]) / (total - self.previous[1])
            self.previous = (busy, total)
            self.ram = read_memory_percent()
        except (OSError, ValueError, KeyError, IndexError):
            ctx.log.exception('cannot read /proc')
        shown = [value for label, value in self.rows(ctx.options) if value is not None]
        ctx.set_state('high' if any(value > 85 for value in shown) else 'normal')
        ctx.set_badge(f'{shown[0]:.0f}%' if shown else None)
        # The key shows whole percentages; a redraw for 41.2 -> 41.4 would
        # push an identical frame to the device every interval.
        displayed = self.displayed(ctx.options)
        if displayed != self.last_displayed:
            self.last_displayed = displayed
            ctx.request_render()

    def displayed(self, options):
        return tuple(None if value is None else f'{value:.0f}' for _label, value in self.rows(options))

    def rows(self, options):
        rows = [('CPU', self.cpu), ('RAM', self.ram)]
        if options['metric'] != 'both':
            rows = [row for row in rows if row[0].lower() == options['metric']]
        return rows

    def render(self, ctx):
        options = ctx.options
        width, height = ctx.size
        image, canvas = draw.canvas(ctx.size, options['background'])
        rows = self.rows(options)
        row_height = (height - 8) // len(rows)
        for index, (label, value) in enumerate(rows):
            top = 4 + index * row_height
            bar_top = top + row_height - 14
            text = f'{label} {value:.0f}%' if value is not None else f'{label} …'
            draw.centered_text(canvas, (8, top + 2, width - 8, bar_top - 2), text, color=options['color'])
            canvas.rectangle((10, bar_top, width - 10, bar_top + 8), outline='#606060')
            if value is not None:
                fill = options['alert_color'] if value > 85 else options['bar_color']
                right = 11 + int((width - 22) * min(max(value, 0.0), 100.0) / 100)
                if right > 11:
                    canvas.rectangle((11, bar_top + 1, right, bar_top + 7), fill=fill)
        return image
