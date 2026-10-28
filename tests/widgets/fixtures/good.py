from streamdock_sdk import Option, Widget, draw


class Good(Widget):
    id = 'fixture_good'
    name = 'Good'
    version = '1.2.3'
    description = 'Draws its label; presses count.'
    options = [
        Option.string('label', default='hi'),
        Option.int('start', default=0, minimum=0, maximum=10),
    ]

    def setup(self, ctx):
        self.count = ctx.options['start']

    def render(self, ctx):
        return draw.text_key(f"{ctx.options['label']}{self.count}", size=ctx.size)

    def on_press(self, ctx):
        self.count += 1
        ctx.request_render()
