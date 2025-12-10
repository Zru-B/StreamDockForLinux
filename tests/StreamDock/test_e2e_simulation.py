import pytest
import os
import time
import tempfile
import yaml
from unittest.mock import MagicMock

from StreamDock.ConfigLoader import ConfigLoader
from StreamDock.WindowMonitor import WindowMonitor
from StreamDock.Devices.DummyStreamDock import DummyStreamDock

class TestE2ESimulation:

    @pytest.fixture
    def simulation_file(self):
        """Create a temp file for window simulation."""
        fd, path = tempfile.mkstemp(prefix="streamdock_test_sim_")
        os.close(fd)
        yield path
        if os.path.exists(path):
            os.remove(path)

    @pytest.fixture
    def e2e_config_path(self):
        """Path to the E2E simulation config."""
        return "tests/resources/simulation_test_data.yml"

    def test_window_switch_triggers_layout_change(self, e2e_config_path, simulation_file):
        """
        Verify that writing to the simulation file triggers a layout change on the dummy device.
        """
        # 1. Setup Components
        dummy_device = DummyStreamDock()
        dummy_device.open()
        dummy_device.init()
        
        # Configure WindowMonitor with our temp simulation file
        # We need to manually set the file path since we can't easily pass it via init arg 
        # (init arg sets it to fixed /tmp/... path)
        # So we patch the instance after creation
        window_monitor = WindowMonitor(poll_interval=0.1, simulation_mode=True)
        window_monitor.simulated_window_file = simulation_file
        
        # Load and Apply Config
        loader = ConfigLoader(e2e_config_path)
        loader.load()
        default_layout, _ = loader.apply(dummy_device, window_monitor)
        
        # Manually apply default layout (just like main.py does)
        default_layout.apply()
        
        # 2. Verify Initial State (DefaultLayout)
        # Key 1 should be loaded from DefaultLayout ("Key1")
        # Since images are generated, we can't easily check the image content equality,
        # but we can check that *something* is there
        assert 1 in dummy_device.keys_state
        initial_image = dummy_device.keys_state[1]
        
        # Start monitoring
        window_monitor.start()
        
        try:
            # 3. Simulate Window Change
            # Write "TargetApp" to simulation file to match the rule
            with open(simulation_file, "w") as f:
                f.write("TargetApp")
                
            # Wait for poll interval + processing time
            time.sleep(0.5)
            
            # 4. Verify New State (SecondLayout)
            # Logic: WindowMonitor sees change -> calls callback -> Layout.apply() -> device.set_key_image
            # We expect that set_key_image was called again for Key 1 (since both layouts use Key 1 slot)
            # In a real scenario, the image would be different (Key1 vs Key2 text)
            
            # Check if key state was updated (it should be wrapped in new object or updated)
            # Since Key1 and Key2 have different text, the generated image bytes should differ
            # NOTE: ConfigLoader generates temp images for text keys. 
            
            current_image = dummy_device.keys_state[1]
            
            # Assert that the image reference changed (implies a re-render/set)
            # or check that we are in the correct layout if we could check that.
            # Checking byte equality might be fragile if fonts drift, but checking identity is safe 
            # if ConfigLoader created distinct files.
            
            # Actually, let's verify simply that a change occurred.
            # Ideally we'd verify it switched to SecondLayout.
            
            assert current_image != initial_image, "Key image should have changed after layout switch"
            
            # 5. Simulate switching back (no rule matches -> default callback -> default layout)?
            # ConfigLoader:597 sets default callback to apply default layout
            
            with open(simulation_file, "w") as f:
                f.write("OtherApp")
            
            time.sleep(0.5)
            
            final_image = dummy_device.keys_state[1]
            # Should revert to initial image (or similar one for DefaultLayout)
            # Since ConfigLoader caches images per Key definition, they might be identical objects if cached,
            # or at least identical content.
            
            # Let's check against initial_image if ConfigLoader reuses the image path
            # ConfigLoader stores image paths in self.keys[name]["image"]
            # So if it applies "Key1" again, it uses the same path.
            
            # However, `dummy_device.keys_state` stores the PIL Image object or bytes depending on how set_key_image is called.
            # StreamDock.py calls `self.device.set_key_image(key_number, image_data)`
            # The image_data comes from `Key.image` which is loaded from `Key.image_path`.
            
            # If implementation details align, this should work.
             
        finally:
            window_monitor.stop()
            dummy_device.close()
