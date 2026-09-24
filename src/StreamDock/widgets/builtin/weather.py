"""
Current weather from Open-Meteo (open-meteo.com), which needs no API key.

The location is a place name, geocoded once through Open-Meteo's geocoding
API, or a "latitude,longitude" pair.
"""

import json
import math
import re
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Optional, Tuple

from streamdock_sdk import Option, Widget, draw
from StreamDock.widgets.builtin import _common

GEOCODE_URL = 'https://geocoding-api.open-meteo.com/v1/search'
FORECAST_URL = 'https://api.open-meteo.com/v1/forecast'
TIMEOUT = 10
# The first reading happens while the widget starts; don't hold it up long.
FIRST_TIMEOUT = 3
COORDINATES = re.compile(r'^\s*(-?\d+(?:\.\d+)?)\s*,\s*(-?\d+(?:\.\d+)?)\s*$')

STATES = ('clear', 'clear_night', 'partly_cloudy', 'cloudy', 'fog', 'rain', 'snow', 'storm', 'unknown')


def condition(code: Optional[int], is_day: bool = True) -> str:
    """Our state name for a WMO weather code."""
    if code is None:
        return 'unknown'
    if code == 0:
        return 'clear' if is_day else 'clear_night'
    if code in (1, 2):
        return 'partly_cloudy'
    if code == 3:
        return 'cloudy'
    if code in (45, 48):
        return 'fog'
    if 71 <= code <= 77 or code in (85, 86):
        return 'snow'
    if code >= 95:
        return 'storm'
    if 51 <= code <= 67 or 80 <= code <= 82:
        return 'rain'
    return 'unknown'


def _get_json(url: str, params: dict, timeout: float = TIMEOUT) -> dict:
    with urllib.request.urlopen(f'{url}?{urllib.parse.urlencode(params)}', timeout=timeout) as response:
        return json.loads(response.read(1024 * 1024))


def locate(location: str, timeout: float = TIMEOUT) -> Tuple[float, float]:
    """(latitude, longitude) for a place name or a 'lat,lon' pair."""
    match = COORDINATES.match(location)
    if match:
        return float(match.group(1)), float(match.group(2))
    results = _get_json(GEOCODE_URL, {'name': location, 'count': 1}, timeout).get('results') or []
    if not results:
        raise LookupError(f'place not found: {location}')
    return results[0]['latitude'], results[0]['longitude']


@dataclass
class Reading:
    temperature: float
    state: str


def fetch(position: Tuple[float, float], units: str, timeout: float = TIMEOUT) -> Reading:
    data = _get_json(FORECAST_URL, {
        'latitude': position[0], 'longitude': position[1],
        'current': 'temperature_2m,weather_code,is_day',
        'temperature_unit': units,
    }, timeout)['current']
    return Reading(float(data['temperature_2m']), condition(data.get('weather_code'), bool(data.get('is_day', 1))))


def _cloud(canvas, cx, cy, size, fill):
    r = size * 0.22
    for dx, dy, rr in ((-0.22, 0.04, 1.0), (0.05, -0.08, 1.35), (0.28, 0.06, 0.95)):
        x, y, radius = cx + dx * size, cy + dy * size, r * rr
        canvas.ellipse((x - radius, y - radius, x + radius, y + radius), fill=fill)
    canvas.rounded_rectangle((cx - size * 0.44, cy, cx + size * 0.5, cy + r * 1.1), radius=r / 2, fill=fill)


