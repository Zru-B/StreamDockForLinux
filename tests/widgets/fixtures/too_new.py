from streamdock_sdk import Widget, draw


class TooNew(Widget):
    id = 'fixture_too_new'
    name = 'Too New'
    version = '1.0'
    sdk_version = 99

    def render(self, ctx):
        return draw.text_key('n', size=ctx.size)
