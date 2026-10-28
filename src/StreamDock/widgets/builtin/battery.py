"""
Battery charge of the laptop and of connected devices.

Devices come from UPower, which knows the laptop's battery, wireless mice and
keyboards, and Bluetooth headphones through BlueZ. Without UPower they come
from ``/sys/class/power_supply``, which has the laptop and devices whose
kernel driver reports a battery (most Logitech receivers), but not Bluetooth
headphones.
"""

import os
import subprocess
from dataclasses import dataclass
from typing import List, Optional

from streamdock_sdk import Option, Widget, draw
from StreamDock.widgets.builtin import _common

POWER_SUPPLY = '/sys/class/power_supply'

# Devices that report only a coarse level, not a percentage.
LEVELS = {'critical': 5, 'low': 15, 'normal': 50, 'high': 80, 'full': 100}

GOOD, WARN, CRITICAL = '#43a047', '#ffb300', '#e53935'

# UPower's device kinds, as the key names them when the device has no model name.
KIND_NAMES = {
    'system': 'Laptop', 'mouse': 'Mouse', 'keyboard': 'Keyboard', 'headset': 'Headset',
    'headphones': 'Headphones', 'gaming-input': 'Controller', 'phone': 'Phone', 'tablet': 'Tablet',
    'touchpad': 'Touchpad', 'pen': 'Pen', 'speakers': 'Speaker', 'battery': 'Battery',
}

UPOWER_STATES = {'charging': 'Charging', 'discharging': 'Discharging', 'fully-charged': 'Full',
                 'pending-charge': 'Not charging'}


@dataclass
class Reading:
    percent: int
    # Charging, Discharging, Full, Not charging or Unknown, as the kernel says.
    status: str = 'Unknown'
    # True when the device reports only a level such as 'Low'.
    approximate: bool = False


@dataclass
class Device:
    """One battery-powered thing the key can show."""

    key: str            # stable identity: UPower's native path, or the sysfs folder name
    name: str           # what the key calls it: its model, or its kind
    kind: str           # 'system' for the laptop, else UPower's kind, e.g. 'mouse'
    reading: Reading


def combine(readings: List[Reading]) -> Reading:
    """One reading for several batteries: a laptop with two counts as one."""
    statuses = {reading.status for reading in readings}
    status = ('Charging' if 'Charging' in statuses else 'Discharging' if 'Discharging' in statuses
              else readings[0].status)
    percent = round(sum(reading.percent for reading in readings) / len(readings))
    return Reading(percent, status, any(reading.approximate for reading in readings))


def _system_first(system: List[Reading], others: List[Device]) -> List[Device]:
    laptop = [Device('system', KIND_NAMES['system'], 'system', combine(system))] if system else []
    return laptop + sorted(others, key=lambda device: (device.name.lower(), device.key))


# ----------------------------------------------------------------------
# UPower
# ----------------------------------------------------------------------

def _upower_blocks(text: str):
    """Each device in ``upower --dump`` output: its object path, kind and properties."""
    path, kind, properties = None, '', {}
    for line in text.splitlines() + ['Device: end']:
        if line.startswith(('Device:', 'Daemon:')):
            if path is not None:
                yield path, kind, properties
            path, kind, properties = (line.split(':', 1)[1].strip(), '', {}) if line.startswith('Device:') \
                else (None, '', {})
            continue
        stripped = line.strip()
        if not stripped or path is None:
            continue
        name, colon, value = stripped.partition(':')
        if colon:
            properties.setdefault(name.strip(), value.strip())
        elif not kind:
            kind = stripped


def parse_upower(text: str) -> List[Device]:
    system, others = [], []
    for path, kind, properties in _upower_blocks(text):
        if kind == 'line-power' or path.endswith('DisplayDevice') or properties.get('present') == 'no':
            continue
        level = properties.get('battery-level', 'none')
        percentage = properties.get('percentage', '').rstrip('%').split('.')[0].strip()
        if level in LEVELS:
            reading = Reading(LEVELS[level], UPOWER_STATES.get(properties.get('state', ''), 'Unknown'), True)
        elif percentage.isdigit():
            reading = Reading(min(int(percentage), 100), UPOWER_STATES.get(properties.get('state', ''), 'Unknown'))
        else:
            continue
        if kind == 'battery' and properties.get('power supply') == 'yes':
            system.append(reading)
            continue
        name = properties.get('model') or KIND_NAMES.get(kind, kind.replace('-', ' ').title() or 'Device')
        others.append(Device(properties.get('native-path') or path, name, kind or 'battery', reading))
    return _system_first(system, others)


def upower_devices() -> Optional[List[Device]]:
    """The devices UPower knows, or None when it isn't there to ask."""
    try:
        result = subprocess.run(['upower', '--dump'], capture_output=True, text=True, timeout=5, check=False)
    except (OSError, subprocess.TimeoutExpired):
        return None
    return parse_upower(result.stdout) if result.returncode == 0 else None


# ----------------------------------------------------------------------
# sysfs
# ----------------------------------------------------------------------

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


def sysfs_devices(root: str = POWER_SUPPLY) -> List[Device]:
    try:
        names = sorted(os.listdir(root))
    except OSError:
        return []
    system, others = [], []
    for name in names:
        folder = os.path.join(root, name)
        if _read(folder, 'type') != 'Battery':
            continue
        reading = _reading(folder)
        if reading is None:
            continue
        # 'Device' marks a peripheral's battery; the laptop's has no scope or 'System'.
        if _read(folder, 'scope') == 'Device':
            others.append(Device(name, _read(folder, 'model_name') or name, 'battery', reading))
        else:
            system.append(reading)
    return _system_first(system, others)


