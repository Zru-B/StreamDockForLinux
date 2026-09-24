from helper import LABEL

from streamdock_sdk import Widget, draw


class FolderWidget(Widget):
    id = 'fixture_folder'
    name = 'Folder'
    version = '1.0'

    def render(self, ctx):
        return draw.text_key(LABEL, size=ctx.size)
