"""Widgets through Application: started with the config, kept across Apply, stopped with the app."""

import time
from unittest.mock import Mock, patch

import pytest
import yaml

from StreamDock.application import Application
from StreamDock.business_logic import SystemEvent
from StreamDock.widgets.registry import WidgetRegistry


def document(clock_options=None):
    return {'streamdock': {
        'keys': {
            'Clock': {'widget': 'digital_clock', 'widget_options': clock_options or {}},
            'Unread': {'widget': 'slack_notifications'},
            'OtherClock': {'widget': 'analog_clock'},
            'Text': {'text': 'A', 'on_press_actions': [{'KEY_PRESS': 'a'}]},
        },
        'layouts': {
            'Main': {'Default': True, 'keys': [{1: 'Clock'}, {2: 'Text'}]},
            'Other': {'keys': [{2: 'Text'}, {3: 'OtherClock'}]},
        },
    }}


@pytest.fixture(autouse=True)
def no_window_manager():
    with patch('StreamDock.application.application.LinuxWindowManager'):
        yield


@pytest.fixture
def device():
    device = Mock()
    device.open = Mock(return_value=True)
    return device


@pytest.fixture
def app(tmp_path, device):
    path = tmp_path / 'config.yml'
    path.write_text(yaml.safe_dump(document()))
    app = Application(str(path), widget_registry=WidgetRegistry(install_dir=str(tmp_path / 'widgets')))
    hardware = Mock()
    hardware.enumerate_devices = Mock(return_value=[Mock(vendor_id=0x6603, product_id=0x1006,
                                                         serial_number='S', path='/dev/hidraw0')])
    with patch('StreamDock.application.application.USBHardware', return_value=hardware), \
         patch('StreamDock.application.application.LinuxSystemInterface'), \
         patch('StreamDock.devices.stream_dock_293_v3.StreamDock293V3', return_value=device):
        app.initialize()
    yield app
    app.stop(force=True)


def runner(app, key_name='Clock'):
    return app._widget_host._instances[key_name].runner


def test_widget_key_is_drawn_when_the_layout_applies(app, device):
    slots = [call.args[0] for call in device.set_key_pil_image.call_args_list]
    assert 1 in slots
    assert app._widget_host._visible == {'Clock': [1]}


def test_apply_with_the_same_widget_keeps_it_running(app):
    # A stopwatch-style widget would lose its state on every Apply otherwise.
    before = runner(app)
    assert app.reload(raw_document=document()['streamdock'])
    assert runner(app) is before


def test_apply_with_new_options_restarts_it(app):
    before = runner(app)
    assert app.reload(raw_document=document({'format': '12h'})['streamdock'])
    assert runner(app) is not before


def test_stop_shuts_the_widgets_down(app):
    thread = runner(app)._driver._thread
    app.stop(force=True)
    thread.join(2)
    assert not thread.is_alive()
    assert app._widget_host is None


def test_change_layout_hides_the_widget(app):
    driver = runner(app)._driver
    wait_until(lambda: driver.visible)

    app._orchestrator.apply_layout('Other')

    assert 'Clock' not in app._widget_host._visible
    assert wait_until(lambda: not driver.visible)


def wait_until(predicate, timeout=2.0):
    deadline = time.monotonic() + timeout
    while not predicate():
        if time.monotonic() > deadline:
            return False
        time.sleep(0.01)
    return True


def test_focused_window_reaches_the_notification_counters(app, monkeypatch):
    focused = []
    monkeypatch.setattr(app._widget_host, 'window_focused', lambda a, t: focused.append((a, t)))
    monkeypatch.setattr(type(app._event_monitor), 'current_window',
                        property(lambda self: Mock(class_='Slack', title='general')))
    app._event_monitor._dispatch_event(SystemEvent.WINDOW_CHANGED)
    assert focused == [('Slack', 'general')]


def test_screen_lock_pauses_the_widgets(app):
    driver = runner(app)._driver
    wait_until(lambda: driver.visible)
    app._event_monitor._dispatch_event(SystemEvent.LOCK)
    assert wait_until(lambda: not driver.visible)


def test_only_shown_widgets_start_except_counters(app):
    # A clock on a layout not yet shown costs nothing; a counter must not miss messages.
    instances = app._widget_host._instances
    assert not instances['OtherClock'].started
    assert instances['Unread'].started

    app._orchestrator.apply_layout('Other')
    assert instances['OtherClock'].started
