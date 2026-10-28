from typing import List, Optional

from streamdock_sdk import Option, Widget, draw
from StreamDock.widgets.builtin import _common, _pulse, _volume


def cycle(sinks: List[_pulse.Sink], patterns: str) -> List[_pulse.Sink]:
    """The outputs a press cycles through: those matching ``patterns``, in the order given, or all."""
    wanted = [pattern.strip().lower() for pattern in patterns.split(',') if pattern.strip()]
    if not wanted:
        return list(sinks)
    chosen = []
    for pattern in wanted:
        for sink in sinks:
            if (pattern in sink.name.lower() or pattern in sink.description.lower()) and sink not in chosen:
                chosen.append(sink)
    return chosen


def display_name(sink: _pulse.Sink, names: str) -> str:
    """The user's short name for ``sink`` from ``names`` ("part=Name, ..."), else its description."""
    for entry in names.split(','):
        part, equals, label = entry.partition('=')
        part = part.strip().lower()
        if equals and part and (part in sink.name.lower() or part in sink.description.lower()):
            return label.strip()
    return sink.description


def next_sink(sinks: List[_pulse.Sink], current: Optional[str]) -> Optional[_pulse.Sink]:
    if not sinks:
        return None
    names = [sink.name for sink in sinks]
    if current not in names:
        return sinks[0]
    return sinks[(names.index(current) + 1) % len(sinks)]


class AudioOutput(Widget):
    id = 'audio_output'
    name = 'Audio Output'
    version = '1.0.0'
    description = ('Which speakers or headphones sound plays through. Each press switches to the next '
                   'output, and the playing sound moves with it.')
    author = 'StreamDock'
    states = ('speakers', 'headphones', 'hdmi', 'unknown')
    options = [
        Option.string('outputs', default='', label='Outputs to switch between',
                      description='Comma-separated parts of output names, in order, e.g. "Speakers, Buds". '
                                  'Empty: every output.'),
        Option.bool('move_streams', default=True, label='Move playing sound',
                    description='Move what is playing to the new output. PipeWire does this by itself.'),
        Option.bool('show_name', default=True, label="Show the output's name"),
        Option.string('names', default='', label='Short names',
                      description='Your own names for outputs, e.g. "Built-in=Desk, Sony=Buds".'),
        Option.color('color', default='#ffffff', label='Icon colour'),
        Option.color('background', default='#1c262b', label='Background'),
    ]

    def setup(self, ctx):
        self.sinks: List[_pulse.Sink] = _pulse.list_sinks() or []
        self.current: Optional[str] = _pulse.default_sink()
        self.report(ctx)
        self.watch = _pulse.ChangeWatch('sink', lambda: self._read_now(ctx))
        # Catches outputs appearing and leaving, which pactl reports as new/remove, not change.
        ctx.every(10, lambda: self.refresh(ctx))

    def on_show(self, ctx):
        self.watch.start()
        self.refresh(ctx)

    def on_hide(self, ctx):
        self.stop_watching()

    def teardown(self, ctx):
        self.stop_watching()

    def stop_watching(self):
        self.watch.stop()

    @staticmethod
    def read():
        return _pulse.list_sinks() or [], _pulse.default_sink()

    def _read_now(self, ctx):
        # Read here rather than through the backstop's refresh(), which skips
        # a read while one is in flight - and that one may predate the change.
        result = self.read()
        ctx.call_soon(lambda: self.update(ctx, *result))

    def refresh(self, ctx):
        ctx.run_in_background(self.read, then=lambda result: self.update(ctx, *result), skip_if_running=True)

    def update(self, ctx, sinks, current):
        if (sinks, current) != (self.sinks, self.current):
            self.sinks, self.current = sinks, current
            self.report(ctx)
            ctx.request_render()

    def on_press(self, ctx):
        target = next_sink(cycle(self.sinks, ctx.options['outputs']), self.current)
        if target is None or target.name == self.current:
            return
        move = ctx.options['move_streams']
        # Show it at once; the read afterwards corrects it if pactl refused.
        self.update(ctx, self.sinks, target.name)

        def switch():
            _pulse.set_default_sink(target.name, move)
            return self.read()
        ctx.run_in_background(switch, then=lambda result: self.update(ctx, *result))

    def current_sink(self) -> Optional[_pulse.Sink]:
        return next((sink for sink in self.sinks if sink.name == self.current), None)

    def report(self, ctx):
        sink = self.current_sink()
        ctx.set_state(sink.kind if sink else 'unknown')

    def render(self, ctx):
        options = ctx.options
        image, canvas, scale = _common.supersampled(ctx.size, options['background'])
        width, height = image.size
        color = options['color']
        sink = self.current_sink()
        if options['show_name']:
            icon = (22 * scale, 8 * scale, width - 22 * scale, 64 * scale)
        else:
            icon = (16 * scale, 16 * scale, width - 16 * scale, height - 16 * scale)
        kind = sink.kind if sink else 'unknown'
        if kind == 'headphones':
            draw_headphones(canvas, icon, color, scale)
        elif kind == 'hdmi':
            draw_monitor(canvas, icon, color, scale)
        else:
            _volume.draw_speaker(canvas, icon, color, scale)
        if options['show_name']:
            name = display_name(sink, options['names']) if sink else 'No output'
            text_font = draw.font(13 * scale)
            lines = draw.wrap(canvas, name, text_font, width - 12 * scale, 2)
            line_height = 16 * scale
            top = 68 * scale + (2 - len(lines)) * line_height // 2
            for index, line in enumerate(lines):
                draw.centered_text(canvas, (6 * scale, top + index * line_height, width - 6 * scale,
                                            top + (index + 1) * line_height), line, color=color, text_font=text_font)
        return _common.downsample(image, ctx.size)


def _square(box):
    left, top, right, bottom = box
    side = min(right - left, bottom - top)
    return (left + right - side) / 2, (top + bottom - side) / 2, side


def draw_headphones(canvas, box, color: str, scale: int) -> None:
    x, y, side = _square(box)
    band = side * 0.09
    canvas.arc((x + side * 0.10, y + side * 0.06, x + side * 0.90, y + side * 0.86), start=180, end=360,
               fill=color, width=int(band))
    canvas.line((x + side * 0.10 + band / 2, y + side * 0.46, x + side * 0.10 + band / 2, y + side * 0.62),
                fill=color, width=int(band))
    canvas.line((x + side * 0.90 - band / 2, y + side * 0.46, x + side * 0.90 - band / 2, y + side * 0.62),
                fill=color, width=int(band))
    for left in (x + side * 0.06, x + side * 0.70):
        canvas.rounded_rectangle((left, y + side * 0.52, left + side * 0.24, y + side * 0.94),
                                 radius=side * 0.07, fill=color)


def draw_monitor(canvas, box, color: str, scale: int) -> None:
    x, y, side = _square(box)
    canvas.rounded_rectangle((x + side * 0.04, y + side * 0.10, x + side * 0.96, y + side * 0.72),
                             radius=side * 0.05, outline=color, width=int(side * 0.07))
    canvas.rectangle((x + side * 0.44, y + side * 0.72, x + side * 0.56, y + side * 0.86), fill=color)
    canvas.rounded_rectangle((x + side * 0.26, y + side * 0.84, x + side * 0.74, y + side * 0.92),
                             radius=side * 0.03, fill=color)
