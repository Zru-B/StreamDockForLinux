from streamdock_sdk import Widget, draw

print('noise at import')


class Printing(Widget):
    id = 'fixture_printing'
    name = 'Printing'
    version = '1.0'

    def render(self, ctx):
        print('noise in render')
        return draw.text_key('p', size=ctx.size)
