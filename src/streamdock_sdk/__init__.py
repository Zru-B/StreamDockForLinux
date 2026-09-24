"""
StreamDock widget SDK.

A widget is a key whose image a Python script draws at runtime. Subclass
``Widget``, declare its ``options``, and return a PIL image from ``render``::

    from streamdock_sdk import Option, Widget, draw

    class Counter(Widget):
        id = 'hello_counter'
        name = 'Counter'
        version = '1.0.0'
        options = [Option.color('color', default='#ffffff')]

        def setup(self, ctx):
            self.count = 0

        def render(self, ctx):
            return draw.text_key(str(self.count), color=ctx.options['color'], size=ctx.size)

        def on_press(self, ctx):
            self.count += 1
            ctx.request_render()

See docs/widgets.md for the full guide.
"""

from streamdock_sdk import draw
from streamdock_sdk.context import WidgetContext
from streamdock_sdk.options import Option, OptionError
from streamdock_sdk.widget import KEY_EVENTS, SDK_VERSION, Widget

__all__ = ['KEY_EVENTS', 'Option', 'OptionError', 'SDK_VERSION', 'Widget', 'WidgetContext', 'draw']
