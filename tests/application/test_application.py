"""
Integration tests for Application class.

Tests dependency injection, component wiring, and lifecycle management.
"""

import pytest
import tempfile
import os
from unittest.mock import Mock, patch, MagicMock

from StreamDock.application import Application, StreamDockConfig
from StreamDock.application.configuration_manager import ConfigValidationError


class TestApplication:
    """Integration tests for Application bootstrap."""
    
    @pytest.fixture
    def temp_dir(self):
        """Create temporary directory for test files."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield tmpdir
    
    @pytest.fixture
    def test_icon_path(self, temp_dir):
        """Create a temporary test icon file."""
        icon_path = os.path.join(temp_dir, "test_icon.png")
        with open(icon_path, 'wb') as f:
            f.write(b'\x89PNG\r\n\x1a\n')
        return icon_path
    
    @pytest.fixture
    def valid_config_content(self, test_icon_path):
        """Valid configuration YAML content."""
        return f"""
streamdock:
  settings:
    brightness: 80
    lock_verification_delay: 3.0
  keys:
    TestKey:
      icon: {test_icon_path}
      on_press_actions:
        - KEY_PRESS: "A"
  layouts:
    DefaultLayout:
      Default: true
      keys:
        - 1: "TestKey"
  windows_rules:
    Firefox:
      window_name: "firefox"
      layout: "DefaultLayout"
      match_field: "class"
"""
    
    def create_config_file(self, temp_dir, content):
        """Helper to create a config file."""
        config_path = os.path.join(temp_dir, "config.yml")
        with open(config_path, 'w') as f:
            f.write(content)
        return config_path
    
    # ==================== Initialization Tests ====================
    
    @patch('StreamDock.application.application.USBHardware')
    @patch('StreamDock.application.application.LinuxSystemInterface')
    @patch('StreamDock.application.application.DeviceRegistry')
    def test_initialize_creates_all_components(
        self, mock_registry, mock_system, mock_hardware,
        temp_dir, valid_config_content
    ):
        """CRITICAL: Initialize creates all layer components."""
        config_path = self.create_config_file(temp_dir, valid_config_content)
        app = Application(config_path)
        
        # Mock infrastructure constructors
        mock_hardware.return_value = Mock()
        mock_system.return_value = Mock()
        mock_registry.return_value = Mock()
        
        app.initialize()
        
        # Verify all layers created
        assert app.is_initialized() is True
        assert app.get_config() is not None
        assert app.get_orchestrator() is not None
        assert app.get_event_monitor() is not None
        assert app.get_layout_manager() is not None
        
        # Verify infrastructure created
        mock_hardware.assert_called_once()
        mock_system.assert_called_once()
        mock_registry.assert_called_once()
    
    @patch('StreamDock.application.application.USBHardware')
    @patch('StreamDock.application.application.LinuxSystemInterface')
    @patch('StreamDock.application.application.DeviceRegistry')
    def test_initialize_wires_dependencies(
        self, mock_registry, mock_system, mock_hardware,
        temp_dir, valid_config_content
    ):
        """CRITICAL: Initialize wires components with dependency injection."""
        config_path = self.create_config_file(temp_dir, valid_config_content)
        app = Application(config_path)
        
        # Mock infrastructure
        hardware_instance = Mock()
        system_instance = Mock()
        registry_instance = Mock()
        
        mock_hardware.return_value = hardware_instance
        mock_system.return_value = system_instance
        mock_registry.return_value = registry_instance
        
        app.initialize()
        
        # Verify orchestrator has correct dependencies
        orchestrator = app.get_orchestrator()
        assert orchestrator._hardware == hardware_instance
        assert orchestrator._system == system_instance
        assert orchestrator._registry == registry_instance
        assert orchestrator._event_monitor == app.get_event_monitor()
        assert orchestrator._layout_manager == app.get_layout_manager()
    
    @patch('StreamDock.application.application.USBHardware')
    @patch('StreamDock.application.application.LinuxSystemInterface')
    @patch('StreamDock.application.application.DeviceRegistry')
    def test_initialize_configures_from_yaml(
        self, mock_registry, mock_system, mock_hardware,
        temp_dir, valid_config_content
    ):
        """CRITICAL: Initialize applies configuration settings."""
        config_path = self.create_config_file(temp_dir, valid_config_content)
        app = Application(config_path)
        
        # Mock infrastructure
        mock_hardware.return_value = Mock()
        mock_system.return_value = Mock()
        mock_registry.return_value = Mock()
        
        app.initialize()
        
        # Verify configuration loaded
        config = app.get_config()
        assert config.brightness == 80
        assert config.lock_verification_delay == 3.0
        assert config.default_layout_name == "DefaultLayout"
        
        # Verify orchestrator configured
        orchestrator = app.get_orchestrator()
        assert orchestrator._default_brightness == 80
        
        # Verify event monitor configured
        event_monitor = app.get_event_monitor()
        assert event_monitor._verification_delay == 3.0
        
        # Verify layout manager configured
        layout_manager = app.get_layout_manager()
        assert layout_manager._default_layout_name == "DefaultLayout"
    
    @patch('StreamDock.application.application.USBHardware')
    @patch('StreamDock.application.application.LinuxSystemInterface')
    @patch('StreamDock.application.application.DeviceRegistry')
    def test_initialize_adds_window_rules(
        self, mock_registry, mock_system, mock_hardware,
        temp_dir, valid_config_content
    ):
        """Design contract: Window rules added to LayoutManager."""
        config_path = self.create_config_file(temp_dir, valid_config_content)
        app = Application(config_path)
        
        # Mock infrastructure
        mock_hardware.return_value = Mock()
        mock_system.return_value = Mock()
        mock_registry.return_value = Mock()
        
        app.initialize()
        
        # Verify window rule added
        layout_manager = app.get_layout_manager()
        assert len(layout_manager._rules) == 1
        rule = layout_manager._rules[0]
        assert rule.pattern == "firefox"
        assert rule.layout_name == "DefaultLayout"
        assert rule.match_field == "class"
    
    def test_initialize_invalid_config(self, temp_dir):
        """Error handling: Invalid config raises error."""
        # Missing keys section
        content = """
