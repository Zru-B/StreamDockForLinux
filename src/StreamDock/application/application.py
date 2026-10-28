"""
Application bootstrap and dependency injection for StreamDock.

This module provides the Application class which is the main entry point
for initializing and starting the StreamDock application.
"""

import logging
from typing import Any, Callable, Dict, Optional

from StreamDock.application.configuration_manager import ConfigurationManager, StreamDockConfig
from StreamDock.application.device_discovery import device_key, device_label, discover_devices
from StreamDock.domain.Models import WindowInfo
from StreamDock.infrastructure.hardware_interface import DeviceInfo
from StreamDock.business_logic import LayoutManager, LayoutRule, SystemEvent, SystemEventMonitor
from StreamDock.business_logic.action_executor import ActionExecutor
from StreamDock.domain.device_geometry import panel_size
from StreamDock.business_logic.layout_manager import rule_patterns
from StreamDock.infrastructure import (
    DeviceRegistry,
    HardwareInterface,
    LinuxSystemInterface,
    LinuxWindowManager,
    SystemInterface,
    USBHardware,
)
from StreamDock.infrastructure.image_sources import make_image_source
from StreamDock.orchestration import DeviceOrchestrator
from StreamDock.widgets.host import WidgetHost, widget_key_specs
from StreamDock.widgets.registry import WidgetRegistry

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

    DEVICE_ID = "device_0"

    def __init__(self, config_path: str,
                 device_info: Optional[DeviceInfo] = None,
                 raw_document: Optional[Dict[str, Any]] = None,
                 on_layout_changed: Optional[Callable[[str], None]] = None,
                 widget_registry: Optional[WidgetRegistry] = None):
        """
        Initialize application with configuration path.

        Args:
            config_path: Path to YAML configuration file
            device_info: Device to open. Defaults to the first discovered.
            raw_document: In-memory 'streamdock' subtree to use instead of
                reading config_path, so the GUI can apply unsaved edits.
            on_layout_changed: Called with the layout name whenever the
                active layout changes. Deliberately a plain callable: the
                runtime must not import Qt.
            widget_registry: Widgets to run. Defaults to the built-ins plus
                those installed for this user.

        Design Contract:
            - Does NOT initialize components on construction
            - Caller must call initialize() explicitly
            - Allows testing of initialization separately
        """
        self._config_path = config_path
        self._device_info = device_info
        self._raw_document = raw_document
        self._on_layout_changed = on_layout_changed

        # Configuration
        self._config_manager: Optional[ConfigurationManager] = None
        self._config: Optional[StreamDockConfig] = None

        # Infrastructure layer
        self._hardware: Optional[HardwareInterface] = None
        self._system: Optional[SystemInterface] = None
        self._windows = None
        self._registry: Optional[DeviceRegistry] = None

        # Device
        self._device = None
        self._layouts: dict = {}
        self._default_layout = None

        # Business logic layer
        self._event_monitor: Optional[SystemEventMonitor] = None
        self._layout_manager: Optional[LayoutManager] = None
        self._action_executor: Optional[ActionExecutor] = None

        # Orchestration layer
        self._orchestrator: Optional[DeviceOrchestrator] = None

        # Widgets outlive a reload so unchanged ones keep their state.
        self._widget_registry = widget_registry
        self._widget_host: Optional[WidgetHost] = None

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
        self._config_manager = ConfigurationManager(self._config_path, self.widget_registry)
        self._config = self._load_config()
        logger.info("Configuration loaded: brightness=%s, default_layout=%s",
                    self._config.brightness, self._config.default_layout_name)

        # 2. Infrastructure layer
        logger.debug("Creating infrastructure layer...")
        self._hardware = USBHardware()
        self._system = LinuxSystemInterface()
        self._windows = LinuxWindowManager()
        self._registry = None  # Simplified: not using registry for now
        logger.debug("Infrastructure layer created")

        # 2.5. Enumerate and create device
        logger.debug("Enumerating devices...")
        devices = discover_devices(self._hardware)
        logger.info("Found %d StreamDeck device(s)", len(devices))

        # Open the requested device, or the first one discovered
        self._device = None
        device_info = self._select_device(devices)
        if device_info:
            logger.info("Opening device: %s", device_label(device_info))

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

            # Open device via StreamDock wrapper — this starts the HID read thread
            # so that button press callbacks are received.
            success = self._device.open()
            if success:
                logger.info("✓ Device opened successfully")
                self._device.init(self._config.brightness)
                self._device_info = device_info
                logger.info("✓ Device initialized (brightness=%s%%)", self._config.brightness)
            else:
                logger.error("✗ Failed to open device")
                self._device = None
        else:
            logger.warning("No StreamDeck devices found - application will start but device will be inactive")

        # 3-6. Everything above the device: business logic, orchestration,
        # and the layouts built from the configuration.
        self._build_runtime()

        self._initialized = True
        logger.info("StreamDock application initialized successfully")

    def _load_config(self) -> StreamDockConfig:
        """
        Produce the validated configuration snapshot.

        Prefers the in-memory document when one was supplied, so the GUI can
        apply unsaved edits without writing a file first.

        Returns:
            StreamDockConfig with validated data

        Raises:
            ConfigValidationError: If the configuration is invalid
            FileNotFoundError: If no document was supplied and the file is missing
        """
        widgets = self.widget_registry
        if self._raw_document is not None:
            return ConfigurationManager.parse_data(self._raw_document, self._config_path, widgets)
        return self._config_manager.load()

    @property
    def widget_registry(self) -> WidgetRegistry:
        if self._widget_registry is None:
            self._widget_registry = WidgetRegistry()
        return self._widget_registry

    def _select_device(self, devices) -> Optional[DeviceInfo]:
        """
        Pick which discovered device to open.

        Args:
            devices: Discovered devices

        Returns:
            The requested device, the first discovered one, or None
        """
        if not devices:
            return None

        if self._device_info is None:
            return devices[0]

        # Re-resolve against this enumeration: the USB path may have changed
        # since the caller picked the device.
        for device in devices:
            if device_key(device) == device_key(self._device_info):
                return device

        logger.warning("Requested device %s is no longer attached; using %s",
                       device_label(self._device_info), device_label(devices[0]))
        return devices[0]

    def _build_runtime(self) -> None:
        """
        Build everything that sits above the open device.

        Split out of initialize() so reload() can rebuild it against the same
        device without closing the HID handle.
        """
        # Business logic layer
        logger.debug("Creating business logic layer...")

        self._event_monitor = SystemEventMonitor(
            system_interface=self._system,
            window_manager=self._windows,
            verification_delay=self._config.lock_verification_delay
        )

        self._layout_manager = LayoutManager(
            default_layout_name=self._config.default_layout_name
        )

        self._action_executor = ActionExecutor(self._system, self._windows)
        self._action_executor.set_default_brightness(self._config.brightness)

        self._configure_window_rules()

        logger.debug("Business logic layer created: %d window rules", len(self._config.window_rules_config))

        # 4. Orchestration layer
        logger.debug("Creating orchestration layer...")
        self._orchestrator = DeviceOrchestrator(
            hardware=self._hardware,
            system=self._system,
            window_manager=self._windows,
            registry=None,
            event_monitor=self._event_monitor,
            layout_manager=self._layout_manager,
            action_executor=self._action_executor
        )
        logger.debug("Orchestration layer created")

        # 5. Configure orchestrator
        self._orchestrator.set_default_brightness(self._config.brightness)
        if self._device:
            self._device.double_press_interval = self._config.double_press_interval
            self._device.long_press_duration = self._config.long_press_duration
        self._orchestrator.set_layout_changed_callback(self._notify_layout_changed)
        screensaver = self._config.screensaver
        if screensaver.enabled:
            self._orchestrator.set_screensaver(screensaver,
                                               make_image_source(screensaver, panel_size()))

        # 6. Create layouts using LayoutFactory (if device is ready)
        if self._device:
            if self._widget_host is None:
                self._widget_host = WidgetHost(self.widget_registry)
            self._widget_host.attach(self._device, self._orchestrator.run_exclusive,
                                     self._orchestrator.is_locked)
            self._widget_host.configure(widget_key_specs(self._config.raw_config.get('keys', {})))
            self._event_monitor.register_handler(SystemEvent.LOCK, lambda _event: self._widget_host.suspend())
            self._event_monitor.register_handler(SystemEvent.WINDOW_CHANGED, self._on_window_focus)

            logger.info("Creating layouts from configuration...")
            from StreamDock.application.layout_factory import LayoutFactory

            factory = LayoutFactory(
                config_data=self._config.raw_config,
                device=self._device,
                action_executor=self._action_executor,
                widget_host=self._widget_host,
            )

            default_layout, all_layouts = factory.create_layouts()
            logger.info("✓ Created %d layouts", len(all_layouts))

            # Give ActionExecutor the layouts dict so CHANGE_LAYOUT can resolve names at runtime
            self._action_executor.set_layouts(all_layouts)
            self._action_executor.set_layout_switcher(self._orchestrator.apply_layout)
            self._action_executor.set_run_exclusive(self._orchestrator.run_exclusive)
            self._action_executor.set_key_builder(factory.build_key)

            # Draw the layout for the focused window straight away: drawing
            # the default first and switching on the first window poll
            # rendered every key twice on each start and Apply.
            initial_layout = self._initial_layout(all_layouts, default_layout)

            # Under the device lock: widgets kept running across a reload may
            # already be pushing frames. Rendered first, so the lock is held
            # only for the writes.
            initial_layout.prepare()
            self._orchestrator.run_exclusive(initial_layout.apply)
            logger.info("✓ Applied layout: %s", initial_layout.name)

            # Store layouts
            self._layouts = all_layouts
            self._default_layout = default_layout

            # Register device and layouts with the orchestrator so window
            # changes can switch between them.
            self._orchestrator.attach_device(
                self.DEVICE_ID, self._device, current_layout=initial_layout.name)

            for layout_name, layout in all_layouts.items():
                self._orchestrator.register_layout(layout_name, layout)

            logger.info("✓ Registered device and %d layouts with orchestrator", len(all_layouts))
            self._notify_layout_changed(initial_layout.name)

    def _initial_layout(self, layouts: dict, default_layout):
        """
        The layout for the window focused right now, or the default.

        Also hands that window to the event monitor, so its first poll does
        not report it as a change, and to the widgets, which would otherwise
        only learn of it from that poll.
        """
        try:
            window = self._windows.get_active_window() if self._windows else None
        except Exception as e:  # pylint: disable=broad-exception-caught
            logger.debug("Could not read the focused window: %s", e)
            return default_layout
        if not isinstance(window, WindowInfo) or not window.class_:
            return default_layout

        self._event_monitor.seed_window(window)
        self._on_window_focus(None)
        return layouts.get(self._layout_manager.select_layout(window), default_layout)

    def _on_window_focus(self, _event) -> None:
        window = self._event_monitor.current_window if self._event_monitor else None
        if self._widget_host is not None and window is not None:
            self._widget_host.window_focused(window.class_ or '', window.title or '')

    def _configure_window_rules(self) -> None:
        """
        Configure window rules in LayoutManager.

        Converts window_rules_config to LayoutRule objects and adds them
        to the layout manager.
        """
        for rule_name, rule_config in self._config.window_rules_config.items():
            # Extract rule parameters
            pattern = rule_patterns(rule_config['window_name'], rule_config.get('is_regex', False))
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

            logger.debug("Added window rule '%s': %s → %s", rule_name, pattern, layout_name)

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
                logger.exception("Failed to initialize application: %s", e)
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

    def stop(self, *, release_devices: bool = True, force: bool = False) -> None:
        """
        Stop the application.

        Args:
            release_devices: Blank and close the device on the way out
            force: Tear down even when start() never succeeded. initialize()
                opens the HID handle, so a failed start would otherwise leak
                it - which a GUI with a Connect button hits constantly.

        Design Contract:
            - Safe to call even if not started
            - Cleans up all resources
            - Idempotent - safe to call multiple times
        """
        if not self._running and not force:
            logger.debug("Application not running, nothing to stop")
            return

        logger.info("Stopping StreamDock application...")

        if self._orchestrator:
            self._orchestrator.stop(release_devices=release_devices)
        elif release_devices and self._device:
            # Failed before the orchestrator existed; release the handle here.
            try:
                self._device.close()
            except Exception as e:  # pylint: disable=broad-exception-caught
                logger.exception("Error closing device: %s", e)

        if self._widget_host is not None:
            self._widget_host.shutdown()
            self._widget_host = None

        if release_devices:
            self._device = None

        self._running = False
        self._initialized = False
        logger.info("✓ StreamDock application stopped")

    def reload(self, config_path: Optional[str] = None,
               raw_document: Optional[Dict[str, Any]] = None) -> bool:
        """
        Apply a new configuration to the device that is already open.

        Rebuilds everything above the device rather than reconnecting: a full
        stop/start would blank the deck for about a second on every Apply.

        Args:
            config_path: Path the configuration belongs to. Defaults to the
                current one.
            raw_document: In-memory 'streamdock' subtree to apply instead of
                reading from disk.

        Returns:
            True if the new configuration was applied. False means the
            previous configuration is running: either it was never touched
            (invalid configuration), or building the new one failed and the
            previous one was rebuilt and put back on the device.
        """
        if not self._initialized:
            logger.error("Cannot reload before initialize()")
            return False

        previous = (self._config_path, self._raw_document, self._config,
                    self._config_manager)

        # Parse and validate BEFORE tearing anything down, so a bad config
        # leaves the running one alone.
        self._config_path = config_path or self._config_path
        self._raw_document = raw_document
        self._config_manager = ConfigurationManager(self._config_path, self.widget_registry)
        self.widget_registry.refresh()
        try:
            new_config = self._load_config()
        except Exception as e:  # pylint: disable=broad-exception-caught
            logger.error("Refusing to apply invalid configuration: %s", e)
            (self._config_path, self._raw_document, self._config,
             self._config_manager) = previous
            return False

        logger.info("Applying configuration: %s", self._config_path)

        was_running = self._running
        try:
            self._replace_runtime(new_config)
        except Exception as e:  # pylint: disable=broad-exception-caught
            logger.exception("Could not apply configuration, restoring the previous one: %s", e)
            (self._config_path, self._raw_document, _,
             self._config_manager) = previous
            try:
                self._replace_runtime(previous[2])
            except Exception as restore_error:  # pylint: disable=broad-exception-caught
                logger.exception("Could not restore the previous configuration: %s",
                                 restore_error)
            if was_running and self._orchestrator:
                self._orchestrator.start()
            return False

        if was_running and self._orchestrator:
            self._orchestrator.start()

        logger.info("✓ Configuration applied")
        return True

    def _replace_runtime(self, config: StreamDockConfig) -> None:
        """
        Tear down everything above the device and build it again for config.

        Raises whatever building the new runtime raises; the old one is gone
        by then, so the caller must build a working one in its place.
        """
        old_orchestrator = self._orchestrator
        if old_orchestrator:
            # Keep the HID handle, its reader thread and its workers alive.
            old_orchestrator.stop(release_devices=False)

        self._config = config

        if self._widget_host is not None:
            self._widget_host.detach()

        if self._device:
            device = self._device

            # Drop stale callbacks and images first: set_per_key_callback only
            # overwrites the keys the new layout defines, so a key removed
            # from the config would keep firing its old action.
            def prepare_device():
                device.clear_all_callbacks()
                device.clear_all_icons()
                device.set_brightness(config.brightness)

            # Under the old device lock: a key action already running on a
            # worker still writes through it.
            try:
                if old_orchestrator:
                    old_orchestrator.run_exclusive(prepare_device)
                else:
                    prepare_device()
            except Exception as e:  # pylint: disable=broad-exception-caught
                logger.exception("Error preparing device for new configuration: %s", e)

        self._build_runtime()

    def _notify_layout_changed(self, layout_name: str) -> None:
        """Forward a layout change to the caller-supplied hook."""
        if self._on_layout_changed is None:
            return
        try:
            self._on_layout_changed(layout_name)
        except Exception as e:  # pylint: disable=broad-exception-caught
            logger.exception("Error in layout changed hook: %s", e)

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

    def get_config_path(self) -> str:
        """Path of the configuration currently applied."""
        return self._config_path

    def get_device(self):
        """The open device, or None if no device is connected."""
        return self._device

    def get_device_info(self) -> Optional[DeviceInfo]:
        """Descriptor of the open device, or None."""
        return self._device_info

    def get_hardware(self):
        """The hardware abstraction, reusable for re-enumeration."""
        return self._hardware

    def get_current_layout_name(self) -> Optional[str]:
        """Name of the layout currently on the device."""
        if not self._orchestrator:
            return None
        return self._orchestrator.get_current_layout(self.DEVICE_ID)

    def get_orchestrator(self) -> Optional[DeviceOrchestrator]:
        """Get orchestrator instance (for testing)."""
        return self._orchestrator

    def get_event_monitor(self) -> Optional[SystemEventMonitor]:
        """Get event monitor instance (for testing)."""
        return self._event_monitor

    def get_layout_manager(self) -> Optional[LayoutManager]:
        """Get layout manager instance (for testing)."""
        return self._layout_manager
