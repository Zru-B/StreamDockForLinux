import os
from unittest.mock import MagicMock, patch

import pytest

from StreamDock.config_loader import ConfigLoader, ConfigValidationError
from StreamDock.devices.stream_dock import StreamDock
from StreamDock.window_monitor import WindowMonitor

CONFIG_DIR = os.path.join(os.path.dirname(__file__), 'configs')

def get_config_path(filename):
    return os.path.join(CONFIG_DIR, filename)

def test_load_valid_config():
    loader = ConfigLoader(get_config_path('valid_config.yml'))
    loader.load()
    assert loader.config is not None
    assert loader.brightness == 50
    assert loader.double_press_interval == 0.3
    assert 'Key1' in loader.config['keys']
    assert 'Layout1' in loader.config['layouts']

def test_load_invalid_brightness_raises_error():
    loader = ConfigLoader(get_config_path('invalid_brightness.yml'))
    with pytest.raises(ConfigValidationError) as excinfo:
        loader.load()
    assert "brightness must be a number between 0 and 100" in str(excinfo.value)

def test_load_invalid_key_def_raises_error():
    loader = ConfigLoader(get_config_path('invalid_key_def.yml'))
    with pytest.raises(ConfigValidationError) as excinfo:
        loader.load()
    assert "must have either 'icon' or 'text' field" in str(excinfo.value)

def test_load_duplicate_key_in_layout_raises_error():
    loader = ConfigLoader(get_config_path('duplicate_key_in_layout.yml'))
    with pytest.raises(ConfigValidationError) as excinfo:
        loader.load()
    assert "duplicate key number 1" in str(excinfo.value)

def test_load_multiple_defaults_raises_error():
    loader = ConfigLoader(get_config_path('multiple_defaults.yml'))
    with pytest.raises(ConfigValidationError) as excinfo:
        loader.load()
    assert "Only one layout can have 'Default: true'" in str(excinfo.value)

def test_load_invalid_window_rule_raises_error():
    loader = ConfigLoader(get_config_path('invalid_window_rule.yml'))
    with pytest.raises(ConfigValidationError) as excinfo:
        loader.load()
    assert "references undefined layout" in str(excinfo.value)

def test_file_not_found():
    loader = ConfigLoader('non_existent.yml')
    with pytest.raises(FileNotFoundError):
        loader.load()

@patch('StreamDock.image_helpers.pil_helper.create_text_image')
def test_apply_valid_config(mock_create_text_image):
    from PIL import Image

    # Setup mocks
    mock_create_text_image.return_value = Image.new('RGB', (112, 112))
    
    # Mock device
    mock_device = MagicMock()
    
    loader = ConfigLoader(get_config_path('valid_config.yml'))
    loader.load()
    
    default_layout, layouts = loader.apply(mock_device)
    
    assert default_layout.name == 'Layout1'
    assert 'Layout1' in layouts
    assert 'Layout2' in layouts
    
    # Check if keys were created
    assert len(loader.keys) == 2
    
    # Verify device brightness was set
    mock_device.set_brightness.assert_called_with(50)

@patch('StreamDock.image_helpers.pil_helper.create_text_image')
def test_apply_with_window_rules(mock_create_text_image):
    from PIL import Image

    # Setup mocks for image creation
    mock_create_text_image.return_value = Image.new('RGB', (112, 112))
    
    # Mock dependencies
    mock_device = MagicMock()
    mock_window_monitor = MagicMock()
    
    # Create a config with window rules on the fly to avoid creating another file if possible, 
    # but since I prefer real files for now, I'll use a mocked loader or create a temporary file.
    # Actually, I'll just write a small test config with window rules.
    
    config_path = get_config_path('valid_config.yml')
    loader = ConfigLoader(config_path)
    loader.load()
    
    # Manually inject a window rule into the loaded config to verify logic
    loader.config['windows_rules'] = {
        'TestRule': {
            'window_name': 'TestWindow',
            'layout': 'Layout2'
        }
    }
    
    loader.apply(mock_device, mock_window_monitor)
    
    mock_window_monitor.add_window_rule.assert_called_once()
    args, kwargs = mock_window_monitor.add_window_rule.call_args
    assert args[0] == 'TestWindow'
    assert kwargs.get('match_field') == 'class'

def test_validate_window_rules_list_valid():
    loader = ConfigLoader(get_config_path('valid_config.yml'))
    # Valid list of strings
    loader.config = {
        'streamdock': {
            'layouts': {'L1': {}},
            'windows_rules': {
                'Rule1': {
                    'window_name': ['Win1', 'Win2'],
                    'layout': 'L1'
                }
            }
        }
    }
    loader.config = loader.config['streamdock']  # Mimic internal structure
    loader._validate_window_rules()

def test_validate_window_rules_list_invalid_content():
    loader = ConfigLoader(get_config_path('valid_config.yml'))
    # List containing non-string
    loader.config = {
        'streamdock': {
            'layouts': {'L1': {}},
            'windows_rules': {
                'Rule1': {
                    'window_name': ['Win1', 123],
                    'layout': 'L1'
                }
            }
        }
    }
    loader.config = loader.config['streamdock']
    with pytest.raises(ConfigValidationError) as excinfo:
        loader._validate_window_rules()
    assert "must contain only strings" in str(excinfo.value)

