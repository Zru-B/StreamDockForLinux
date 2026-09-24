"""
Child-process entry point for a third-party widget: ``python -m streamdock_sdk.host <script>``.

Speaks JSON lines with the app. stdin carries commands::

    {"op": "start", "options": {...}, "size": [112, 112], "data_dir": "...", "frames": true}
    {"op": "render_once", "options": {...}, "size": [112, 112]}
    {"op": "event", "name": "press"}
    {"op": "focus", "app": "slack", "title": "..."}
    {"op": "show"} / {"op": "hide"} / {"op": "stop"}

stdout carries replies::

    {"op": "ready", "manifest": {...}}
    {"op": "frame", "png": "<base64>"}
    {"op": "state", "state": "connected"}      (or null)
    {"op": "badge", "text": "3"}               (or null)
    {"op": "error", "message": "..."}

Widget code shares the process, so before it runs, file descriptor 1 is
pointed at stderr and the protocol keeps a private duplicate: a stray
``print()`` in a widget lands in the app's log instead of corrupting a reply.
"""

import base64
import io
import json
import logging
import os
import sys
import threading
import traceback

from streamdock_sdk.loader import load_widget_class
from streamdock_sdk.options import OptionError, resolve_options
from streamdock_sdk.scheduler import WidgetDriver


class _Channel:
    def __init__(self, stream):
        self._stream = stream
        self._lock = threading.Lock()

    def send(self, message) -> None:
        line = json.dumps(message)
        with self._lock:
            self._stream.write(line + '\n')
            self._stream.flush()

    def frame(self, image) -> None:
        buffer = io.BytesIO()
        image.save(buffer, format='PNG')
        self.send({'op': 'frame', 'png': base64.b64encode(buffer.getvalue()).decode('ascii')})

    def error(self, message: str) -> None:
        self.send({'op': 'error', 'message': message})

    def state(self, state) -> None:
        self.send({'op': 'state', 'state': state})

    def badge(self, text) -> None:
        self.send({'op': 'badge', 'text': text})


def _driver(widget_cls, message, channel: _Channel) -> WidgetDriver:
    options, warnings = resolve_options(widget_cls.options, message.get('options'))
    for warning in warnings:
        logging.getLogger(f'widget.{widget_cls.id}').warning(warning)
    return WidgetDriver(widget_cls, options, tuple(message.get('size', (112, 112))),
                        on_frame=channel.frame, on_error=channel.error,
                        data_dir=message.get('data_dir'),
                        on_state=channel.state, on_badge=channel.badge,
                        draw_frames=bool(message.get('frames', True)))


def main(argv=None) -> int:
    argv = sys.argv if argv is None else argv
    channel = _Channel(os.fdopen(os.dup(1), 'w', encoding='utf-8'))
    os.dup2(2, 1)
    sys.stdout = sys.stderr
    logging.basicConfig(stream=sys.stderr, level=logging.INFO,
                        format='%(levelname)s %(name)s: %(message)s')
    try:
        os.nice(10)
    except OSError:
        pass

    if len(argv) != 2:
        channel.error('usage: python -m streamdock_sdk.host <script>')
        return 2
    try:
        widget_cls = load_widget_class(argv[1])
    except Exception:  # pylint: disable=broad-exception-caught
        channel.error(traceback.format_exc(limit=5))
        return 2
    channel.send({'op': 'ready', 'manifest': widget_cls.manifest()})

    driver = None
    for line in sys.stdin:
        try:
            message = json.loads(line)
            op = message.get('op')
            if op == 'stop':
                break
            if op == 'start' and driver is None:
                driver = _driver(widget_cls, message, channel)
                driver.start()
            elif op == 'render_once':
                channel.frame(_driver(widget_cls, message, channel).render_once())
            elif op == 'event' and driver is not None:
                driver.post_event(message['name'])
            elif op == 'focus' and driver is not None:
                driver.post_focus(str(message.get('app', '')), str(message.get('title', '')))
            elif op == 'show' and driver is not None:
                driver.show()
            elif op == 'hide' and driver is not None:
                driver.hide()
        except OptionError as exc:
            channel.error(f'invalid option: {exc}')
        except Exception:  # pylint: disable=broad-exception-caught
            channel.error(traceback.format_exc(limit=5))

    if driver is not None:
        driver.stop()
    return 0


if __name__ == '__main__':
    sys.exit(main())
