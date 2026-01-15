import os
from unittest.mock import MagicMock, patch
import pytest
from StreamDock.config_loader import ConfigLoader, ConfigValidationError

def test_on_press_standard_key_rejected():
    loader = ConfigLoader('dummy_path')
    loader.config = {
        'keys': {
            'TestKey': {
                'text': 'Test',
                'on_press': [{'TYPE_TEXT': 'Standard'}]
            }
        },
        'layouts': {'L1': {'Default': True, 'keys': []}}
    }
    
    with pytest.raises(ConfigValidationError) as excinfo:
        loader._validate_keys()
    
    assert "Action 'on_press' for key 'TestKey' is not supported" in str(excinfo.value)
    assert "Use any of" in str(excinfo.value)

def test_on_press_actions_legacy_key_accepted():
    loader = ConfigLoader('dummy_path')
    loader.config = {
        'keys': {
            'TestKey': {
                'text': 'Test',
                'on_press_actions': [{'TYPE_TEXT': 'Standard'}]
            }
        },
        'layouts': {'L1': {'Default': True, 'keys': []}}
    }
    
    loader._validate_keys() 
    # Should not raise exception

def test_on_release_standard_key_rejected():
    loader = ConfigLoader('dummy_path')
    loader.config = {
        'keys': {
            'TestKey': {
                'text': 'Test',
                'on_release': [{'TYPE_TEXT': 'Standard'}]
            }
        },
        'layouts': {'L1': {'Default': True, 'keys': []}}
    }
    
    with pytest.raises(ConfigValidationError) as excinfo:
        loader._validate_keys()
    
    assert "Action 'on_release' for key 'TestKey' is not supported" in str(excinfo.value)

def test_on_double_press_alias_rejected():
    loader = ConfigLoader('dummy_path')
    loader.config = {
        'keys': {
            'TestKey': {
                'text': 'Test',
                'on_double_press': [{'TYPE_TEXT': 'Standard'}]
            }
        },
        'layouts': {'L1': {'Default': True, 'keys': []}}
    }
    
    with pytest.raises(ConfigValidationError) as excinfo:
        loader._validate_keys()
    
    assert "Action 'on_double_press' for key 'TestKey' is not supported" in str(excinfo.value)

def test_on_double_press_actions_valid():
    loader = ConfigLoader('dummy_path')
    loader.config = {
        'keys': {
            'TestKey': {
                'text': 'Test',
                'on_double_press_actions': [{'TYPE_TEXT': 'Standard'}]
            }
        },
        'layouts': {'L1': {'Default': True, 'keys': []}}
    }
    loader._validate_keys() 

def test_legacy_alias_removal_in_create_keys():
    # Only verify that create_keys doesn't pick up on_double_press if it somehow bypasses validation
    loader = ConfigLoader('dummy_path')
    loader.config = {
        'keys': {
            'TestKey': {
                'text': 'Test',
                'on_double_press': [{'TYPE_TEXT': 'Standard'}]
            }
        },
        'layouts': {'L1': {'Default': True, 'keys': []}}
    }
    
    mock_device = MagicMock()
    # We bypass validation to check _create_keys behavior
    loader._create_keys(mock_device)
    
    key_def = loader.keys['TestKey']
    # It should NOT be loaded
    assert key_def['on_double_press'] is None
