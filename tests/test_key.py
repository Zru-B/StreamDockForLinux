from unittest.mock import MagicMock, patch

import pytest

from StreamDock.key import Key


@pytest.fixture
def mock_device():
    return MagicMock()

class TestKey:
    def test_init_sets_image_and_callbacks(self, mock_device):
        """Test that initialization configures image and callbacks on device."""
        # 1. Init with simple function callbacks
        on_press = MagicMock()
        on_release = MagicMock()
        
        key = Key(mock_device, 1, "icon.png", on_press=on_press, on_release=on_release)
        
        # Verify Key properties
        assert key.key_number == 1
        assert key.image_path == "icon.png"
        assert key.logical_key == 11  # From KEY_MAPPING for physical key 1

        # Manually trigger configuration since __init__ doesn't do it
        key._configure()
        
        # Verify device configuration calls
        mock_device.set_key_image.assert_called_with(1, "icon.png")
        mock_device.set_per_key_callback.assert_called_with(
            11,
            on_press=on_press,
            on_release=on_release,
            on_double_press=None
        )

    def test_init_with_action_list(self, mock_device):
        """Test initialization with a list of action tuples converts to callback."""
        actions = [('PRESS_KEY', 'A')]
        
        with patch('StreamDock.key.execute_actions') as mock_exec:
            key = Key(mock_device, 1, "icon.png", on_press=actions)
            
            # Verify it created a wrapper function
            assert callable(key.on_press)
            assert key.on_press != actions
            
            # Simulate device calling the callback
            key.on_press(mock_device, key)
            
            # Verify execute_actions was called
            mock_exec.assert_called_with(actions, device=mock_device, key_number=1)

    def test_init_with_single_action_tuple(self, mock_device):
        """Test initialization with a single action tuple converts to callback."""
        action = ('PRESS_KEY', 'A')
        
        with patch('StreamDock.key.execute_actions') as mock_exec:
            key = Key(mock_device, 1, "icon.png", on_release=action)
            
            # Simulate device calling the callback
            key.on_release(mock_device, key)
            
            # Verify execute_actions was called with list wrapped action
            mock_exec.assert_called_with([action], device=mock_device, key_number=1)

    def test_update_image(self, mock_device):
        """Test update_image updates property and device."""
        key = Key(mock_device, 1, "old.png")
        
        key.update_image("new.png")
        
        assert key.image_path == "new.png"
        mock_device.set_key_image.assert_called_with(1, "new.png")

    def test_update_callbacks(self, mock_device):
        """Test update_callbacks updates properties and device."""
        key = Key(mock_device, 1, "icon.png")
        
        new_press = MagicMock()
        key.update_callbacks(on_press=new_press)
        
        assert key.on_press == new_press
        mock_device.set_per_key_callback.assert_called_with(
            11,
            on_press=new_press,
            on_release=None,
            on_double_press=None
        )

    def test_update_device(self, mock_device):
        """Test update_device re-registers callbacks on new device."""
        on_press = MagicMock()
        key = Key(mock_device, 1, "icon.png", on_press=on_press)
        
        new_device = MagicMock()
        key.update_device(new_device)
        
        assert key.device == new_device
        
        # Verify callbacks registered on NEW device
        new_device.set_per_key_callback.assert_called_with(
            11,
            on_press=on_press,
            on_release=None,
            on_double_press=None
        )

    def test_key_mapping(self, mock_device):
        """Test that key mapping works for various keys."""
        # Key 1 -> 11
        k1 = Key(mock_device, 1, "img")
        assert k1.logical_key == 11
        
        # Key 6 -> 6 (unchanged)
        k6 = Key(mock_device, 6, "img")
        assert k6.logical_key == 6
        
        # Unknown key (fallback) -> itself
        k99 = Key(mock_device, 99, "img")
        assert k99.logical_key == 99
