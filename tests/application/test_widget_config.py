"""
Widget keys through the config path: validation, the editor model, the
factory, and the layout fixes widgets depend on.
"""

import os
from unittest.mock import MagicMock, Mock

import pytest
from PIL import Image

from streamdock_sdk import Option
from StreamDock.application.config_document import KeyDefinition
from StreamDock.application.configuration_manager import ConfigurationManager, ConfigValidationError
from StreamDock.application.layout_factory import LayoutFactory
from StreamDock.business_logic.action_executor import ActionExecutor
from StreamDock.business_logic.action_type import ActionType
from StreamDock.devices.stream_dock_293_v3 import StreamDock293V3
from StreamDock.domain.widget_key import WidgetKey
from StreamDock.orchestration.device_orchestrator import DeviceOrchestrator
from StreamDock.widgets.registry import WidgetSpec


class Catalog:
    def get(self, widget_id):
        if widget_id == 'clock':
            return WidgetSpec(manifest={'id': 'clock', 'options': [
                Option.choice('format', ['24h', '12h']).to_dict()]}, builtin=True)
        if widget_id == 'vpn':
            return WidgetSpec(manifest={'id': 'vpn', 'states': ['connected', 'disconnected'],
                                        'supports_badge': False}, builtin=True)
        return None


def validate(keys, widgets=None, tmp_path='/tmp'):
    streamdock = {'keys': keys, 'layouts': {'Main': {'Default': True, 'keys': [{1: next(iter(keys))}]}}}
    ConfigurationManager.validate_data(streamdock, os.path.join(str(tmp_path), 'config.yml'), widgets)


class TestValidation:
    def test_widget_alone_is_a_valid_key(self):
        # A clock needs no action to be useful.
        validate({'Clock': {'widget': 'clock'}}, Catalog())

    def test_widget_cannot_combine_with_text(self):
        with pytest.raises(ConfigValidationError, match="cannot combine 'widget'"):
            validate({'Clock': {'widget': 'clock', 'text': 'x'}})

    def test_widget_can_sit_on_an_icon_with_state_images(self, tmp_path):
        for name in ('base.png', 'on.png'):
            (tmp_path / name).write_bytes(b'')
        validate({'VPN': {'widget': 'vpn', 'icon': 'base.png', 'state_icons': {'connected': 'on.png'},
                          'badge': {'position': 'bottom_left', 'color': '#ff0000'}}},
                 Catalog(), tmp_path)

    def test_state_images_must_name_declared_states(self, tmp_path):
        (tmp_path / 'on.png').write_bytes(b'')
        with pytest.raises(ConfigValidationError, match="unknown state"):
            validate({'VPN': {'widget': 'vpn', 'state_icons': {'online': 'on.png'}}}, Catalog(), tmp_path)

    def test_state_image_must_exist(self, tmp_path):
        with pytest.raises(ConfigValidationError, match="not found"):
            validate({'VPN': {'widget': 'vpn', 'state_icons': {'connected': 'gone.png'}}}, Catalog(), tmp_path)

    @pytest.mark.parametrize('badge, message', [
        ({'position': 'middle'}, 'position'),
        ({'color': 'nope'}, 'not a colour'),
        ({'size': 3}, 'unknown field'),
        ('big', 'true, false or a mapping'),
    ])
    def test_badge_shape_is_checked(self, badge, message):
        with pytest.raises(ConfigValidationError, match=message):
            validate({'VPN': {'widget': 'vpn', 'badge': badge}})

    @pytest.mark.parametrize('field', ['state_icons', 'badge'])
    def test_image_settings_need_a_widget(self, field):
        with pytest.raises(ConfigValidationError, match="no 'widget'"):
            validate({'K': {'text': 'x', field: {}, 'on_press_actions': [{'WAIT': 1}]}})

    def test_options_without_widget_are_refused(self):
        with pytest.raises(ConfigValidationError, match="no 'widget'"):
            validate({'K': {'text': 'x', 'widget_options': {}, 'on_press_actions': [{'WAIT': 1}]}})

    def test_options_are_checked_against_the_schema(self):
        with pytest.raises(ConfigValidationError, match="must be one of"):
            validate({'Clock': {'widget': 'clock', 'widget_options': {'format': '25h'}}}, Catalog())

    def test_unknown_widget_only_warns(self, caplog):
        # An uninstalled widget must not stop the whole config from loading.
        validate({'Gone': {'widget': 'uninstalled'}}, Catalog())
        assert "not installed" in caplog.text

    def test_options_must_be_a_mapping(self):
        with pytest.raises(ConfigValidationError, match='mapping'):
            validate({'Clock': {'widget': 'clock', 'widget_options': ['24h']}})