def draw_condition(canvas, state: str, box, scale: int) -> None:
    """A glyph for the weather state, drawn into ``box`` (supersampled pixels)."""
    left, top, right, bottom = box
    size = min(right - left, bottom - top)
    cx, cy = (left + right) / 2, (top + bottom) / 2
    sun, cloud, dark_cloud, blue, white = '#ffc107', '#eceff1', '#90a4ae', '#4fc3f7', '#ffffff'

    if state in ('clear', 'partly_cloudy'):
        sx, sy = (cx, cy) if state == 'clear' else (cx - size * 0.15, cy - size * 0.15)
        r = size * (0.22 if state == 'clear' else 0.18)
        for ray in range(8):
            angle = math.radians(ray * 45)
            canvas.line((sx + math.cos(angle) * r * 1.35, sy + math.sin(angle) * r * 1.35,
                         sx + math.cos(angle) * r * 1.8, sy + math.sin(angle) * r * 1.8), fill=sun, width=3 * scale)
        canvas.ellipse((sx - r, sy - r, sx + r, sy + r), fill=sun)
        if state == 'partly_cloudy':
            _cloud(canvas, cx + size * 0.08, cy + size * 0.08, size * 0.8, cloud)
    elif state == 'clear_night':
        r = size * 0.28
        canvas.ellipse((cx - r, cy - r, cx + r, cy + r), fill='#fff59d')
        canvas.ellipse((cx - r * 0.45, cy - r * 1.15, cx + r * 1.4, cy + r * 0.7), fill='#000000')
    elif state in ('cloudy', 'fog'):
        _cloud(canvas, cx, cy - size * 0.08, size, dark_cloud if state == 'fog' else cloud)
        if state == 'fog':
            for i in range(3):
                y = cy + size * (0.22 + i * 0.1)
                canvas.line((cx - size * 0.4, y, cx + size * 0.4, y), fill=cloud, width=3 * scale)
    elif state in ('rain', 'snow', 'storm'):
        _cloud(canvas, cx, cy - size * 0.18, size, dark_cloud if state == 'storm' else cloud)
        base = cy + size * 0.18
        if state == 'storm':
            canvas.polygon([(cx + size * 0.05, base - size * 0.05), (cx - size * 0.12, base + size * 0.2),
                            (cx, base + size * 0.2), (cx - size * 0.08, base + size * 0.38),
                            (cx + size * 0.15, base + size * 0.1), (cx + size * 0.03, base + size * 0.1)],
                           fill=sun)
        for i in range(3):
            x = cx + (i - 1) * size * 0.25
            if state == 'snow':
                r = size * 0.045
                canvas.ellipse((x - r, base + size * 0.12 - r, x + r, base + size * 0.12 + r), fill=white)
            elif state == 'rain':
                canvas.line((x, base + size * 0.02, x - size * 0.06, base + size * 0.24), fill=blue, width=3 * scale)
    else:
        draw.centered_text(canvas, box, '?', color='#9e9e9e')


class Weather(Widget):
    id = 'weather'
    name = 'Weather'
    version = '1.0.0'
    description = 'Current temperature and conditions from Open-Meteo (no account needed).'
    author = 'StreamDock'
    states = STATES
    supports_badge = True
    options = [
        Option.string('location', default='London', label='Location',
                      description='A place name, or latitude,longitude such as 32.08,34.78'),
        Option.choice('units', ['celsius', 'fahrenheit'], default='celsius', label='Units'),
        Option.int('refresh_minutes', default=15, minimum=5, maximum=180, label='Update every (min)'),
        Option.color('color', default='#ffffff', label='Text colour'),
        Option.color('background', default='#000000', label='Background'),
    ]

    def setup(self, ctx):
        self.position: Optional[Tuple[float, float]] = None
        self.reading: Optional[Reading] = None
        self.failed = False
        self.fetched_at = 0.0
        ctx.set_state('unknown')
        self.update(ctx, self._guarded(ctx, self._work(ctx, FIRST_TIMEOUT))())
        ctx.every(ctx.options['refresh_minutes'] * 60, lambda: self.refresh(ctx))
        # Offline at login: try again every minute until the first reading lands.
        ctx.every(60, lambda: self.reading is None and self.refresh(ctx))

    def _work(self, ctx, timeout):
        options = dict(ctx.options)

        def work():
            if self.position is None:
                self.position = locate(options['location'], timeout)
            return fetch(self.position, options['units'], timeout)
        return work

    def refresh(self, ctx):
        ctx.run_in_background(self._guarded(ctx, self._work(ctx, TIMEOUT)),
                              then=lambda reading: self.update(ctx, reading))

    @staticmethod
    def _guarded(ctx, work):
        """Network trouble keeps the last reading rather than raising into the log each time."""
        def run():
            try:
                return work()
            except (OSError, ValueError, KeyError, LookupError) as exc:
                ctx.log.warning('weather update failed: %s', exc)
                return None
        return run

    def update(self, ctx, reading):
        if reading is None:
            if self.reading is None:
                self.failed = True
                ctx.request_render()
            return
        self.reading, self.failed = reading, False
        self.fetched_at = time.time()
        ctx.set_state(reading.state)
        ctx.set_badge(self.temperature_text())
        ctx.request_render()

    def on_press(self, ctx):
        self.refresh(ctx)

    def on_show(self, ctx):
        # Timers stop while the key is hidden; catch up if the reading went stale.
        if time.time() - self.fetched_at >= ctx.options['refresh_minutes'] * 60:
            self.refresh(ctx)

    def temperature_text(self) -> str:
        return f'{self.reading.temperature:.0f}°' if self.reading else '--°'

    def render(self, ctx):
        options = ctx.options
        image, canvas, scale = _common.supersampled(ctx.size, options['background'])
        width, height = image.size
        state = self.reading.state if self.reading else 'unknown'
        draw_condition(canvas, state, (width * 0.18, height * 0.06, width * 0.82, height * 0.60), scale)
        text = 'offline' if self.failed and not self.reading else self.temperature_text()
        draw.centered_text(canvas, (6 * scale, int(height * 0.62), width - 6 * scale, height - 4 * scale),
                           text, color=options['color'])
        return _common.downsample(image, ctx.size)
