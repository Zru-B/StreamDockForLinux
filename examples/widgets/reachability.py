"""
Is a server reachable? Shows up/down and the connection time.

Demonstrates what the counter example doesn't: background work that must not
block render, declared states (so users can map their own images to up and
down), a badge, and pausing while the key is off the device.
"""

import socket
import time

from streamdock_sdk import Option, Widget, draw


def connect_ms(host, port, timeout):
    """Milliseconds to open a TCP connection, or None if it failed."""
    started = time.monotonic()
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return (time.monotonic() - started) * 1000
    except OSError:
        return None


class Reachability(Widget):
    id = 'reachability'
    name = 'Reachability'
    version = '1.0.0'
    description = 'Whether a server answers on a TCP port, and how fast.'
    author = 'StreamDock examples'
    states = ('up', 'down', 'checking')
    supports_badge = True
    options = [
        Option.string('host', default='example.com', label='Host'),
        Option.int('port', default=443, minimum=1, maximum=65535, label='Port'),
        Option.int('interval', default=30, minimum=5, maximum=3600, label='Check every (s)'),
        Option.color('up_color', default='#1b5e20', label='Up background'),
        Option.color('down_color', default='#b71c1c', label='Down background'),
    ]

    def setup(self, ctx):
        self.latency = None
        self.checked = False
        ctx.set_state('checking')
        # Timers only run while the key is shown.
        ctx.every(ctx.options['interval'], lambda: self.check(ctx))

    def on_show(self, ctx):
        # Timers were paused while hidden; don't show a stale answer.
        self.check(ctx)

    def check(self, ctx):
        host, port = ctx.options['host'], ctx.options['port']
        # The network call runs off the widget's thread; the result comes back to it.
        ctx.run_in_background(lambda: connect_ms(host, port, timeout=5),
                              then=lambda latency: self.update(ctx, latency))

    def update(self, ctx, latency):
        self.latency, self.checked = latency, True
        ctx.set_state('up' if latency is not None else 'down')
        ctx.set_badge(f'{latency:.0f}' if latency is not None else None)
        ctx.request_render()

    def on_press(self, ctx):
        self.check(ctx)

    def render(self, ctx):
        options = ctx.options
        if not self.checked:
            return draw.text_key('…', background='#303030', size=ctx.size)
        up = self.latency is not None
        image, canvas = draw.canvas(ctx.size, options['up_color'] if up else options['down_color'])
        width, height = ctx.size
        draw.centered_text(canvas, (6, 6, width - 6, height * 0.55), options['host'], bold=False)
        draw.centered_text(canvas, (10, height * 0.55, width - 10, height - 8),
                           f'{self.latency:.0f} ms' if up else 'DOWN')
        return image
