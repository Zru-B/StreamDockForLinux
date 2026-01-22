"""
Layout factory for creating Key and Layout objects from configuration.

This factory converts the parsed StreamDockConfig into actual runtime objects
that can be used by the application.
"""

import logging
from typing import Dict, List, Tuple, Any
from PIL import Image, ImageDraw, ImageFont

from StreamDock.key import Key  
from StreamDock.layout import Layout
from StreamDock.actions import ActionType

logger = logging.getLogger(__name__)


class LayoutFactory:
    """
    Factory for creating Key and Layout objects from configuration data.
    
    Converts StreamDockConfig (pure data) into runtime objects.
    """
    
    def __init__(self, config_data: Dict[str, Any], device):
        """
        Initialize factory with configuration data and device.
        
        Args:
            config_data: Parsed configuration dictionary
            device: Device instance to bind objects to
        """
        self._config = config_data
        self._device = device
        self._keys: Dict[str, Key] = {}
        self._temp_images: List[str] = []  # For cleanup
        
        logger.debug("LayoutFactory initialized")
    
    def create_layouts(self) -> Tuple[Layout, Dict[str, Layout]]:
        """
        Create all layouts from configuration.
        
        Returns:
            Tuple of (default_layout, all_layouts_dict)
        """
        # 1. Create keys first
        self._create_keys()
        
        # 2. Create layouts
        layouts = self._create_layouts_dict()
        
        # 3. Find default layout
        default_layout = self._find_default_layout(layouts)
        
        logger.info(f"Created {len(layouts)} layouts with {len(self._keys)} keys")
        
        return default_layout, layouts
    
    def _create_keys(self) -> None:
        """Create Key objects from configuration."""
        keys_config = self._config.get('keys', {})
        
        for key_name, key_data in keys_config.items():
            # Parse actions
            actions = self._parse_key_actions(key_data)
            
            # Get icon path - if not specified and text is provided, use empty string
            # The Key/Layout will need to handle text rendering
            icon_path = key_data.get('icon', '')
            
            # If no icon but has text, we'd need to generate an image with text
            # For now, log a warning
            if not icon_path and 'text' in key_data:
                logger.warning(f"Key '{key_name}' has text but no icon - text rendering not yet implemented")
                icon_path = ''  # Empty path - will cause error but Key still created
            
            # Key constructor: device, key_number, image_path, on_press, on_release
            # key_number will be set later when adding to layout
            key = Key(
                device=self._device,
                key_number=0,  # Will be set when added to layout
                image_path=icon_path,
                on_press=actions.get('on_press', []),
                on_release=actions.get('on_release', [])
            )
            
            # Store reference to key name and text for debugging
            key._factory_name = key_name
            if 'text' in key_data:
                key._factory_text = key_data['text']
            
            self._keys[key_name] = key
            logger.debug(f"Created key: {key_name} (icon={icon_path or 'none'})")
    
    def _create_layouts_dict(self) -> Dict[str, Layout]:
        """Create Layout objects from configuration."""
        layouts_config = self._config.get('layouts', {})
        layouts = {}
        
        for layout_name, layout_data in layouts_config.items():
            # Get key assignments
            keys_list_config = layout_data.get('keys', [])
            
            # Build list of keys for this layout
            keys_for_layout = []
            for key_entry in keys_list_config:
                for position_str, key_name in key_entry.items():
                    if key_name in self._keys:
                        # Convert position to int
                        position = int(position_str)
                        key = self._keys[key_name]
                        # Update key's position
                        key.key_number = position
                        keys_for_layout.append(key)
            
            # Create layout: Layout(device, keys, clear_keys, clear_all, name)
            layout = Layout(
                device=self._device,
                keys=keys_for_layout,
                name=layout_name
            )
            
            layouts[layout_name] = layout
            logger.debug(f"Created layout: {layout_name} with {len(keys_for_layout)} keys")
        
        return layouts
    
    def _find_default_layout(self, layouts: Dict[str, Layout]) -> Layout:
        """Find the default layout."""
        layouts_config = self._config.get('layouts', {})
        
        # Find layout marked as Default in config
        for layout_name, layout_data in layouts_config.items():
            if layout_data.get('Default', False) and layout_name in layouts:
                logger.debug(f"Default layout from config: {layout_name}")
                return layouts[layout_name]
        
        # Fallback: return first layout
        if layouts:
            first_name = next(iter(layouts.keys()))
            logger.debug(f"No default specified, using first layout: {first_name}")
            return layouts[first_name]
        
        raise ValueError("No layouts defined in configuration")
    
    def _parse_key_actions(self, key_data: Dict) -> Dict[str, List[Tuple]]:
        """
        Parse actions from key configuration.
        
        Returns:
            Dict with 'on_press' and 'on_release' action lists
        """
        actions = {
            'on_press': [],
            'on_release': []
        }
        
        # Parse on_press actions
        if 'on_press_actions' in key_data:
            actions['on_press'] = self._parse_action_list(key_data['on_press_actions'])
        
        # Parse on_release actions  
        if 'on_release_actions' in key_data:
            actions['on_release'] = self._parse_action_list(key_data['on_release_actions'])
        
        return actions
    
    def _parse_action_list(self, action_configs: List[Dict]) -> List[Tuple]:
        """
        Parse list of action configurations into action tuples.
        
        Args:
            action_configs: List of {ACTION_TYPE: parameter} dicts
            
        Returns:
            List of (ActionType, parameter) tuples
        """
        actions = []
        
        for action_config in action_configs:
            for action_type_str, param in action_config.items():
                # Convert string to ActionType enum
                try:
                    action_type = ActionType[action_type_str]
                    actions.append((action_type, param))
                except KeyError:
                    logger.warning(f"Unknown action type: {action_type_str}")
        
        return actions
