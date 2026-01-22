#!/usr/bin/env python3
"""
StreamDock main application with new layered architecture.

This version uses the Application bootstrap with dependency injection.
"""
import argparse
import logging
import os
import sys
import time

from StreamDock.application import Application
from StreamDock.application.configuration_manager import ConfigValidationError
from StreamDock.dependency_check import DependencyChecker


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="StreamDock Linux Controller")
    parser.add_argument('config', nargs='?', help="Path to configuration file")
    parser.add_argument('--mock', '--headless', action='store_true', 
                       help="Run in mock/headless mode without physical device")
    parser.add_argument('--check-deps', action='store_true', 
                       help="Check dependencies and exit")
    parser.add_argument('--debug', action='store_true', 
                       help="Enable debug logging")
    return parser.parse_args()


def setup_logging(args):
    """Set up logging configuration."""
    log_level = logging.DEBUG if args.debug else logging.INFO
    
    logging.basicConfig(
        level=log_level,
        format='%(asctime)s %(levelname)s:%(name)s:%(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )


def check_dependencies(args):
    """Check and log dependency status."""
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


def determine_config_path(args) -> str:
    """Determine configuration file path."""
    if args.config:
        return args.config
    
    # Try config.yml in current directory
    config_file = 'config.yml'
    if os.path.exists(config_file):
        return config_file
    
    # Try config.yml in script directory
    script_dir = os.path.dirname(os.path.abspath(__file__))
    config_file = os.path.join(script_dir, 'config.yml')
    if os.path.exists(config_file):
        return config_file
    
    logging.error("config.yml not found in current directory or script directory")
    sys.exit(1)


def main():
    """Main application entry point."""
    # Parse arguments
    args = parse_args()
    
    # Set up logging
    setup_logging(args)
    
    # Check dependencies
    check_dependencies(args)
    
    # Determine config path
    config_file = determine_config_path(args)
    logging.info(f"Using configuration file: {config_file}")
    
    # Create application
    try:
        app = Application(config_file)
    except FileNotFoundError as e:
        logging.error(f"Configuration file not found: {e}")
        sys.exit(1)
    except ConfigValidationError as e:
        logging.error(f"Configuration validation error: {e}")
        sys.exit(1)
    except Exception as e:
        logging.exception(f"Unexpected error creating application: {e}")
        sys.exit(1)
    
    # Start application
    logging.info("Starting StreamDock application...")
    try:
        success = app.start()
        if not success:
            logging.error("Failed to start application")
            sys.exit(1)
        
        logging.info("\\n✓ StreamDock is ready. Press Ctrl+C to exit.\\n")
        
        # Keep the program running
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            logging.info("\\nShutting down...")
            app.stop()
            logging.info("✓ Shutdown complete")
    
    except Exception as e:
        logging.exception(f"Error during application runtime: {e}")
        app.stop()
        sys.exit(1)


if __name__ == "__main__":
    main()
