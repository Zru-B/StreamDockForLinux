"""
Configuration loader for StreamDock.
Loads keys, layouts, and window rules from YAML configuration file.

Expected YAML structure:
streamdock:
  settings:
    brightness: 15                   # Device brightness (0-100), default: 50
    lock_monitor: true               # Enable lock detection, default: true  
    lock_verification_delay: 2.0     # Seconds to verify lock, default: 2.0
    double_press_interval: 0.3       # Double-press time window, default: 0.3
  keys:
    KeyName:
      icon: "./img/icon.png"
      on_press_actions:
        - "ACTION_TYPE": "parameter"
      on_release_actions:
        - "ACTION_TYPE": "parameter"
      on_double_press_actions:
        - "ACTION_TYPE": "parameter"
  layouts:
    LayoutName:
      Default: true  # optional, one layout must be default
      keys:
        - 1: "KeyName"
        - 2: "KeyName"
  windows_rules:
    RuleName:
      window_name: "pattern"
      layout: "LayoutName"
      match_field: "class"  # optional: class, title, raw
"""
import logging
import os

import yaml

from .actions import ActionType
from .key import Key
from .layout import Layout
from .Models import WindowInfo

VALID_ACTIONS = ['on_press_actions', 'on_release_actions', 'on_double_press_actions']


class ConfigValidationError(Exception):
    """Exception raised when configuration validation fails."""


