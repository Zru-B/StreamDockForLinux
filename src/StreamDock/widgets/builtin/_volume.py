"""
Volume of the default speaker, shared by the volume widgets.

The level and mute come from ``pactl``, like the mute widgets, and ``pactl
subscribe`` redraws the keys as soon as the volume changes anywhere: a
keyboard volume key, the desktop's applet or another key.
"""

from streamdock_sdk import Option, Widget
from StreamDock.widgets.builtin import _pulse

STATES = ('muted', 'unmuted', 'unknown')

STEP_OPTIONS = [
    Option.int('step', default=5, minimum=1, maximum=25, label='Step (%)',
               description='How much one press raises or lowers the volume.'),
    Option.int('max_volume', default=100, minimum=100, maximum=150, label='Highest volume (%)',
               description='Raising stops here. Above 100% the sound is amplified and may distort.'),
    Option.bool('unmute_on_raise', default=True, label='Raising unmutes',
                description='Raising the volume while muted also unmutes, as keyboard volume keys do.'),
]


class VolumeWidget(Widget):
    """Tracks the default speaker's volume and mute; not registered itself."""

    kind = 'sink'
    states = STATES
    supports_badge = True

    def setup(self, ctx):
        # One quick pactl call, so the first frame shows the real level.
        self.level = _pulse.read_level(self.kind)
        self.report(ctx)
        self.watch = _pulse.ChangeWatch(self.kind, lambda: self._read_now(ctx))
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
        level = _pulse.read_level(self.kind)
        ctx.call_soon(lambda: self.update(ctx, level))

    def refresh(self, ctx):
        ctx.run_in_background(lambda: _pulse.read_level(self.kind), then=lambda level: self.update(ctx, level),
                              skip_if_running=True)

    def update(self, ctx, level: _pulse.AudioLevel):
        if level != self.level:
            self.level = level
            self.report(ctx)
            ctx.request_render()

    def report(self, ctx):
        muted = self.level.muted
        ctx.set_state('unknown' if muted is None else 'muted' if muted else 'unmuted')
        ctx.set_badge(None if self.level.volume is None else f'{self.level.volume}%')

    def change_volume(self, ctx, step: int):
        options = ctx.options
        ctx.run_in_background(
            lambda: _pulse.step_volume(self.kind, step, options['max_volume'], options['unmute_on_raise']),
            then=lambda level: self.update(ctx, level))

    def toggle_mute(self, ctx):
        def toggle():
            _pulse.toggle_muted(self.kind)
            return _pulse.read_level(self.kind)
        ctx.run_in_background(toggle, then=lambda level: self.update(ctx, level))

    def render(self, ctx):
        raise NotImplementedError


def draw_speaker(canvas, box, color: str, scale: int, waves: int = 2) -> None:
    """A loudspeaker filling ``box``: its body on the left, ``waves`` sound arcs to its right."""
    left, top, right, bottom = box
    width, height = right - left, bottom - top
    middle = top + height / 2
    body_left = left + width * 0.05
    canvas.polygon([
        (body_left, middle - height * 0.16), (body_left + width * 0.20, middle - height * 0.16),
        (body_left + width * 0.48, middle - height * 0.40), (body_left + width * 0.48, middle + height * 0.40),
        (body_left + width * 0.20, middle + height * 0.16), (body_left, middle + height * 0.16),
    ], fill=color)
    for step, reach in enumerate((0.22, 0.38)[:waves]):
        radius = height * reach
        origin = body_left + width * 0.48
        canvas.arc((origin - radius, middle - radius, origin + radius, middle + radius),
                   start=-50, end=50, fill=color, width=(3 - step) * scale + scale)


def draw_sign(canvas, box, sign: str, color: str, scale: int) -> None:
    """A bold '+' or '-' filling the square centred in ``box``."""
    left, top, right, bottom = box
    center_x, center_y = (left + right) / 2, (top + bottom) / 2
    half = min(right - left, bottom - top) / 2
    thickness = max(scale, half * 0.30)
    canvas.rectangle((center_x - half, center_y - thickness / 2, center_x + half, center_y + thickness / 2),
                     fill=color)
    if sign == '+':
        canvas.rectangle((center_x - thickness / 2, center_y - half, center_x + thickness / 2, center_y + half),
                         fill=color)
