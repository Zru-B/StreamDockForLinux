import unittest
from unittest.mock import MagicMock, patch
import sys
import os

# Add src to path
sys.path.append(os.path.join(os.path.dirname(__file__), '../src'))

from StreamDock.VirtualKeyboard import VirtualKeyboard

class TestVirtualKeyboard(unittest.TestCase):
    def setUp(self):
        # Reset singleton logic for testing
        VirtualKeyboard._instance = None
        VirtualKeyboard._initialized = False

    @patch('StreamDock.VirtualKeyboard.UInput')
    def test_initialization_success(self, mock_uinput):
        vk = VirtualKeyboard()
        self.assertTrue(vk.available)
        self.assertIsNotNone(vk.device)
        mock_uinput.assert_called_once()

    @patch('StreamDock.VirtualKeyboard.UInput')
    def test_initialization_permission_error(self, mock_uinput):
        mock_uinput.side_effect = PermissionError("Permission denied")
        vk = VirtualKeyboard()
        self.assertFalse(vk.available)
        self.assertIsNone(vk.device)

    @patch('StreamDock.VirtualKeyboard.UInput')
    def test_key_mapping(self, mock_uinput):
        vk = VirtualKeyboard()
        
        # Test basic keys
        self.assertIsNotNone(vk._get_keycode('A'))
        self.assertIsNotNone(vk._get_keycode('1'))
        
        # Test modifiers
        self.assertIsNotNone(vk._get_keycode('CTRL'))
        self.assertIsNotNone(vk._get_keycode('SHIFT'))
        
        # Test special keys
        self.assertIsNotNone(vk._get_keycode('ENTER'))
        self.assertIsNotNone(vk._get_keycode('ESC'))
        
        # Test invalid key
        self.assertIsNone(vk._get_keycode('INVALID_KEY_NAME'))

    @patch('StreamDock.VirtualKeyboard.UInput')
    def test_send_combo(self, mock_uinput):
        vk = VirtualKeyboard()
        mock_device = mock_uinput.return_value
        
        # Test valid combo
        result = vk.send_combo('CTRL+C')
        self.assertTrue(result)
        # Should press keys
        self.assertTrue(mock_device.write.called)
        self.assertTrue(mock_device.syn.called)

    @patch('StreamDock.VirtualKeyboard.UInput')
    def test_singleton(self, mock_uinput):
        vk1 = VirtualKeyboard()
        vk2 = VirtualKeyboard()
        self.assertIs(vk1, vk2)
        # Should only initialize once
        mock_uinput.assert_called_once()

if __name__ == '__main__':
    unittest.main()
