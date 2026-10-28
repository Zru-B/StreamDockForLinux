from streamdock_sdk import Option, Widget, draw


class BadOption(Widget):
    id = 'fixture_bad_option'
    name = 'Bad Option'
    version = '1.0'
    options = [Option.choice('mode', ['a', 'b'], default='c')]

    def render(self, ctx):
        return draw.text_key('b', size=ctx.size)
