from unittest.mock import MagicMock, call

import pytest

from StreamDock.key import Key
from StreamDock.layout import Layout


@pytest.fixture
def mock_device():
    return MagicMock()

@pytest.fixture
def mock_key_list(mock_device):
    return [MagicMock(spec=Key, key_number=i) for i in range(1, 4)]

class TestLayout:
    def test_init_validation(self, mock_device, mock_key_list):
        """Test layout initialization validation rules."""
        # Valid init (3 keys)
        layout = Layout(mock_device, mock_key_list)
        assert layout.keys == mock_key_list
        
        # Invalid: not a list
        with pytest.raises(TypeError):
            Layout(mock_device, "not a list")
            
        # Invalid: empty list (less than 1 op)
        with pytest.raises(ValueError):
            Layout(mock_device, [])
            
        # Invalid: too many keys
        many_keys = [MagicMock(spec=Key) for _ in range(16)]
        with pytest.raises(ValueError):
            Layout(mock_device, many_keys)

    def test_init_with_clears(self, mock_device):
        """Test validation considers both keys and clears."""
        # 0 keys but 1 clear = 1 op (Valid)
        layout = Layout(mock_device, [], clear_keys=[1])
        assert len(layout.clear_keys) == 1
        
        # 14 keys + 2 clears = 16 ops (Invalid)
        keys = [MagicMock(spec=Key) for _ in range(14)]
        with pytest.raises(ValueError):
            Layout(mock_device, keys, clear_keys=[1, 2])

    def test_apply_layout(self, mock_device, mock_key_list):
        """Test applying a layout configures keys and refreshes device."""
        layout = Layout(mock_device, mock_key_list, clear_all=True)
        
        layout.apply()
        
        # Verify clear all was called
        mock_device.clear_all_icons.assert_called_once()
        mock_device.clear_all_callbacks.assert_called_once()
        
        # Verify each key was configured
        for key in mock_key_list:
            key._configure.assert_called_once()
            
        # Verify refresh called
        mock_device.refresh.assert_called_once()

    def test_apply_with_specific_clears(self, mock_device, mock_key_list):
        """Test applying layout with specific key clears."""
        layout = Layout(mock_device, mock_key_list, clear_keys=[5, 6])
        
        layout.apply()
        
        # Verify specific clears (icon and callback)
        mock_device.cleaerIcon.assert_has_calls([call(5), call(6)], any_order=True)
        
        # Note: key.py logic maps 6->6, 5->15 for callback clearing
        # We need to verify clear_key_callback is called.
        # Assuming KEY_MAPPING: 5->15, 6->6
        mock_device.clear_key_callback.assert_any_call(15) 
        mock_device.clear_key_callback.assert_any_call(6)

    def test_get_key(self, mock_device, mock_key_list):
        """Test retrieving keys by number."""
        layout = Layout(mock_device, mock_key_list)
        
        # Key 1 is at index 0
        found = layout.get_key(1)
        assert found == mock_key_list[0]
        
        # Key 2 is at index 1
        found = layout.get_key(2)
        assert found == mock_key_list[1]
        
        # Key 99 doesn't exist
        assert layout.get_key(99) is None

    def test_update_key(self, mock_device, mock_key_list):
        """Test updating a specific key within the layout."""
        layout = Layout(mock_device, mock_key_list)
        target_key = mock_key_list[0] # Key 1
        
        new_press = MagicMock()
        layout.update_key(1, new_image="new.png", new_on_press=new_press)
        
        # Verify delegation to Key object
        target_key.update_image.assert_called_with("new.png")
        target_key.update_callbacks.assert_called_with(new_press, None)
        
        # Verify refresh called
        mock_device.refresh.assert_called_once()
        
    def test_update_key_not_found(self, mock_device, mock_key_list):
        """Test error when updating non-existent key."""
        layout = Layout(mock_device, mock_key_list)
        with pytest.raises(ValueError):
            layout.update_key(99)

    def test_update_device(self, mock_device, mock_key_list):
        """Test updating device reference propagates to keys."""
        layout = Layout(mock_device, mock_key_list)
        new_device = MagicMock()
        
        layout.update_device(new_device)
        
        assert layout.device == new_device
        for key in mock_key_list:
            key.update_device.assert_called_with(new_device)
