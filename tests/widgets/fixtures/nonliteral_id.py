from streamdock_sdk import Widget, draw

PREFIX = 'fixture'


class Computed(Widget):
    id = PREFIX + '_computed'
    name = 'Computed'
    version = '1.0'

    def render(self, ctx):
        return draw.text_key('c', size=ctx.size)
