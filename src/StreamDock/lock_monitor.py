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
    
    def __init__(self, device, enabled=True, current_layout=None, all_layouts=None, device_class=None, window_monitor=None):
        """
        Initialize the lock monitor.
        
        :param device: StreamDock device instance
        :param enabled: Enable monitoring (default: True)
        :param current_layout: Current layout to reapply after unlock (optional)
        :param all_layouts: Dictionary of all layouts {name: Layout} for device reference updates (optional)
        :param device_class: Device class type for recreating device instance
        :param window_monitor: WindowMonitor instance to stop/start on lock/unlock (optional)
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
        
        :param is_locked: True if screen is locked, False if unlocked
        """
        try:
            current_time = time.time()
            
            # Debounce: Ignore if same state or too soon after last change (within 2 seconds)
            if self.is_locked == is_locked:
                return  # Already in this state, ignore duplicate signal
            
            if current_time - self._last_state_change < 2.0:
                return  # Too soon after last change, ignore (debounce)
            
            # Prevent concurrent processing
            if self._processing_state_change:
                return
            
            self._processing_state_change = True
            self._last_state_change = current_time
            self.is_locked = is_locked
            
            if is_locked:
                self.logger.info("🔒 Computer locked - turning off StreamDock")
                self.saved_brightness = getattr(self.device, '_current_brightness', 50)
                
                # Stop window monitor if it's running
                if self.window_monitor and self.window_monitor.running:
                    self.logger.info("🔒 Stopping window monitor")
                    self.window_monitor.stop()
                
                # Clear all icons before closing
                self.device.clear_all_icons()
                time.sleep(0.5)  # Give device time to process clear command
                self.device.close()
            else:
                self.logger.info("🔓 Computer unlocked - turning on StreamDock")
                
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
                    raise Exception("Device not found after re-enumeration")
                
                # Create fresh device instance
                self.device = self.device_class(self.device_transport, device_info)
                
                # Open and initialize
                self.device.open()
                self.device.init()

                # Restore brightness
                self.device.set_brightness(self.saved_brightness)
                self.device._current_brightness = self.saved_brightness

                # Update device reference for ALL layouts (not just current)
                # This is critical for window monitor callbacks to work after unlock
                for layout_name, layout in self.all_layouts.items():
                    layout.update_device(self.device)
                
                # Now apply the current layout with the updated device reference
                if self.current_layout:
                    self.current_layout.apply()
                
                # Restart window monitor if it was running before lock
                if self.window_monitor:
                    self.logger.info("🔓 Restarting window monitor")
                    self.window_monitor.start()
            
            # Reset processing flag
            self._processing_state_change = False
                
        except Exception:
            self.logger.exception("Error handling lock state change")
            self._processing_state_change = False  # Reset flag even on error
    
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
