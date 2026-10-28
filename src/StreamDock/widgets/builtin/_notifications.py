"""
Unread counts from desktop notifications, shared by the messaging widgets.

One ``busctl monitor`` on the session bus serves every counter in the process.
It sees each ``Notify`` call (a new notification) and each
``CloseNotification`` call (an app withdrawing one of its own, which chat apps
do once the message is read).

A count clears in three ways, each optional:

- pressing the key;
- the app's window getting focus (``focus_match`` against its class or title,
  so a browser tab titled "WhatsApp" counts);
- the app closing the notifications it had sent.

Counters keep listening while their key is off the device
(``run_while_hidden``); a counter that only counted while visible would miss
exactly the messages it exists to report.
"""

import json
import logging
from dataclasses import dataclass
from typing import Dict, List, Optional

from streamdock_sdk import Option, Widget
from StreamDock.widgets.builtin import _common

logger = logging.getLogger(__name__)

_MATCHES = [
    "type='method_call',interface='org.freedesktop.Notifications',member='Notify'",
    "type='method_call',interface='org.freedesktop.Notifications',member='CloseNotification'",
]


@dataclass
class NotificationEvent:
    kind: str  # 'notify' or 'close'
    sender: str
    app: str = ''
    summary: str = ''
    body: str = ''
    desktop_entry: str = ''
    replaces_id: int = 0

    @property
    def text(self) -> str:
        return f'{self.summary}\n{self.body}'


def parse_event(line: str) -> Optional[NotificationEvent]:
    """One line of ``busctl monitor --json=short`` output, if it's a call we care about."""
    try:
        message = json.loads(line)
        member = message.get('member')
        data = message['payload']['data']
        sender = str(message.get('sender', ''))
    except (ValueError, KeyError, TypeError, AttributeError):
        return None
    if member == 'CloseNotification':
        return NotificationEvent('close', sender)
    if member != 'Notify':
        return None
    try:
        app, replaces_id, _icon, summary, body = data[:5]
        hints = data[6] if len(data) > 6 and isinstance(data[6], dict) else {}
        replaces_id = int(replaces_id or 0)
    except (ValueError, TypeError):
        return None
    entry = hints.get('desktop-entry')
    entry = entry.get('data') if isinstance(entry, dict) else entry
    return NotificationEvent('notify', sender, str(app), str(summary), str(body),
                             entry if isinstance(entry, str) else '', replaces_id)


class NotificationHub(_common.ProcessHub):
    """
    The one monitor process, started by the first subscriber and stopped with the last.

    ``callback(event)`` per event; ``callback(None)`` if the bus can't be watched.
    """

    def __init__(self):
        command = ['busctl', '--user', 'monitor', '--json=short']
        for match in _MATCHES:
            command += ['--match', match]
        super().__init__(command, 'notification-monitor', parse_event)


HUB = NotificationHub()


def counter_options(apps: str, site: str, focus: str, unread_color: str) -> List[Option]:
    return [
        Option.string('app_name', default=apps, label='Application',
                      description='Comma-separated parts of the app name that sends the notifications'),
        Option.string('site', default=site, label='Website',
                      description='Count browser notifications whose text mentions this site. Empty to skip.'),
        Option.bool('reset_on_press', default=True, label='Press clears the count'),
        Option.bool('clear_on_focus', default=True, label='Clear when the app gets focus'),
        Option.string('focus_match', default=focus, label='App window',
                      description='Part of the window class or title that means you are reading messages'),
        Option.bool('follow_app', default=True, label='Clear when the app clears its notifications'),
        Option.color('unread_color', default=unread_color, label='Unread background'),
        Option.color('idle_color', default='#202020', label='No-unread background'),
        Option.color('color', default='#ffffff', label='Icon colour'),
    ]


def _terms(value: str) -> List[str]:
    return [term.strip().lower() for term in value.split(',') if term.strip()]


class NotificationCounter(Widget):
    """Counts one app's notifications; subclasses set the defaults and draw the glyph."""

    states = ('unread', 'none', 'unavailable')
    supports_badge = True
    run_while_hidden = True

    def setup(self, ctx):
        self.count = 0
        self.available = True
        # Unread notifications per sending connection, so an app withdrawing
        # its notifications only uncounts what it sent.
        self.pending: Dict[str, int] = {}
        self.apps = _terms(ctx.options['app_name'])
        self.site = ctx.options['site'].strip().lower()
        self.focus = ctx.options['focus_match'].strip().lower()
        self._listener = lambda event: ctx.call_soon(lambda: self.on_notification(ctx, event))
        HUB.subscribe(self._listener)
        self.publish(ctx)

    def teardown(self, ctx):
        HUB.unsubscribe(self._listener)

    def matches(self, event: NotificationEvent) -> bool:
        app = f'{event.app}\n{event.desktop_entry}'.lower()
        if any(term in app for term in self.apps):
            return True
        return bool(self.site) and self.site in event.text.lower()

    def on_notification(self, ctx, event: Optional[NotificationEvent]):
        if event is None:
            self.available = False
        elif event.kind == 'notify':
            self.available = True
            if event.replaces_id or not self.matches(event):
                return
            self.count += 1
            self.pending[event.sender] = self.pending.get(event.sender, 0) + 1
        elif event.kind == 'close':
            if not ctx.options['follow_app'] or not self.pending.get(event.sender):
                return
            self.pending[event.sender] -= 1
            self.count = max(0, self.count - 1)
        self.publish(ctx)

    def on_window_focus(self, ctx, app, title):
        if ctx.options['clear_on_focus'] and self.focus and self.count and \
                (self.focus in app.lower() or self.focus in title.lower()):
            self.clear(ctx)

    def on_press(self, ctx):
        if ctx.options['reset_on_press'] and self.count:
            self.clear(ctx)

    def clear(self, ctx):
        self.count = 0
        self.pending.clear()
        self.publish(ctx)

    def count_text(self) -> str:
        return '99+' if self.count > 99 else str(self.count)

    def publish(self, ctx):
        ctx.set_state('unavailable' if not self.available else 'unread' if self.count else 'none')
        ctx.set_badge(self.count_text() if self.count else None)
        ctx.request_render()

    def draw_glyph(self, canvas, box, color, background, scale):
        raise NotImplementedError

    def render(self, ctx):
        options = ctx.options
        caption = self.count_text() if self.count else ('—' if self.available else '?')
        background = options['unread_color'] if self.count else options['idle_color']
        image, canvas, scale, box = _common.status_tile(ctx.size, background, caption, options['color'])
        self.draw_glyph(canvas, box, options['color'], background, scale)
        return _common.downsample(image, ctx.size)
