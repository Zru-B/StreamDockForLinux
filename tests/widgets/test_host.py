"""WidgetHost: which frames reach which slots, and when."""

import threading
from unittest.mock import MagicMock

import pytest
from PIL import Image

from streamdock_sdk import Option
from StreamDock.domain.widget_key import WidgetKey
from StreamDock.widgets.appearance import Appearance, BadgeStyle
from StreamDock.widgets.host import WidgetHost, WidgetKeySpec
from StreamDock.widgets.registry import WidgetSpec


class FakeRunner:
    def __init__(self, spec, options, size, on_frame, on_error, data_dir=None,
                 on_state=None, on_badge=None, draw_frames=True):
        self.spec = spec
        self.options = options
        self.on_frame = on_frame
        self.on_error = on_error
        self.on_state = on_state
        self.on_badge = on_badge
        self.draw_frames = draw_frames
        self.calls = []

    def start(self):
        self.calls.append('start')

    def stop(self):
        self.calls.append('stop')

    def post_event(self, name):
        self.calls.append(('event', name))

    def post_focus(self, app, title):
        self.calls.append(('focus', app, title))

    def show(self):
        self.calls.append('show')

    def hide(self):
        self.calls.append('hide')


class FakeRegistry:
    def __init__(self):
        self.specs = {
            'clock': WidgetSpec(manifest={'id': 'clock', 'events': ['press'],
                                          'options': [Option.bool('seconds').to_dict()]}, builtin=True),
            'vpn': WidgetSpec(manifest={'id': 'vpn', 'states': ['on', 'off'], 'supports_badge': True},
                              builtin=True),
            'counter': WidgetSpec(manifest={'id': 'counter', 'run_while_hidden': True, 'window_focus': True},
                                  builtin=True),
        }

    def get(self, widget_id):
        return self.specs.get(widget_id)


class Lock:
    """Stands in for the orchestrator: records that pushes ran under its lock."""

    def __init__(self):
        self.lock = threading.RLock()
        self.held = False
        self.locked_screen = False

    def run_exclusive(self, operation):
        with self.lock:
            self.held = True
            try:
                return operation()
            finally:
                self.held = False


@pytest.fixture
def device():
    return MagicMock()


@pytest.fixture
def orchestrator():
    return Lock()


@pytest.fixture
def host(device, orchestrator):
    runners = []

    def factory(*args, **kwargs):
        runner = FakeRunner(*args, **kwargs)
        runners.append(runner)
        return runner

    host = WidgetHost(FakeRegistry(), runner_factory=factory, state_dir='/tmp/unused')
    host.MIN_PUSH_INTERVAL = 0
    host.attach(device, orchestrator.run_exclusive, lambda: orchestrator.locked_screen)
    host.runners = runners
    return host


def frame(color):
    return Image.new('RGB', (112, 112), color)


def test_frames_for_hidden_keys_are_not_pushed(host, device):
    host.configure({'Clock': WidgetKeySpec('clock')})
    host.runners[0].on_frame(frame('red'))
    device.set_key_pil_image.assert_not_called()


def test_frames_go_to_every_visible_slot_under_the_device_lock(host, device, orchestrator):
    host.configure({'Clock': WidgetKeySpec('clock')})
    host.layout_applied({3: 'Clock', 7: 'Clock'})
    device.set_key_pil_image.side_effect = lambda *args: pushes.append(orchestrator.held)
    pushes = []

    host.runners[0].on_frame(frame('red'))

    assert [call.args[0] for call in device.set_key_pil_image.call_args_list] == [3, 7]
    assert pushes == [True, True]
    device.refresh.assert_called_once()


def test_identical_frames_are_pushed_once(host, device):
    host.configure({'Clock': WidgetKeySpec('clock')})
    host.layout_applied({1: 'Clock'})
    host.runners[0].on_frame(frame('red'))
    host.runners[0].on_frame(frame('red'))
    assert device.set_key_pil_image.call_count == 1


