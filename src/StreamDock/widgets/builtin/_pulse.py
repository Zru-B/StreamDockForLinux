"""
Mute state of the default microphone or speaker, through ``pactl``.

pactl talks to PulseAudio and to PipeWire's pulse server alike. ``pactl
subscribe`` streams change events, so a mute made anywhere - a keyboard key,
the desktop's volume applet - shows on the key at once instead of at the next
poll.
"""

import re
import subprocess
import threading
from dataclasses import dataclass
from typing import Callable, Optional

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


class EventWatcher:
    """Runs ``pactl subscribe`` and calls ``on_change`` for events that concern ``kind``."""

    def __init__(self, kind: str, on_change: Callable[[], None]):
        self._kind = kind
        self._on_change = on_change
        self._stopping = threading.Event()
        self._process: Optional[subprocess.Popen] = None

    def start(self) -> None:
        threading.Thread(target=self._run, name=f'pactl-subscribe-{self._kind}', daemon=True).start()

    def stop(self) -> None:
        self._stopping.set()
        if self._process is not None:
            self._process.terminate()

    def _run(self) -> None:
        # 'server' events fire when the default device changes.
        wanted = (f"on {self._kind} #", 'on server')
        while not self._stopping.is_set():
            try:
                self._process = subprocess.Popen(  # pylint: disable=consider-using-with
                    ['pactl', 'subscribe'], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)
            except OSError:
                return
            for line in self._process.stdout:
                if "'change'" in line and any(token in line for token in wanted):
                    self._on_change()
            self._process.wait()
            self._stopping.wait(5)


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
        self.watcher: Optional[EventWatcher] = None
        # A backstop for a pactl subscribe that died unnoticed.
        ctx.every(10, lambda: self.refresh(ctx))

    def on_show(self, ctx):
        # Watch for changes only while the key is on the device.
        self.watcher = EventWatcher(self.kind, lambda: self.refresh(ctx))
        self.watcher.start()
        self.refresh(ctx)

    def on_hide(self, ctx):
        self.stop_watching()

    def teardown(self, ctx):
        self.stop_watching()

    def stop_watching(self):
        if self.watcher is not None:
            self.watcher.stop()
            self.watcher = None

    def refresh(self, ctx):
        ctx.run_in_background(lambda: read_muted(self.kind), then=lambda muted: self.update(ctx, muted))

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
