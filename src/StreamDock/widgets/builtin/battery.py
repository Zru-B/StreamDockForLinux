"""
Battery charge, from ``/sys/class/power_supply``.

That covers the laptop's battery and the wireless devices whose driver
reports one: many Logitech mice and keyboards, some headsets and game
controllers. They're found by name or model, e.g. "MX Master".
"""

import os
from dataclasses import dataclass
from typing import List, Optional

from streamdock_sdk import Option, Widget, draw
from StreamDock.widgets.builtin import _common

POWER_SUPPLY = '/sys/class/power_supply'

# Devices that report only a coarse level, not a percentage.
LEVELS = {'critical': 5, 'low': 15, 'normal': 50, 'high': 80, 'full': 100}

GOOD, WARN, CRITICAL = '#43a047', '#ffb300', '#e53935'


@dataclass
class Reading:
    percent: int
    # Charging, Discharging, Full, Not charging or Unknown, as the kernel says.
    status: str = 'Unknown'
    # True when the device reports only a level such as 'Low'.
    approximate: bool = False


def _read(folder: str, name: str) -> str:
    try:
        with open(os.path.join(folder, name), encoding='utf-8') as handle:
            return handle.read().strip()
    except OSError:
        return ''


def _reading(folder: str) -> Optional[Reading]:
    status = _read(folder, 'status') or 'Unknown'
    capacity = _read(folder, 'capacity')
    if capacity.isdigit():
        return Reading(min(int(capacity), 100), status)
    level = LEVELS.get(_read(folder, 'capacity_level').lower())
    return None if level is None else Reading(level, status, approximate=True)


def find_batteries(device: str, root: str = POWER_SUPPLY) -> List[str]:
    """
    The folders to read: the system batteries when ``device`` is empty, else
    every battery whose name, model or maker contains ``device``.
    """
    try:
        names = sorted(os.listdir(root))
    except OSError:
        return []
    wanted = device.strip().lower()
    found = []
    for name in names:
        folder = os.path.join(root, name)
        if _read(folder, 'type') != 'Battery':
            continue
        if wanted:
            text = ' '.join((name, _read(folder, 'model_name'), _read(folder, 'manufacturer'))).lower()
            if wanted in text:
                found.append(folder)
        elif _read(folder, 'scope') != 'Device':
            # 'Device' marks a peripheral's battery; the laptop's has no scope or 'System'.
            found.append(folder)
    return found


def read_battery(device: str, root: str = POWER_SUPPLY) -> Optional[Reading]:
    """One reading for all matching batteries: a laptop with two counts as one."""
    readings = [reading for reading in map(_reading, find_batteries(device, root)) if reading is not None]
    if not readings:
        return None
    statuses = {reading.status for reading in readings}
    status = ('Charging' if 'Charging' in statuses else 'Discharging' if 'Discharging' in statuses
              else readings[0].status)
    percent = round(sum(reading.percent for reading in readings) / len(readings))
    return Reading(percent, status, any(reading.approximate for reading in readings))


