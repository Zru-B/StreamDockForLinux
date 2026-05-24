"""
Unit tests for ConfigurationManager.

Tests pure configuration parsing and validation logic.
"""

import pytest
import tempfile
import os
from pathlib import Path

from StreamDock.application.configuration_manager import (
    ConfigurationManager,
    StreamDockConfig,
    ConfigValidationError
)


class TestConfigurationManager:
    """Unit tests for ConfigurationManager."""
    
    @pytest.fixture
    def temp_dir(self):
        """Create temporary directory for test files."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield tmpdir
    
    @pytest.fixture
    def test_icon_path(self, temp_dir):
        """Create a temporary test icon file."""
        icon_path = os.path.join(temp_dir, "test_icon.png")
        # Create empty PNG file
        with open(icon_path, 'wb') as f:
            # Minimal PNG header
            f.write(b'\x89PNG\r\n\x1a\n')
        return icon_path
    
    @pytest.fixture
    def valid_config_content(self, test_icon_path):
        """Valid configuration YAML content."""
        return f"""
streamdock:
  settings:
    brightness: 75
    lock_monitor: true
    lock_verification_delay: 2.5
    double_press_interval: 0.4
  keys:
    TestKey:
      icon: {test_icon_path}
      on_press_actions:
        - KEY_PRESS: "CTRL+C"
  layouts:
    TestLayout:
      Default: true
      keys:
        - 1: "TestKey"
  windows_rules:
    TestRule:
      window_name: "firefox"
      layout: "TestLayout"
      match_field: "class"
"""
    
    @pytest.fixture
    def minimal_config_content(self, test_icon_path):
        """Minimal valid configuration."""
        return f"""
streamdock:
  keys:
    Key1:
      icon: {test_icon_path}
      on_press_actions:
        - KEY_PRESS: "A"
  layouts:
    default:
      Default: true
      keys:
        - 1: "Key1"
"""
    
    def create_config_file(self, temp_dir, content):
        """Helper to create a config file."""
        config_path = os.path.join(temp_dir, "config.yml")
        with open(config_path, 'w') as f:
            f.write(content)
        return config_path
    
    # ==================== Loading Tests ====================
    
    def test_load_valid_config(self, temp_dir, valid_config_content):
        """Design contract: Load valid configuration successfully."""
        config_path = self.create_config_file(temp_dir, valid_config_content)
        manager = ConfigurationManager(config_path)
        
        config = manager.load()
        
        assert isinstance(config, StreamDockConfig)
        assert config.brightness == 75
        assert config.default_layout_name == "TestLayout"
        assert config.lock_monitor_enabled is True
        assert config.lock_verification_delay == 2.5
        assert config.double_press_interval == 0.4
        assert "TestKey" in config.keys_config
        assert "TestLayout" in config.layouts_config
        assert "TestRule" in config.window_rules_config
    
    def test_load_minimal_config(self, temp_dir, minimal_config_content):
        """Design contract: Load minimal configuration with defaults."""
        config_path = self.create_config_file(temp_dir, minimal_config_content)
        manager = ConfigurationManager(config_path)
        
        config = manager.load()
        
        assert config.brightness == 50  # Default
        assert config.default_layout_name == "default"
        assert config.lock_monitor_enabled is True  # Default
        assert config.lock_verification_delay == 2.0  # Default
        assert config.double_press_interval == 0.3  # Default
    
    def test_load_missing_file(self, temp_dir):
        """Error handling: Missing file raises FileNotFoundError."""
        config_path = os.path.join(temp_dir, "nonexistent.yml")
        manager = ConfigurationManager(config_path)
        
        with pytest.raises(FileNotFoundError):
            manager.load()
    
    def test_load_empty_file(self, temp_dir):
        """Error handling: Empty file raises ConfigValidationError."""
        config_path = self.create_config_file(temp_dir, "")
        manager = ConfigurationManager(config_path)
        
        with pytest.raises(ConfigValidationError, match="Configuration file is empty"):
            manager.load()
    
    def test_load_missing_root_element(self, temp_dir):
        """Error handling: Missing 'streamdock' root element."""
        config_path = self.create_config_file(temp_dir, "other_key: value")
        manager = ConfigurationManager(config_path)
        
        with pytest.raises(ConfigValidationError, match="must contain 'streamdock' root element"):
            manager.load()
    
    # ==================== Settings Validation Tests ====================
    
    def test_validate_brightness_range(self, temp_dir, test_icon_path):
        """Design contract: Brightness must be 0-100."""
        # Invalid: too high
        content = f"""
streamdock:
  settings:
    brightness: 150
  keys:
    K1:
      icon: {test_icon_path}
      on_press_actions:
        - KEY_PRESS: "A"
  layouts:
    L1:
      Default: true
      keys:
        - 1: "K1"
"""
        config_path = self.create_config_file(temp_dir, content)
        manager = ConfigurationManager(config_path)
        
        with pytest.raises(ConfigValidationError, match="brightness must be a number between 0 and 100"):
            manager.load()
    
    def test_validate_lock_verification_delay_range(self, temp_dir, test_icon_path):
        """Design contract: Lock verification delay must be 0.1-30.0."""
        content = f"""
