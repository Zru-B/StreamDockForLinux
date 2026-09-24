from StreamDock.widgets.builtin._pulse import MuteWidget


class SoundMuted(MuteWidget):
    id = 'sound_muted'
    name = 'Sound Mute'
    version = '1.0.0'
    description = 'Whether the default speaker is muted. Pressing the key can toggle it.'
    author = 'StreamDock'
    kind = 'sink'
    on_caption = 'ON'
    options = MuteWidget.options
    states = MuteWidget.states

    def draw_icon(self, canvas, box, color, scale):
        left, top, right, bottom = box
        width, height = right - left, bottom - top
        middle = top + height / 2
        body_left = left + width * 0.05
        canvas.polygon([
            (body_left, middle - height * 0.16), (body_left + width * 0.20, middle - height * 0.16),
            (body_left + width * 0.48, middle - height * 0.40), (body_left + width * 0.48, middle + height * 0.40),
            (body_left + width * 0.20, middle + height * 0.16), (body_left, middle + height * 0.16),
        ], fill=color)
        for step, reach in enumerate((0.22, 0.38)):
            radius = height * reach
            origin = body_left + width * 0.48
            canvas.arc((origin - radius, middle - radius, origin + radius, middle + radius),
                       start=-50, end=50, fill=color, width=(3 - step) * scale + scale)
