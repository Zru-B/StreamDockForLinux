import pytest
import os
import yaml
import tempfile
from StreamDock.ConfigLoader import ConfigLoader, ConfigValidationError

class TestConfigLoader:
    
    @pytest.fixture
    def config_file_path(self):
        """Path to the valid test configuration."""
        # Assume tests are run from project root
        return "tests/resources/valid_test_data.yml"

    @pytest.fixture
    def create_config_file(self):
        """
        Helper to create a temporary config file for tests that need mutation.
        Uses valid_test_data.yml as base template.
        """
        base_path = "tests/resources/valid_test_data.yml"
        with open(base_path, 'r') as f:
            base_data = yaml.safe_load(f)

        files_to_cleanup = []
        
        def _create(data=None):
            # If no data provided, return the base path (read-only usage)
            if data is None:
                return base_path

            # Mutate base data
            mutated_data = data
            
            # Handle icons if they point to non-existent temp paths in mutated data
            # (Logic simplified: we rely on existing test resource for base case)

            fd, path = tempfile.mkstemp(suffix=".yml")
            with os.fdopen(fd, 'w') as f:
                # Merge logic is complex if we want partial overrides, 
                # but existing tests usually pass full structure. 
                # So we assume 'data' is the full config.
                yaml.dump(mutated_data, f)
            files_to_cleanup.append(path)
            return path
            
        yield _create
        
        # Cleanup
        for f in files_to_cleanup:
            if os.path.exists(f):
                os.remove(f)

    def test_load_valid_config(self, config_file_path):
        """Test loading a perfectly valid configuration."""
        loader = ConfigLoader(config_file_path)
        loader.load()
        
        assert loader.config is not None
        assert loader.brightness == 30
        assert loader.double_press_interval == 0.5

    def test_apply_config(self, config_file_path, mock_device, mock_window_monitor):
        """Test applying configuration to a device."""
        loader = ConfigLoader(config_file_path)
        loader.load()
        
        default_layout, all_layouts = loader.apply(mock_device, mock_window_monitor)
        
        assert default_layout is not None
        assert "Main" in all_layouts
        assert len(all_layouts["Main"].keys) == 2
        
        # Verify brightness was set on device
        mock_device.set_brightness.assert_called_with(30)
        
        # Verify window rules were added
        # We wrapped the callback in a lambda, so we can't easily check equality, 
        # but we can check if add_window_rule was called
        assert len(mock_window_monitor.add_window_rule.call_args_list) == 1
        args, _ = mock_window_monitor.add_window_rule.call_args
        assert args[0] == "Firefox"

    def test_missing_required_sections(self, create_config_file):
        """Test validation when required sections are missing."""
        data = {"streamdock": {}}  # Missing keys, layouts
        config_path = create_config_file(data)
        loader = ConfigLoader(config_path)
        
        with pytest.raises(ConfigValidationError) as exc:
            loader.load()
        assert "must contain 'keys' section" in str(exc.value)

    def test_invalid_key_definition(self, create_config_file):
        """Test invalid key definitions."""
        # Load base data to modify it
        with open("tests/resources/valid_test_data.yml", 'r') as f:
            data = yaml.safe_load(f)
            
        data["streamdock"]["keys"]["BadKey"] = {}  # Missing icon/text
        config_path = create_config_file(data)
        loader = ConfigLoader(config_path)
        
        with pytest.raises(ConfigValidationError) as exc:
            loader.load()
        assert "must have either 'icon' or 'text'" in str(exc.value)

    def test_invalid_layout_reference(self, create_config_file):
        """Test referencing a non-existent key in layout."""
        with open("tests/resources/valid_test_data.yml", 'r') as f:
            data = yaml.safe_load(f)

        data["streamdock"]["layouts"]["Main"]["keys"].append({3: "GhostKey"})
        config_path = create_config_file(data)
        loader = ConfigLoader(config_path)
        
        with pytest.raises(ConfigValidationError) as exc:
            loader.load()
        assert "references undefined key" in str(exc.value)

    def test_duplicate_default_layout(self, create_config_file):
        """Test having multiple default layouts."""
        with open("tests/resources/valid_test_data.yml", 'r') as f:
            data = yaml.safe_load(f)

        data["streamdock"]["layouts"]["Second"] = {
            "Default": True,
            "keys": [{1: "IconKey"}]
        }
        config_path = create_config_file(data)
        loader = ConfigLoader(config_path)
        
        with pytest.raises(ConfigValidationError) as exc:
            loader.load()
        assert "Only one layout can have 'Default: true'" in str(exc.value)

    def test_change_key_resolution(self, mock_device):
        """Test that CHANGE_KEY actions are properly resolved to Key instances."""
        config_path = "tests/resources/test_change_key.yml"
        loader = ConfigLoader(config_path)
        loader.load()
        
        default_layout, all_layouts = loader.apply(mock_device)
        
        # Get the PrintScreenKey definition
        print_screen_key_def = loader.keys["PrintScreenKey"]
        on_press_actions = print_screen_key_def["on_press"]
        
        # Find the CHANGE_KEY action (should be the third action)
        change_key_action = on_press_actions[2]
        action_type, parameter = change_key_action
        
        # Verify it's a CHANGE_KEY action
        from StreamDock.Actions import ActionType
        assert action_type == ActionType.CHANGE_KEY
        
        # Verify the parameter is now a Key instance, not a string
        from StreamDock.Key import Key
        assert isinstance(parameter, Key), f"Expected Key instance, got {type(parameter)}"
        
        # Verify it's the correct key (CancelPrintScreenKey)
        assert parameter.key_number == 2  # CancelPrintScreenKey is on key 2
        
        # Verify the Key has _configure method (would fail if it was still a string)
        assert hasattr(parameter, "_configure")
        assert callable(parameter._configure)

    def test_change_key_missing_reference(self, create_config_file):
        """Test that referencing a non-existent key in CHANGE_KEY raises an error."""
        with open("tests/resources/test_change_key.yml", 'r') as f:
            data = yaml.safe_load(f)
        
        # Add a key that references a non-existent key
        data["streamdock"]["keys"]["BadKey"] = {
            "icon": "tests/resources/test_icon.png",
            "on_press_actions": [
                {"CHANGE_KEY": "NonExistentKey"}
            ]
        }
        data["streamdock"]["layouts"]["Main"]["keys"].append({3: "BadKey"})
        
        config_path = create_config_file(data)
        loader = ConfigLoader(config_path)
        loader.load()
        
        from unittest.mock import MagicMock
        mock_device = MagicMock()
        
        with pytest.raises(ConfigValidationError) as exc:
            loader.apply(mock_device)
        assert "references undefined key 'NonExistentKey'" in str(exc.value)

    def test_change_key_not_in_layout(self, create_config_file, mock_device):
        """Test CHANGE_KEY can reference a key that's not in any layout."""
        # Create a config where TargetKey is not in the layout, but PrintKey is
        data = {
            "streamdock": {
                "settings": {"brightness": 30},
                "keys": {
                    "PrintKey": {
                        "icon": "tests/resources/test_icon.png",
                        "on_press_actions": [
                            {"CHANGE_KEY": "TargetKey"}
                        ]
                    },
                    "TargetKey": {
                        "icon": "tests/resources/test_icon.png",
                        "on_press_actions": [
                            {"KEY_PRESS": "Esc"}
                        ]
                    }
                },
                "layouts": {
                    "Main": {
                        "Default": True,
                        "keys": [
                            {1: "PrintKey"}  # TargetKey is NOT in layout
                        ]
                    }
                }
            }
        }
        
        config_path = create_config_file(data)
        loader = ConfigLoader(config_path)
        loader.load()
        
        # This should NOT raise an error because we create Key instances on-the-fly
        default_layout, all_layouts = loader.apply(mock_device)
        
        # Verify that TargetKey instance was created
        assert "TargetKey" in loader.key_instances
        
        # Verify the CHANGE_KEY action was resolved to a Key instance
        print_key_def = loader.keys["PrintKey"]
        change_key_action = print_key_def["on_press"][0]
        action_type, parameter = change_key_action
        
        from StreamDock.Actions import ActionType
        from StreamDock.Key import Key
        assert action_type == ActionType.CHANGE_KEY
        assert isinstance(parameter, Key)

