import unittest
from unittest.mock import MagicMock

import pytest

from StreamDock.actions import ActionType, execute_action
from StreamDock.key import Key


@pytest.mark.issue
@pytest.mark.regression
class TestChangeKeyCrash(unittest.TestCase):
    def test_change_key_with_string_parameter(self):
        """
        Verify fix: CHANGE_KEY with string parameter should treat it as image path and update key.
        """
        device = MagicMock()
        # Simulate the action: CHANGE_KEY with string (image path)
        action = (ActionType.CHANGE_KEY, "/path/to/image.png")
        
        # Execute with key_number context
        execute_action(action, device=device, key_number=5)
        
        # Verification
        device.set_key_image.assert_called_with(5, "/path/to/image.png")
        
    def test_change_key_with_dict_parameter(self):
        """
        Verify fix: CHANGE_KEY with dict parameter should configure full key.
        """
        device = MagicMock()
        config = {
            'image': '/path/to/icon.png',
            'actions': [{'foo': 'bar'}] # Mock action list
        }
        action = (ActionType.CHANGE_KEY, config)
        
        # Execute with key_number context
        execute_action(action, device=device, key_number=3)
        
        # Verification
        device.set_key_image.assert_called_with(3, '/path/to/icon.png')
        device.set_per_key_callback.assert_called()

if __name__ == '__main__':
    unittest.main()
