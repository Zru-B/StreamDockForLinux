"""
A Pomodoro timer: work for a while, take a short break, repeat.

The phase ends at a wall-clock time, so the count stays right while the key
is hidden or the computer sleeps. A background timer ends a phase even when
the key isn't on the device, so the desktop notification comes on time.
"""

import math
import subprocess
import threading
import time
from typing import Optional

from streamdock_sdk import Option, Widget, draw
from StreamDock.widgets.builtin import _common

# Tests replace this to control time.
clock = time.time

# Blinking while paused: the ring shows for one quarter second, hides for the next (2 Hz).
BLINK_INTERVAL = 0.25

TOMATO = '#e53935'
TOMATO_SHADE = '#b71c1c'
LEAVES = '#43a047'
TRACK = '#2b2b2b'


def notify(summary: str, body: str) -> None:
    try:
        subprocess.run(['notify-send', '--app-name=StreamDock', '--icon=appointment-soon', summary, body],
                       capture_output=True, timeout=5, check=False)
    except (OSError, subprocess.TimeoutExpired):
        pass


class Pomodoro(Widget):
    id = 'pomodoro'
    name = 'Pomodoro'
    version = '1.0.0'
    description = ('A Pomodoro timer: 25 minutes of work, then a 5-minute break. Press to start or pause, '
                   'hold to reset. A ring around the tomato shows the time left.')
    author = 'StreamDock'
    # 'paused' covers a paused work session and a paused break alike.
    states = ('idle', 'work', 'break', 'paused')
    supports_badge = True
    options = [
        Option.int('work_minutes', default=25, minimum=1, maximum=180, label='Work (minutes)'),
        Option.int('break_minutes', default=5, minimum=1, maximum=60, label='Break (minutes)'),
        Option.bool('auto_start_work', default=False, label='Start work again after a break',
                    description='Off: after a break the timer waits for a press.'),
        Option.bool('notify', default=True, label='Desktop notification when a phase ends'),
        Option.bool('show_time', default=False, label='Show the time left',
                    description='Draw the minutes and seconds left on the tomato instead of its hands or face.'),
        Option.color('work_color', default='#ffb300', label='Work ring colour'),
        Option.color('break_color', default='#66bb6a', label='Break ring colour'),
        Option.color('background', default='#000000', label='Background'),
    ]

    def setup(self, ctx):
        self.phase = 'idle'          # idle, work or break
        self.running = False
        self.ends_at = 0.0           # while running: when the phase ends
        self.remaining = 0.0         # while paused: what was left
        self.phase_timer: Optional[threading.Timer] = None
        self.shown_second: Optional[int] = None
        self.blink_on = True
        self.report(ctx)
        ctx.every(BLINK_INTERVAL, lambda: self.tick(ctx), align=True)

    def teardown(self, ctx):
        self.cancel_phase_timer()

    def on_show(self, ctx):
        self.advance(ctx)

    # ------------------------------------------------------------------
    # Key events
    # ------------------------------------------------------------------

    def on_press(self, ctx):
        now = clock()
        if self.phase == 'idle':
            self.start_phase(ctx, 'work', now)
        elif self.running:
            self.running = False
            self.remaining = max(self.ends_at - now, 0.0)
            self.blink_on = True
            self.cancel_phase_timer()
        else:
            self.running = True
            self.ends_at = now + self.remaining
            self.schedule_phase_end(ctx)
        self.report(ctx)
        ctx.request_render()

    def on_long_press(self, ctx):
        self.cancel_phase_timer()
        self.phase, self.running = 'idle', False
        self.report(ctx)
        ctx.request_render()

    # ------------------------------------------------------------------
    # Time
    # ------------------------------------------------------------------

    def duration(self, ctx, phase: str) -> float:
        return 60.0 * ctx.options['work_minutes' if phase == 'work' else 'break_minutes']

    def start_phase(self, ctx, phase: str, starts_at: float):
        self.phase = phase
        self.running = True
        self.ends_at = starts_at + self.duration(ctx, phase)
        self.schedule_phase_end(ctx)

    def time_left(self) -> float:
        if self.phase == 'idle':
            return 0.0
        return max(self.ends_at - clock(), 0.0) if self.running else self.remaining

    def schedule_phase_end(self, ctx):
        self.cancel_phase_timer()
        # Runs even while the key is hidden, when the widget's own timers pause.
        self.phase_timer = threading.Timer(max(self.ends_at - clock(), 0.0) + 0.05,
                                           lambda: ctx.call_soon(lambda: self.advance(ctx)))
        self.phase_timer.daemon = True
        self.phase_timer.start()

    def cancel_phase_timer(self):
        if self.phase_timer is not None:
            self.phase_timer.cancel()
            self.phase_timer = None

    def advance(self, ctx):
        """End every phase whose time is up; after a long sleep that may be more than one."""
        now = clock()
        ended = None
        while self.running and now >= self.ends_at:
            ended = self.phase
            if self.phase == 'work':
                self.start_phase(ctx, 'break', self.ends_at)
            elif ctx.options['auto_start_work']:
                self.start_phase(ctx, 'work', self.ends_at)
            else:
                self.cancel_phase_timer()
                self.phase, self.running = 'idle', False
        if ended is None:
            return
        if ctx.options['notify']:
            if self.phase == 'break':
                message = ('Time for a break', f"{ctx.options['break_minutes']} minutes. Well done!")
            elif self.phase == 'work':
                message = ('Back to work', f"{ctx.options['work_minutes']} minutes of focus.")
            else:
                message = ('Break is over', 'Press the key to start the next Pomodoro.')
            ctx.run_in_background(lambda: notify(*message))
        self.report(ctx)
        ctx.request_render()

    def tick(self, ctx):
        self.advance(ctx)
        if self.phase == 'idle':
            return
        if self.running:
            second = math.ceil(self.time_left())
            if second != self.shown_second:
                self.report(ctx)
                ctx.request_render()
        else:
            self.blink_on = not self.blink_on
            ctx.request_render()

    def report(self, ctx):
        if self.phase == 'idle':
            ctx.set_state('idle')
            ctx.set_badge(None)
            self.shown_second = None
            return
        ctx.set_state(self.phase if self.running else 'paused')
        self.shown_second = math.ceil(self.time_left())
        ctx.set_badge(format_time(self.shown_second))

    # ------------------------------------------------------------------
    # Drawing
    # ------------------------------------------------------------------

    def render(self, ctx):
        options = ctx.options
        image, canvas, scale = _common.supersampled(ctx.size, options['background'])
        size = image.size[0]

        if self.phase != 'idle':
            ring = (5 * scale, 5 * scale, size - 5 * scale, size - 5 * scale)
            width = 7 * scale
            canvas.ellipse(ring, outline=TRACK, width=width)
            if self.running or self.blink_on:
                fraction = self.time_left() / self.duration(ctx, self.phase)
                color = options['work_color'] if self.phase == 'work' else options['break_color']
                if fraction > 0:
                    # From twelve o'clock, clockwise; it shortens from its end as time runs out.
                    canvas.arc(ring, -90, -90 + 360 * min(fraction, 1.0), fill=color, width=width)

        # The tomato is the same size with or without the ring around it.
        box = (22 * scale, 26 * scale, size - 22 * scale, size - 18 * scale)
        draw_tomato(canvas, box, scale)
        if options['show_time'] and self.phase != 'idle':
            left, top, right, bottom = box
            draw.centered_text(canvas, (left + 8 * scale, top + 14 * scale, right - 8 * scale, bottom - 14 * scale),
                               format_time(math.ceil(self.time_left())), color='white')
        elif self.phase == 'break':
            draw_smile(canvas, box, scale)
        else:
            draw_hands(canvas, box, scale)
        return _common.downsample(image, ctx.size)


