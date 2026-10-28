from StreamDock.widgets.builtin import _volume
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
        _volume.draw_speaker(canvas, box, color, scale)
