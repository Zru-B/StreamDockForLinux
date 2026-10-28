import unittest
from unittest.mock import MagicMock

import pytest

from StreamDock.business_logic.action_type import ActionType
from StreamDock.business_logic.action_executor import ActionExecutor
from StreamDock.domain.key import Key


@pytest.mark.issue
@pytest.mark.regression
class TestChangeKeyCrash(unittest.TestCase):
    def test_change_key_with_string_parameter(self):
        """
        Verify fix: CHANGE_KEY with string parameter should treat it as image path and update key.
        """
        device = MagicMock()
        action_executor = ActionExecutor(MagicMock(), MagicMock())
        action = (ActionType.CHANGE_KEY, "/path/to/image.png")
        
        # Execute with key_number context
        action_executor.execute_action(action, device=device, key_number=5)
        
        # Verification
        device.set_key_image.assert_called_with(5, "/path/to/image.png")
        
    def test_change_key_with_dict_parameter(self):
        """
        Verify fix: CHANGE_KEY with dict parameter should configure full key.
        """
        device = MagicMock()
        action_executor = ActionExecutor(MagicMock(), MagicMock())
        action_executor._system = MagicMock()
        config = {
            'image': '/path/to/icon.png',
            'actions': [{'type_text': 'hi'}],
        }
        action = (ActionType.CHANGE_KEY, config)

        action_executor.execute_action(action, device=device, key_number=3)

        device.set_key_image.assert_called_with(3, '/path/to/icon.png')
        # The raw YAML actions are parsed and the key can run them: it was once
        # built without an executor and with unparsed dicts, so pressing did nothing.
        on_press = device.set_per_key_callback.call_args.kwargs['on_press']
        on_press(device, 3)
        action_executor._system.type_text.assert_called_once_with('hi')

if __name__ == '__main__':
    unittest.main()
