#!/usr/bin/env python3
"""
StreamDock main application with YAML configuration support.
"""
import argparse
import logging
import os
import sys
import threading
import time

from StreamDock.config_loader import ConfigLoader, ConfigValidationError
from StreamDock.dependency_check import DependencyChecker
from StreamDock.device_manager import DeviceManager
from StreamDock.lock_monitor import LockMonitor
from StreamDock.window_monitor import WindowMonitor


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="StreamDock Linux Controller")
    parser.add_argument('config', nargs='?', help="Path to configuration file")
    parser.add_argument('--mock', '--headless', action='store_true', help="Run in mock/headless mode without physical device")
    parser.add_argument('--check-deps', action='store_true', help="Check dependencies and exit")
    parser.add_argument('--debug', action='store_true', help="Enable debug logging")
    return parser.parse_args()


def main():
    """Main application entry point."""
    # Initialize argument parser
    args = parse_args()

    # Set log level
    log_level = logging.DEBUG if args.debug else logging.INFO
    
    logging.basicConfig(
        level=log_level,
        format='%(asctime)s %(levelname)s:%(name)s:%(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    # Run dependency check if requested or on startup
    dependency_checker = DependencyChecker()
    if args.check_deps:
        dependency_checker.print_report()
        sys.exit(0)
    
    # Log summary and check for critical failures
    dependency_summary = dependency_checker.get_summary()
    logging.info(dependency_summary)
    
    if dependency_checker.has_critical_failures():
        logging.error("Critical dependencies missing. Run with --check-deps for details.")
        sys.exit(1)
    
    # Determine config file path
    if args.config:
        config_file = args.config
    else:
        # Use config.yml in the same directory as the script
        # script_dir = os.path.dirname(os.path.abspath(__file__))
        # config_file = os.path.join(script_dir, 'config.yml')
        # Find 'config.yml' in the parent directory or the current directory
        config_file = 'config.yml'
        if not os.path.exists(config_file):
            config_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'config.yml')
        if not os.path.exists(config_file):
            logging.error("config.yml not found")
            sys.exit(1)
    
    # Determine transport mode
    transport_type = 'mock' if args.mock else None
    
    if transport_type == 'mock':
        logging.info("Starting in MOCK/HEADLESS mode")
    
    # Load configuration
    try:
        config_loader = ConfigLoader(config_file)
        config_loader.load()
    except FileNotFoundError as e:
        logging.error(f"{e}")
        sys.exit(1)
    except ConfigValidationError as e:
        logging.error(f"Configuration Error: {e}")
        sys.exit(1)
    except Exception as e:
        logging.exception(f"Unexpected error loading configuration: {e}")
        sys.exit(1)
    
    # Initialize device manager
    deviceManager = DeviceManager(transport=transport_type)
    streamdocks = deviceManager.enumerate()
    
    # Start listening thread
    t = threading.Thread(target=deviceManager.listen)
    t.daemon = True
    t.start()
    
    if len(streamdocks) == 0:
        logging.error("No Stream Dock devices found. Please connect a device and try again.")
        sys.exit(1)
    
    for device in streamdocks:
        if transport_type != 'mock':
            device.open()
        device.init()

        # device.set_touchscreen_image("/home/zrubi/Development_Private/StreamDock/img/zrubi_logo.jpg")

        # Initialize window monitor
        window_monitor = WindowMonitor(poll_interval=0.5)
        
        # Apply configuration to device
        try:
            default_layout, all_layouts = config_loader.apply(device, window_monitor)
            
            # Initialize lock monitor (from config setting) with default layout, all layouts, and window monitor
            lock_monitor = LockMonitor(
                device, 
                enabled=config_loader.lock_monitor_enabled, 
                current_layout=default_layout,
                all_layouts=all_layouts,
                window_monitor=window_monitor if config_loader.config.get('windows_rules') else None,
                lock_verification_delay=config_loader.lock_verification_delay
            )
            
            # Apply the default layout
            default_layout.apply()
            
            # Start window monitoring if rules were configured
            if config_loader.config.get('windows_rules'):
                window_monitor.start()
            
            # Start lock monitoring
            lock_monitor.start()

            # Keep lock monitor updated with current layout
            config_loader.set_layout_change_callback(lock_monitor.set_current_layout)
            
        except ConfigValidationError as e:
            logging.exception(f"Error applying configuration: {e}")
            device.close()
            sys.exit(1)
        except Exception as e:
            logging.exception(f"Error applying configuration: {e}")
            device.close()
            sys.exit(1)
        
        # Keep the program running to process key events
        logging.info("\nStreamDock is ready. Press Ctrl+C to exit.\n")
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            logging.info("\nShutting down...")
            if config_loader.config.get('windows_rules'):
                window_monitor.stop()
            lock_monitor.stop()
            device.close()

if __name__ == "__main__":
    main()
