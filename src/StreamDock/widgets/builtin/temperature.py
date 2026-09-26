"""
A temperature from the kernel's hardware sensors (``/sys/class/hwmon``).

``sensor`` names a preset - cpu, gpu, nvme - that knows the usual drivers, or
a sensor chip by name, optionally with one of its readings: ``k10temp`` or
``nvme/Composite``. NVIDIA's own driver has no hwmon sensor, so the gpu
preset asks ``nvidia-smi`` when no other GPU sensor is found.
"""

import glob
import os
import subprocess
from typing import List, Optional, Tuple

from streamdock_sdk import Option, Widget, draw
from StreamDock.widgets.builtin import _common

HWMON = '/sys/class/hwmon'

# (chip name, reading label or None for its first reading), best first.
PRESETS = {
    'cpu': [('coretemp', 'package id 0'), ('k10temp', 'tctl'), ('k10temp', 'tdie'), ('zenpower', 'tdie'),
            ('cpu_thermal', None), ('acpitz', None)],
    'gpu': [('amdgpu', 'edge'), ('nouveau', None), ('radeon', None), ('i915', None), ('xe', None)],
    'nvme': [('nvme', 'composite')],
}

NORMAL_COLOR, WARM_COLOR, HOT_COLOR = '#43a047', '#ffb300', '#e53935'


def _read(path: str) -> str:
    try:
        with open(path, encoding='utf-8') as handle:
            return handle.read().strip()
    except OSError:
        return ''


def chips(root: str = HWMON) -> List[Tuple[str, List[Tuple[str, str]]]]:
    """Every sensor chip: its name and its (label, input file) temperature readings, in order."""
    found = []
    for folder in sorted(glob.glob(os.path.join(root, 'hwmon*'))):
        inputs = sorted(glob.glob(os.path.join(folder, 'temp*_input')),
                        key=lambda path: int(''.join(filter(str.isdigit, os.path.basename(path))) or 0))
        readings = [(_read(path.replace('_input', '_label')).lower(), path) for path in inputs]
        if readings:
            found.append((_read(os.path.join(folder, 'name')).lower(), readings))
    return found


def _wanted(sensor: str) -> List[Tuple[str, Optional[str]]]:
    sensor = sensor.strip().lower()
    if sensor in PRESETS:
        return PRESETS[sensor]
    chip, _, label = sensor.partition('/')
    return [(chip, label or None)]


def read_celsius(sensor: str, root: str = HWMON) -> Optional[float]:
    available = chips(root)
    for chip, label in _wanted(sensor):
        for name, readings in available:
            if name != chip:
                continue
            for reading_label, path in readings:
                if label is None or reading_label == label:
                    value = _read(path)
                    if value.lstrip('-').isdigit():
                        return int(value) / 1000
    if sensor.strip().lower() == 'gpu':
        return nvidia_celsius()
    return None


def nvidia_celsius() -> Optional[float]:
    try:
        result = subprocess.run(['nvidia-smi', '--query-gpu=temperature.gpu', '--format=csv,noheader,nounits'],
                                capture_output=True, text=True, timeout=3, check=False)
    except (OSError, subprocess.TimeoutExpired):
        return None
    first = result.stdout.strip().splitlines()[0] if result.stdout.strip() else ''
    return float(first) if result.returncode == 0 and first.replace('.', '', 1).isdigit() else None