streamdock:
  settings:
    lock_verification_delay: 50.0
  keys:
    K1:
      icon: {test_icon_path}
      on_press_actions:
        - KEY_PRESS: "A"
  layouts:
    L1:
      Default: true
      keys:
        - 1: "K1"
"""
        config_path = self.create_config_file(temp_dir, content)
        manager = ConfigurationManager(config_path)
        
        with pytest.raises(ConfigValidationError, match="lock_verification_delay must be a number between"):
            manager.load()
    
    # ==================== Keys Validation Tests ====================
    
    def test_validate_key_missing_icon_and_text(self, temp_dir):
        """Error handling: Key must have either icon or text."""
        content = """
streamdock:
  keys:
    BadKey:
      on_press_actions:
        - KEY_PRESS: "A"
  layouts:
    L1:
      Default: true
      keys:
        - 1: "BadKey"
"""
        config_path = self.create_config_file(temp_dir, content)
        manager = ConfigurationManager(config_path)
        
        with pytest.raises(ConfigValidationError, match="must have either 'icon' or 'text' field"):
            manager.load()
    
    def test_validate_key_both_icon_and_text(self, temp_dir, test_icon_path):
        """Error handling: Key cannot have both icon and text."""
        content = f"""
streamdock:
  keys:
    BadKey:
      icon: {test_icon_path}
      text: "Label"
      on_press_actions:
        - KEY_PRESS: "A"
  layouts:
    L1:
      Default: true
      keys:
        - 1: "BadKey"
"""
        config_path = self.create_config_file(temp_dir, content)
        manager = ConfigurationManager(config_path)
        
        with pytest.raises(ConfigValidationError, match="cannot have both 'icon' and 'text' fields"):
            manager.load()
    
    def test_validate_icon_path_not_found(self, temp_dir):
        """Error handling: Icon file must exist."""
        content = """
streamdock:
  keys:
    K1:
      icon: "/nonexistent/icon.png"
      on_press_actions:
        - KEY_PRESS: "A"
  layouts:
    L1:
      Default: true
      keys:
        - 1: "K1"
"""
        config_path = self.create_config_file(temp_dir, content)
        manager = ConfigurationManager(config_path)
        
        with pytest.raises(ConfigValidationError, match="Icon file not found"):
            manager.load()
    
    def test_validate_text_key(self, temp_dir):
        """Design contract: Text keys are valid."""
        content = """
streamdock:
  keys:
    TextKey:
      text: "Hello"
      on_press_actions:
        - KEY_PRESS: "A"
  layouts:
    L1:
      Default: true
      keys:
        - 1: "TextKey"
"""
        config_path = self.create_config_file(temp_dir, content)
        manager = ConfigurationManager(config_path)
        
        config = manager.load()
        assert "TextKey" in config.keys_config
        assert config.keys_config["TextKey"]["text"] == "Hello"
    
    def test_validate_key_missing_actions(self, temp_dir, test_icon_path):
        """Error handling: Key must have at least one action."""
        content = f"""
streamdock:
  keys:
    K1:
      icon: {test_icon_path}
  layouts:
    L1:
      Default: true
      keys:
        - 1: "K1"
"""
        config_path = self.create_config_file(temp_dir, content)
        manager = ConfigurationManager(config_path)
        
        with pytest.raises(ConfigValidationError, match="must have at least one action"):
            manager.load()
    
    def test_validate_invalid_action_type(self, temp_dir, test_icon_path):
        """Error handling: Invalid action type raises error."""
        content = f"""
streamdock:
  keys:
    K1:
      icon: {test_icon_path}
      on_press_actions:
        - INVALID_ACTION: "param"
  layouts:
    L1:
      Default: true
      keys:
        - 1: "K1"
"""
        config_path = self.create_config_file(temp_dir, content)
        manager = ConfigurationManager(config_path)
        
        with pytest.raises(ConfigValidationError, match="invalid action type"):
            manager.load()
    
    # ==================== Layouts Validation Tests ====================
    
    def test_validate_layout_missing_keys_field(self, temp_dir, test_icon_path):
        """Error handling: Layout must have 'keys' field."""
        content = f"""
streamdock:
  keys:
    K1:
      icon: {test_icon_path}
      on_press_actions:
        - KEY_PRESS: "A"
  layouts:
    BadLayout:
      Default: true
"""
        config_path = self.create_config_file(temp_dir, content)
        manager = ConfigurationManager(config_path)
        
        with pytest.raises(ConfigValidationError, match="is missing 'keys' field"):
            manager.load()
    
    def test_validate_multiple_default_layouts(self, temp_dir, test_icon_path):
        """Error handling: Only one default layout allowed."""
        content = f"""
streamdock:
  keys:
    K1:
      icon: {test_icon_path}
      on_press_actions:
        - KEY_PRESS: "A"
  layouts:
    L1:
      Default: true
      keys:
        - 1: "K1"
    L2:
      Default: true
      keys:
        - 1: "K1"
