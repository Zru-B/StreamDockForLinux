"""
Configuration management for StreamDock.

This module provides pure configuration parsing and validation logic,
extracted from ConfigLoader to be infrastructure-independent.
"""

import logging
import os
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import yaml

from StreamDock.business_logic.action_type import ActionType

logger = logging.getLogger(__name__)


class ConfigValidationError(Exception):
    """Exception raised when configuration validation fails."""
    pass


@dataclass
class StreamDockConfig:
    """
    Parsed StreamDock configuration.

    Pure data structure - no business logic, no infrastructure dependencies.

    Attributes:
        brightness: Device brightness (0-100)
        default_layout_name: Name of default layout
        lock_monitor_enabled: Whether lock monitoring is enabled
        lock_verification_delay: Seconds to verify lock state
        double_press_interval: Time window for double-press detection
        keys_config: Raw key definitions from YAML
        layouts_config: Raw layout definitions from YAML
        window_rules_config: Raw window rule definitions from YAML
        raw_config: Complete raw configuration for debugging/extension
    """
    brightness: int = 50
    default_layout_name: str = "default"
    lock_monitor_enabled: bool = True
    lock_verification_delay: float = 2.0
    double_press_interval: float = 0.3
    keys_config: Dict[str, Dict] = field(default_factory=dict)
    layouts_config: Dict[str, Dict] = field(default_factory=dict)
    window_rules_config: Dict[str, Dict] = field(default_factory=dict)
    raw_config: Dict[str, Any] = field(default_factory=dict)


VALID_ACTIONS = ['on_press_actions', 'on_release_actions', 'on_double_press_actions']


