"""
Application bootstrap and dependency injection for StreamDock.

This module provides the Application class which is the main entry point
for initializing and starting the StreamDock application.
"""

import logging
from typing import Optional

from StreamDock.infrastructure import (
    HardwareInterface,
    SystemInterface,
    DeviceRegistry,
    USBHardware,
    LinuxSystemInterface
)
from StreamDock.business_logic import (
    SystemEventMonitor,
    LayoutManager,
    LayoutRule
)
from StreamDock.orchestration import DeviceOrchestrator
from StreamDock.application.configuration_manager import (
    ConfigurationManager,
    StreamDockConfig
)


logger = logging.getLogger(__name__)


class Application:
    """
    StreamDock application bootstrap.
    
    Responsibilities:
    - Initialize all layers with dependency injection
    - Wire components together
    - Provide lifecycle management (start/stop)
    - Load and apply configuration
    
    Design Pattern: Dependency Injection Container
    
    Layers Initialized:
    1. Configuration Layer (ConfigurationManager)
    2. Infrastructure Layer (Hardware, System, Registry)
    3. Business Logic Layer (EventMonitor, LayoutManager)
    4. Orchestration Layer (DeviceOrchestrator)
    """
    
    def __init__(self, config_path: str):
        """
        Initialize application with configuration path.
        
        Args:
            config_path: Path to YAML configuration file
            
        Design Contract:
            - Does NOT initialize components on construction
            - Caller must call initialize() explicitly
            - Allows testing of initialization separately
        """
        self._config_path = config_path
        
        # Configuration
        self._config_manager: Optional[ConfigurationManager] = None
        self._config: Optional[StreamDockConfig] = None
        
        # Infrastructure layer
        self._hardware: Optional[HardwareInterface] = None
        self._system: Optional[SystemInterface] = None
        self._registry: Optional[DeviceRegistry] = None
        
        # Business logic layer
        self._event_monitor: Optional[SystemEventMonitor] = None
        self._layout_manager: Optional[LayoutManager] = None
        
        # Orchestration layer
        self._orchestrator: Optional[DeviceOrchestrator] = None
        
        # State
        self._initialized = False
        self._running = False
    
    def initialize(self) -> None:
        """
        Initialize all components with dependency injection.
        
        Order:
        1. Load configuration
        2. Create infrastructure layer
        3. Create business logic layer
        4. Create orchestration layer
        5. Configure orchestrator
        6. Set up ConfigLoader for object creation (HYBRID)
        
        Raises:
            ConfigValidationError: If configuration is invalid
            FileNotFoundError: If configuration file not found
        """
        logger.info("Initializing StreamDock application...")
        
        # 1. Load configuration
        logger.debug("Loading configuration...")
        self._config_manager = ConfigurationManager(self._config_path)
        self._config = self._config_manager.load()
        logger.info(f"Configuration loaded: brightness={self._config.brightness}, "
                   f"default_layout={self._config.default_layout_name}")
        
        # 2. Infrastructure layer
        logger.debug("Creating infrastructure layer...")
        self._hardware = USBHardware()
        self._system = LinuxSystemInterface()
        self._registry = None  # Simplified: not using registry for now
        logger.debug("Infrastructure layer created")
        
        # 2.5. Enumerate and create device
        logger.debug("Enumerating devices...")
        # Device VID/PID from lsusb
        STREAMDECK_VID = 0x6603  # HOTSPOTEKUSB
        STREAMDECK_PID = 0x1006  # HID DEMO
        devices = self._hardware.enumerate_devices(STREAMDECK_VID, STREAMDECK_PID)
        logger.info(f"Found {len(devices)} StreamDeck device(s)")
        
        # Create device wrapper for first device
        self._device = None
        if devices:
            device_info = devices[0]
            logger.info(f"Opening device: {device_info.device_id}")
            
            # Open device
            success = self._hardware.open_device(device_info)
            if success:
                logger.info("✓ Device opened successfully")
                
                # Create device wrapper
                # Convert DeviceInfo to dict for legacy StreamDock compatibility
                device_dict = {
                    'vendor_id': device_info.vendor_id,
                    'product_id': device_info.product_id,
                    'serial_number': device_info.serial_number,
                    'path': device_info.path,
                    'manufacturer_string': device_info.manufacturer,
                    'product_string': device_info.product
                }
                
                from StreamDock.devices.stream_dock_293_v3 import StreamDock293V3
                self._device = StreamDock293V3(self._hardware, device_dict)
                
                # Initialize device
                self._device.init()
                logger.info("✓ Device initialized")
            else:
                logger.error("✗ Failed to open device")
        else:
            logger.warning("No StreamDeck devices found - application will start but device will be inactive")
        
        # 3. Business logic layer
        logger.debug("Creating business logic layer...")
        
        self._event_monitor = SystemEventMonitor(
            system_interface=self._system,
            verification_delay=self._config.lock_verification_delay
        )
        
        self._layout_manager = LayoutManager(
            default_layout_name=self._config.default_layout_name
        )
        
        self._configure_window_rules()
        
        logger.debug(f"Business logic layer created: {len(self._config.window_rules_config)} window rules")
        
        # 4. Orchestration layer
        logger.debug("Creating orchestration layer...")
        self._orchestrator = DeviceOrchestrator(
            hardware=self._hardware,
            system=self._system,
            registry=None,
            event_monitor=self._event_monitor,
            layout_manager=self._layout_manager
        )
        logger.debug("Orchestration layer created")
        
        # 5. Configure orchestrator  
        self._orchestrator.set_default_brightness(self._config.brightness)
        
        # 6. Create layouts using LayoutFactory (if device is ready)
        if self._device:
            logger.info("Creating layouts from configuration...")
            from StreamDock.application.layout_factory import LayoutFactory
            
            factory = LayoutFactory(
                config_data=self._config.raw_config,
                device=self._device
            )
            
            default_layout, all_layouts = factory.create_layouts()
            logger.info(f"✓ Created {len(all_layouts)} layouts")
            
            # Apply default layout
            default_layout.apply()
            logger.info(f"✓ Applied default layout: {default_layout.name}")
            
            # Store layouts
            self._layouts = all_layouts
            self._default_layout = default_layout
            
            # CRITICAL: Register device and layouts with orchestrator for window switching
            # Since we're not using DeviceRegistry, we need to manually populate orchestrator
            device_id = "device_0"  # Simple ID since we only have one device
            self._orchestrator._devices[device_id] = self._device
            self._orchestrator._current_layouts[device_id] = default_layout.name
            
            # Register all layouts with orchestrator
            for layout_name, layout in all_layouts.items():
                self._orchestrator.register_layout(layout_name, layout)
            
            logger.info(f"✓ Registered device and {len(all_layouts)} layouts with orchestrator")
        
        self._initialized = True
        logger.info("StreamDock application initialized successfully")
    
    def _configure_window_rules(self) -> None:
        """
        Configure window rules in LayoutManager.
        
        Converts window_rules_config to LayoutRule objects and adds them
        to the layout manager.
        """
        for rule_name, rule_config in self._config.window_rules_config.items():
            # Extract rule parameters
            pattern = rule_config['window_name']
            layout_name = rule_config['layout']
            match_field = rule_config.get('match_field', 'class')
            priority = rule_config.get('priority', 0)
            
            # Add rule using LayoutManager API
            self._layout_manager.add_rule(
                pattern=pattern,
                layout_name=layout_name,
                match_field=match_field,
                priority=priority
            )
            
            logger.debug(f"Added window rule '{rule_name}': {pattern} → {layout_name}")
    
    def start(self) -> bool:
        """
        Start the application.
        
        Returns:
            True if started successfully, False otherwise
            
        Design Contract:
            - Initializes if not already initialized
            - Starts orchestrator (which starts monitoring)
            - Returns True only if fully operational
        """
        if not self._initialized:
            try:
                self.initialize()
            except Exception as e:
                logger.exception(f"Failed to initialize application: {e}")
                return False
        
        logger.info("Starting StreamDock application...")
        
        # Start orchestrator (which starts monitoring)
        success = self._orchestrator.start()
        
        if success:
            self._running = True
            logger.info("✓ StreamDock application started successfully")
        else:
            logger.error("✗ Failed to start StreamDock application")
        
        return success
    
    def stop(self) -> None:
        """
        Stop the application.
        
        Design Contract:
            - Safe to call even if not started
            - Cleans up all resources
            - Idempotent - safe to call multiple times
        """
        if not self._running:
            logger.debug("Application not running, nothing to stop")
            return
        
        logger.info("Stopping StreamDock application...")
        
        if self._orchestrator:
            self._orchestrator.stop()
        
        self._running = False
        logger.info("✓ StreamDock application stopped")
    
    def is_running(self) -> bool:
        """
        Check if application is running.
        
        Returns:
            True if application is running, False otherwise
        """
        return self._running
    
    def is_initialized(self) -> bool:
        """
        Check if application is initialized.
        
        Returns:
            True if application is initialized, False otherwise
        """
        return self._initialized
    
    # Accessors for testing
    
    def get_config(self) -> Optional[StreamDockConfig]:
        """Get loaded configuration (for testing)."""
        return self._config
    
    def get_orchestrator(self) -> Optional[DeviceOrchestrator]:
        """Get orchestrator instance (for testing)."""
        return self._orchestrator
    
    def get_event_monitor(self) -> Optional[SystemEventMonitor]:
        """Get event monitor instance (for testing)."""
        return self._event_monitor
    
    def get_layout_manager(self) -> Optional[LayoutManager]:
        """Get layout manager instance (for testing)."""
        return self._layout_manager
