"""
Lock/Unlock monitor for KDE Plasma and other desktop environments.
Automatically turns off StreamDock device screen when computer is locked.
"""
import logging
import threading
import time


class LockMonitor:
    """
    Monitor system lock/unlock state and control device screen accordingly.
    
    Supports:
    - KDE Plasma (via org.freedesktop.ScreenSaver D-Bus interface)
    - GNOME (via org.gnome.ScreenSaver D-Bus interface)
    - Other freedesktop.org compliant screen savers
    """
    
    def __init__(self, device, enabled=True, current_layout=None, all_layouts=None, 
                 device_class=None, window_monitor=None, lock_verification_delay=2.0):
        """
        Initialize the lock monitor.
        
        :param device: StreamDock device instance
        :param enabled: Enable monitoring (default: True)
        :param current_layout: Current layout to reapply after unlock (optional)
        :param all_layouts: Dictionary of all layouts {name: Layout} for device reference updates (optional)
        :param device_class: Device class type for recreating device instance
        :param window_monitor: WindowMonitor instance to stop/start on lock/unlock (optional)
        :param lock_verification_delay: Seconds to wait before confirming lock (default: 2.0)
        """
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
            self._reopen_device_and_restore()
    
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
        """Fallback: close current handle (if any), reopen device, and restore."""
        # Close current handle if it exists
        try:
            self.device.close()
        except Exception:
            pass  # Ignore errors on close - handle may already be invalid
        
        time.sleep(0.5)  # Give device time to be ready
        
        # Re-enumerate and find device
        found_devices = self.device_transport.enumerate(
            vid=self.device_vendor_id,
            pid=self.device_product_id
        )
        
        device_info = None
        for dev_info in found_devices:
            if dev_info['path'] == self.device_path:
                device_info = dev_info
                break
        
        # Retry once if not found immediately
        if not device_info:
            self.logger.debug(f"Device path '{self.device_path}' not found, retrying...")
            time.sleep(1)
            found_devices = self.device_transport.enumerate(
                vid=self.device_vendor_id,
                pid=self.device_product_id
            )
            for dev_info in found_devices:
                if dev_info['path'] == self.device_path:
                    device_info = dev_info
                    break
        
        if not device_info:
            raise Exception(f"Device not found after re-enumeration (path: {self.device_path})")
        
        # Create fresh device instance
        self.device = self.device_class(self.device_transport, device_info)
        
        # Open device with retry logic
        max_retries = 5
        retry_delay = 0.5
        
        for attempt in range(1, max_retries + 1):
            if self.device.open():
                self.logger.debug(f"Device opened on attempt {attempt}")
                break
            elif attempt < max_retries:
                self.logger.debug(f"Device open failed, retry in {retry_delay}s...")
                time.sleep(retry_delay)
                retry_delay += 0.5
                self.device = self.device_class(self.device_transport, device_info)
            else:
                raise Exception(f"Failed to open device after {max_retries} attempts")
        
        self.device.init()
        self.device.set_brightness(self.saved_brightness)
        self.device._current_brightness = self.saved_brightness

        # Update device reference for ALL layouts (critical after device recreation)
        for layout_name, layout in self.all_layouts.items():
            layout.update_device(self.device)
        
        self._restore_after_unlock()
    
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
