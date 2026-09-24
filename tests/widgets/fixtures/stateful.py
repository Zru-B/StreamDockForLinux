from streamdock_sdk import Widget, draw


class Stateful(Widget):
    id = 'fixture_stateful'
    name = 'Stateful'
    version = '1.0'
    states = ('on', 'off')
    supports_badge = True

    def setup(self, ctx):
        self.on = True
        ctx.set_state('on')
        ctx.set_badge('5')

    def render(self, ctx):
        return draw.text_key('on' if self.on else 'off', size=ctx.size)

    def on_press(self, ctx):
        self.on = not self.on
        ctx.set_state('on' if self.on else 'off')
        ctx.set_badge(None if not self.on else '5')
        ctx.request_render()

    def on_window_focus(self, ctx, app, title):
        ctx.set_badge(app[:3])