class Battery(Widget):
    id = 'battery'
    name = 'Battery'
    version = '1.0.0'
    description = ("Battery charge: the laptop's, or a wireless mouse's, keyboard's or headset's that "
                   'reports one. Shows a bolt while charging and turns red when low.')
    author = 'StreamDock'
    states = ('charging', 'discharging', 'full', 'low', 'unavailable')
    supports_badge = True
    options = [
        Option.string('device', default='', label='Device',
                      description='Empty: the laptop battery. Otherwise part of a name or model, '
                                  'e.g. "MX Master" or "hidpp_battery_0".'),
        Option.string('label', default='', label='Label', description='A short name shown above the battery.'),
        Option.int('low', default=20, minimum=1, maximum=90, label='Low below (%)'),
        Option.int('interval', default=30, minimum=5, maximum=600, label='Check every (s)'),
        Option.color('color', default='#ffffff', label='Text and outline colour'),
        Option.color('background', default='#000000', label='Background'),
    ]

    def setup(self, ctx):
        self.reading: Optional[Reading] = read_battery(ctx.options['device'])
        self.report(ctx)
        ctx.every(ctx.options['interval'], lambda: self.check(ctx))

    def on_show(self, ctx):
        self.check(ctx)

    def on_press(self, ctx):
        # Check now, e.g. right after plugging the charger in.
        self.check(ctx)

    def check(self, ctx):
        ctx.run_in_background(lambda: read_battery(ctx.options['device']),
                              then=lambda reading: self.update(ctx, reading))

    def update(self, ctx, reading):
        if reading != self.reading:
            self.reading = reading
            self.report(ctx)
            ctx.request_render()

    def state_name(self, low: int) -> str:
        reading = self.reading
        if reading is None:
            return 'unavailable'
        if reading.status == 'Charging':
            return 'charging'
        if reading.status == 'Full' or (reading.percent >= 100 and reading.status != 'Discharging'):
            return 'full'
        return 'low' if reading.percent <= low else 'discharging'

    def report(self, ctx):
        ctx.set_state(self.state_name(ctx.options['low']))
        ctx.set_badge(None if self.reading is None else f'{self.reading.percent}%')

    def render(self, ctx):
        options = ctx.options
        image, canvas, scale = _common.supersampled(ctx.size, options['background'])
        width, height = image.size
        color = options['color']
        reading = self.reading

        top = 8 * scale
        if options['label']:
            draw.centered_text(canvas, (6 * scale, 4 * scale, width - 6 * scale, 22 * scale), options['label'],
                               color=color, bold=False)
            top = 26 * scale
        body = (12 * scale, top, width - 22 * scale, top + 40 * scale)
        fill = None
        if reading is not None:
            fill = (CRITICAL if reading.percent <= options['low']
                    else WARN if reading.percent < 50 else GOOD)
        draw_battery(canvas, body, color, reading.percent if reading else 0, fill, scale)
        if reading is not None and reading.status == 'Charging':
            draw_bolt(canvas, body, options['background'], scale)

        if reading is None:
            caption = 'N/A'
        elif reading.approximate:
            caption = next((name for name, value in LEVELS.items() if value == reading.percent), '?').upper()
        else:
            caption = f'{reading.percent}%'
        draw.centered_text(canvas, (8 * scale, body[3] + 6 * scale, width - 8 * scale, height - 6 * scale),
                           caption, color=color)
        return _common.downsample(image, ctx.size)


def draw_battery(canvas, box, color: str, percent: int, fill: Optional[str], scale: int) -> None:
    """A battery lying on its side, filled from the left to ``percent``."""
    left, top, right, bottom = box
    line = 4 * scale
    canvas.rounded_rectangle(box, radius=7 * scale, outline=color, width=line)
    nub_height = (bottom - top) * 0.40
    middle = (top + bottom) / 2
    canvas.rounded_rectangle((right + 2 * scale, middle - nub_height / 2, right + 9 * scale, middle + nub_height / 2),
                             radius=2 * scale, fill=color)
    if fill is not None and percent > 0:
        inset = line + 3 * scale
        inner_right = left + inset + (right - left - 2 * inset) * min(percent, 100) / 100
        canvas.rounded_rectangle((left + inset, top + inset, max(inner_right, left + inset + 2 * scale),
                                  bottom - inset), radius=3 * scale, fill=fill)


def draw_bolt(canvas, box, outline: str, scale: int) -> None:
    """A lightning bolt over the battery, outlined so it shows on any fill."""
    left, top, right, bottom = box
    size = bottom - top
    x, y = (left + right) / 2, (top + bottom) / 2
    shape = [(0.16, -0.58), (-0.24, 0.08), (0.0, 0.08), (-0.14, 0.58), (0.26, -0.10), (0.02, -0.10)]
    points = [(x + dx * size, y + dy * size) for dx, dy in shape]
    # The outline goes around the outside, so it doesn't thin the bolt.
    canvas.line([*points, points[0]], fill=outline, width=6 * scale, joint='curve')
    canvas.polygon(points, fill='white')