def test_visibility_is_checked_inside_the_lock(host, device, orchestrator):
    # A frame queued before a layout switch must not land on the new layout.
    host.configure({'Clock': WidgetKeySpec('clock')})
    host.layout_applied({1: 'Clock'})

    def switch_then_push(operation):
        host.layout_applied({})
        return orchestrator.run_exclusive(operation)

    host._run_exclusive = switch_then_push
    host.runners[0].on_frame(frame('red'))
    device.set_key_pil_image.assert_not_called()


def test_nothing_is_pushed_while_the_screen_is_locked(host, device, orchestrator):
    host.configure({'Clock': WidgetKeySpec('clock')})
    host.layout_applied({1: 'Clock'})
    orchestrator.locked_screen = True
    host.runners[0].on_frame(frame('red'))
    device.set_key_pil_image.assert_not_called()


def test_show_and_hide_follow_the_layout(host):
    host.configure({'Clock': WidgetKeySpec('clock')})
    runner = host.runners[0]
    host.layout_applied({1: 'Clock'})
    host.layout_applied({2: 'Clock'})
    host.layout_applied({})
    assert [call for call in runner.calls if call in ('show', 'hide')] == ['show', 'hide']


def test_detach_keeps_widgets_shown_until_the_next_layout(host):
    host.configure({'Clock': WidgetKeySpec('clock')})
    runner = host.runners[0]
    host.layout_applied({1: 'Clock'})
    host.detach()
    host.layout_applied({})
    assert [call for call in runner.calls if call in ('show', 'hide')] == ['show', 'hide']


def test_reconfigure_keeps_unchanged_instances(host):
    host.configure({'Clock': WidgetKeySpec('clock', {'seconds': False})})
    host.layout_applied({1: 'Clock'})
    first = host.runners[0]

    host.configure({'Clock': WidgetKeySpec('clock', {})})  # same options once defaults are filled
    assert host.runners == [first]
    assert 'stop' not in first.calls

    host.configure({'Clock': WidgetKeySpec('clock', {'seconds': True})})
    assert 'stop' in first.calls
    assert len(host.runners) == 2


def test_unknown_widget_shows_error_tile_without_a_runner(host):
    host.configure({'Gone': WidgetKeySpec('uninstalled')})
    assert host.runners == []
    assert host.frame_for('Gone').getpixel((2, 2)) == (0x5a, 0x10, 0x10)


def test_runner_error_puts_the_error_tile_on_the_key(host, device):
    host.configure({'Clock': WidgetKeySpec('clock')})
    host.layout_applied({4: 'Clock'})
    host.runners[0].on_error('render failed: boom')
    pushed = device.set_key_pil_image.call_args.args[1]
    assert pushed.getpixel((2, 2)) == (0x5a, 0x10, 0x10)


def test_widget_key_sends_the_event_before_the_configured_actions(host, device):
    host.configure({'Clock': WidgetKeySpec('clock')})
    order = []
    host.dispatch_event = lambda name, event: order.append(('widget', event))
    executor = MagicMock()
    executor.execute_actions.side_effect = lambda *args, **kwargs: order.append(('actions', 'press'))

    key = WidgetKey(device, 5, host, 'Clock', on_press=[('KEY_PRESS', 'a')], action_executor=executor)
    key.on_press(device, 5)

    assert order == [('widget', 'press'), ('actions', 'press')]


def test_widget_key_registers_events_the_config_lacks(host, device):
    # The widget handles press; the key has no press actions of its own.
    host.configure({'Clock': WidgetKeySpec('clock')})
    key = WidgetKey(device, 5, host, 'Clock')
    assert key.on_press is not None
    assert key.on_long_press is None


