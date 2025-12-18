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

from StreamDock.ConfigLoader import ConfigLoader, ConfigValidationError
from StreamDock.DeviceManager import DeviceManager
from StreamDock.LockMonitor import LockMonitor
from StreamDock.WindowMonitor import WindowMonitor


def parse_arguments():
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(description="StreamDock Linux Driver")
    parser.add_argument(
        "config", nargs="?", default=None, help="Path to configuration file"
    )
    parser.add_argument(
        "--no-device",
        action="store_true",
        help="Run without a physical device (debug mode)",
    )
    parser.add_argument(
        "--simulate-windows",
        action="store_true",
        help="Simulate window focus changes using a temporary file (for E2E testing)",
    )
    parser.add_argument(
        "-d", "--debug",
        action="store_true",
        help="Enable debug logging",
    )
    parser.add_argument(
        "--print-config",
        action="store_true",
        help="Print the configuration and exit",
    )
    return parser.parse_args()


def main():
    """Main application entry point."""
    args = parse_arguments()


    logging.basicConfig(
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        level=logging.DEBUG if args.debug else logging.INFO)
    logger = logging.getLogger(__name__)

    # Determine config file path
    if args.config:
        config_file = args.config
    else:
        # Use config.yml in the project root directory
        script_dir = os.path.dirname(os.path.abspath(__file__))
        # Go up one level from src/ to project root
        project_root = os.path.dirname(script_dir)
        config_file = os.path.join(project_root, "config.yml")

    # Load configuration
    try:
        config_loader = ConfigLoader(config_file)
        config_loader.load()
    except FileNotFoundError as e:
        logger.error(f"{e}")
        sys.exit(1)
    except ConfigValidationError as e:
        logger.error(f"Configuration Error: {e}")
        sys.exit(1)
    except Exception as e:
        logger.exception(f"Unexpected error loading configuration: {e}")
        sys.exit(1)
    
    logger.info("Application started")
    logger.debug(f"Configuration loaded from: {config_file}")
    logger.debug(f"Root logger log level set to: {logging.getLevelName(logging.getLogger().level)}")
    logger.debug(f"Main logger log level set to: {logging.getLevelName(logger.level)}")

    streamdocks = []

    if args.no_device:
        logger.info("Running in NO-DEVICE mode")
        from StreamDock.Devices.DummyStreamDock import DummyStreamDock

        # Create a dummy device
        dummy_device = DummyStreamDock()
        streamdocks.append(dummy_device)
        # Device manager is not used in no-device mode for listening
    else:
        # Initialize device manager
        logger.debug("Initializing DeviceManager")
        deviceManager = DeviceManager()
        streamdocks = deviceManager.enumerate()

        # Start listening thread
        logger.debug("Starting device listener thread")
        t = threading.Thread(target=deviceManager.listen)
        t.daemon = True
        t.start()

        if len(streamdocks) == 0:
            logger.error("No Stream Dock devices found. Please connect a device and try again.")
            sys.exit(1)

    for device in streamdocks:
        logger.info(f"Opening device: {device.id()}")
        device.open()
        device.init()

        # device.set_touchscreen_image("/home/zrubi/Development_Private/StreamDock/img/zrubi_logo.jpg")

        # Initialize window monitor
        logger.debug("Initializing WindowMonitor")
        window_monitor = WindowMonitor(poll_interval=0.5, simulation_mode=args.simulate_windows)

        # Apply configuration to device
        try:
            default_layout, all_layouts = config_loader.apply(device, window_monitor)
            logger.debug(f"Device configuration applied. Default layout: {default_layout}")

            # Initialize lock monitor (from config setting) with default layout, all layouts, and window monitor
            logger.debug("Initializing LockMonitor")
            lock_monitor = LockMonitor(
                device,
                enabled=config_loader.lock_monitor_enabled,
                current_layout=default_layout,
                all_layouts=all_layouts,
                window_monitor=(
                    window_monitor
                    if config_loader.config.get("windows_rules")
                    else None
                ),
            )

            # Apply the default layout
            default_layout.apply()

            # Start window monitoring if rules were configured
            if config_loader.config.get("windows_rules"):
                logger.info("Starting WindowMonitor")
                window_monitor.start()

            # Start lock monitoring
            logger.info("Starting LockMonitor")
            lock_monitor.start()

        except ConfigValidationError as e:
            logger.error(f"Error applying configuration: {e}")
            device.close()
            sys.exit(1)
        except Exception as e:
            logger.exception("Error applying configuration")
            device.close()
            sys.exit(1)

        # Keep the program running to process key events
        logger.info("StreamDock is ready. Press Ctrl+C to exit.")
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            logger.info("Shutting down...")
            if config_loader.config.get("windows_rules"):
                window_monitor.stop()
            lock_monitor.stop()
            device.close()


if __name__ == "__main__":
    main()
