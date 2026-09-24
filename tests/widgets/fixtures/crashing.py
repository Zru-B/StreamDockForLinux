import os

from streamdock_sdk import Widget, draw


class Crashing(Widget):
    id = 'fixture_crashing'
    name = 'Crashing'
    version = '1.0'

    def setup(self, ctx):
        os._exit(3)

    def render(self, ctx):
        return draw.text_key('x', size=ctx.size)
