"""
Lock/Unlock monitor for KDE Plasma and other desktop environments.
Automatically turns off StreamDock device screen when computer is locked.

**DEPRECATED**: This module is deprecated and will be removed in a future version.
Please use the new layered architecture components instead:
- StreamDock.business_logic.system_event_monitor.SystemEventMonitor (event monitoring)
- StreamDock.orchestration.device_orchestrator.DeviceOrchestrator (device coordination)

For migration guide, see: docs/architecture/MIGRATION_GUIDE.md
"""
import logging
import threading
import time
import warnings


class LockMonitor:
    """
    Monitor system lock/unlock state and control device screen accordingly.
    
    .. deprecated::
        This class is deprecated. Use SystemEventMonitor + DeviceOrchestrator instead.
        See docs/architecture/MIGRATION_GUIDE.md for migration instructions.
    
    Supports:
    - KDE Plasma (via org.freedesktop.ScreenSaver D-Bus interface)
    - GNOME (via org.gnome.ScreenSaver D-Bus interface)
    - Other freedesktop.org compliant screen savers
    """
    
    def __init__(self, device, enabled=True, current_layout=None, all_layouts=None, 
                 device_class=None, window_monitor=None, lock_verification_delay=2.0):
        """
        Initialize the lock monitor.
        
        .. deprecated::
            LockMonitor is deprecated. Use SystemEventMonitor + DeviceOrchestrator instead.
        
        :param device: StreamDock device instance
        :param enabled: Enable monitoring (default: True)
        :param current_layout: Current layout to reapply after unlock (optional)
        :param all_layouts: Dictionary of all layouts {name: Layout} for device reference updates (optional)
        :param device_class: Device class type for recreating device instance
        :param window_monitor: WindowMonitor instance to stop/start on lock/unlock (optional)
        :param lock_verification_delay: Seconds to wait before confirming lock (default: 2.0)
        """
        warnings.warn(
            "LockMonitor is deprecated and will be removed in a future version. "
            "Use StreamDock.business_logic.system_event_monitor.SystemEventMonitor "
            "with StreamDock.orchestration.device_orchestrator.DeviceOrchestrator instead. "
            "See docs/architecture/MIGRATION_GUIDE.md",
            DeprecationWarning,
            stacklevel=2
        )
        self.logger = logging.getLogger(__name__)
        self.device = device
        self.enabled = enabled
        self.is_locked = False
        self.monitor_thread = None
        self.running = False
        self.current_layout = current_layout
        self.all_layouts = all_layouts or {}  # Store all layouts for device reference updates
        self.window_monitor = window_monitor
        self._last_state_change = 0  # Timestamp of last state change for debouncing
        self._processing_state_change = False  # Flag to prevent concurrent processing
        
        # Lock verification attributes (to handle aborted lock scenarios)
        self._lock_verification_delay = lock_verification_delay
        self._pending_lock_timer = None  # Timer for delayed lock verification
        self._screensaver_interface = None  # D-Bus interface for GetActive() polling
        
        # Store device info for re-enumeration after close
        self.device_path = device.path
        self.device_vendor_id = device.vendor_id
        self.device_product_id = device.product_id
        self.device_transport = device.transport
        self.device_class = device_class or device.__class__
        
        # Store current brightness to restore after unlock
        self.saved_brightness = getattr(device, '_current_brightness', 50)
        
        # Try to import dbus
        try:
            import dbus
            from dbus.mainloop.glib import DBusGMainLoop
            self.dbus = dbus
            self.DBusGMainLoop = DBusGMainLoop
            self.dbus_available = True
        except ImportError:
            self.logger.warning("Warning: python-dbus not available. Lock monitoring disabled.")
            self.logger.warning("Install with: pip install dbus-python")
            self.dbus_available = False
            self.enabled = False
    
    def start(self):
        """Start monitoring lock/unlock events."""
        if not self.enabled or not self.dbus_available:
            return
        
        self.running = True
        self.monitor_thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self.monitor_thread.start()
        self.logger.info("🔒 Lock monitor started")
    
    def stop(self):
        """Stop monitoring lock/unlock events."""
        self.running = False
        # Cancel any pending lock verification timer
        if self._pending_lock_timer:
            self._pending_lock_timer.cancel()
            self._pending_lock_timer = None
        if self.monitor_thread:
            self.monitor_thread.join(timeout=2)
        self.logger.info("🔒 Lock monitor stopped")
    
    def _monitor_loop(self):
        """Main monitoring loop using D-Bus."""
        try:
            from gi.repository import GLib

            # Initialize D-Bus main loop
            self.DBusGMainLoop(set_as_default=True)
            bus = self.dbus.SessionBus()
            
            # Try KDE/freedesktop screen saver first
            try:
                screensaver = bus.get_object(
                    'org.freedesktop.ScreenSaver',
                    '/ScreenSaver'
                )
                screensaver_interface = self.dbus.Interface(
                    screensaver,
                    'org.freedesktop.ScreenSaver'
                )
                
                # Connect to ActiveChanged signal
                screensaver_interface.connect_to_signal(
                    'ActiveChanged',
                    self._on_lock_state_changed
                )
                
                # Store interface for lock verification polling
                self._screensaver_interface = screensaver_interface
                
                self.logger.info("🔒 Connected to org.freedesktop.ScreenSaver")
                
            except self.dbus.DBusException as e:
                # Try GNOME screen saver as fallback
                try:
                    screensaver = bus.get_object(
                        'org.gnome.ScreenSaver',
                        '/org/gnome/ScreenSaver'
                    )
                    screensaver_interface = self.dbus.Interface(
                        screensaver,
                        'org.gnome.ScreenSaver'
                    )
                    
                    screensaver_interface.connect_to_signal(
                        'ActiveChanged',
                        self._on_lock_state_changed
                    )
                    
                    # Store interface for lock verification polling
                    self._screensaver_interface = screensaver_interface
                    
                    self.logger.info("🔒 Connected to org.gnome.ScreenSaver")
                    
                except self.dbus.DBusException as e2:
                    self.logger.warning(f"Warning: Could not connect to screen saver D-Bus service: {e2}")
                    return
            
            # Run the GLib main loop
            loop = GLib.MainLoop()
            
            # Run in a separate thread so we can stop it
            def run_loop():
                while self.running:
                    try:
                        loop.get_context().iteration(False)
                        time.sleep(0.1)
                    except Exception as e:
                        self.logger.error(f"Error in lock monitor loop: {e}")
                        break
            
            run_loop()
            
        except ImportError:
            self.logger.warning("Warning: GLib not available. Using polling fallback.")
            self._monitor_loop_polling(bus)
        except Exception as e:
            self.logger.exception(f"Error starting lock monitor: {e}")
    
    def _monitor_loop_polling(self, bus):
        """Fallback polling method if GLib is not available."""
        try:
            # Get screen saver interface
            try:
                screensaver = bus.get_object(
                    'org.freedesktop.ScreenSaver',
                    '/ScreenSaver'
                )
            except:
                screensaver = bus.get_object(
                    'org.gnome.ScreenSaver',
                    '/org/gnome/ScreenSaver'
                )
            
            screensaver_interface = self.dbus.Interface(
                screensaver,
                'org.freedesktop.ScreenSaver'
            )
            
            self.logger.info("🔒 Using polling method for lock detection")
            
            # Poll the GetActive method
            while self.running:
                try:
                    is_active = screensaver_interface.GetActive()
                    
                    if is_active != self.is_locked:
                        self._on_lock_state_changed(is_active)
                    
                    time.sleep(1)  # Poll every second
                    
                except Exception as e:
                    self.logger.error(f"Error polling lock state: {e}")
                    time.sleep(5)
                    
        except Exception as e:
            self.logger.error(f"Error in polling monitor: {e}")
    
    def _on_lock_state_changed(self, is_locked):
        """
        Callback when lock state changes.
        
        For lock events: Schedules a verification poll to confirm lock actually
        completed (handles the case where user aborts lock by moving mouse).
        
        For unlock events: Processes immediately and cancels any pending lock
        verification.
        
        :param is_locked: True if screen is locked, False if unlocked
        """
        try:
            current_time = time.time()
            
            # For unlock events: Always cancel any pending lock verification first
            # This handles the race condition where lock was initiated but user aborted
            # by moving the mouse before verification could complete
            if not is_locked and self._pending_lock_timer:
                self.logger.debug("Unlock signal received while lock verification pending - cancelling timer")
                self._cancel_pending_lock_verification()
            
            # Debounce: Ignore if same state
            if self.is_locked == is_locked:
                self.logger.debug(f"Lock state unchanged ({is_locked}), ignoring duplicate signal")
                return  # Already in this state, ignore duplicate signal
            
            # Prevent concurrent processing
            if self._processing_state_change:
                self.logger.debug("Already processing state change, ignoring")
                return
            
            if is_locked:
                # Lock event: Schedule verification instead of immediate action
                # This handles the race condition where user aborts lock by moving mouse
                self._cancel_pending_lock_verification()
                self.logger.debug(f"Lock signal received, scheduling verification in {self._lock_verification_delay}s")
                self._pending_lock_timer = threading.Timer(
                    self._lock_verification_delay,
                    self._verify_and_handle_lock
                )
                self._pending_lock_timer.daemon = True
                self._pending_lock_timer.start()
            else:
                # Unlock event: Process immediately (no debounce needed for unlock)
                # Also cancel any pending lock verification
                self._cancel_pending_lock_verification()
                
                self._processing_state_change = True
                self._last_state_change = current_time
                self.is_locked = False
                
                self._handle_unlock()
                
                self._processing_state_change = False
                
        except Exception:
            self.logger.exception("Error handling lock state change")
            self._processing_state_change = False  # Reset flag even on error
    
    def _cancel_pending_lock_verification(self):
        """
        Cancel any pending lock verification timer.
        
        Called when:
        - A new lock signal arrives (to reset the timer)
        - An unlock signal arrives (lock was aborted)
        - Monitor is stopped
        """
        if self._pending_lock_timer:
            self._pending_lock_timer.cancel()
            self._pending_lock_timer = None
            self.logger.debug("Cancelled pending lock verification timer")
    
    def _verify_and_handle_lock(self):
        """
        Verify that the screen is actually locked before turning off the device.
        
        This method is called after _lock_verification_delay seconds to handle
        the race condition where a lock event fires but the user aborts the lock
        by moving the mouse or pressing a key.
        
        Polls GetActive() to confirm the actual lock state:
        - If locked: Proceed with turning off the StreamDock
        - If not locked: Log and ignore (lock was aborted)
        - If poll fails: Fallback to assuming lock is real (fail-safe)
        """
        try:
            self._pending_lock_timer = None  # Timer has fired
            
            # Poll D-Bus to verify actual lock state
            actual_locked = self._poll_lock_state()
            
            if actual_locked:
                self.logger.debug("Lock verification confirmed - screen is locked")
                self._processing_state_change = True
                self._last_state_change = time.time()
                self.is_locked = True
                self._handle_lock()
                self._processing_state_change = False
            else:
                self.logger.info("🔒 Lock was aborted (user activity detected), ignoring lock event")
                # Reset state - we never actually locked
                self.is_locked = False
                
        except Exception:
            self.logger.exception("Error during lock verification")
            self._processing_state_change = False
    
    def _poll_lock_state(self):
        """
        Poll the screensaver D-Bus interface to get the actual lock state.
        
        :return: True if screen is locked, False if not locked.
                 Returns True on error (fail-safe: assume locked if we can't verify)
        """
        if not self._screensaver_interface:
            self.logger.warning("Screensaver interface not available, assuming locked")
            return True  # Fail-safe: assume locked
        
        try:
            is_active = self._screensaver_interface.GetActive()
            self.logger.debug(f"GetActive() returned: {is_active}")
            return bool(is_active)
        except Exception as e:
            self.logger.warning(f"Failed to poll lock state via GetActive(): {e}")
            return True  # Fail-safe: assume locked if poll fails
    
    def _handle_lock(self):
        """Handle computer lock - turn off screen but keep HID handle open."""
        self.logger.info("🔒 Computer locked - turning off StreamDock")
        self.saved_brightness = getattr(self.device, '_current_brightness', 50)
        
        # Stop window monitor if it's running
        if self.window_monitor and self.window_monitor.running:
            self.logger.info("🔒 Stopping window monitor")
            self.window_monitor.stop()
        
        # Put device in standby mode (screen goes dark, handle stays open)
        self.device.transport.disconnected()
    
    def _handle_unlock(self):
        """Handle computer unlock - try existing handle first, fallback to reopen if stale."""
        self.logger.info("🔓 Computer unlocked - turning on StreamDock")
        
        # Try to wake with existing handle
        if self._try_wake_existing_handle():
            self.logger.debug("Woke device using existing handle")
            self._restore_after_unlock()
        else:
            self.logger.info("🔓 Existing handle stale, reopening device...")
            try:
                self._reopen_device_and_restore()
            except Exception as e:
                # Device not connected - log warning and continue
                # The hotplug mechanism will restore when device reconnects
                self.logger.warning(
                    f"⚠️  StreamDock device not found after unlock. "
                    f"The application will continue running and automatically restore "
                    f"when you reconnect the device. (Details: {e})"
                )
                # Mark as unlocked even though device restore failed
                self.is_locked = False
    
    def _try_wake_existing_handle(self):
        """
        Attempt to wake the device using the existing HID handle.
        
        :return: True if successful, False if handle is stale
        """
        try:
            # Wake screen from standby and restore brightness
            self.device.wake_screen()
            result = self.device.transport.set_brightness(self.saved_brightness)
            return result == 1
        except Exception:
            return False
    
    def _restore_after_unlock(self):
        """Restore device state after successful wake."""
        self.device._current_brightness = self.saved_brightness
        
        # Apply the current layout
        if self.current_layout:
            self.current_layout.apply()
        
        # Restart window monitor if it was running before lock
        if self.window_monitor:
            self.logger.info("🔓 Restarting window monitor")
            self.window_monitor.start()
    
    def _reopen_device_and_restore(self):
        """Fallback: close current handle (if any), reopen device, and restore.
        
        This method handles the complete device reconnection lifecycle:
        1. Close stale handle
        2. Wait for device re-enumeration (up to 20s)
        3. Create and initialize fresh device instance
        4. Restore all layouts and application state
        """
        self.logger.info("Starting device reconnection procedure...")
        
        # Phase 1: Close stale handle
        try:
            self.device.close()
        except Exception:
            pass  # Ignore errors on close - handle may already be invalid
        
        time.sleep(0.5)  # Give device time to be ready
        
        # Phase 2: Wait for device to re-enumerate
        try:
            device_info = self._wait_for_device_enumeration(timeout=20, interval=1)
        except Exception as e:
            raise Exception(f"Device reconnection failed during enumeration: {e}")
        
        # Phase 3: Initialize fresh device instance
        self._initialize_fresh_device(device_info)
        
        # Phase 4: Restore all layouts and application state
        self._restore_all_layouts()
        self._restore_after_unlock()
        
        self.logger.info("✅ Device reconnection completed successfully")
        
    def _wait_for_device_enumeration(self, timeout=20, interval=1):
        """
        Wait for device to appear in enumeration results.
        
        :param timeout: Total time to wait in seconds (default: 20s)
        :param interval: Interval between checks in seconds (default: 1s)
        :return: Device info dictionary
        :raises Exception: If device is not found within timeout
        """
        max_attempts = int(timeout / interval)
        
        self.logger.info(f"Waiting for device to re-enumerate (max {max_attempts} attempts, ~{timeout}s)...")
        
        for attempt in range(1, max_attempts + 1):
            found_devices = self.device_transport.enumerate(
                vid=self.device_vendor_id,
                pid=self.device_product_id
            )
            
            for dev_info in found_devices:
                # Accept any matching VID/PID device, regardless of USB path.
                # The path changes when the device is plugged into a different port.
                new_path = dev_info['path']
                if new_path != self.device_path:
                    self.logger.info(
                        f"Device found at new USB path '{new_path}' "
                        f"(was '{self.device_path}') — updating tracked path"
                    )
                    self.device_path = new_path  # Update tracked path for _initialize_fresh_device
                elapsed = attempt * interval
                self.logger.info(f"✅ Device found after {attempt} attempts (~{elapsed}s)")
                return dev_info
            
            # Show progress every 5 attempts or on first attempt
            if attempt == 1 or attempt % 5 == 0:
                self.logger.info(f"Waiting for device... (attempt {attempt}/{max_attempts})")
            else:
                self.logger.debug(f"Device not found, retrying ({attempt}/{max_attempts})...")
            
            # Sleep between attempts (except after last attempt)
            if attempt < max_attempts:
                time.sleep(interval)
            
        raise Exception(f"Device not found after {max_attempts} attempts (~{timeout}s, path: {self.device_path})")


    def _open_device_with_retry(self, max_retries=5):
        """
        Attempt to open the device with retries.
        
        :param max_retries: Maximum number of open attempts
        :return: True if opened successfully, False otherwise
        """
        retry_delay = 0.5
        
        for attempt in range(1, max_retries + 1):
            self.logger.debug(f"Attempting to open device (attempt {attempt}/{max_retries})...")
            
            if self.device.open():
                self.logger.info(f"✅ Device opened successfully on attempt {attempt}")
                return True
            elif attempt < max_retries:
                self.logger.warning(f"Device open failed (attempt {attempt}/{max_retries}), retrying in {retry_delay}s...")
                time.sleep(retry_delay)
                retry_delay += 0.5  # Exponential backoff
            else:
                self.logger.error(f"❌ Failed to open device after {max_retries} attempts")
        
        return False
    
    def _initialize_fresh_device(self, device_info):
        """
        Create a fresh device instance and initialize it.
        
        :param device_info: Device information dictionary from enumeration
        """
        self.logger.info("Creating fresh device instance...")
        
        # Create new device instance
        self.device = self.device_class(self.device_transport, device_info)
        
        # Open device with retry logic
        if not self._open_device_with_retry(max_retries=5):
            raise Exception("Failed to open device after retries")
        
        # Initialize device and restore brightness
        self.logger.debug("Initializing device and restoring brightness...")
        self.device.init()
        self.device.set_brightness(self.saved_brightness)
        self.device._current_brightness = self.saved_brightness
    
    def _restore_all_layouts(self):
        """
        Update device reference for all layouts after device recreation.
        
        This is critical to ensure all layouts can communicate with the new device instance.
        """
        self.logger.debug(f"Updating device reference for {len(self.all_layouts)} layouts...")
        
        for layout_name, layout in self.all_layouts.items():
            layout.update_device(self.device)
        
        self.logger.debug("All layouts updated successfully")
    
    def get_device(self):
        """
        Get the current device instance.
        This may be a different instance after unlock (device is recreated).
        
        :return: Current device instance
        """
        return self.device
    
    def set_current_layout(self, layout):
        """
        Set the current layout to be reapplied after unlock.
        
        :param layout: Layout instance to reapply
        """
        self.current_layout = layout

    def update_device(self, new_device):
        """
        Update the device instance (e.g. after hotplug/reconnection).
        
        This allows external components (like DeviceManager) to push a new device
        instance when it's detected, bypassing internal reconnection logic.
        
        :param new_device: New StreamDock device instance
        """
        self.logger.info(f"🔄 Updating device reference in LockMonitor: {new_device.path}")
        
        # Close old device if different
        if self.device and self.device != new_device:
            try:
                self.device.close()
            except Exception:
                pass
        
        # Update references
        self.device = new_device
        self.device_path = new_device.path
        
        # We need to make sure we update internal tracking of VID/PID too just in case
        self.device_vendor_id = new_device.vendor_id
        self.device_product_id = new_device.product_id
        self.device_transport = new_device.transport
        
        # Branch on lock state:
        # - If the PC is currently locked, keep the screen off and preserve is_locked=True
        #   so that the real unlock signal still fires properly via _on_lock_state_changed.
        # - If not locked, restore full state immediately.
        if self.is_locked:
            self.logger.info("🔒 Device reconnected while PC is locked — keeping screen off until unlock")
            try:
                new_device.transport.disconnected()
            except Exception:
                pass
            return

        # Not locked: restore full state
        try:
            # WAKE SCREEN: Critical for black screen fix
            new_device.wake_screen()
            
            # Restore brightness
            new_device.set_brightness(self.saved_brightness)
            new_device._current_brightness = self.saved_brightness
            
            # Update all layouts
            for layout_name, layout in self.all_layouts.items():
                layout.update_device(new_device)
            
            # Re-apply current layout
            if self.current_layout:
                self.current_layout.apply()
                # Force refresh of keys to ensure images are sent
                # (apply() essentially re-sends keys, but maybe we need more?)
                # If apply() just updates mapping, we might need render()
                # Assuming layout.apply() triggers render.
                
            # Restart window monitor if needed and force an immediate layout update.
            if self.window_monitor:
                # Reset detection state BEFORE starting so the first poll sees
                # the current window as "changed" and fires the layout callback.
                self.window_monitor.current_window_id = None
                if not self.window_monitor.running:
                    self.window_monitor.start()
                
        except Exception as e:
            self.logger.exception(f"Error restoring state after device update: {e}")

