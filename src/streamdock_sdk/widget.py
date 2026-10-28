"""The Widget base class every widget script subclasses."""

from typing import Any, Dict, List, Tuple

from streamdock_sdk.options import Option

SDK_VERSION = 1

KEY_EVENTS: Tuple[str, ...] = ('press', 'release', 'double_press', 'long_press')


class Widget:
    """
    A key whose image the widget draws.

    Every hook runs on the widget's own thread, one at a time, so a widget
    needs no locking of its own state. Blocking work (network, D-Bus,
    subprocesses) goes through ``ctx.run_in_background`` so ``render`` stays
    fast and only reads cached state.

    Override only the key-event hooks the widget reacts to: the app registers
    device callbacks for exactly the overridden ones, and a long-press hook
    delays the key's single press until the hold time has passed.
    """

    id: str = ''
    name: str = ''
    version: str = '0.0.0'
    sdk_version: int = SDK_VERSION
    description: str = ''
    author: str = ''
    options: List[Option] = []
    # Named conditions the widget reports with ctx.set_state, so a user can
    # show an image of their own per state instead of the widget's drawing.
    states: Tuple[str, ...] = ()
    # Whether the widget reports a short badge text with ctx.set_badge, drawn
    # in a corner over the user's image.
    supports_badge: bool = False
    # A widget starts when its key first appears on the device and pauses
    # while the key is off it. One that must not miss events meanwhile - a
    # notification counter - sets this to start at once and keep listening.
    run_while_hidden: bool = False

    def setup(self, ctx) -> None:
        """Called once before the first render; register timers here."""

    def render(self, ctx):
        """Return a PIL image of exactly ``ctx.size``."""
        raise NotImplementedError

    def on_press(self, ctx) -> None:
        pass

    def on_release(self, ctx) -> None:
        pass

    def on_double_press(self, ctx) -> None:
        pass

    def on_long_press(self, ctx) -> None:
        pass

    def on_window_focus(self, ctx, app: str, title: str) -> None:
        """
        Another window got focus: ``app`` is its class (e.g. 'slack'), ``title`` its title.

        Only delivered to widgets that override it, visible or not.
        """

    def on_show(self, ctx) -> None:
        """The key is now visible on the device."""

    def on_hide(self, ctx) -> None:
        """The key left the device; timers are paused until it returns."""

    def teardown(self, ctx) -> None:
        """Called once when the widget stops."""

    @classmethod
    def handled_events(cls) -> Tuple[str, ...]:
        return tuple(
            event for event in KEY_EVENTS
            if getattr(cls, f'on_{event}') is not getattr(Widget, f'on_{event}')
        )

    @classmethod
    def wants_window_focus(cls) -> bool:
        return cls.on_window_focus is not Widget.on_window_focus

    @classmethod
    def manifest(cls) -> Dict[str, Any]:
        return {
            'id': cls.id,
            'name': cls.name,
            'version': cls.version,
            'sdk_version': cls.sdk_version,
            'description': cls.description,
            'author': cls.author,
            'options': [option.to_dict() for option in cls.options],
            'events': list(cls.handled_events()),
            'states': list(cls.states),
            'supports_badge': bool(cls.supports_badge),
            'run_while_hidden': bool(cls.run_while_hidden),
            'window_focus': cls.wants_window_focus(),
        }