class TestKeyDefinition:
    def test_widget_fields_round_trip(self):
        data = {'widget': 'clock', 'widget_options': {'format': '12h'},
                'on_press_actions': [{'KEY_PRESS': 'a'}]}
        assert KeyDefinition('Clock', data).to_dict() == data

    def test_widget_wins_over_leftover_text(self):
        key = KeyDefinition('Clock', {'widget': 'clock'})
        key.text = 'x'
        assert key.to_dict() == {'widget': 'clock'}

    def test_widget_images_round_trip(self):
        data = {'widget': 'vpn', 'icon': 'base.png', 'state_icons': {'connected': 'on.png'},
                'badge': {'position': 'bottom_left'}}
        assert KeyDefinition('VPN', data).to_dict() == data
        assert KeyDefinition('VPN', {'widget': 'vpn', 'badge': False}).to_dict()['badge'] is False


class FakeHost:
    def __init__(self):
        self.reported = []

    def events_for(self, key_name):
        return ('press',)

    def frame_for(self, key_name):
        return Image.new('RGB', (112, 112))

    def dispatch_event(self, key_name, event):
        pass

    def layout_applied(self, slots):
        self.reported.append(dict(slots))


class TestFactory:
    def build(self, keys, layouts, host=None):
        device = MagicMock()
        config = {'keys': keys, 'layouts': layouts}
        return device, LayoutFactory(config, device, widget_host=host).create_layouts()

    def test_widget_keys_become_widget_keys(self):
        host = FakeHost()
        device, (default, _) = self.build({'Clock': {'widget': 'clock'}},
                                          {'Main': {'Default': True, 'keys': [{4: 'Clock'}]}}, host)
        key = default.keys[0]
        assert isinstance(key, WidgetKey)
        assert key.key_number == 4 and key.on_press is not None

        default.apply()
        device.set_key_pil_image.assert_called_once()
        assert host.reported == [{4: 'Clock'}]

    def test_without_a_host_widget_keys_are_skipped(self):
        _, (default, _) = self.build({'Clock': {'widget': 'clock'}},
                                     {'Main': {'Default': True, 'keys': [{4: 'Clock'}]}})
        assert default.keys == []

    def test_same_key_keeps_its_position_in_each_layout(self):
        # Used to share one Key, left at the position of the last layout built.
        keys = {'A': {'text': 'a', 'on_press_actions': [{'KEY_PRESS': 'a'}]}}
        layouts = {'One': {'Default': True, 'keys': [{1: 'A'}]}, 'Two': {'keys': [{9: 'A'}]}}
        _, (_, built) = self.build(keys, layouts)
        assert built['One'].keys[0].key_number == 1
        assert built['Two'].keys[0].key_number == 9
        assert built['One'].keys[0].logical_key == 11


class TestChangeLayoutGoesThroughTheOrchestrator:
    def test_executor_hands_named_layouts_to_the_switcher(self):
        executor = ActionExecutor(Mock(), Mock())
        layout = Mock(clear_all=False)
        executor.set_layouts({'Other': layout})
        switcher = Mock()
        executor.set_layout_switcher(switcher)

        executor.execute_action((ActionType.CHANGE_LAYOUT, {'layout': 'Other', 'clear_all': True}), device=Mock())

        switcher.assert_called_once_with('Other', True)
        layout.apply.assert_not_called()

    def test_orchestrator_applies_under_its_lock_and_notifies(self):
        orchestrator = DeviceOrchestrator(Mock(), Mock(), Mock(), None, Mock(), Mock(), Mock())
        device = MagicMock()
        orchestrator.attach_device('d', device, current_layout='Main')
        held = []
        layout = Mock()
        layout.apply.side_effect = lambda: held.append(orchestrator._device_lock._is_owned())
        orchestrator.register_layout('Other', layout)
        notified = []
        orchestrator.set_layout_changed_callback(notified.append)

        orchestrator.apply_layout('Other')

        assert held == [True]
        assert notified == ['Other']
        assert orchestrator.get_current_layout('d') == 'Other'


class TestInMemoryKeyImages:
    def test_frames_are_not_written_to_the_working_directory(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        transport = MagicMock()
        device = StreamDock293V3(transport, {'vendor_id': 1, 'product_id': 2, 'path': 'p'})

        device.set_key_pil_image(3, Image.new('RGB', (112, 112), 'red'))

        transport.set_key_img_dual_device.assert_called_once()
        assert os.listdir(tmp_path) == []

    def test_out_of_range_key_is_refused(self):
        transport = MagicMock()
        device = StreamDock293V3(transport, {'vendor_id': 1, 'product_id': 2, 'path': 'p'})
        assert device.set_key_pil_image(16, Image.new('RGB', (112, 112))) == -1
        transport.set_key_img_dual_device.assert_not_called()
