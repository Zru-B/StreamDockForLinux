from typing import Optional

from streamdock_sdk import Option, Widget
from StreamDock.widgets.builtin import _common, _dnd


class DoNotDisturb(Widget):
    id = 'do_not_disturb'
    name = 'Do Not Disturb'
    version = '1.0.0'
    description = ('Silences desktop notifications. Each press switches Do Not Disturb on or off; the key '
                   'shows a moon while it is on and a bell while notifications are shown.')
    author = 'StreamDock'
    states = ('on', 'off', 'unavailable')
    options = [
        Option.choice('backend', list(_dnd.BACKENDS), default='auto', label='Desktop',
                      description='auto picks KDE, GNOME or XFCE by desktop, else a running swaync or dunst.'),
        Option.int('interval', default=5, minimum=1, maximum=300, label='Check every (s)',
                   description='How often to pick up Do Not Disturb switched elsewhere, e.g. in the tray.'),
        Option.bool('show_caption', default=True, label='Show caption'),
        Option.color('on_color', default='#4a148c', label='Background when on'),
        Option.color('off_color', default='#263238', label='Background when off'),
        Option.color('color', default='#ffffff', label='Icon colour'),
    ]

    def setup(self, ctx):
        self.backend = _dnd.backend(ctx.options['backend'])
        self.on: Optional[bool] = self.backend.read() if self.backend else None
        ctx.set_state(self.state_name())
        ctx.every(ctx.options['interval'], lambda: self.check(ctx))

    def on_show(self, ctx):
        self.check(ctx)

    def check(self, ctx):
        backend = self.backend
        if backend is None:
            return
        ctx.run_in_background(backend.read, then=lambda on: self.update(ctx, on))

    def on_press(self, ctx):
        backend = self.backend
        if backend is None:
            # Maybe the notification daemon has started since.
            self.backend = backend = _dnd.backend(ctx.options['backend'])
            if backend is None:
                return
        wanted = not self.on
        # Show the new state at once; the read afterwards corrects it if the switch didn't take.
        self.update(ctx, wanted)

        def switch():
            backend.write(wanted)
            return backend.read()
        ctx.run_in_background(switch, then=lambda on: self.update(ctx, on))

    def state_name(self) -> str:
        return 'unavailable' if self.on is None else 'on' if self.on else 'off'

    def update(self, ctx, on: Optional[bool]):
        if on != self.on:
            self.on = on
            ctx.set_state(self.state_name())
            ctx.request_render()

    def render(self, ctx):
        options = ctx.options
        if self.on is None:
            background, caption = '#424242', 'DND ?'
        elif self.on:
            background, caption = options['on_color'], 'DND ON'
        else:
            background, caption = options['off_color'], 'DND OFF'
        image, canvas, scale, box = _common.status_tile(ctx.size, background,
                                                        caption if options['show_caption'] else '',
                                                        options['color'])
        if not options['show_caption']:
            left, top, right, _ = box
            box = (left, top + 4 * scale, right, image.size[1] - 14 * scale)
        if self.on:
            draw_moon(canvas, box, options['color'], background)
        else:
            draw_bell(canvas, box, options['color'])
        return _common.downsample(image, ctx.size)


def _square(box):
    """The largest square centred in ``box``."""
    left, top, right, bottom = box
    side = min(right - left, bottom - top)
    x, y = (left + right - side) / 2, (top + bottom - side) / 2
    return x, y, side


def draw_moon(canvas, box, color: str, background: str) -> None:
    """A crescent moon with two small stars."""
    x, y, side = _square(box)
    radius = side * 0.40
    center_x, center_y = x + side * 0.46, y + side * 0.54
    canvas.ellipse((center_x - radius, center_y - radius, center_x + radius, center_y + radius), fill=color)
    # Cut the crescent with a disc of the background, up and to the right.
    cut_x, cut_y, cut = center_x + radius * 0.50, center_y - radius * 0.38, radius * 0.86
    canvas.ellipse((cut_x - cut, cut_y - cut, cut_x + cut, cut_y + cut), fill=background)
    for star_x, star_y, size in ((0.84, 0.16, 0.07), (0.70, 0.36, 0.045)):
        _star(canvas, x + side * star_x, y + side * star_y, side * size, color)


def _star(canvas, center_x, center_y, size, color):
    canvas.polygon([
        (center_x, center_y - size), (center_x + size * 0.3, center_y - size * 0.3),
        (center_x + size, center_y), (center_x + size * 0.3, center_y + size * 0.3),
        (center_x, center_y + size), (center_x - size * 0.3, center_y + size * 0.3),
        (center_x - size, center_y), (center_x - size * 0.3, center_y - size * 0.3),
    ], fill=color)


def draw_bell(canvas, box, color: str) -> None:
    """A notification bell."""
    x, y, side = _square(box)
    center = x + side / 2
    # Knob, dome, flared skirt, rim and clapper, top to bottom.
    knob = side * 0.06
    canvas.ellipse((center - knob, y + side * 0.02, center + knob, y + side * 0.02 + 2 * knob), fill=color)
    dome = side * 0.30
    canvas.pieslice((center - dome, y + side * 0.10, center + dome, y + side * 0.10 + 2 * dome),
                    start=180, end=360, fill=color)
    dome_middle = y + side * 0.10 + dome
    canvas.polygon([
        (center - dome, dome_middle - 1), (center + dome, dome_middle - 1),
        (center + side * 0.40, y + side * 0.74), (center - side * 0.40, y + side * 0.74),
    ], fill=color)
    canvas.rounded_rectangle((center - side * 0.46, y + side * 0.72, center + side * 0.46, y + side * 0.80),
                             radius=side * 0.04, fill=color)
    clapper = side * 0.09
    canvas.pieslice((center - clapper, y + side * 0.80 - clapper, center + clapper, y + side * 0.80 + clapper),
                    start=0, end=180, fill=color)
