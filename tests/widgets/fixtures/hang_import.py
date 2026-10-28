import time

from streamdock_sdk import Widget, draw

time.sleep(60)


class Hang(Widget):
    id = 'fixture_hang'
    name = 'Hang'
    version = '1.0'

    def render(self, ctx):
        return draw.text_key('h', size=ctx.size)
