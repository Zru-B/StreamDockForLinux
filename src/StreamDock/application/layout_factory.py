"""
Layout factory for creating Key and Layout objects from configuration.

This factory converts the parsed StreamDockConfig into actual runtime objects
that can be used by the application.
"""

import logging
from typing import Any, Dict, List, Optional, Tuple

from StreamDock.business_logic.action_executor import parse_action_list
from StreamDock.domain.key import Key
from StreamDock.domain.layout import Layout
from StreamDock.domain.widget_key import WidgetKey

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

    def __init__(self, config_data: Dict[str, Any], device, action_executor=None, widget_host=None):
        """
        Initialize factory with configuration data and device.

        Args:
            config_data: Parsed configuration dictionary
            device: Device instance to bind objects to
            action_executor: Optional ActionExecutor instance
            widget_host: WidgetHost already configured with this config's
                widget keys; without one, widget keys are skipped
        """
        self._config = config_data
        self._device = device
        self._action_executor = action_executor
        self._widget_host = widget_host
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
        """Validate every key definition once, so a bad one is reported even if unused."""
        keys_config = self._config.get('keys', {})

        for key_name, key_data in keys_config.items():
            key = self._build_key(key_name, key_data)
            if key is not None:
                self._keys[key_name] = key
                logger.debug(
                    f"Created key: {key_name} "
                    f"(icon={key.image_path or 'none'}, text={key.text or 'none'})"
                )

    def build_key(self, key_name: str, key_number: int) -> Optional[Key]:
        """
        Build the configured key ``key_name`` for slot ``key_number``.

        CHANGE_KEY names a key from the config, and the runtime resolves that
        name through here so the swapped-in key gets the same parsed actions,
        action executor and resolved icon path as one placed by a layout.

        Returns None when no key of that name is configured.
        """
        key_data = self._config.get('keys', {}).get(key_name)
        if not isinstance(key_data, dict):
            return None
        return self._build_key(key_name, key_data, key_number)

    def _build_key(self, key_name: str, key_data: Dict, position: int = 0) -> Optional[Key]:
        """Build a single Key object from its configuration dict."""
        actions = self._parse_key_actions(key_data)
        action_kwargs = dict(
            on_press=actions.get('on_press', []),
            on_release=actions.get('on_release', []),
            on_double_press=actions.get('on_double_press', []),
            on_long_press=actions.get('on_long_press', []),
            action_executor=self._action_executor,
        )

        if key_data.get('widget'):
            if self._widget_host is None:
                logger.warning(f"Key '{key_name}' is a widget but widgets are not available; skipping")
                return None
            key = WidgetKey(self._device, position, self._widget_host, key_name, **action_kwargs)
            key._factory_name = key_name
            return key

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

        key = Key(
            device=self._device,
            key_number=position,
            image_path=icon_path,
            **action_kwargs,
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
            clear_keys: List[int] = []
            for key_entry in keys_list_config:
                for position_str, key_name in key_entry.items():
                    if key_name is None:
                        # A null slot is documented as an explicitly empty key:
                        # without clearing it, whatever the previous layout put
                        # there stays visible and keeps firing its actions.
                        clear_keys.append(int(position_str))
                    elif key_name in self._keys:
                        # A Key per slot: one shared instance would carry the
                        # position of whichever layout was built last.
                        position = int(position_str)
                        key_data = self._config['keys'][key_name]
                        key = self._build_key(key_name, key_data, position)
                        if key is not None:
                            keys_for_layout.append(key)
                    else:
                        logger.warning(
                            f"Layout '{layout_name}': key '{key_name}' not found in keys config"
                        )

            layout = Layout(
                device=self._device,
                keys=keys_for_layout,
                clear_keys=clear_keys,
                clear_all=clear_all,
                name=layout_name,
                on_applied=self._report_widget_slots if self._widget_host else None,
            )
            layouts[layout_name] = layout
            logger.debug(f"Created layout: {layout_name} with {len(keys_for_layout)} keys")

        return layouts

    def _report_widget_slots(self, layout: Layout) -> None:
        self._widget_host.layout_applied({
            key.key_number: key.widget_key_name for key in layout.keys if isinstance(key, WidgetKey)
        })

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
            Dict with 'on_press', 'on_release', 'on_double_press' and 'on_long_press' action lists
        """
        actions: Dict[str, List[Tuple]] = {
            'on_press': [],
            'on_release': [],
            'on_double_press': [],
            'on_long_press': [],
        }

        if 'on_press_actions' in key_data:
            actions['on_press'] = self._parse_action_list(key_data['on_press_actions'])

        if 'on_release_actions' in key_data:
            actions['on_release'] = self._parse_action_list(key_data['on_release_actions'])

        if 'on_double_press_actions' in key_data:
            actions['on_double_press'] = self._parse_action_list(key_data['on_double_press_actions'])

        if 'on_long_press_actions' in key_data:
            actions['on_long_press'] = self._parse_action_list(key_data['on_long_press_actions'])

        return actions

    def _parse_action_list(self, action_configs: List[Dict]) -> List[Tuple]:
        """Parse a list of {ACTION_TYPE: parameter} dicts into (ActionType, parameter) tuples."""
        return parse_action_list(action_configs)
