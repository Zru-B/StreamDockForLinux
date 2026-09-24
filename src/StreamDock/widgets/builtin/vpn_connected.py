import fnmatch
import os
import subprocess
from typing import Optional

from streamdock_sdk import Option, Widget
from StreamDock.widgets.builtin import _common

SYS_NET = '/sys/class/net'


def interface_up(pattern_list: str, sys_net: str = SYS_NET) -> bool:
    """Whether an administratively-up interface matches any comma-separated glob."""
    patterns = [pattern.strip() for pattern in pattern_list.split(',') if pattern.strip()]
    try:
        names = os.listdir(sys_net)
    except OSError:
        return False
    for name in names:
        if not any(fnmatch.fnmatch(name, pattern) for pattern in patterns):
            continue
        try:
            with open(os.path.join(sys_net, name, 'flags'), encoding='ascii') as handle:
                # operstate reads 'unknown' for tun devices, so use IFF_UP.
                if int(handle.read().strip(), 16) & 0x1:
                    return True
        except (OSError, ValueError):
            continue
    return False


def networkmanager_vpn() -> Optional[bool]:
    """True if NetworkManager has an active VPN or WireGuard connection; None without nmcli."""
    try:
        result = subprocess.run(['nmcli', '-t', '-f', 'TYPE,STATE', 'connection', 'show', '--active'],
                                capture_output=True, text=True, timeout=3, check=False)
    except (OSError, subprocess.TimeoutExpired):
        return None
    if result.returncode != 0:
        return None
    for line in result.stdout.splitlines():
        kind, _, state = line.partition(':')
        if kind in ('vpn', 'wireguard') and state == 'activated':
            return True
    return False


class VpnConnected(Widget):
    id = 'vpn_connected'
    name = 'VPN Status'
    version = '1.0.0'
    description = 'Whether a VPN is connected, from NetworkManager and/or matching network interfaces.'
    author = 'StreamDock'
    states = ('connected', 'disconnected', 'unknown')
    options = [
        Option.choice('source', ['auto', 'networkmanager', 'interfaces'], default='auto', label='Detect with',
                      description='auto: connected if either NetworkManager or an interface says so.'),
        Option.string('interfaces', default='tun*,wg*,ppp*', label='Interface names',
                      description='Comma-separated patterns, e.g. tun*,wg0,tailscale0'),
        Option.int('interval', default=3, minimum=1, maximum=300, label='Check every (s)'),
        Option.color('connected_color', default='#1b5e20', label='Connected background'),
        Option.color('disconnected_color', default='#424242', label='Disconnected background'),
        Option.color('color', default='#ffffff', label='Icon colour'),
    ]

    def setup(self, ctx):
        # Checked once up front so the first frame shows the real state.
        self.connected: Optional[bool] = self.detect(ctx.options)
        ctx.set_state(self.state_name())
        ctx.every(ctx.options['interval'], lambda: self.check(ctx))

    def on_show(self, ctx):
        self.check(ctx)

    def check(self, ctx):
        ctx.run_in_background(lambda: self.detect(ctx.options), then=lambda state: self.update(ctx, state))

    @staticmethod
    def detect(options) -> Optional[bool]:
        source = options['source']
        manager = networkmanager_vpn() if source in ('auto', 'networkmanager') else None
        interfaces = interface_up(options['interfaces']) if source in ('auto', 'interfaces') else None
        if manager is None and interfaces is None:
            return None
        return bool(manager) or bool(interfaces)

    def state_name(self) -> str:
        return 'unknown' if self.connected is None else 'connected' if self.connected else 'disconnected'

    def update(self, ctx, state):
        if state != self.connected:
            self.connected = state
            ctx.set_state(self.state_name())
            ctx.request_render()

    def render(self, ctx):
        options = ctx.options
        if self.connected is None:
            background, caption = '#424242', '?'
        elif self.connected:
            background, caption = options['connected_color'], 'VPN ON'
        else:
            background, caption = options['disconnected_color'], 'VPN OFF'
        image, canvas, scale, (left, top, right, bottom) = _common.status_tile(
            ctx.size, background, caption, options['color'])
        width, height = right - left, bottom - top
        center = (left + right) / 2
        shield = [
            (center, top), (right - width * 0.08, top + height * 0.16),
            (right - width * 0.12, top + height * 0.60), (center, bottom),
            (left + width * 0.12, top + height * 0.60), (left + width * 0.08, top + height * 0.16),
        ]
        if self.connected:
            canvas.polygon(shield, fill=options['color'])
            canvas.line((center - width * 0.18, top + height * 0.50, center - width * 0.03, top + height * 0.66,
                         center + width * 0.22, top + height * 0.34), fill=background, width=5 * scale)
        else:
            canvas.polygon(shield, outline=options['color'], width=3 * scale)
        return _common.downsample(image, ctx.size)
