"""
A minimal StreamDock widget: counts presses, and a long press resets it.

Install it from the app's Widgets window, then pick "Counter" as a key's
widget. See docs/widgets.md.
"""

from streamdock_sdk import Option, Widget, draw


class Counter(Widget):
    id = 'hello_counter'
    name = 'Counter'
    version = '1.0.0'
    sdk_version = 1
    description = 'Counts presses; hold the key to reset.'
    author = 'StreamDock examples'
    options = [
        Option.color('color', default='#ffffff', label='Text colour'),
        Option.color('background', default='#1a237e', label='Background'),
        Option.int('start', default=0, minimum=0, label='Start at'),
    ]

    def setup(self, ctx):
        self.count = ctx.options['start']

    def render(self, ctx):
        return draw.text_key(str(self.count), color=ctx.options['color'],
                             background=ctx.options['background'], size=ctx.size)

    def on_press(self, ctx):
        self.count += 1
        ctx.request_render()

    def on_long_press(self, ctx):
        self.count = ctx.options['start']
        ctx.request_render()
