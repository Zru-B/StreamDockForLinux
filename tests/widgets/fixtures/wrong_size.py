from PIL import Image

from streamdock_sdk import Widget


class WrongSize(Widget):
    id = 'fixture_wrong_size'
    name = 'Wrong Size'
    version = '1.0'

    def render(self, ctx):
        return Image.new('RGB', (50, 50))