streamdock:
  layouts:
    L1:
      Default: true
"""
        config_path = self.create_config_file(temp_dir, content)
        app = Application(config_path)
        
        with pytest.raises(ConfigValidationError):
            app.initialize()
    
    # ==================== Lifecycle Tests ====================
    
    @patch('StreamDock.application.application.USBHardware')
    @patch('StreamDock.application.application.LinuxSystemInterface')
    @patch('StreamDock.application.application.DeviceRegistry')
    def test_start_initializes_if_needed(
        self, mock_registry, mock_system, mock_hardware,
        temp_dir, valid_config_content
    ):
        """Design contract: Start initializes if not already initialized."""
        config_path = self.create_config_file(temp_dir, valid_config_content)
        app = Application(config_path)
        
        # Mock infrastructure
        mock_hardware.return_value = Mock()
        mock_system.return_value = Mock()
        mock_registry.return_value = Mock()
        
        # Mock orchestrator start
        with patch.object(Application, 'initialize', wraps=app.initialize) as mock_init:
            app.start()
            mock_init.assert_called_once()
    
    @patch('StreamDock.application.application.USBHardware')
    @patch('StreamDock.application.application.LinuxSystemInterface')
    @patch('StreamDock.application.application.DeviceRegistry')
    def test_start_and_stop(
        self, mock_registry, mock_system, mock_hardware,
        temp_dir, valid_config_content
    ):
        """CRITICAL: Start and stop lifecycle works."""
        config_path = self.create_config_file(temp_dir, valid_config_content)
        app = Application(config_path)
        
        # Mock infrastructure
        hardware_instance = Mock()
        system_instance = Mock()
        registry_instance = Mock()
        
        mock_hardware.return_value = hardware_instance
        mock_system.return_value = system_instance
        mock_registry.return_value = registry_instance
        
        # Mock orchestrator start to return True
        app.initialize()
        app._orchestrator.start = Mock(return_value=True)
        app._orchestrator.stop = Mock()
        
        # Start
        result = app.start()
        assert result is True
        assert app.is_running() is True
        app._orchestrator.start.assert_called_once()
        
        # Stop
        app.stop()
        assert app.is_running() is False
        app._orchestrator.stop.assert_called_once()
    
    @patch('StreamDock.application.application.USBHardware')
    @patch('StreamDock.application.application.LinuxSystemInterface')
    @patch('StreamDock.application.application.DeviceRegistry')
    def test_start_returns_false_on_failure(
        self, mock_registry, mock_system, mock_hardware,
        temp_dir, valid_config_content
    ):
        """Error handling: Start returns False if orchestrator fails."""
        config_path = self.create_config_file(temp_dir, valid_config_content)
        app = Application(config_path)
        
        # Mock infrastructure
        mock_hardware.return_value = Mock()
        mock_system.return_value = Mock()
        mock_registry.return_value = Mock()
        
        # Mock orchestrator start to return False
        app.initialize()
        app._orchestrator.start = Mock(return_value=False)
        
        result = app.start()
        assert result is False
        assert app.is_running() is False
    
    @patch('StreamDock.application.application.USBHardware')
    @patch('StreamDock.application.application.LinuxSystemInterface')
    @patch('StreamDock.application.application.DeviceRegistry')
    def test_stop_when_not_running(
        self, mock_registry, mock_system, mock_hardware,
        temp_dir, valid_config_content
    ):
        """Design contract: Stop is safe when not running."""
        config_path = self.create_config_file(temp_dir, valid_config_content)
        app = Application(config_path)
        
        # Mock infrastructure
        mock_hardware.return_value = Mock()
        mock_system.return_value = Mock()
        mock_registry.return_value = Mock()
        
        app.initialize()
        
        # Stop without starting (should not crash)
        app.stop()
        assert app.is_running() is False
    
    # ==================== State Query Tests ====================
    
    def test_initial_state(self, temp_dir, valid_config_content):
        """Design contract: Initial state is not initialized or running."""
        config_path = self.create_config_file(temp_dir, valid_config_content)
        app = Application(config_path)
        
        assert app.is_initialized() is False
        assert app.is_running() is False
        assert app.get_config() is None
        assert app.get_orchestrator() is None
    
    @patch('StreamDock.application.application.USBHardware')
    @patch('StreamDock.application.application.LinuxSystemInterface')
    @patch('StreamDock.application.application.DeviceRegistry')
    def test_state_after_init(
        self, mock_registry, mock_system, mock_hardware,
        temp_dir, valid_config_content
    ):
        """Design contract: State correct after initialization."""
        config_path = self.create_config_file(temp_dir, valid_config_content)
        app = Application(config_path)
        
        # Mock infrastructure
        mock_hardware.return_value = Mock()
        mock_system.return_value = Mock()
        mock_registry.return_value = Mock()
        
        app.initialize()
        
        assert app.is_initialized() is True
        assert app.is_running() is False
        assert app.get_config() is not None
        assert app.get_orchestrator() is not None
