"""
Mute state of the default microphone or speaker, through ``pactl``.

pactl talks to PulseAudio and to PipeWire's pulse server alike. ``pactl
subscribe`` streams change events, so a mute made anywhere - a keyboard key,
the desktop's volume applet - shows on the key at once instead of at the next
poll.
"""

import json
import re
import subprocess
import threading
from dataclasses import dataclass
from typing import Callable, List, Optional

from streamdock_sdk import Option, Widget
from StreamDock.widgets.builtin import _common

TARGETS = {
    'source': '@DEFAULT_SOURCE@',
    'sink': '@DEFAULT_SINK@',
}


def read_muted(kind: str) -> Optional[bool]:
    """True/False for the default source or sink, None when pactl can't tell."""
    try:
        result = subprocess.run(['pactl', f'get-{kind}-mute', TARGETS[kind]], capture_output=True,
                                text=True, timeout=3, check=False)
    except (OSError, subprocess.TimeoutExpired):
        return None
    words = result.stdout.split()
    if result.returncode != 0 or len(words) < 2:
        return None
    return words[-1].lower() == 'yes'


def toggle_muted(kind: str) -> Optional[bool]:
    """Flip the mute and return the new state."""
    try:
        subprocess.run(['pactl', f'set-{kind}-mute', TARGETS[kind], 'toggle'], capture_output=True,
                       timeout=3, check=False)
    except (OSError, subprocess.TimeoutExpired):
        return None
    return read_muted(kind)


@dataclass(frozen=True)
class AudioLevel:
    """The default device's volume in percent and its mute; None where pactl can't tell."""

    volume: Optional[int] = None
    muted: Optional[bool] = None


def read_volume(kind: str) -> Optional[int]:
    """The default source's or sink's volume in percent, averaged over its channels."""
    try:
        result = subprocess.run(['pactl', f'get-{kind}-volume', TARGETS[kind]], capture_output=True,
                                text=True, timeout=3, check=False)
    except (OSError, subprocess.TimeoutExpired):
        return None
    if result.returncode != 0:
        return None
    # "Volume: front-left: 26214 /  40% / -23.88 dB,   front-right: 26214 /  40% / ..."
    first_line = result.stdout.strip().splitlines()[0] if result.stdout.strip() else ''
    percents = [int(value) for value in re.findall(r'(\d+)%', first_line)]
    if not percents:
        return None
    return round(sum(percents) / len(percents))


def read_level(kind: str) -> AudioLevel:
    return AudioLevel(read_volume(kind), read_muted(kind))


def step_volume(kind: str, step: int, maximum: int = 100, unmute: bool = True) -> AudioLevel:
    """
    Raise (``step`` > 0) or lower the volume by ``step`` percent, never above ``maximum``.

    A relative change keeps the channels' balance; only the last step up to
    ``maximum`` sets an absolute value. With ``unmute``, raising the volume
    also unmutes, as desktop volume keys do.
    """
    current = read_volume(kind)
    if current is None:
        return read_level(kind)
    if step > 0 and current >= maximum:
        change = None
    elif step > 0 and current + step > maximum:
        change = f'{maximum}%'
    else:
        change = f'{step:+d}%'
    commands = []
    if change is not None:
        # '--' so pactl doesn't read '-5%' as an option.
        commands.append(['pactl', f'set-{kind}-volume', '--', TARGETS[kind], change])
    if unmute and step > 0:
        commands.append(['pactl', f'set-{kind}-mute', TARGETS[kind], '0'])
    try:
        for command in commands:
            subprocess.run(command, capture_output=True, timeout=3, check=False)
    except (OSError, subprocess.TimeoutExpired):
        pass
    return read_level(kind)


@dataclass(frozen=True)
class Sink:
    """An audio output: its pactl name, what the desktop calls it, and what kind of device it is."""

    name: str
    description: str
    # 'speakers', 'headphones' or 'hdmi'.
    kind: str = 'speakers'


HEADPHONE_FORMS = ('headphone', 'headset', 'hands-free', 'handsfree', 'earbuds')


def sink_kind(name: str, description: str = '', port: str = '', form_factor: str = '', bus: str = '') -> str:
    text = ' '.join((name, description, port)).lower()
    if 'hdmi' in text or 'displayport' in text:
        return 'hdmi'
    if form_factor.lower() in HEADPHONE_FORMS or bus.lower() == 'bluetooth' or \
            any(word in text for word in ('headphone', 'headset')):
        return 'headphones'
    return 'speakers'


def _pactl_output(*args: str) -> Optional[str]:
    try:
        result = subprocess.run(['pactl', *args], capture_output=True, text=True, timeout=3, check=False)
    except (OSError, subprocess.TimeoutExpired):
        return None
    return result.stdout if result.returncode == 0 else None


def list_sinks() -> Optional[List[Sink]]:
    """Every output, or None when pactl can't be asked."""
    output = _pactl_output('--format=json', 'list', 'sinks')
    if output is not None:
        try:
            sinks = []
            for entry in json.loads(output):
                properties = entry.get('properties') or {}
                name = entry.get('name', '')
                description = entry.get('description') or name
                sinks.append(Sink(name, description, sink_kind(
                    name, description, entry.get('active_port') or '',
                    properties.get('device.form_factor', ''), properties.get('device.bus', ''))))
            return sinks
        except (ValueError, AttributeError, TypeError):
            pass
    # pactl older than 16 has no JSON: names only.
    output = _pactl_output('list', 'short', 'sinks')
    if output is None:
        return None
    names = [line.split('\t')[1] for line in output.splitlines() if line.count('\t') >= 1]
    return [Sink(name, name, sink_kind(name)) for name in names]


