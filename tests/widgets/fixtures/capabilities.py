import subprocess
import urllib.request

from streamdock_sdk import Widget, draw


class Capable(Widget):
    id = 'fixture_capable'
    name = 'Capable'
    version = '1.0'

    def render(self, ctx):
        return draw.text_key('c', size=ctx.size)

    def fetch(self):
        eval('1')
        subprocess.run(['true'], check=False)
        return urllib.request.urlopen