def format_time(seconds: float) -> str:
    seconds = max(int(seconds), 0)
    return f'{seconds // 60}:{seconds % 60:02d}'


def draw_tomato(canvas, box, scale) -> None:
    """A round tomato filling ``box`` with its green calyx and stem on top."""
    left, top, right, bottom = box
    width, height = right - left, bottom - top
    center = (left + right) / 2
    canvas.ellipse((left, top + height * 0.06, right, bottom), fill=TOMATO_SHADE)
    canvas.ellipse((left + width * 0.03, top + height * 0.06, right - width * 0.03, bottom - height * 0.05),
                   fill=TOMATO)
    # A soft highlight on the upper left.
    canvas.ellipse((left + width * 0.16, top + height * 0.20, left + width * 0.34, top + height * 0.34),
                   fill='#ef6c6c')
    # Calyx: five pointed leaves around the stem.
    calyx_y = top + height * 0.08
    points = []
    for index in range(10):
        angle = math.pi * index / 5 - math.pi / 2
        reach = width * (0.26 if index % 2 == 0 else 0.08)
        points.append((center + reach * math.cos(angle), calyx_y + reach * 0.55 * math.sin(angle)))
    canvas.polygon(points, fill=LEAVES)
    canvas.rounded_rectangle((center - width * 0.03, top - height * 0.08, center + width * 0.03, calyx_y),
                             radius=width * 0.03, fill='#2e7d32')


def _face_center(box):
    left, top, right, bottom = box
    return (left + right) / 2, top + (bottom - top) * 0.56, right - left


def draw_hands(canvas, box, scale) -> None:
    """Watch hands at ten past ten, the way watches are pictured."""
    center_x, center_y, width = _face_center(box)
    # (degrees clockwise from twelve o'clock, length, thickness): hour hand at ten, minute hand at two.
    for angle, length, thickness in ((300, 0.20, 4), (60, 0.28, 3)):
        radians = math.radians(angle)
        tip = (center_x + width * length * math.sin(radians), center_y - width * length * math.cos(radians))
        canvas.line((center_x, center_y, *tip), fill='white', width=thickness * scale)
    dot = 3.5 * scale
    canvas.ellipse((center_x - dot, center_y - dot, center_x + dot, center_y + dot), fill='white')


def draw_smile(canvas, box, scale) -> None:
    """A happy face: two eyes and a smile."""
    center_x, center_y, width = _face_center(box)
    eye = width * 0.055
    for side in (-1, 1):
        eye_x, eye_y = center_x + side * width * 0.16, center_y - width * 0.10
        canvas.ellipse((eye_x - eye, eye_y - eye * 1.3, eye_x + eye, eye_y + eye * 1.3), fill='white')
    smile = width * 0.24
    canvas.arc((center_x - smile, center_y - smile * 0.9, center_x + smile, center_y + smile * 0.85),
               start=25, end=155, fill='white', width=4 * scale)