def test_validate_window_rules_invalid_type():
    loader = ConfigLoader(get_config_path('valid_config.yml'))
    loader.config = {
        'streamdock': {
            'layouts': {'L1': {}},
            'windows_rules': {
                'Rule1': {
                    'window_name': 123,  # Not str or list
                    'layout': 'L1'
                }
            }
        }
    }
    loader.config = loader.config['streamdock']
    with pytest.raises(ConfigValidationError) as excinfo:
        loader._validate_window_rules()
    assert "must be a string or a list of strings" in str(excinfo.value)

@patch('StreamDock.image_helpers.pil_helper.create_text_image')
def test_apply_window_rules_list(mock_create_text_image):
    from PIL import Image
    mock_create_text_image.return_value = Image.new('RGB', (112, 112))
    
    mock_device = MagicMock()
    mock_window_monitor = MagicMock()
    
    loader = ConfigLoader(get_config_path('valid_config.yml'))
    loader.load()
    
    # Inject rule with list
    loader.config['windows_rules'] = {
        'ListRule': {
            'window_name': ['App1', 'App2'],
            'layout': 'Layout1'
        }
    }
    
    loader.apply(mock_device, mock_window_monitor)
    
    # Should call add_window_rule once with list
    assert mock_window_monitor.add_window_rule.call_count == 1
    
    # Verify calls
    args, _ = mock_window_monitor.add_window_rule.call_args
    patterns = args[0]
    assert isinstance(patterns, list)
    assert 'App1' in patterns
    assert 'App2' in patterns

@patch('StreamDock.image_helpers.pil_helper.create_text_image')
def test_apply_window_rules_regex(mock_create_text_image):
    from PIL import Image
    import re
    mock_create_text_image.return_value = Image.new('RGB', (112, 112))
    
    mock_device = MagicMock()
    mock_window_monitor = MagicMock()
    
    loader = ConfigLoader(get_config_path('valid_config.yml'))
    loader.load()
    
    # Inject rule with regex
    loader.config['windows_rules'] = {
        'RegexRule': {
            'window_name': '^App.*',
            'is_regex': True,
            'layout': 'Layout1'
        }
    }
    
    loader.apply(mock_device, mock_window_monitor)
    
    # Verify add_window_rule called with regex
    args, kwargs = mock_window_monitor.add_window_rule.call_args
    pattern = args[0]
    assert isinstance(pattern, re.Pattern)
    assert pattern.pattern == '^App.*'
    assert kwargs.get('is_regex') is True

@patch('StreamDock.image_helpers.pil_helper.create_text_image')
def test_apply_window_rules_regex_list(mock_create_text_image):
    from PIL import Image
    import re
    mock_create_text_image.return_value = Image.new('RGB', (112, 112))
    
    mock_device = MagicMock()
    mock_window_monitor = MagicMock()
    
    loader = ConfigLoader(get_config_path('valid_config.yml'))
    loader.load()
    
    # Inject rule with regex list
    loader.config['windows_rules'] = {
        'RegexListRule': {
            'window_name': ['^App1.*', '^App2.*'],
            'is_regex': True,
            'layout': 'Layout1'
        }
    }
    
    loader.apply(mock_device, mock_window_monitor)
    
    # Verify add_window_rule called with list of regexes
    args, kwargs = mock_window_monitor.add_window_rule.call_args
    patterns = args[0]
    assert isinstance(patterns, list)
    assert len(patterns) == 2
    assert isinstance(patterns[0], re.Pattern)
    assert patterns[0].pattern == '^App1.*'
    assert kwargs.get('is_regex') is True


@patch('StreamDock.image_helpers.pil_helper.create_text_image')
def test_change_key_resolution(mock_create_text_image):
    from StreamDock.actions import ActionType
    mock_create_text_image.return_value = MagicMock()
    
    loader = ConfigLoader(get_config_path('valid_config.yml'))
    # Minimal config with two keys, one referencing the other
    loader.config = {
        'settings': {'brightness': 50},
        'keys': {
            'TargetKey': {
                'text': 'Target', 
                'on_press_actions': [{'KEY_PRESS': 'A'}]
            },
            'SourceKey': {
                'text': 'Source',
                'on_press_actions': [{'CHANGE_KEY': 'TargetKey'}]
            }
        },
        'layouts': {
            'Main': {
                'Default': True,
                'keys': [{1: 'SourceKey'}]
            }
        }
    }
    
    mock_device = MagicMock()
    loader._create_keys(mock_device)
    loader._create_layouts(mock_device)
    loader._resolve_layout_references()
    
    # Check SourceKey's action
    source_key_def = loader.keys['SourceKey']
    action_type, param = source_key_def['on_press'][0]
    
    assert action_type == ActionType.CHANGE_KEY
    assert isinstance(param, dict)
    assert param['on_press'] is not None  # Should contain TargetKey's actions
    assert param['image'] is not None     # Should contain TargetKey's image path/obj

