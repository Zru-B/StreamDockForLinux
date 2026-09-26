"""
Download and upload speed, with a graph of the last minute or so.

Speeds are the difference of two readings of ``/proc/net/dev``. By default
only physical interfaces count - the ones backed by a device - so traffic
isn't counted twice through a VPN tunnel, a bridge or a container's veth.
"""

import fnmatch
import os
import time
from collections import deque
from typing import Dict, Optional, Tuple

from streamdock_sdk import Option, Widget, draw
from StreamDock.widgets.builtin import _common

# Samples kept for the graph.
HISTORY = 40

# Tests replace this to control time.
clock = time.monotonic


def read_counters(path: str = '/proc/net/dev') -> Dict[str, Tuple[int, int]]:
    """(received, sent) bytes per interface."""
    counters = {}
    with open(path, encoding='ascii') as handle:
        for line in handle:
            name, colon, rest = line.partition(':')
            fields = rest.split()
            if not colon or len(fields) < 9:
                continue
            counters[name.strip()] = (int(fields[0]), int(fields[8]))
    return counters


def is_physical(name: str, sys_net: str = '/sys/class/net') -> bool:
    return os.path.exists(os.path.join(sys_net, name, 'device'))


def selected(names, patterns: str, physical=is_physical):
    """The interfaces to count: those matching ``patterns``, or every physical one when it's empty."""
    wanted = [pattern.strip() for pattern in patterns.split(',') if pattern.strip()]
    if wanted:
        return [name for name in names if any(fnmatch.fnmatch(name, pattern) for pattern in wanted)]
    return [name for name in names if name != 'lo' and physical(name)]


def format_rate(bytes_per_second: float, bits: bool) -> str:
    """A short rate such as '1.2 MB/s' or '850 kb/s'."""
    value = bytes_per_second * 8 if bits else bytes_per_second
    suffix = 'b/s' if bits else 'B/s'
    for prefix in ('', 'k', 'M', 'G'):
        if value < 999.5 or prefix == 'G':
            if prefix == '':
                return f'{value:.0f} {suffix}'
            return f'{value:.1f} {prefix}{suffix}' if value < 9.95 else f'{value:.0f} {prefix}{suffix}'
        value /= 1000


