"""
Layout factory for creating Key and Layout objects from configuration.

This factory converts the parsed StreamDockConfig into actual runtime objects
that can be used by the application.
"""

import logging
from typing import Any, Dict, List, Optional, Tuple

from StreamDock.business_logic.action_type import ActionType
from StreamDock.domain.key import Key
from StreamDock.domain.layout import Layout

logger = logging.getLogger(__name__)

# Default text rendering settings used when not overridden per-key
_TEXT_DEFAULTS = {
    'text_color': 'white',
    'background_color': 'black',
    'font_size': 20,
    'bold': True,
    'text_position': 'bottom',
}


class LayoutFactory:
    """
    Factory for creating Key and Layout objects from configuration data.

    Converts StreamDockConfig (pure data) into runtime objects.
    """

    def __init__(self, config_data: Dict[str, Any], device, action_executor=None):
        """
        Initialize factory with configuration data and device.

        Args:
            config_data: Parsed configuration dictionary
            device: Device instance to bind objects to
            action_executor: Optional ActionExecutor instance
        """
        self._config = config_data
        self._device = device
        self._action_executor = action_executor
        self._keys: Dict[str, Key] = {}

        logger.debug("LayoutFactory initialized")

    def create_layouts(self) -> Tuple[Layout, Dict[str, Layout]]:
        """
        Create all layouts from configuration.

        Returns:
            Tuple of (default_layout, all_layouts_dict)
        """
        self._create_keys()
        layouts = self._create_layouts_dict()
        default_layout = self._find_default_layout(layouts)

        logger.info(f"Created {len(layouts)} layouts with {len(self._keys)} keys")
        return default_layout, layouts

    # ------------------------------------------------------------------
    # Key creation
    # ------------------------------------------------------------------

    def _create_keys(self) -> None:
        """Create Key objects from configuration."""
        keys_config = self._config.get('keys', {})

        for key_name, key_data in keys_config.items():
            key = self._build_key(key_name, key_data)
            if key is not None:
                self._keys[key_name] = key
                logger.debug(
                    f"Created key: {key_name} "
                    f"(icon={key.image_path or 'none'}, text={key.text or 'none'})"
                )

    def _build_key(self, key_name: str, key_data: Dict) -> Optional[Key]:
        """Build a single Key object from its configuration dict."""
        actions = self._parse_key_actions(key_data)

        icon_path = key_data.get('icon', '')

        # ------------------------------------------------------------------
        # Text rendering parameters
        # ------------------------------------------------------------------
        text = key_data.get('text', '')
        text_color = key_data.get('text_color', _TEXT_DEFAULTS['text_color'])
        background_color = key_data.get('background_color', _TEXT_DEFAULTS['background_color'])
        font_size = int(key_data.get('font_size', _TEXT_DEFAULTS['font_size']))
        bold = bool(key_data.get('bold', _TEXT_DEFAULTS['bold']))
        text_position = key_data.get('text_position', _TEXT_DEFAULTS['text_position'])

        if not icon_path and not text:
            logger.warning(
                f"Key '{key_name}' has neither an icon nor text – "
                "it will appear as a blank black square."
            )

        # key_number is set to 0 here; _create_layouts_dict assigns the real position.
        key = Key(
            device=self._device,
            key_number=0,
            image_path=icon_path,
            on_press=actions.get('on_press', []),
            on_release=actions.get('on_release', []),
            on_double_press=actions.get('on_double_press', []),
            action_executor=self._action_executor,
            text=text,
            text_color=text_color,
            background_color=background_color,
            font_size=font_size,
            bold=bold,
            text_position=text_position,
        )

        # Store factory metadata for debugging
        key._factory_name = key_name

        return key

    # ------------------------------------------------------------------
    # Layout creation
    # ------------------------------------------------------------------

    def _create_layouts_dict(self) -> Dict[str, Layout]:
        """Create Layout objects from configuration."""
        layouts_config = self._config.get('layouts', {})
        layouts: Dict[str, Layout] = {}

        for layout_name, layout_data in layouts_config.items():
            keys_list_config = layout_data.get('keys', [])
            clear_all = layout_data.get('clear_all', False)

            keys_for_layout: List[Key] = []
            for key_entry in keys_list_config:
                for position_str, key_name in key_entry.items():
                    if key_name in self._keys:
                        position = int(position_str)
                        key = self._keys[key_name]
                        key.key_number = position
                        # Keep logical key in sync with the physical position
                        key.logical_key = Key.KEY_MAPPING.get(position, position)
                        keys_for_layout.append(key)
                    else:
                        logger.warning(
                            f"Layout '{layout_name}': key '{key_name}' not found in keys config"
                        )

            layout = Layout(
                device=self._device,
                keys=keys_for_layout,
                clear_all=clear_all,
                name=layout_name,
            )
            layouts[layout_name] = layout
            logger.debug(f"Created layout: {layout_name} with {len(keys_for_layout)} keys")

        return layouts

    def _find_default_layout(self, layouts: Dict[str, Layout]) -> Layout:
        """Find the default layout."""
        layouts_config = self._config.get('layouts', {})

        for layout_name, layout_data in layouts_config.items():
            if layout_data.get('Default', False) and layout_name in layouts:
                logger.debug(f"Default layout from config: {layout_name}")
                return layouts[layout_name]

        if layouts:
            first_name = next(iter(layouts.keys()))
            logger.debug(f"No default specified, using first layout: {first_name}")
            return layouts[first_name]

        raise ValueError("No layouts defined in configuration")

    # ------------------------------------------------------------------
    # Action parsing
    # ------------------------------------------------------------------

    def _parse_key_actions(self, key_data: Dict) -> Dict[str, List[Tuple]]:
        """
        Parse actions from key configuration.

        Returns:
            Dict with 'on_press', 'on_release', and 'on_double_press' action lists
        """
        actions: Dict[str, List[Tuple]] = {
            'on_press': [],
            'on_release': [],
            'on_double_press': [],
        }

        if 'on_press_actions' in key_data:
            actions['on_press'] = self._parse_action_list(key_data['on_press_actions'])

        if 'on_release_actions' in key_data:
            actions['on_release'] = self._parse_action_list(key_data['on_release_actions'])

        if 'on_double_press_actions' in key_data:
            actions['on_double_press'] = self._parse_action_list(key_data['on_double_press_actions'])

        return actions

    def _parse_action_list(self, action_configs: List[Dict]) -> List[Tuple]:
        """
        Parse a list of action configurations into (ActionType, parameter) tuples.

        Args:
            action_configs: List of {ACTION_TYPE: parameter} dicts

        Returns:
            List of (ActionType, parameter) tuples
        """
        actions: List[Tuple] = []

        if not action_configs:
            return actions

        for action_config in action_configs:
            if not isinstance(action_config, dict):
                logger.warning(f"Skipping non-dict action entry: {action_config!r}")
                continue
            for action_type_str, param in action_config.items():
                # Handle CHANGE_LAYOUT shorthand: string value → dict with layout name
                if action_type_str == 'CHANGE_LAYOUT' and isinstance(param, str):
                    param = {'layout': param}

                # Resolve layout references inside CHANGE_LAYOUT
                if action_type_str == 'CHANGE_LAYOUT' and isinstance(param, dict):
                    layout_name = param.get('layout')
                    if layout_name and isinstance(layout_name, str):
                        # We can't resolve the Layout object here yet (layouts aren't
                        # fully built), so we leave as a name string and the
                        # orchestrator / action executor will look it up at runtime.
                        pass

                try:
                    action_type = ActionType[action_type_str]
                    actions.append((action_type, param))
                except KeyError:
                    logger.warning(f"Unknown action type: {action_type_str!r}")

        return actions
