"""
Single entry point for StreamDock.

Opens the configuration GUI by default; --headless runs the device controller
with no Qt imported at all, for sessions without a display.
"""

import argparse
import logging
import os
import sys
import time
from typing import Optional

from StreamDock.dependency_check import DependencyChecker

logger = logging.getLogger(__name__)


def parse_args(argv=None) -> argparse.Namespace:
    """Parse the command line."""
    parser = argparse.ArgumentParser(
        prog="streamdock",
        description="Stream Dock controller and configuration editor")
    parser.add_argument('config', nargs='?',
                        help="Path to configuration file")
    parser.add_argument('--headless', action='store_true',
                        help="Run the controller without the GUI")
    parser.add_argument('--minimized', action='store_true',
                        help="Start the GUI hidden in the system tray")
    parser.add_argument('--device', default='',
                        help="Device to use, as reported in the device list")
    parser.add_argument('--check-deps', action='store_true',
                        help="Check dependencies and exit")
    parser.add_argument('--debug', action='store_true',
                        help="Enable debug logging")
    return parser.parse_args(argv)


def setup_logging(debug: bool = False) -> None:
    """Configure root logging."""
    logging.basicConfig(
        level=logging.DEBUG if debug else logging.INFO,
        format='%(asctime)s %(levelname)s:%(name)s:%(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    # PIL is extremely chatty at debug level.
    logging.getLogger('PIL.PngImagePlugin').setLevel(logging.INFO)


def check_dependencies(check_only: bool = False) -> None:
    """
    Report on dependencies, exiting if any critical one is missing.

    Args:
        check_only: Print the full report and exit 0
    """
    checker = DependencyChecker()

    if check_only:
        checker.print_report()
        sys.exit(0)

    checker.run_check()
    logging.info(checker.get_summary())

    if checker.has_critical_failures():
        logging.error("Critical dependencies missing. Full report:")
        checker.print_report()
        sys.exit(1)


def determine_config_path(explicit: Optional[str], *, required: bool) -> Optional[str]:
    """
    Resolve which configuration file to use.

    Args:
        explicit: Path given on the command line
        required: Exit with an error when nothing is found. The GUI passes
            False - it opens with an empty document instead.

    Returns:
        A path, or None when nothing was found and none is required
    """
    if explicit:
        return explicit

    candidates = ['config.yml',
                  os.path.join(os.path.dirname(os.path.abspath(__file__)),
                               os.pardir, 'config.yml')]
    for candidate in candidates:
        if os.path.exists(candidate):
            return os.path.abspath(candidate)

    if required:
        logging.error("config.yml not found in current directory or script directory")
        sys.exit(1)
    return None


def run_headless(config_path: str, device_id: str = "") -> int:
    """
    Run the device controller with no GUI.

    Args:
        config_path: Configuration to apply
        device_id: Device to open, or '' for the first discovered

    Returns:
        Process exit code
    """
    # Imported here so --headless never pulls in Qt.
    from StreamDock.application import Application
    from StreamDock.application.configuration_manager import ConfigValidationError
    from StreamDock.application.device_discovery import find_device
    from StreamDock.application.instance_lock import InstanceLock

    lock = InstanceLock()
    if not lock.acquire():
        pid = lock.owner_pid()
        logging.error("Another StreamDock instance%s already controls the device",
                      f" (pid {pid})" if pid else "")
        return 1

    try:
        device_info = find_device(device_id) if device_id else None
        if device_id and device_info is None:
            logging.error("Device not found: %s", device_id)
            return 1

        try:
            app = Application(config_path, device_info=device_info)
        except FileNotFoundError as e:
            logging.error("Configuration file not found: %s", e)
            return 1
        except ConfigValidationError as e:
            logging.error("Configuration validation error: %s", e)
            return 1

        logging.info("Starting StreamDock application...")
        try:
            if not app.start():
                logging.error("Failed to start application")
                return 1

            logging.info("✓ StreamDock is ready. Press Ctrl+C to exit.")
            try:
                while True:
                    time.sleep(1)
            except KeyboardInterrupt:
                logging.info("Shutting down...")
        except Exception as e:  # pylint: disable=broad-exception-caught
            logging.exception("Error during application runtime: %s", e)
            return 1
        finally:
            app.stop(force=True)
            logging.info("✓ Shutdown complete")

        return 0
    finally:
        lock.release()


def main(argv=None) -> int:
    """
    Application entry point.

    Returns:
        Process exit code
    """
    args = parse_args(argv)
    setup_logging(args.debug)
    check_dependencies(args.check_deps)

    if args.headless:
        config_path = determine_config_path(args.config, required=True)
        logging.info("Using configuration file: %s", config_path)
        return run_headless(config_path, args.device)

    config_path = determine_config_path(args.config, required=False)

    from StreamDock.ui.app import main as run_gui
    return run_gui(config_path=config_path, device_id=args.device,
                   start_minimized=args.minimized)


def main_gui(argv=None) -> int:
    """Entry point for the GUI launcher, which never runs headless."""
    args = [a for a in (argv if argv is not None else sys.argv[1:]) if a != '--headless']
    return main(args)


if __name__ == "__main__":
    sys.exit(main())
