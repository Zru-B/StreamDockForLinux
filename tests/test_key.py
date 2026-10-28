from unittest.mock import MagicMock, patch

import pytest

from StreamDock.domain.key import Key


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
            on_double_press=None,
            on_long_press=None
        )

    def test_init_with_action_list(self, mock_device):
        """Test initialization with a list of action tuples converts to callback."""
        actions = [('PRESS_KEY', 'A')]
        
        mock_executor = MagicMock()
        key = Key(mock_device, 1, "icon.png", on_press=actions, action_executor=mock_executor)
        
        # Verify it created a wrapper function
        assert callable(key.on_press)
        assert key.on_press != actions
        
        # Simulate device calling the callback
        key.on_press(mock_device, key)
        
        # Verify execute_actions was called
        mock_executor.execute_actions.assert_called_with(actions, device=mock_device, key_number=1)

    def test_init_with_single_action_tuple(self, mock_device):
        """Test initialization with a single action tuple converts to callback."""
        action = ('PRESS_KEY', 'A')
        
        mock_executor = MagicMock()
        key = Key(mock_device, 1, "icon.png", on_release=action, action_executor=mock_executor)
        
        # Simulate device calling the callback
        key.on_release(mock_device, key)
        
        # Verify execute_actions was called with list wrapped action
        mock_executor.execute_actions.assert_called_with([action], device=mock_device, key_number=1)

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
            on_double_press=None,
            on_long_press=None
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
            on_double_press=None,
            on_long_press=None
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

    def test_a_long_press_only_key_registers_its_callbacks(self, mock_device):
        """A key whose only action is a long press must still reach the device."""
        mock_executor = MagicMock()
        key = Key(mock_device, 1, "icon.png", on_long_press=[('KEY_PRESS', 'A')],
                  action_executor=mock_executor)

        key._configure()

        kwargs = mock_device.set_per_key_callback.call_args.kwargs
        assert kwargs['on_press'] is None
        kwargs['on_long_press'](mock_device, key)
        mock_executor.execute_actions.assert_called_with(
            [('KEY_PRESS', 'A')], device=mock_device, key_number=1)


class TestRenderedImageCache:
    """Re-applying a layout must not decode icons or render text again."""

    def test_text_is_rendered_once_across_applies_and_keys(self, mock_device):
        from PIL import Image
        with patch('StreamDock.domain.key.render_key_image',
                   return_value=Image.new('RGB', (112, 112))) as render:
            Key(mock_device, 1, '', text='cache-once')._configure()
            Key(mock_device, 2, '', text='cache-once')._configure()
            Key(mock_device, 1, '', text='cache-once')._configure()

        assert render.call_count == 1
        assert mock_device.set_key_pil_image.call_count == 3

    def test_an_icon_edited_on_disk_is_rendered_again(self, mock_device, tmp_path):
        import os
        from PIL import Image
        icon = tmp_path / "icon.png"
        Image.new('RGB', (10, 10), 'red').save(icon)
        key = Key(mock_device, 1, str(icon))
        key._configure()

        Image.new('RGB', (10, 10), 'blue').save(icon)
        os.utime(icon, ns=(0, os.stat(icon).st_mtime_ns + 1_000_000))
        key._configure()

        first, second = (c.args[1] for c in mock_device.set_key_pil_image.call_args_list)
        assert first.getpixel((5, 5)) == (255, 0, 0)
        assert second.getpixel((5, 5)) == (0, 0, 255)

    def test_prepare_does_not_touch_the_device(self, mock_device):
        Key(mock_device, 1, '', text='prepared').prepare()

        assert mock_device.method_calls == []

    def test_an_unreadable_icon_is_left_to_the_device_to_report(self, mock_device):
        Key(mock_device, 1, "/nonexistent/icon.png")._configure()

        mock_device.set_key_image.assert_called_once_with(1, "/nonexistent/icon.png")
        mock_device.set_key_pil_image.assert_not_called()
