from streamdock_sdk import draw


class NotAWidget:
    def render(self, ctx):
        return draw.text_key('n')