class ConfigLoader:
    """Load and validate StreamDock configuration from YAML file."""
    
    def __init__(self, config_path):
        """
        Initialize the configuration loader.
        
        :param config_path: Path to the YAML configuration file
        """
        self.config_path = config_path
        self.config = None
        self.keys = {}  # name -> Key definition dict
        self.layouts = {}  # name -> Layout object
        self.window_rules = []
        self.default_layout = None
        self.brightness = None
        self.lock_monitor_enabled = True  # Default enabled
        self.lock_verification_delay = 2.0  # Default 2 seconds before confirming lock
        self.double_press_interval = 0.3  # Default 300ms
        self._temp_text_images = []  # Track temporary text image files
        self.active_layout = None
        self.layout_change_callback = None
        self.logger = logging.getLogger(__name__)
    
    def set_layout_change_callback(self, callback):
        """
        Set a callback to be called when the active layout changes.
        
        :param callback: Function taking (layout_object) as argument
        """
        self.layout_change_callback = callback
    
    def __del__(self):
        """Cleanup temporary text image files."""
        if hasattr(self, '_temp_text_images'):
            for temp_file in self._temp_text_images:
                try:
                    if os.path.exists(temp_file):
                        os.remove(temp_file)
                except:
                    pass
    
    def load(self):
        """
        Load and parse the YAML configuration file.
        
        :raises ConfigValidationError: If configuration is invalid
        :raises FileNotFoundError: If config file doesn't exist
        """
        if not os.path.exists(self.config_path):
            raise FileNotFoundError(f"Configuration file not found: {self.config_path}")
        
        with open(self.config_path, 'r') as f:
            self.config = yaml.safe_load(f)
        
        if not self.config:
            raise ConfigValidationError("Configuration file is empty")
        
        if 'streamdock' not in self.config:
            raise ConfigValidationError("Configuration must contain 'streamdock' root element")
        
        self.config = self.config['streamdock']
        
        # Validate configuration structure
        self._validate_config()
    
    def _validate_config(self):
        """
        Validate the configuration structure and content.
        
        :raises ConfigValidationError: If validation fails
        """
        # Check required sections
        if 'keys' not in self.config:
            raise ConfigValidationError("Configuration must contain 'keys' section")
        
        if 'layouts' not in self.config:
            raise ConfigValidationError("Configuration must contain 'layouts' section")
        
        # Validate settings (optional)
        if 'settings' in self.config:
            self._validate_settings()
        
        # Validate keys section
        self._validate_keys()
        
        # Validate layouts section
        self._validate_layouts()
        
        # Validate window_rules section (optional)
        if 'windows_rules' in self.config:
            self._validate_window_rules()
    
    def _validate_settings(self):
        """Validate settings section."""
        settings = self.config['settings']
        
        if not isinstance(settings, dict):
            raise ConfigValidationError("'settings' must be a dictionary")
        
        if 'brightness' in settings:
            brightness = settings['brightness']
            if not isinstance(brightness, (int, float)) or brightness < 0 or brightness > 100:
                raise ConfigValidationError("brightness must be a number between 0 and 100")
            self.brightness = int(brightness)
        
        if 'lock_monitor' in settings:
            lock_monitor = settings['lock_monitor']
            if not isinstance(lock_monitor, bool):
                raise ConfigValidationError("lock_monitor must be true or false")
            self.lock_monitor_enabled = lock_monitor
        else:
            self.lock_monitor_enabled = True  # Enabled by default
        
        if 'lock_verification_delay' in settings:
            delay = settings['lock_verification_delay']
            if not isinstance(delay, (int, float)) or delay < 0.1 or delay > 30.0:
                raise ConfigValidationError(
                    "lock_verification_delay must be a number between 0.1 and 30.0 (seconds)"
                )
            self.lock_verification_delay = float(delay)
        
        if 'double_press_interval' in settings:
            interval = settings['double_press_interval']
            if not isinstance(interval, (int, float)) or interval <= 0 or interval > 2.0:
                raise ConfigValidationError("double_press_interval must be a number between 0 and 2.0 (seconds)")
            self.double_press_interval = float(interval)
    
    def _validate_keys(self):
        """Validate keys section of configuration."""
        keys_config = self.config['keys']
        
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
                raise ConfigValidationError(f"Key '{key_name}' must have either 'icon' or 'text' field")
            
            if has_icon and has_text:
                raise ConfigValidationError(f"Key '{key_name}' cannot have both 'icon' and 'text' fields")
            
            # Validate icon path exists if using icon
            if has_icon:
                icon_path = key_def['icon']
                
                if icon_path is None:
                    raise ConfigValidationError(f"Icon path for key '{key_name}' cannot be empty")
                
                if not isinstance(icon_path, str):
                    raise ConfigValidationError(f"Icon path for key '{key_name}' must be a string")
                
                # Expand environment variables and user path (~)
                icon_path = os.path.expanduser(os.path.expandvars(icon_path.strip()))
                
                # If path is relative, make it relative to the config file directory
                if not os.path.isabs(icon_path):
                    config_dir = os.path.dirname(os.path.abspath(self.config_path))
                    icon_path = os.path.abspath(os.path.join(config_dir, icon_path))
                
                # Update the config with expanded path
                key_def['icon'] = icon_path
                
                if not os.path.exists(icon_path):
                    raise ConfigValidationError(f"Icon file not found for key '{key_name}': {icon_path}")
                if not os.path.isfile(icon_path):
                    raise ConfigValidationError(f"Icon file for key '{key_name}' must be a file")
                if not icon_path.lower().endswith(('.png', '.jpg', '.jpeg', '.gif', '.svg', '.bmp')):
                    raise ConfigValidationError(f"Icon file for key '{key_name}' must be an image file")
                if not os.access(icon_path, os.R_OK):
                    raise ConfigValidationError(f"Icon file for key '{key_name}' must be readable")
            
            # Validate text field if using text
            if has_text:
                if not isinstance(key_def['text'], str):
                    raise ConfigValidationError(f"Key '{key_name}' text field must be a string")
                if not key_def['text'].strip():
                    raise ConfigValidationError(f"Key '{key_name}' text field cannot be empty")

            # Validate unsupported actions
            # Check for any key starting with 'on_' that is not in VALID_ACTIONS
            for key in key_def:
                if (key.startswith('on_') or key == 'actions') and key not in VALID_ACTIONS:
                    valid_actions_str = ", ".join(f"'{a}'" for a in VALID_ACTIONS)
                    raise ConfigValidationError(
                        f"Action '{key}' for key '{key_name}' is not supported. Use any of {valid_actions_str} instead."
                    )
            
            if not any(action_key in key_def for action_key in VALID_ACTIONS):
                raise ConfigValidationError(f"Key '{key_name}' must have at least one action")
            for action_key in VALID_ACTIONS:
                if action_key in key_def:
                    self._validate_actions(key_def[action_key], f"Key '{key_name}' {action_key}")
    
    def _validate_actions(self, actions, context):
        """Validate action definitions."""
        if not isinstance(actions, list):
            raise ConfigValidationError(f"{context}: actions must be a list")
        
        for i, action in enumerate(actions):
            if not isinstance(action, (dict, str)):
                raise ConfigValidationError(f"{context}[{i}]: action must be a dictionary or string")
            
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
    
    def _validate_layouts(self):
        """Validate layouts section of configuration."""
        layouts_config = self.config['layouts']
        
        if not isinstance(layouts_config, dict):
            raise ConfigValidationError("'layouts' must be a dictionary")
        
        if not layouts_config:
            raise ConfigValidationError("'layouts' dictionary cannot be empty")
        
        default_count = 0
        
        for layout_name, layout_def in layouts_config.items():
            if not isinstance(layout_def, dict):
                raise ConfigValidationError(f"Layout '{layout_name}' definition must be a dictionary")
            
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
                if key_name is not None and key_name not in self.config['keys']:
                    raise ConfigValidationError(
                        f"Layout '{layout_name}' references undefined key: '{key_name}'"
                    )
        
        # Ensure at least one default layout exists
        if default_count == 0:
            raise ConfigValidationError("At least one layout must have 'Default: true'")
    
    def _validate_window_rules(self):
        """Validate window_rules section of configuration."""
        rules_config = self.config['windows_rules']
        
        if not isinstance(rules_config, dict):
            raise ConfigValidationError("'windows_rules' must be a dictionary")
        
        for rule_name, rule_def in rules_config.items():
            if not isinstance(rule_def, dict):
                raise ConfigValidationError(f"Window rule '{rule_name}' definition must be a dictionary")
            
            # Check required fields
            if 'window_name' not in rule_def:
                raise ConfigValidationError(f"Window rule '{rule_name}' is missing 'window_name' field")
            
            # Validate window_name type
            window_name = rule_def['window_name']
            if not isinstance(window_name, (str, list)):
                raise ConfigValidationError(f"Window rule '{rule_name}': 'window_name' must be a string or a list of strings")
            
            if isinstance(window_name, list):
                if not window_name:
                    raise ConfigValidationError(f"Window rule '{rule_name}': 'window_name' list cannot be empty")
                if not all(isinstance(item, str) for item in window_name): 
                    raise ConfigValidationError(f"Window rule '{rule_name}': 'window_name' list must contain only strings")
            
            if 'layout' not in rule_def:
                raise ConfigValidationError(f"Window rule '{rule_name}' is missing 'layout' field")
            
            # Check if referenced layout exists
            layout_name = rule_def['layout']
            if layout_name not in self.config['layouts']:
                raise ConfigValidationError(
                    f"Window rule '{rule_name}' references undefined layout: '{layout_name}'"
                )
            
            if 'is_regex' in rule_def:
                if not isinstance(rule_def['is_regex'], bool):
                    raise ConfigValidationError(f"Window rule '{rule_name}': 'is_regex' must be a boolean")
            
            # Validate match_field (optional)
            if 'match_field' in rule_def:
                valid_fields = ['class', 'title', 'raw']
                if rule_def['match_field'] not in valid_fields:
                    raise ConfigValidationError(
                        f"Window rule '{rule_name}': invalid match_field '{rule_def['match_field']}'. "
                        f"Valid values: {', '.join(valid_fields)}"
                    )
    
    def _parse_actions(self, actions_config):
        """
        Parse action definitions from config into action tuples.
        
        :param actions_config: List of action dictionaries or strings
        :return: List of action tuples (ActionType, parameter)
        """
        actions = []
        
        for action_item in actions_config:
            if isinstance(action_item, dict):
                # Format: {"ACTION_TYPE": "parameter"}
                action_type_str = list(action_item.keys())[0]
                parameter = list(action_item.values())[0]
                
                action_type = ActionType[action_type_str.upper()]
                
                # Handle special parameter types
                if action_type == ActionType.CHANGE_LAYOUT:
                    # Layout reference will be resolved later
                    # Support both string and dict format
                    if isinstance(parameter, str):
                        # Simple format: just layout name
                        parameter = {"layout": parameter, "clear_all": False}
                    elif isinstance(parameter, dict):
                        # Dict format with options
                        if "layout" not in parameter:
                            raise ConfigValidationError(
                                f"CHANGE_LAYOUT action must have 'layout' parameter"
                            )
                        # Ensure clear_all has default
                        if "clear_all" not in parameter:
                            parameter["clear_all"] = False
                    else:
                        raise ConfigValidationError(
                            f"CHANGE_LAYOUT parameter must be string or dict, got {type(parameter)}"
                        )
                elif action_type in (ActionType.DEVICE_BRIGHTNESS_UP, ActionType.DEVICE_BRIGHTNESS_DOWN):
                    # Brightness actions don't need parameters, use None
                    parameter = None
                
                actions.append((action_type, parameter))
            elif isinstance(action_item, str):
                # Simple string format for certain actions
                # This is a fallback, main format should be dict
                pass
        
        return actions

    def switch_to_layout(self, layout, window_info: WindowInfo = None):
        """
        Switch to a new layout if it's not already active.
        
        :param layout: Layout object to switch to
        :param window_info: Optional dictionary with window information for logging
        """
        window_desc = f"{window_info.class_name}" if window_info and window_info.class_name else "manual/unknown"
        if window_desc.startswith('org.kde.'):
            window_desc = window_desc.replace('org.kde.', '')
        
        if self.active_layout == layout:
            self.logger.debug(f"Active window: {window_desc} | Layout '{layout.name}' is already active, skipping reload")
            return
        
        self.logger.info(f"Active window: {window_desc} | Switching to layout: '{layout.name}'")
        self.active_layout = layout
        layout.apply()
        
        if self.layout_change_callback:
            try:
                self.layout_change_callback(layout)
            except Exception:
                self.logger.exception("Error in layout change callback")

    def apply(self, device, window_monitor=None):
        """
        Apply the configuration to the device.
        
        :param device: StreamDock device instance
        :param window_monitor: Optional WindowMonitor instance for window rules
        :return: Tuple of (default_layout, all_layouts_dict)
        """
        if not self.config:
            raise ConfigValidationError("Configuration not loaded. Call load() first.")
        
        # Set brightness
        if self.brightness is not None:
            device.set_brightness(self.brightness)
            # Store brightness value on device for relative adjustments
            device._current_brightness = self.brightness
        else:
            # Default brightness if not specified
            device._current_brightness = 50
        
        # Set double-press interval
        device.double_press_interval = self.double_press_interval
        
        # Create key definitions (without numbers yet)
        self._create_keys(device)
        self.logger.info(f"Loaded {len(self.keys)} key definitions")
        
        # Create layouts
        self._create_layouts(device)
        self.logger.info(f"Loaded {len(self.layouts)} layouts")
        
        # Resolve CHANGE_LAYOUT action references
        self._resolve_layout_references()
        
        # Apply window rules
        if window_monitor and 'windows_rules' in self.config:
            self._apply_window_rules(window_monitor)
        
        # Initialize active layout state
        if self.default_layout:
            self.active_layout = self.default_layout

        return self.default_layout, self.layouts
    
    def _create_keys(self, device):
        """Create Key definitions from configuration."""
        import tempfile

        from .image_helpers.pil_helper import create_text_image
        
        keys_config = self.config['keys']
        
        for key_name, key_def in keys_config.items():
            # Handle icon or text
            if 'icon' in key_def:
                icon = key_def['icon']
            elif 'text' in key_def:
                # Create image from text
                text = key_def['text']
                text_color = key_def.get('text_color', 'white')
                background_color = key_def.get('background_color', 'black')
                font_size = key_def.get('font_size', 20)
                bold = key_def.get('bold', True)
                
                # Create text image
                text_image = create_text_image(
                    text=text,
                    size=(112, 112),
                    text_color=text_color,
                    background_color=background_color,
                    font_size=font_size,
                    bold=bold
                )
                
                # Save to temporary file
                temp_fd, temp_path = tempfile.mkstemp(suffix='.png', prefix=f'text_key_{key_name}_')
                os.close(temp_fd)
                text_image.save(temp_path)
                
                icon = temp_path
                
                # Store temp file path for cleanup
                if not hasattr(self, '_temp_text_images'):
                    self._temp_text_images = []
                self._temp_text_images.append(temp_path)
            
            # Parse actions
            on_press = None
            on_release = None
            on_double_press = None
            
            if 'on_press_actions' in key_def:
                on_press = self._parse_actions(key_def['on_press_actions'])
            
            if 'on_release_actions' in key_def:
                on_release = self._parse_actions(key_def['on_release_actions'])
            
            if 'on_double_press_actions' in key_def:
                on_double_press = self._parse_actions(key_def['on_double_press_actions'])
            
            # Store key definition (will get number when added to layout)
            self.keys[key_name] = {
                'device': device,
                'image': icon,
                'on_press': on_press,
                'on_release': on_release,
                'on_double_press': on_double_press
            }
    
    def _create_layouts(self, device):
        """Create Layout objects from configuration."""
        layouts_config = self.config['layouts']
        
        for layout_name, layout_def in layouts_config.items():
            is_default = layout_def.get('Default', False)
            clear_all = layout_def.get('clear_all', False)
            
            # Create Key instances with numbers for this layout
            layout_keys = []
            clear_keys = []
            
            for key_ref in layout_def['keys']:
                # Format: {number: "key_name"} or {number: None}
                key_number = list(key_ref.keys())[0]
                key_name = list(key_ref.values())[0]
                
                # Handle None values (empty keys)
                if key_name is None:
                    clear_keys.append(key_number)
                    continue
                
                # Get key definition
                key_def = self.keys[key_name]
                
                # Create Key instance with number
                key_instance = Key(
                    device=key_def['device'],
                    key_number=key_number,
                    image_path=key_def['image'],
                    on_press=key_def['on_press'],
                    on_release=key_def['on_release'],
                    on_double_press=key_def['on_double_press']
                )
                
                layout_keys.append(key_instance)
            
            # Create Layout with clear_keys list and clear_all option
            layout = Layout(device, layout_keys, clear_keys=clear_keys, clear_all=clear_all, name=layout_name)
            self.layouts[layout_name] = layout
            
            if is_default:
                self.default_layout = layout
    
    def _resolve_layout_references(self):
        """Resolve CHANGE_LAYOUT action references to actual Layout objects."""
        for key_name, key_def in self.keys.items():
            for action_list_name in ['on_press', 'on_release', 'on_double_press']:
                actions = key_def.get(action_list_name)
                if not actions:
                    continue
                
                for i, (action_type, parameter) in enumerate(actions):
                    if action_type == ActionType.CHANGE_LAYOUT:
                        # Parameter is now a dict with layout name and options
                        layout_name = parameter["layout"]
                        clear_all = parameter["clear_all"]
                        
                        if layout_name not in self.layouts:
                            raise ConfigValidationError(
                                f"Key '{key_name}' {action_list_name}: "
                                f"references undefined layout '{layout_name}'"
                            )
                        
                        # Replace with dict containing Layout object and options
                        actions[i] = (action_type, {
                            "layout": self.layouts[layout_name],
                            "clear_all": clear_all
                        })
                        
                    elif action_type == ActionType.CHANGE_KEY:
                        # Resolve key reference if parameter is a string that matches a known key
                        if isinstance(parameter, str) and parameter in self.keys:
                            ref_key_def = self.keys[parameter]
                            
                            # Construct the config dict expected by actions.py (Case 3)
                            # Note: We use the pre-parsed values from self.keys
                            replacement_param = {
                                'image': ref_key_def['image'],
                                'on_press': ref_key_def['on_press'],
                                'on_release': ref_key_def['on_release'],
                                'on_double_press': ref_key_def['on_double_press']
                            }
                            
                            # Update the action tuple in place
                            actions[i] = (action_type, replacement_param)
    
    def _apply_window_rules(self, window_monitor):
        """Apply window rules to window monitor."""
        rules_config = self.config['windows_rules']
        
        for rule_name, rule_def in rules_config.items():
            pattern_def = rule_def['window_name']
            layout_name = rule_def['layout']
            match_field = rule_def.get('match_field', 'class')
            is_regex = rule_def.get('is_regex', False)
            
            layout = self.layouts[layout_name]
            
            # Handle regex compilation
            final_pattern = pattern_def
            if is_regex:
                try:
                    import re
                    if isinstance(pattern_def, list):
                        final_pattern = [re.compile(p, re.IGNORECASE) for p in pattern_def]
                    else:
                        final_pattern = re.compile(pattern_def, re.IGNORECASE)
                except re.error as e:
                    self.logger.error(f"Invalid regex in rule '{rule_name}': {e}")
                    continue  # Skip invalid rule
            
            # Add rule to window monitor 
            window_monitor.add_window_rule(
                final_pattern,
                lambda win_info, layout=layout: self.switch_to_layout(layout, window_info=win_info),
                match_field=match_field,
                is_regex=is_regex
            )
        
        # Set default callback
        if self.default_layout:
            window_monitor.set_default_callback(
                lambda win_info: self.switch_to_layout(self.default_layout, window_info=win_info)
            )
