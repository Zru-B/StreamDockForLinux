from streamdock_sdk import Widget, draw


class One(Widget):
    id = 'fixture_one'
    name = 'One'
    version = '1.0'

    def render(self, ctx):
        return draw.text_key('1', size=ctx.size)


class Two(Widget):
    id = 'fixture_two'
    name = 'Two'
    version = '1.0'

    def render(self, ctx):
        return draw.text_key('2', size=ctx.size)