class ConfigurationManager:
    """
    Pure configuration management - parsing and validation only.

    Responsibilities:
    - Load YAML file
    - Validate configuration structure
    - Parse into StreamDockConfig dataclass
    - Path expansion for icon files

    NOT Responsible For:
    - Object creation (Keys/Layouts) - Phase 5
    - Device operations - Orchestration layer
    - Window monitoring - Infrastructure layer

    Design:
    - Pure parsing approach
    - Returns data structures, not objects
    - Zero infrastructure dependencies
    - Zero orchestration dependencies
    """

    def __init__(self, config_path: str):
        """
        Initialize configuration manager.

        Args:
            config_path: Path to YAML configuration file
        """
        self._config_path = config_path
        self._raw_config: Optional[Dict] = None

    def load(self) -> StreamDockConfig:
        """
        Load and validate configuration file.

        Returns:
            StreamDockConfig with validated data

        Raises:
            ConfigValidationError: If validation fails
            FileNotFoundError: If file doesn't exist
        """
        # Load YAML
        self._load_yaml()

        # Validate structure
        self._validate_config()

        # Parse into dataclass
        return self._parse_config()

    def _load_yaml(self) -> None:
        """
        Load YAML file into self._raw_config.

        Raises:
            FileNotFoundError: If config file doesn't exist
            ConfigValidationError: If YAML is invalid
        """
        if not os.path.exists(self._config_path):
            raise FileNotFoundError(f"Configuration file not found: {self._config_path}")

        with open(self._config_path, 'r') as f:
            config = yaml.safe_load(f)

        if not config:
            raise ConfigValidationError("Configuration file is empty")

        if 'streamdock' not in config:
            raise ConfigValidationError("Configuration must contain 'streamdock' root element")

        self._raw_config = config['streamdock']

    def _validate_config(self) -> None:
        """
        Validate the configuration structure and content.

        Raises:
            ConfigValidationError: If validation fails
        """
        # Check required sections
        if 'keys' not in self._raw_config:
            raise ConfigValidationError("Configuration must contain 'keys' section")

        if 'layouts' not in self._raw_config:
            raise ConfigValidationError("Configuration must contain 'layouts' section")

        # Validate settings (optional)
        if 'settings' in self._raw_config:
            self._validate_settings()

        # Validate keys section
        self._validate_keys()

        # Validate layouts section
        self._validate_layouts()

        # Validate window_rules section (optional)
        if 'windows_rules' in self._raw_config:
            self._validate_window_rules()

    def _validate_settings(self) -> None:
        """
        Validate settings section.

        Raises:
            ConfigValidationError: If settings are invalid
        """
        settings = self._raw_config['settings']

        if not isinstance(settings, dict):
            raise ConfigValidationError("'settings' must be a dictionary")

        # Validate brightness
        if 'brightness' in settings:
            brightness = settings['brightness']
            if not isinstance(brightness, (int, float)) or brightness < 0 or brightness > 100:
                raise ConfigValidationError("brightness must be a number between 0 and 100")

        # Validate lock_monitor
        if 'lock_monitor' in settings:
            lock_monitor = settings['lock_monitor']
            if not isinstance(lock_monitor, bool):
                raise ConfigValidationError("lock_monitor must be true or false")

        # Validate lock_verification_delay
        if 'lock_verification_delay' in settings:
            delay = settings['lock_verification_delay']
            if not isinstance(delay, (int, float)) or delay < 0.1 or delay > 30.0:
                raise ConfigValidationError(
                    "lock_verification_delay must be a number between 0.1 and 30.0 (seconds)"
                )

        # Validate double_press_interval
        if 'double_press_interval' in settings:
            interval = settings['double_press_interval']
            if not isinstance(interval, (int, float)) or interval <= 0 or interval > 2.0:
                raise ConfigValidationError(
                    "double_press_interval must be a number between 0 and 2.0 (seconds)"
                )

    def _validate_keys(self) -> None:
        """
        Validate keys section of configuration.

        Raises:
            ConfigValidationError: If keys are invalid
        """
        keys_config = self._raw_config['keys']

        if not isinstance(keys_config, dict):
            raise ConfigValidationError("'keys' must be a dictionary")

        if not keys_config:
            raise ConfigValidationError("'keys' dictionary cannot be empty")

        for key_name, key_def in keys_config.items():
            if not isinstance(key_def, dict):
                raise ConfigValidationError(f"Key '{key_name}' definition must be a dictionary")

            # Check required fields - either 'icon' or 'text'
            has_icon = 'icon' in key_def
            has_text = 'text' in key_def

            if not has_icon and not has_text:
                raise ConfigValidationError(
                    f"Key '{key_name}' must have either 'icon' or 'text' field"
                )

            if has_icon and has_text:
                raise ConfigValidationError(
                    f"Key '{key_name}' cannot have both 'icon' and 'text' fields"
                )

            # Validate and expand icon path
            if has_icon:
                self._validate_and_expand_icon_path(key_name, key_def)

            # Validate text field
            if has_text:
                if not isinstance(key_def['text'], str):
                    raise ConfigValidationError(f"Key '{key_name}' text field must be a string")
                if not key_def['text'].strip():
                    raise ConfigValidationError(f"Key '{key_name}' text field cannot be empty")

            # Validate unsupported actions
            for key in key_def:
                if (key.startswith('on_') or key == 'actions') and key not in VALID_ACTIONS:
                    valid_actions_str = ", ".join(f"'{a}'" for a in VALID_ACTIONS)
                    raise ConfigValidationError(
                        f"Action '{key}' for key '{key_name}' is not supported. "
                        f"Use any of {valid_actions_str} instead."
                    )

            # Validate at least one action exists
            if not any(action_key in key_def for action_key in VALID_ACTIONS):
                raise ConfigValidationError(f"Key '{key_name}' must have at least one action")

            # Validate each action list
            for action_key in VALID_ACTIONS:
                if action_key in key_def:
                    self._validate_actions(key_def[action_key], f"Key '{key_name}' {action_key}")

    def _validate_and_expand_icon_path(self, key_name: str, key_def: Dict) -> None:
        """
        Validate icon path and expand it to absolute path.

        Args:
            key_name: Name of the key being validated
            key_def: Key definition dictionary (modified in place)

        Raises:
            ConfigValidationError: If icon path is invalid
        """
        icon_path = key_def['icon']

        if icon_path is None:
            raise ConfigValidationError(f"Icon path for key '{key_name}' cannot be empty")

        if not isinstance(icon_path, str):
            raise ConfigValidationError(f"Icon path for key '{key_name}' must be a string")

        # Expand environment variables and user path (~)
        icon_path = os.path.expanduser(os.path.expandvars(icon_path.strip()))

        # If path is relative, make it relative to the config file directory
        if not os.path.isabs(icon_path):
            config_dir = os.path.dirname(os.path.abspath(self._config_path))
            icon_path = os.path.abspath(os.path.join(config_dir, icon_path))

        # Update the config with expanded path
        key_def['icon'] = icon_path

        # Validate file exists and is readable
        if not os.path.exists(icon_path):
            raise ConfigValidationError(f"Icon file not found for key '{key_name}': {icon_path}")
        if not os.path.isfile(icon_path):
            raise ConfigValidationError(f"Icon file for key '{key_name}' must be a file")
        if not icon_path.lower().endswith(('.png', '.jpg', '.jpeg', '.gif', '.svg', '.bmp')):
            raise ConfigValidationError(f"Icon file for key '{key_name}' must be an image file")
        if not os.access(icon_path, os.R_OK):
            raise ConfigValidationError(f"Icon file for key '{key_name}' must be readable")

    def _validate_actions(self, actions: List, context: str) -> None:
        """
        Validate action definitions.

        Args:
            actions: List of action definitions
            context: Context string for error messages

        Raises:
            ConfigValidationError: If actions are invalid
        """
        if not isinstance(actions, list):
            raise ConfigValidationError(f"{context}: actions must be a list")

        for i, action in enumerate(actions):
            if not isinstance(action, (dict, str)):
                raise ConfigValidationError(
                    f"{context}[{i}]: action must be a dictionary or string"
                )

            if isinstance(action, dict):
                # Get the action type (the key in the dict)
                if len(action) != 1:
                    raise ConfigValidationError(
                        f"{context}[{i}]: action dict must have exactly one key-value pair"
                    )

                action_type_str = list(action.keys())[0]

                # Validate action type exists
                try:
                    ActionType[action_type_str.upper()]
                except KeyError:
                    valid_types = ', '.join([t.name for t in ActionType])
                    raise ConfigValidationError(
                        f"{context}[{i}]: invalid action type '{action_type_str}'. "
                        f"Valid types: {valid_types}"
                    )

    def _validate_layouts(self) -> None:
        """
        Validate layouts section of configuration.

        Raises:
            ConfigValidationError: If layouts are invalid
        """
        layouts_config = self._raw_config['layouts']

        if not isinstance(layouts_config, dict):
            raise ConfigValidationError("'layouts' must be a dictionary")

        if not layouts_config:
            raise ConfigValidationError("'layouts' dictionary cannot be empty")

        default_count = 0

        for layout_name, layout_def in layouts_config.items():
            if not isinstance(layout_def, dict):
                raise ConfigValidationError(
                    f"Layout '{layout_name}' definition must be a dictionary"
                )

            # Check required fields
            if 'keys' not in layout_def:
                raise ConfigValidationError(f"Layout '{layout_name}' is missing 'keys' field")

            # Check default flag
            if layout_def.get('Default', False):
                default_count += 1
                if default_count > 1:
                    raise ConfigValidationError("Only one layout can have 'Default: true'")

            # Validate keys list
            if not isinstance(layout_def['keys'], list):
                raise ConfigValidationError(f"Layout '{layout_name}' keys must be a list")

            if not layout_def['keys']:
                raise ConfigValidationError(f"Layout '{layout_name}' keys list cannot be empty")

            # Validate each key reference
            key_numbers = set()
            for j, key_ref in enumerate(layout_def['keys']):
                if not isinstance(key_ref, dict):
                    raise ConfigValidationError(
                        f"Layout '{layout_name}' key at index {j} must be a dictionary"
                    )

                # Key ref format: {number: "key_name"} or {number: None}
                if len(key_ref) != 1:
                    raise ConfigValidationError(
                        f"Layout '{layout_name}' key at index {j} must have exactly one key-value pair"
                    )

                key_number = list(key_ref.keys())[0]
                key_name = list(key_ref.values())[0]

                # Validate key number
                if not isinstance(key_number, int) or key_number < 1 or key_number > 15:
                    raise ConfigValidationError(
                        f"Layout '{layout_name}': invalid key number {key_number}. "
                        f"Must be between 1 and 15"
                    )

                # Check for duplicate key numbers in layout
                if key_number in key_numbers:
                    raise ConfigValidationError(
                        f"Layout '{layout_name}': duplicate key number {key_number}"
                    )

                key_numbers.add(key_number)

                # Check if referenced key exists (None is allowed for empty keys)
                if key_name is not None and key_name not in self._raw_config['keys']:
                    raise ConfigValidationError(
                        f"Layout '{layout_name}' references undefined key: '{key_name}'"
                    )

        # Ensure at least one default layout exists
        if default_count == 0:
            raise ConfigValidationError("At least one layout must have 'Default: true'")

    def _validate_window_rules(self) -> None:
        """
        Validate window_rules section of configuration.

        Raises:
            ConfigValidationError: If window rules are invalid
        """
        rules_config = self._raw_config['windows_rules']

        if not isinstance(rules_config, dict):
            raise ConfigValidationError("'windows_rules' must be a dictionary")

        for rule_name, rule_def in rules_config.items():
            if not isinstance(rule_def, dict):
                raise ConfigValidationError(
                    f"Window rule '{rule_name}' definition must be a dictionary"
                )

            # Check required fields
            if 'window_name' not in rule_def:
                raise ConfigValidationError(
                    f"Window rule '{rule_name}' is missing 'window_name' field"
                )

            # Validate window_name type
            window_name = rule_def['window_name']
            if not isinstance(window_name, (str, list)):
                raise ConfigValidationError(
                    f"Window rule '{rule_name}': 'window_name' must be a string or a list of strings"
                )

            if isinstance(window_name, list):
                if not window_name:
                    raise ConfigValidationError(
                        f"Window rule '{rule_name}': 'window_name' list cannot be empty"
                    )
                if not all(isinstance(item, str) for item in window_name):
                    raise ConfigValidationError(
                        f"Window rule '{rule_name}': 'window_name' list must contain only strings"
                    )

            if 'layout' not in rule_def:
                raise ConfigValidationError(f"Window rule '{rule_name}' is missing 'layout' field")

            # Check if referenced layout exists
            layout_name = rule_def['layout']
            if layout_name not in self._raw_config['layouts']:
                raise ConfigValidationError(
                    f"Window rule '{rule_name}' references undefined layout: '{layout_name}'"
                )

            # Validate is_regex (optional)
            if 'is_regex' in rule_def:
                if not isinstance(rule_def['is_regex'], bool):
                    raise ConfigValidationError(
                        f"Window rule '{rule_name}': 'is_regex' must be a boolean"
                    )

            # Validate match_field (optional)
            if 'match_field' in rule_def:
                valid_fields = ['class', 'title', 'raw']
                if rule_def['match_field'] not in valid_fields:
                    raise ConfigValidationError(
                        f"Window rule '{rule_name}': invalid match_field '{rule_def['match_field']}'. "
                        f"Valid values: {', '.join(valid_fields)}"
                    )

    def _parse_config(self) -> StreamDockConfig:
        """
        Parse raw config into StreamDockConfig dataclass.

        Returns:
            StreamDockConfig with validated data
        """
        # Extract settings
        settings = self._raw_config.get('settings', {})
        brightness = int(settings.get('brightness', 50))
        lock_monitor_enabled = settings.get('lock_monitor', True)
        lock_verification_delay = float(settings.get('lock_verification_delay', 2.0))
        double_press_interval = float(settings.get('double_press_interval', 0.3))

        # Find default layout
        default_layout_name = "default"
        for layout_name, layout_def in self._raw_config['layouts'].items():
            if layout_def.get('Default', False):
                default_layout_name = layout_name
                break

        return StreamDockConfig(
            brightness=brightness,
            default_layout_name=default_layout_name,
            lock_monitor_enabled=lock_monitor_enabled,
            lock_verification_delay=lock_verification_delay,
            double_press_interval=double_press_interval,
            keys_config=self._raw_config.get('keys', {}),
            layouts_config=self._raw_config.get('layouts', {}),
            window_rules_config=self._raw_config.get('windows_rules', {}),
            raw_config=self._raw_config
        )
