"""
Keeps the configured widgets running and puts their frames on the device.

One widget instance runs per key name, not per slot: a counter placed in two
layouts keeps its count when the layout switches. Frames only go to the slots
of the layout currently on the device, and every write happens under the
orchestrator's device lock with visibility re-checked inside it, so a frame
rendered just before a layout switch can't land on the new layout.
"""

import logging
import os
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Mapping, Optional, Set, Tuple

from PIL import Image

from streamdock_sdk import draw
from streamdock_sdk.options import OptionError, resolve_options
from StreamDock.widgets.appearance import Appearance, compose
from StreamDock.widgets.registry import WidgetRegistry, default_state_dir
from StreamDock.widgets.runners import WidgetRunner, create_runner

logger = logging.getLogger(__name__)

KEY_SIZE = (112, 112)


def placeholder_tile(size: Tuple[int, int] = KEY_SIZE) -> Image.Image:
    return draw.text_key('…', color='#808080', background='black', size=size)


def error_tile(widget_id: str, size: Tuple[int, int] = KEY_SIZE) -> Image.Image:
    image, canvas = draw.canvas(size, '#5a1010')
    width, height = size
    draw.centered_text(canvas, (8, 6, width - 8, height * 2 // 3), '!', color='white')
    draw.centered_text(canvas, (6, height * 2 // 3, width - 6, height - 6), widget_id or '?',
                       color='#ffd0d0', text_font=draw.font(12, bold=False))
    return image


def _composed(widget_id: str, appearance: Appearance, state: Optional[str], badge: Optional[str],
              drawn: Optional[Image.Image]) -> Optional[Image.Image]:
    """compose(), with the error tile when the key's icon can't be loaded."""
    frame = compose(appearance, state, badge, drawn, KEY_SIZE)
    if frame is None and appearance.replaces_drawing:
        # The widget draws nothing when an icon replaces its drawing, so a
        # missing icon would otherwise leave the placeholder up for good.
        return error_tile(widget_id)
    return frame


@dataclass
class _Instance:
    key_name: str
    widget_id: str
    options: Dict[str, Any]
    runner: Optional[WidgetRunner]
    frame: Image.Image
    digest: bytes = b''
    last_push: float = 0.0
    flush_timer: Optional[threading.Timer] = None
    events: Tuple[str, ...] = ()
    appearance: Appearance = field(default_factory=Appearance)
    state: Optional[str] = None
    badge: Optional[str] = None
    # The widget's own latest drawing, shown for states without an image.
    drawn: Optional[Image.Image] = None
    # Runners start when their key first appears, unless run_while_hidden.
    started: bool = False
    window_focus: bool = False

    def __post_init__(self):
        # Layout.apply writes the starting frame; its digest stops a re-push.
        self.digest = self.frame.tobytes()


@dataclass
class WidgetKeySpec:
    """What config.yml asks of one widget key."""

    widget_id: str
    options: Dict[str, Any] = field(default_factory=dict)
    appearance: Appearance = field(default_factory=Appearance)


def widget_key_specs(keys_config: Mapping[str, Any]) -> Dict[str, WidgetKeySpec]:
    """The widget keys of a parsed 'keys' section, whose image paths are already absolute."""
    return {
        name: WidgetKeySpec(data['widget'], dict(data.get('widget_options') or {}),
                            Appearance.from_key_config(data))
        for name, data in keys_config.items()
        if isinstance(data, dict) and data.get('widget')
    }


class WidgetHost:
    """Owns widget runners across configuration reloads."""

    # Cap per key, so a widget asking for a frame per millisecond can't hog the USB link.
    MIN_PUSH_INTERVAL = 0.25

    def __init__(self, registry: WidgetRegistry, device=None,
                 runner_factory: Callable[..., WidgetRunner] = create_runner,
                 state_dir: Optional[str] = None):
        self._registry = registry
        self._device = device
        self._runner_factory = runner_factory
        self._state_dir = state_dir or default_state_dir()
        self._lock = threading.RLock()
        self._instances: Dict[str, _Instance] = {}
        self._visible: Dict[str, List[int]] = {}
        # Tracked apart from _visible: detach() empties the slot map, but the
        # widgets stay shown until the next layout says otherwise.
        self._shown: Set[str] = set()
        self._slot_digests: Dict[int, bytes] = {}
        # The digest of the frame frame_for() last handed out per key, i.e.
        # what Layout.apply wrote; None if two different frames went out.
        self._handed_out: Dict[str, Optional[bytes]] = {}
        self._run_exclusive: Optional[Callable[[Callable[[], Any]], Any]] = None
        self._is_locked: Callable[[], bool] = lambda: False

    # ------------------------------------------------------------------
    # Wiring
    # ------------------------------------------------------------------

    def attach(self, device, run_exclusive: Callable[[Callable[[], Any]], Any],
               is_locked: Callable[[], bool]) -> None:
        """Route pushes through a (new) orchestrator's device lock."""
        with self._lock:
            self._device = device
            self._run_exclusive = run_exclusive
            self._is_locked = is_locked

    def detach(self) -> None:
        """
        Stop pushing until the next layout is applied.

        Taken under the device lock so a push already in flight finishes
        before the caller clears the device for a reload.
        """
        run_exclusive = self._run_exclusive

        def clear():
            with self._lock:
                self._visible = {}
                self._slot_digests = {}
                self._run_exclusive = None

        if run_exclusive is not None:
            run_exclusive(clear)
        else:
            clear()

    def configure(self, keys: Mapping[str, WidgetKeySpec]) -> None:
        """
        Make the running widgets match ``keys``.

        An instance whose widget and options are unchanged keeps running, so a
        stopwatch survives an Apply that only touched another key. Changing
        only the key's images keeps it running too; the key is recomposed.
        """
        recompose = []
        stopped = []
        with self._lock:
            for key_name in list(self._instances):
                instance = self._instances[key_name]
                wanted = keys.get(key_name)
                if wanted is None or wanted.widget_id != instance.widget_id or \
                        self._resolved(wanted) != instance.options or \
                        wanted.appearance.replaces_drawing != instance.appearance.replaces_drawing:
                    # Stopped after the lock is released, like shutdown(): a
                    # stop can wait seconds on a child process.
                    stopped.append(self._instances.pop(key_name))
                    # The replacement is a new, unstarted runner: the next
                    # layout must start and show it even if the key stayed put.
                    self._shown.discard(key_name)
                elif wanted.appearance != instance.appearance:
                    instance.appearance = wanted.appearance
                    recompose.append((key_name, instance))
            for key_name, wanted in keys.items():
                if key_name not in self._instances:
                    self._instances[key_name] = self._start(key_name, wanted)
        for instance in stopped:
            self._stop(instance)
        for key_name, instance in recompose:
            self._refresh(key_name, instance)

    def shutdown(self) -> None:
        with self._lock:
            instances = list(self._instances.values())
            self._instances = {}
            self._visible = {}
            self._shown = set()
        for instance in instances:
            self._stop(instance)

    # ------------------------------------------------------------------
    # Queries used by WidgetKey
    # ------------------------------------------------------------------

    def frame_for(self, key_name: str) -> Image.Image:
        with self._lock:
            instance = self._instances.get(key_name)
            if instance is None:
                return error_tile('')
            if self._handed_out.get(key_name, instance.digest) != instance.digest:
                self._handed_out[key_name] = None
            else:
                self._handed_out[key_name] = instance.digest
            return instance.frame

    def events_for(self, key_name: str) -> Tuple[str, ...]:
        with self._lock:
            instance = self._instances.get(key_name)
            return instance.events if instance else ()

    def window_focused(self, app: str, title: str) -> None:
        """Tell running widgets that asked for it which window now has focus."""
        with self._lock:
            runners = [instance.runner for instance in self._instances.values()
                       if instance.started and instance.window_focus]
        for runner in runners:
            runner.post_focus(app or '', title or '')

    def suspend(self) -> None:
        """
        The device went dark (screen locked): pause every widget.

        The layout applied on unlock shows them again.
        """
        with self._lock:
            shown, self._shown = self._shown, set()
            self._visible = {}
            instances = [self._instances[name] for name in shown if name in self._instances]
        for instance in instances:
            if instance.runner is not None:
                instance.runner.hide()

    def dispatch_event(self, key_name: str, event: str) -> None:
        with self._lock:
            instance = self._instances.get(key_name)
        if instance and instance.runner:
            instance.runner.post_event(event)

    def layout_applied(self, slots: Mapping[int, str]) -> None:
        """
        Record which widget keys are now on the device, by slot.

        Called from Layout.apply after every key was written. A slot is
        recorded with the frame frame_for() handed out for it, not the
        instance's current one: a frame arriving mid-apply is newer than what
        was written, and must still be pushed.
        """
        visible: Dict[str, List[int]] = {}
        for slot, key_name in slots.items():
            visible.setdefault(key_name, []).append(slot)
        with self._lock:
            before, self._shown = self._shown, set(visible)
            self._visible = visible
            self._slot_digests = {
                slot: self._handed_out.get(key_name, self._instances[key_name].digest)
                for slot, key_name in slots.items() if key_name in self._instances
            }
            self._handed_out = {}
            instances = dict(self._instances)
        for key_name, instance in instances.items():
            if instance.runner is None:
                continue
            if key_name in visible and key_name not in before:
                self._ensure_started(instance)
                instance.runner.show()
            elif key_name not in visible and key_name in before:
                instance.runner.hide()

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _resolved(self, wanted: WidgetKeySpec) -> Optional[Dict[str, Any]]:
        spec = self._registry.get(wanted.widget_id)
        if spec is None:
            return None
        try:
            return resolve_options(spec.options, wanted.options)[0]
        except OptionError:
            return None

    def _start(self, key_name: str, wanted: WidgetKeySpec) -> _Instance:
        spec = self._registry.get(wanted.widget_id)
        options = self._resolved(wanted)
        if spec is None or not spec.runnable or options is None:
            reason = 'not installed' if spec is None else spec.problem or 'invalid options'
            logger.error("Key '%s': widget '%s' can't run: %s", key_name, wanted.widget_id, reason)
            return _Instance(key_name, wanted.widget_id, {}, None, error_tile(wanted.widget_id))

        appearance = wanted.appearance
        instance = _Instance(key_name, spec.id, options, None,
                             _composed(spec.id, appearance, None, None, None) or placeholder_tile(),
                             events=spec.events, appearance=appearance, window_focus=spec.window_focus)
        instance.runner = self._runner_factory(
            spec, options, KEY_SIZE,
            on_frame=lambda image, name=key_name, inst=instance: self._on_drawn(name, inst, image),
            on_error=lambda message, name=key_name, inst=instance: self._on_error(name, inst, message),
            data_dir=os.path.join(self._state_dir, spec.id),
            on_state=lambda state, name=key_name, inst=instance: self._on_state(name, inst, state),
            on_badge=lambda text, name=key_name, inst=instance: self._on_badge(name, inst, text),
            draw_frames=not appearance.replaces_drawing,
        )
        if spec.run_while_hidden:
            self._ensure_started(instance)
        return instance

    @staticmethod
    def _ensure_started(instance: _Instance) -> None:
        if not instance.started:
            instance.started = True
            instance.runner.start()

    @staticmethod
    def _stop(instance: _Instance) -> None:
        if instance.flush_timer is not None:
            instance.flush_timer.cancel()
        if instance.runner is not None and instance.started:
            try:
                instance.runner.stop()
            except Exception:  # pylint: disable=broad-exception-caught
                logger.exception("Error stopping widget for key '%s'", instance.key_name)

    def _on_error(self, key_name: str, instance: _Instance, message: str) -> None:
        logger.warning("Key '%s': widget '%s' error: %s", key_name, instance.widget_id, message)
        self._on_frame(key_name, instance, error_tile(instance.widget_id))

    def _on_drawn(self, key_name: str, instance: _Instance, image: Image.Image) -> None:
        instance.drawn = image
        self._refresh(key_name, instance)

    def _on_state(self, key_name: str, instance: _Instance, state: Optional[str]) -> None:
        instance.state = state
        self._refresh(key_name, instance)

    def _on_badge(self, key_name: str, instance: _Instance, text: Optional[str]) -> None:
        instance.badge = text
        self._refresh(key_name, instance)

    def _refresh(self, key_name: str, instance: _Instance) -> None:
        """Recompose the key from the widget's latest drawing, state and badge."""
        frame = _composed(instance.widget_id, instance.appearance, instance.state, instance.badge, instance.drawn)
        if frame is not None:
            self._on_frame(key_name, instance, frame)

    def _on_frame(self, key_name: str, instance: _Instance, image: Image.Image) -> None:
        with self._lock:
            if self._instances.get(key_name) is not instance:
                return
            instance.frame = image
            instance.digest = image.tobytes()
            wait = instance.last_push + self.MIN_PUSH_INTERVAL - time.monotonic()
            if wait > 0:
                if instance.flush_timer is None:
                    instance.flush_timer = threading.Timer(wait, self._flush, args=(key_name, instance))
                    instance.flush_timer.daemon = True
                    instance.flush_timer.start()
                return
        self._flush(key_name, instance)

    def _flush(self, key_name: str, instance: _Instance) -> None:
        with self._lock:
            instance.flush_timer = None
            run_exclusive = self._run_exclusive
        if run_exclusive is None:
            return
        try:
            run_exclusive(lambda: self._push(key_name, instance))
        except Exception:  # pylint: disable=broad-exception-caught
            logger.exception("Error pushing widget frame for key '%s'", key_name)

    def _push(self, key_name: str, instance: _Instance) -> None:
        """Runs under the device lock; visibility is decided here, not by the caller."""
        if self._is_locked():
            return
        with self._lock:
            if self._instances.get(key_name) is not instance or self._device is None:
                return
            frame, digest = instance.frame, instance.digest
            slots = [slot for slot in self._visible.get(key_name, ())
                     if self._slot_digests.get(slot) != digest]
            instance.last_push = time.monotonic()
        for slot in slots:
            self._device.set_key_pil_image(slot, frame)
            with self._lock:
                self._slot_digests[slot] = digest
        if slots:
            self._device.refresh()
