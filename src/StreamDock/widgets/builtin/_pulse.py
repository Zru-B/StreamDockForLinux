"""
Mute state of the default microphone or speaker, through ``pactl``.

pactl talks to PulseAudio and to PipeWire's pulse server alike. ``pactl
subscribe`` streams change events, so a mute made anywhere - a keyboard key,
the desktop's volume applet - shows on the key at once instead of at the next
poll.
"""

import subprocess
import threading
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


# One ``pactl subscribe`` serves every mute key in the process.
HUB = _common.ProcessHub(['pactl', 'subscribe'], 'pactl-subscribe')
# A volume slider dragged across sends dozens of events; they become one read.
DEBOUNCE = 0.1


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
        self._listener: Optional[Callable[[Optional[str]], None]] = None
        self._debounce_lock = threading.Lock()
        self._debounce: Optional[threading.Timer] = None
        # A backstop for a pactl subscribe that died unnoticed.
        ctx.every(10, lambda: self.refresh(ctx))

    def on_show(self, ctx):
        # Watch for changes only while the key is on the device.
        if self._listener is None:
            # 'server' events fire when the default device changes.
            wanted = (f"on {self.kind} #", 'on server')

            def listener(line):
                if line is not None and "'change'" in line and any(token in line for token in wanted):
                    self.changed(ctx)
            self._listener = listener
            HUB.subscribe(listener)
        self.refresh(ctx)

    def on_hide(self, ctx):
        self.stop_watching()

    def teardown(self, ctx):
        self.stop_watching()

    def stop_watching(self):
        if self._listener is not None:
            HUB.unsubscribe(self._listener)
            self._listener = None
        with self._debounce_lock:
            if self._debounce is not None:
                self._debounce.cancel()
                self._debounce = None

    def changed(self, ctx):
        """A change event: read the state once the burst it belongs to is over."""
        with self._debounce_lock:
            if self._debounce is not None:
                return
            self._debounce = threading.Timer(DEBOUNCE, self._read_now, args=(ctx,))
            self._debounce.daemon = True
            self._debounce.start()

    def _read_now(self, ctx):
        # Read here rather than through the backstop's refresh(), which skips
        # a read while one is in flight - and that one may predate the change.
        with self._debounce_lock:
            self._debounce = None
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