"""
        config_path = self.create_config_file(temp_dir, content)
        manager = ConfigurationManager(config_path)
        
        with pytest.raises(ConfigValidationError, match="Only one layout can have 'Default: true'"):
            manager.load()
    
    def test_validate_no_default_layout(self, temp_dir, test_icon_path):
        """Error handling: At least one default layout required."""
        content = f"""
streamdock:
  keys:
    K1:
      icon: {test_icon_path}
      on_press_actions:
        - KEY_PRESS: "A"
  layouts:
    L1:
      keys:
        - 1: "K1"
"""
        config_path = self.create_config_file(temp_dir, content)
        manager = ConfigurationManager(config_path)
        
        with pytest.raises(ConfigValidationError, match="At least one layout must have 'Default: true'"):
            manager.load()
    
    def test_validate_layout_undefined_key_reference(self, temp_dir, test_icon_path):
        """Error handling: Layout cannot reference undefined keys."""
        content = f"""
streamdock:
  keys:
    K1:
      icon: {test_icon_path}
      on_press_actions:
        - KEY_PRESS: "A"
  layouts:
    L1:
      Default: true
      keys:
        - 1: "UndefinedKey"
"""
        config_path = self.create_config_file(temp_dir, content)
        manager = ConfigurationManager(config_path)
        
        with pytest.raises(ConfigValidationError, match="references undefined key: 'UndefinedKey'"):
            manager.load()
    
    def test_validate_layout_duplicate_key_number(self, temp_dir, test_icon_path):
        """Error handling: Duplicate key numbers not allowed."""
        content = f"""
streamdock:
  keys:
    K1:
      icon: {test_icon_path}
      on_press_actions:
        - KEY_PRESS: "A"
  layouts:
    L1:
      Default: true
      keys:
        - 1: "K1"
        - 1: "K1"
"""
        config_path = self.create_config_file(temp_dir, content)
        manager = ConfigurationManager(config_path)
        
        with pytest.raises(ConfigValidationError, match="duplicate key number 1"):
            manager.load()
    
    # ==================== Window Rules Validation Tests ====================
    
    def test_validate_window_rule_missing_window_name(self, temp_dir, test_icon_path):
        """Error handling: Window rule must have window_name."""
        content = f"""
streamdock:
  keys:
    K1:
      icon: {test_icon_path}
      on_press_actions:
        - KEY_PRESS: "A"
  layouts:
    L1:
      Default: true
      keys:
        - 1: "K1"
  windows_rules:
    BadRule:
      layout: "L1"
"""
        config_path = self.create_config_file(temp_dir, content)
        manager = ConfigurationManager(config_path)
        
        with pytest.raises(ConfigValidationError, match="is missing 'window_name' field"):
            manager.load()
    
    def test_validate_window_rule_undefined_layout(self, temp_dir, test_icon_path):
        """Error handling: Window rule cannot reference undefined layout."""
        content = f"""
streamdock:
  keys:
    K1:
      icon: {test_icon_path}
      on_press_actions:
        - KEY_PRESS: "A"
  layouts:
    L1:
      Default: true
      keys:
        - 1: "K1"
  windows_rules:
    BadRule:
      window_name: "firefox"
      layout: "UndefinedLayout"
"""
        config_path = self.create_config_file(temp_dir, content)
        manager = ConfigurationManager(config_path)
        
        with pytest.raises(ConfigValidationError, match="references undefined layout: 'UndefinedLayout'"):
            manager.load()
    
    def test_validate_window_rule_invalid_match_field(self, temp_dir, test_icon_path):
        """Error handling: Invalid match_field rejected."""
        content = f"""
streamdock:
  keys:
    K1:
      icon: {test_icon_path}
      on_press_actions:
        - KEY_PRESS: "A"
  layouts:
    L1:
      Default: true
      keys:
        - 1: "K1"
  windows_rules:
    Rule1:
      window_name: "firefox"
      layout: "L1"
      match_field: "invalid"
"""
        config_path = self.create_config_file(temp_dir, content)
        manager = ConfigurationManager(config_path)
        
        with pytest.raises(ConfigValidationError, match="invalid match_field"):
            manager.load()
    
    # ==================== Path Expansion Tests ====================
    
    def test_icon_path_expansion(self, temp_dir):
        """Design contract: Relative icon paths are expanded."""
        # Create icon in subdirectory
        icon_dir = os.path.join(temp_dir, "icons")
        os.makedirs(icon_dir)
        icon_path = os.path.join(icon_dir, "test.png")
        with open(icon_path, 'wb') as f:
            f.write(b'\x89PNG\r\n\x1a\n')
        
        # Use relative path in config
        content = """
streamdock:
  keys:
    K1:
      icon: "./icons/test.png"
      on_press_actions:
        - KEY_PRESS: "A"
  layouts:
    L1:
      Default: true
      keys:
        - 1: "K1"
"""
        config_path = self.create_config_file(temp_dir, content)
        manager = ConfigurationManager(config_path)
        
        config = manager.load()
        
        # Path should be expanded to absolute
        key_icon = config.keys_config["K1"]["icon"]
        assert os.path.isabs(key_icon)
        assert key_icon == icon_path