class NetworkSpeed(Widget):
    id = 'network_speed'
    name = 'Network Speed'
    version = '1.0.0'
    description = 'Download and upload speed right now, over a graph of the recent past.'
    author = 'StreamDock'
    states = ('idle', 'active')
    supports_badge = True
    options = [
        Option.string('interfaces', default='', label='Interfaces',
                      description='Comma-separated names or patterns, e.g. "wlan0" or "en*". '
                                  'Empty: every physical interface.'),
        Option.choice('units', ['bytes', 'bits'], default='bytes', label='Units',
                      description='bytes: MB/s, as file managers show. bits: Mb/s, as speed tests show.'),
        Option.int('interval', default=2, minimum=1, maximum=60, label='Update every (s)'),
        Option.int('idle_below', default=10, minimum=0, maximum=100000, label='Idle below (kB/s)',
                   description='Below this, in both directions, the state is idle.'),
        Option.color('down_color', default='#29b6f6', label='Download colour'),
        Option.color('up_color', default='#ffa726', label='Upload colour'),
        Option.color('color', default='#ffffff', label='Text colour'),
        Option.color('background', default='#000000', label='Background'),
    ]

    def setup(self, ctx):
        self.previous: Optional[Tuple[float, int, int]] = None
        self.down: Optional[float] = None
        self.up: Optional[float] = None
        self.history: deque = deque(maxlen=HISTORY)
        self.sample(ctx)
        ctx.every(ctx.options['interval'], lambda: self.sample(ctx))

    def on_show(self, ctx):
        # The first reading after a pause would average over the whole pause.
        self.previous = None
        self.sample(ctx)

    def sample(self, ctx):
        try:
            counters = read_counters()
        except (OSError, ValueError):
            ctx.log.exception('cannot read /proc/net/dev')
            return
        names = selected(counters, ctx.options['interfaces'])
        received = sum(counters[name][0] for name in names)
        sent = sum(counters[name][1] for name in names)
        now = clock()
        if self.previous is not None and now > self.previous[0]:
            elapsed = now - self.previous[0]
            # A counter going backwards (interface reset) reads as zero, not negative.
            self.down = max(received - self.previous[1], 0) / elapsed
            self.up = max(sent - self.previous[2], 0) / elapsed
            self.history.append((self.down, self.up))
            idle = ctx.options['idle_below'] * 1000
            ctx.set_state('idle' if self.down < idle and self.up < idle else 'active')
            ctx.set_badge(format_rate(self.down, ctx.options['units'] == 'bits').replace(' ', ''))
            ctx.request_render()
        self.previous = (now, received, sent)

    def render(self, ctx):
        options = ctx.options
        bits = options['units'] == 'bits'
        image, canvas, scale = _common.supersampled(ctx.size, options['background'])
        width, height = image.size

        self.draw_graph(canvas, options, (0, height * 0.58, width, height))
        rows = [(self.down, options['down_color'], False), (self.up, options['up_color'], True)]
        texts = ['…' if value is None else format_rate(value, bits) for value, _, _ in rows]
        # One size for both rows, so they line up.
        text_box = (26 * scale, 0, width - 4 * scale, 28 * scale)
        longest = max(texts, key=lambda text: canvas.textlength(text, font=draw.font(10 * scale)))
        text_font = draw.fit_font(canvas, longest, text_box[2] - text_box[0], text_box[3], start=text_box[3])
        for row, ((_, color, pointing_up), text) in enumerate(zip(rows, texts)):
            top = (6 + row * 30) * scale
            draw_arrow(canvas, (6 * scale, top + 5 * scale, 22 * scale, top + 23 * scale), color, pointing_up)
            draw.centered_text(canvas, (text_box[0], top, text_box[2], top + text_box[3]), text,
                               color=options['color'], text_font=text_font)
        return _common.downsample(image, ctx.size)

    def draw_graph(self, canvas, options, box):
        """Download as a filled area, upload as a line, both on one scale."""
        if len(self.history) < 2:
            return
        left, top, right, bottom = box
        peak = max(max(down, up) for down, up in self.history) or 1.0
        step = (right - left) / (HISTORY - 1)
        start = right - step * (len(self.history) - 1)

        def point(index, value):
            return start + index * step, bottom - (bottom - top) * value / peak

        downs = [point(index, down) for index, (down, _) in enumerate(self.history)]
        canvas.polygon([(start, bottom), *downs, (right, bottom)], fill=_dim(options['down_color']))
        canvas.line(downs, fill=options['down_color'], width=6)
        ups = [point(index, up) for index, (_, up) in enumerate(self.history)]
        canvas.line(ups, fill=options['up_color'], width=6)


def _dim(color: str) -> str:
    """``color`` at 40% brightness, for the area under the download line."""
    from PIL import ImageColor  # pylint: disable=import-outside-toplevel
    red, green, blue = ImageColor.getrgb(color)[:3]
    return f'#{int(red * 0.4):02x}{int(green * 0.4):02x}{int(blue * 0.4):02x}'


def draw_arrow(canvas, box, color: str, pointing_up: bool) -> None:
    left, top, right, bottom = box
    middle = (left + right) / 2
    shaft = (right - left) * 0.18
    head = top + (bottom - top) * 0.5
    if pointing_up:
        canvas.polygon([(middle, top), (right, head), (middle + shaft, head), (middle + shaft, bottom),
                        (middle - shaft, bottom), (middle - shaft, head), (left, head)], fill=color)
    else:
        head = bottom - (bottom - top) * 0.5
        canvas.polygon([(middle, bottom), (right, head), (middle + shaft, head), (middle + shaft, top),
                        (middle - shaft, top), (middle - shaft, head), (left, head)], fill=color)
