import os

from streamdock_sdk import Widget, draw


class Keeper(Widget):
    id = 'fixture_data_dir'
    name = 'Keeper'
    version = '1.0'

    def setup(self, ctx):
        with open(os.path.join(ctx.data_dir, 'state.txt'), 'w', encoding='utf-8') as handle:
            handle.write('kept')

    def render(self, ctx):
        return draw.text_key('k', size=ctx.size)
