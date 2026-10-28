from StreamDock.widgets.builtin._pulse import MuteWidget


class MicMuted(MuteWidget):
    id = 'mic_muted'
    name = 'Microphone Mute'
    version = '1.0.0'
    description = 'Whether the default microphone is muted. Pressing the key can toggle it.'
    author = 'StreamDock'
    kind = 'source'
    on_caption = 'LIVE'
    options = MuteWidget.options
    states = MuteWidget.states

    def draw_icon(self, canvas, box, color, scale):
        left, top, right, bottom = box
        width = right - left
        center = (left + right) / 2
        capsule = width * 0.34
        canvas.rounded_rectangle((center - capsule / 2, top, center + capsule / 2, top + (bottom - top) * 0.62),
                                 radius=capsule / 2, fill=color)
        cup = width * 0.56
        cup_top = top + (bottom - top) * 0.30
        cup_bottom = top + (bottom - top) * 0.78
        canvas.arc((center - cup / 2, cup_top - (cup_bottom - cup_top), center + cup / 2, cup_bottom),
                   start=0, end=180, fill=color, width=3 * scale)
        canvas.line((center, cup_bottom, center, bottom), fill=color, width=3 * scale)
        canvas.line((center - width * 0.18, bottom, center + width * 0.18, bottom), fill=color, width=3 * scale)