class Temperature(Widget):
    id = 'temperature'
    name = 'Temperature'
    version = '1.0.0'
    description = 'CPU, GPU or SSD temperature, with a thermometer that turns amber when warm and red when hot.'
    author = 'StreamDock'
    states = ('normal', 'warm', 'hot', 'unavailable')
    supports_badge = True
    options = [
        Option.string('sensor', default='cpu', label='Sensor',
                      description='cpu, gpu or nvme; or a sensor chip, optionally with a reading, '
                                  'e.g. "k10temp" or "nvme/Composite" (see the `sensors` command).'),
        Option.string('label', default='', label='Label', description='Empty: the sensor, e.g. CPU.'),
        Option.choice('units', ['celsius', 'fahrenheit'], default='celsius', label='Units'),
        Option.int('warm', default=70, minimum=20, maximum=120, label='Warm from (°C)'),
        Option.int('hot', default=85, minimum=20, maximum=130, label='Hot from (°C)'),
        Option.int('interval', default=3, minimum=1, maximum=300, label='Update every (s)'),
        Option.color('color', default='#ffffff', label='Text colour'),
        Option.color('background', default='#000000', label='Background'),
    ]

    def setup(self, ctx):
        self.celsius: Optional[float] = read_celsius(ctx.options['sensor'])
        self.report(ctx)
        ctx.every(ctx.options['interval'], lambda: self.check(ctx))

    def on_show(self, ctx):
        self.check(ctx)

    def check(self, ctx):
        ctx.run_in_background(lambda: read_celsius(ctx.options['sensor']),
                              then=lambda celsius: self.update(ctx, celsius))

    def update(self, ctx, celsius):
        if celsius != self.celsius:
            self.celsius = celsius
            self.report(ctx)
            ctx.request_render()

    def level(self, options) -> str:
        if self.celsius is None:
            return 'unavailable'
        return 'hot' if self.celsius >= options['hot'] else 'warm' if self.celsius >= options['warm'] else 'normal'

    def shown(self, options) -> Optional[int]:
        if self.celsius is None:
            return None
        return round(self.celsius * 9 / 5 + 32 if options['units'] == 'fahrenheit' else self.celsius)

    def report(self, ctx):
        ctx.set_state(self.level(ctx.options))
        value = self.shown(ctx.options)
        ctx.set_badge(None if value is None else f'{value}°')

    def render(self, ctx):
        options = ctx.options
        image, canvas, scale = _common.supersampled(ctx.size, options['background'])
        width, height = image.size
        level = self.level(options)
        fill = {'normal': NORMAL_COLOR, 'warm': WARM_COLOR, 'hot': HOT_COLOR}.get(level, '#616161')
        # The column fills from 20 °C to 10 degrees past hot.
        fraction = 0.0 if self.celsius is None else \
            min(max((self.celsius - 20) / (options['hot'] + 10 - 20), 0.08), 1.0)
        draw_thermometer(canvas, (8 * scale, 10 * scale, 34 * scale, height - 10 * scale), fill, fraction,
                         options['color'], scale)

        value = self.shown(options)
        text = '--' if value is None else f'{value}°'
        draw.centered_text(canvas, (38 * scale, 16 * scale, width - 6 * scale, 66 * scale), text,
                           color=options['color'])
        label = options['label'] or options['sensor'].split('/')[0].upper()
        draw.centered_text(canvas, (38 * scale, 72 * scale, width - 6 * scale, 94 * scale), label,
                           color=options['color'], bold=False)
        return _common.downsample(image, ctx.size)


def draw_thermometer(canvas, box, fill: str, fraction: float, outline: str, scale: int) -> None:
    """A thermometer standing in ``box``, its column filled to ``fraction``."""
    left, top, right, bottom = box
    width = right - left
    center = (left + right) / 2
    bulb = width / 2
    tube = width * 0.30
    bulb_top = bottom - 2 * bulb
    line = 3 * scale
    canvas.rounded_rectangle((center - tube - line, top, center + tube + line, bulb_top + bulb), radius=tube + line,
                             fill=outline)
    canvas.ellipse((left, bulb_top, right, bottom), fill=outline)
    canvas.rounded_rectangle((center - tube, top + line, center + tube, bulb_top + bulb), radius=tube, fill='#202020')
    canvas.ellipse((left + line, bulb_top + line, right - line, bottom - line), fill=fill)
    column_bottom = bulb_top + bulb
    column_top = column_bottom - (column_bottom - top - line - tube) * fraction
    canvas.rounded_rectangle((center - tube + line, column_top, center + tube - line, column_bottom),
                             radius=tube - line, fill=fill)
