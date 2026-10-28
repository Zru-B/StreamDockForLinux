from streamdock_sdk import Widget, draw


class BadStates(Widget):
    id = 'fixture_bad_states'
    name = 'Bad States'
    version = '1.0'
    states = ('On Air', 'on')

    def render(self, ctx):
        return draw.text_key('x', size=ctx.size)