def list_devices() -> List[Device]:
    """Every device with a battery, the laptop first."""
    devices = upower_devices()
    return sysfs_devices() if devices is None else devices


def matching(devices: List[Device], patterns: str) -> List[Device]:
    """
    The devices a press cycles through: those matching ``patterns`` (parts of a
    name or kind, comma-separated, e.g. "laptop, mouse, WH-1000"), in that
    order, or all of them.
    """
    wanted = [pattern.strip().lower() for pattern in patterns.split(',') if pattern.strip()]
    if not wanted:
        return list(devices)
    chosen = []
    for pattern in wanted:
        for device in devices:
            text = ' '.join((device.name, device.kind, device.key)).lower()
            if pattern in text and device not in chosen:
                chosen.append(device)
    return chosen


class Battery(Widget):
    id = 'battery'
    name = 'Battery'
    version = '1.0.0'
    description = ('Battery charge of the laptop and connected devices: mouse, keyboard, headphones... '
                   'Each press shows the next device. A bolt shows while charging; red means low.')
    author = 'StreamDock'
    states = ('charging', 'discharging', 'full', 'low', 'unavailable')
    supports_badge = True
    options = [
        Option.string('devices', default='', label='Devices',
                      description='Which devices a press cycles through, in order: parts of their names or '
                                  'kinds, e.g. "laptop, mouse, WH-1000". Empty: every device found.'),
        Option.string('label', default='', label='Label',
                      description="Shown above the battery instead of the device's name."),
        Option.int('low', default=20, minimum=1, maximum=90, label='Low below (%)'),
        Option.int('interval', default=30, minimum=5, maximum=600, label='Check every (s)'),
        Option.color('color', default='#ffffff', label='Text and outline colour'),
        Option.color('background', default='#000000', label='Background'),
    ]

    def setup(self, ctx):
        self.devices: List[Device] = list_devices()
        self.selected: Optional[str] = None
        self.report(ctx)
        ctx.every(ctx.options['interval'], lambda: self.check(ctx))

    def on_show(self, ctx):
        self.check(ctx)

    def on_press(self, ctx):
        cycle = self.cycle(ctx.options)
        if cycle:
            current = self.current(ctx.options)
            keys = [device.key for device in cycle]
            index = keys.index(current.key) if current is not None and current.key in keys else -1
            self.selected = keys[(index + 1) % len(keys)]
            self.report(ctx)
            ctx.request_render()
        # And read again: a device may have connected since.
        self.check(ctx, poll=False)

    def check(self, ctx, poll=True):
        # A check after a press must run even while a poll is in flight: that
        # poll may have read the devices before the press.
        ctx.run_in_background(list_devices, then=lambda devices: self.update(ctx, devices), skip_if_running=poll)

    def update(self, ctx, devices):
        if devices != self.devices:
            self.devices = devices
            self.report(ctx)
            ctx.request_render()

    def cycle(self, options) -> List[Device]:
        return matching(self.devices, options['devices'])

    def current(self, options) -> Optional[Device]:
        """The device on show: the one last picked while it's still there, else the first."""
        cycle = self.cycle(options)
        return next((device for device in cycle if device.key == self.selected), cycle[0] if cycle else None)

    def state_name(self, options) -> str:
        device = self.current(options)
        if device is None:
            return 'unavailable'
        reading = device.reading
        if reading.status == 'Charging':
            return 'charging'
        if reading.status == 'Full' or (reading.percent >= 100 and reading.status != 'Discharging'):
            return 'full'
        return 'low' if reading.percent <= options['low'] else 'discharging'

    def report(self, ctx):
        device = self.current(ctx.options)
        ctx.set_state(self.state_name(ctx.options))
        ctx.set_badge(None if device is None else f'{device.reading.percent}%')

    def render(self, ctx):
        options = ctx.options
        image, canvas, scale = _common.supersampled(ctx.size, options['background'])
        width, height = image.size
        color = options['color']
        cycle = self.cycle(options)
        device = self.current(options)
        reading = device.reading if device else None

        label = options['label'] or (device.name if device else '')
        top = 10 * scale
        if label:
            label_font = draw.fit_font(canvas, label, width - 12 * scale, 18 * scale, start=16 * scale, bold=False)
            draw.centered_text(canvas, (6 * scale, 4 * scale, width - 6 * scale, 22 * scale), label,
                               color=color, text_font=label_font)
            top = 26 * scale
        body = (12 * scale, top, width - 22 * scale, top + 38 * scale)
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
        bottom = height - (12 if len(cycle) > 1 else 6) * scale
        draw.centered_text(canvas, (8 * scale, body[3] + 4 * scale, width - 8 * scale, bottom), caption, color=color)
        if len(cycle) > 1 and device is not None:
            draw_dots(canvas, len(cycle), cycle.index(device), color, width, height - 6 * scale, scale)
        return _common.downsample(image, ctx.size)


def draw_dots(canvas, count: int, active: int, color: str, width: int, middle: float, scale: int) -> None:
    """A row of dots, one per device, the one on show filled."""
    radius, gap = 2 * scale, 8 * scale
    start = width / 2 - gap * (count - 1) / 2
    for index in range(count):
        x = start + index * gap
        box = (x - radius, middle - radius, x + radius, middle + radius)
        if index == active:
            canvas.ellipse(box, fill=color)
        else:
            canvas.ellipse(box, outline='#808080', width=max(scale // 2, 1))


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
