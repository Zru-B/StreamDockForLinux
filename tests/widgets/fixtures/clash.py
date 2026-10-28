from streamdock_sdk import Widget, draw


class Clash(Widget):
    id = 'digital_clock'
    name = 'Impostor Clock'
    version = '1.0'

    def render(self, ctx):
        return draw.text_key('00:00', size=ctx.size)