def default_sink() -> Optional[str]:
    output = _pactl_output('get-default-sink')
    return output.strip() or None if output is not None else None


def set_default_sink(name: str, move_streams: bool = True) -> None:
    """
    Make ``name`` the default output.

    PipeWire moves the playing streams along by itself; PulseAudio leaves
    them where they are, so with ``move_streams`` they're moved explicitly.
    """
    _pactl_output('set-default-sink', name)
    if not move_streams:
        return
    for line in (_pactl_output('list', 'short', 'sink-inputs') or '').splitlines():
        stream = line.split('\t')[0]
        if stream.isdigit():
            _pactl_output('move-sink-input', stream, name)


# One ``pactl subscribe`` serves every mute and volume key in the process.
HUB = _common.ProcessHub(['pactl', 'subscribe'], 'pactl-subscribe')
# A volume slider dragged across sends dozens of events; they become one read.
DEBOUNCE = 0.1


class ChangeWatch:
    """
    Calls ``on_change`` once per burst of ``pactl subscribe`` change events concerning ``kind``.

    ``on_change`` runs on a timer thread, DEBOUNCE after the burst's first event.
    """

    def __init__(self, kind: str, on_change: Callable[[], None]):
        # 'server' events fire when the default device changes.
        self._wanted = (f"on {kind} #", 'on server')
        self._on_change = on_change
        self._lock = threading.Lock()
        self._timer: Optional[threading.Timer] = None
        self._subscribed = False

    def start(self) -> None:
        if not self._subscribed:
            self._subscribed = True
            HUB.subscribe(self._event)

    def stop(self) -> None:
        if self._subscribed:
            HUB.unsubscribe(self._event)
            self._subscribed = False
        with self._lock:
            if self._timer is not None:
                self._timer.cancel()
                self._timer = None

    def _event(self, line: Optional[str]) -> None:
        if line is None or "'change'" not in line or not any(token in line for token in self._wanted):
            return
        with self._lock:
            if self._timer is not None:
                return
            self._timer = threading.Timer(DEBOUNCE, self._fire)
            self._timer.daemon = True
            self._timer.start()

    def _fire(self) -> None:
        with self._lock:
            self._timer = None
        self._on_change()


class MuteWidget(Widget):
    """Shared behaviour of the microphone and speaker widgets; not registered itself."""

    kind = 'source'
    on_caption = 'LIVE'
    states = ('muted', 'unmuted', 'unknown')
    options = [
        Option.bool('toggle_on_press', default=True, label='Press toggles mute'),
        Option.bool('show_caption', default=True, label='Show caption'),
        Option.color('muted_color', default='#b71c1c', label='Muted background'),
        Option.color('unmuted_color', default='#1b5e20', label='Unmuted background'),
        Option.color('color', default='#ffffff', label='Icon colour'),
    ]

    def setup(self, ctx):
        # One quick pactl call, so the first frame shows the real state.
        self.muted: Optional[bool] = read_muted(self.kind)
        ctx.set_state(self.state_name())
        self.watch = ChangeWatch(self.kind, lambda: self._read_now(ctx))
        # A backstop for a pactl subscribe that died unnoticed.
        ctx.every(10, lambda: self.refresh(ctx))

    def on_show(self, ctx):
        # Watch for changes only while the key is on the device.
        self.watch.start()
        self.refresh(ctx)

    def on_hide(self, ctx):
        self.stop_watching()

    def teardown(self, ctx):
        self.stop_watching()

    def stop_watching(self):
        self.watch.stop()

    def _read_now(self, ctx):
        # Read here rather than through the backstop's refresh(), which skips
        # a read while one is in flight - and that one may predate the change.
        muted = read_muted(self.kind)
        ctx.call_soon(lambda: self.update(ctx, muted))

    def refresh(self, ctx):
        ctx.run_in_background(lambda: read_muted(self.kind), then=lambda muted: self.update(ctx, muted),
                              skip_if_running=True)

    def state_name(self) -> str:
        return 'unknown' if self.muted is None else 'muted' if self.muted else 'unmuted'

    def update(self, ctx, muted):
        if muted != self.muted:
            self.muted = muted
            ctx.set_state(self.state_name())
            ctx.request_render()

    def on_press(self, ctx):
        if ctx.options['toggle_on_press']:
            ctx.run_in_background(lambda: toggle_muted(self.kind), then=lambda muted: self.update(ctx, muted))

    def draw_icon(self, canvas, box, color, scale):
        raise NotImplementedError

    def render(self, ctx):
        options = ctx.options
        if self.muted is None:
            background, caption = '#424242', '?'
        elif self.muted:
            background, caption = options['muted_color'], 'MUTED'
        else:
            background, caption = options['unmuted_color'], self.on_caption
        image, canvas, scale, box = _common.status_tile(ctx.size, background,
                                                        caption if options['show_caption'] else '',
                                                        options['color'])
        if not options['show_caption']:
            left, top, right, _ = box
            box = (left, top + 4 * scale, right, image.size[1] - 14 * scale)
        self.draw_icon(canvas, box, options['color'], scale)
        if self.muted:
            _common.slash(canvas, box, options['color'], 5 * scale)
        return _common.downsample(image, ctx.size)