@pytest.fixture
def images(tmp_path):
    paths = {}
    for name, color in (('on', 'green'), ('off', 'gray'), ('base', 'blue')):
        paths[name] = str(tmp_path / f'{name}.png')
        Image.new('RGB', (112, 112), color).save(paths[name])
    return paths


def centre(image):
    return image.getpixel((56, 56))


def test_state_images_replace_the_drawing_for_their_states(host, device, images):
    # A state without an image falls back to what the widget draws.
    host.configure({'VPN': WidgetKeySpec('vpn', appearance=Appearance(state_icons=(('on', images['on']),)))})
    host.layout_applied({1: 'VPN'})
    runner = host.runners[0]
    assert runner.draw_frames is True

    runner.on_state('on')
    assert centre(device.set_key_pil_image.call_args.args[1]) == (0, 128, 0)

    runner.on_frame(frame('red'))
    runner.on_state('off')
    assert centre(device.set_key_pil_image.call_args.args[1]) == (255, 0, 0)


def test_a_base_icon_turns_drawing_off_and_carries_the_badge(host, device, images):
    appearance = Appearance(icon=images['base'], badge=BadgeStyle(position='top_left', color='#ffff00'))
    host.configure({'VPN': WidgetKeySpec('vpn', appearance=appearance)})
    host.layout_applied({1: 'VPN'})
    runner = host.runners[0]
    assert runner.draw_frames is False

    runner.on_badge('3')
    shown = device.set_key_pil_image.call_args.args[1]
    assert centre(shown) == (0, 0, 255)
    assert shown.getpixel((12, 16))[:2] == (255, 255)
    assert shown.getpixel((100, 100)) == (0, 0, 255)


def test_hidden_badge_draws_nothing(host, device, images):
    host.configure({'VPN': WidgetKeySpec('vpn', appearance=Appearance(icon=images['base'], badge=None))})
    host.layout_applied({1: 'VPN'})
    host.runners[0].on_badge('3')
    assert device.set_key_pil_image.call_count == 0


def test_changing_only_images_keeps_the_widget_running(host, images):
    host.configure({'VPN': WidgetKeySpec('vpn', appearance=Appearance(state_icons=(('on', images['on']),)))})
    host.configure({'VPN': WidgetKeySpec('vpn', appearance=Appearance(state_icons=(('off', images['off']),)))})
    assert len(host.runners) == 1

    host.configure({'VPN': WidgetKeySpec('vpn', appearance=Appearance(icon=images['base']))})
    assert len(host.runners) == 2


def test_widgets_start_only_when_their_key_is_first_shown(host):
    # A widget on a layout that never appears costs nothing.
    host.configure({'Clock': WidgetKeySpec('clock')})
    runner = host.runners[0]
    assert runner.calls == []

    host.layout_applied({1: 'Clock'})
    assert runner.calls == ['start', 'show']
    host.layout_applied({})
    host.layout_applied({1: 'Clock'})
    assert runner.calls == ['start', 'show', 'hide', 'show']


def test_run_while_hidden_widgets_start_at_once(host):
    host.configure({'Unread': WidgetKeySpec('counter')})
    assert host.runners[0].calls == ['start']


def test_screen_lock_pauses_widgets_until_the_next_layout(host):
    host.configure({'Clock': WidgetKeySpec('clock')})
    runner = host.runners[0]
    host.layout_applied({1: 'Clock'})
    host.suspend()
    host.layout_applied({1: 'Clock'})
    assert runner.calls == ['start', 'show', 'hide', 'show']


def test_focus_goes_only_to_running_widgets_that_asked(host):
    host.configure({'Clock': WidgetKeySpec('clock'), 'Unread': WidgetKeySpec('counter')})
    host.layout_applied({1: 'Clock'})
    host.window_focused('slack', 'general - Slack')
    clock, counter = host.runners
    assert ('focus', 'slack', 'general - Slack') in counter.calls
    assert not any(isinstance(call, tuple) and call[0] == 'focus' for call in clock.calls)
