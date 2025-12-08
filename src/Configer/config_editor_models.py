#!/usr/bin/env python3
"""
Data models for StreamDock Configuration Editor
Handles configuration data structures and YAML I/O
"""

from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml


class KeyDefinition:
    """Represents a key definition in the configuration"""
    
    def __init__(self, name: str, data: Optional[Dict[str, Any]] = None):
        self.name = name
        self.icon: Optional[str] = None
        self.text: Optional[str] = None
        self.text_color: str = "white"
        self.background_color: str = "black"
        self.font_size: int = 20
        self.bold: bool = True
        self.on_press_actions: List[Dict[str, Any]] = []
        self.on_release_actions: List[Dict[str, Any]] = []
        self.on_double_press_actions: List[Dict[str, Any]] = []
        
        if data:
            self.load_from_dict(data)
    
    def load_from_dict(self, data: Dict[str, Any]):
        """Load key definition from dictionary"""
        self.icon = data.get('icon')
        self.text = data.get('text')
        self.text_color = data.get('text_color', 'white')
        self.background_color = data.get('background_color', 'black')
        self.font_size = data.get('font_size', 20)
        self.bold = data.get('bold', True)
        self.on_press_actions = data.get('on_press_actions', [])
        self.on_release_actions = data.get('on_release_actions', [])
        self.on_double_press_actions = data.get('on_double_press_actions', [])
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert key definition to dictionary for YAML"""
        result = {}
        
        if self.icon:
            result['icon'] = self.icon
        elif self.text:
            result['text'] = self.text
            result['text_color'] = self.text_color
            result['background_color'] = self.background_color
            result['font_size'] = self.font_size
            result['bold'] = self.bold
        
        if self.on_press_actions:
            result['on_press_actions'] = self.on_press_actions
        if self.on_release_actions:
            result['on_release_actions'] = self.on_release_actions
        if self.on_double_press_actions:
            result['on_double_press_actions'] = self.on_double_press_actions
        
        return result
    
    def is_text_based(self) -> bool:
        """Check if this is a text-based key"""
        return self.text is not None and self.icon is None
    
    def is_icon_based(self) -> bool:
        """Check if this is an icon-based key"""
        return self.icon is not None and self.text is None


class Layout:
    """Represents a layout configuration"""
    
    def __init__(self, name: str, data: Optional[Dict[str, Any]] = None):
        self.name = name
        self.is_default: bool = False
        self.clear_all: bool = False
        self.keys: Dict[int, Optional[str]] = {}  # key_number -> key_name
        
        if data:
            self.load_from_dict(data)
    
    def load_from_dict(self, data: Dict[str, Any]):
        """Load layout from dictionary"""
        self.is_default = data.get('Default', False)
        self.clear_all = data.get('clear_all', False)
        
        keys_list = data.get('keys', [])
        self.keys = {}
        for item in keys_list:
            if isinstance(item, dict):
                for key_num, key_name in item.items():
                    self.keys[int(key_num)] = key_name
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert layout to dictionary for YAML"""
        result = {}
        
        if self.is_default:
            result['Default'] = True
        if self.clear_all:
            result['clear_all'] = True
        
        # Convert keys dict to list of single-item dicts
        keys_list = []
        for key_num in sorted(self.keys.keys()):
            keys_list.append({key_num: self.keys[key_num]})
        
        result['keys'] = keys_list
        return result
    
    def get_key_at_position(self, position: int) -> Optional[str]:
        """Get key name at given position (1-15)"""
        return self.keys.get(position)
    
    def set_key_at_position(self, position: int, key_name: Optional[str]):
        """Set key at given position"""
        if key_name is None:
            if position in self.keys:
                del self.keys[position]
        else:
            self.keys[position] = key_name
    
    def remove_key_at_position(self, position: int):
        """Remove key at given position"""
        if position in self.keys:
            del self.keys[position]


class WindowRule:
    """Represents a window monitoring rule"""
    
    def __init__(self, name: str, data: Optional[Dict[str, Any]] = None):
        self.name = name
        self.window_name: str = ""
        self.layout: str = ""
        self.match_field: str = "class"
        
        if data:
            self.load_from_dict(data)
    
    def load_from_dict(self, data: Dict[str, Any]):
        """Load window rule from dictionary"""
        self.window_name = data.get('window_name', '')
        self.layout = data.get('layout', '')
        self.match_field = data.get('match_field', 'class')
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert window rule to dictionary for YAML"""
        return {
            'window_name': self.window_name,
            'layout': self.layout,
            'match_field': self.match_field
        }


class StreamDockConfig:
    """Main configuration model"""
    
    def __init__(self):
        self.brightness: int = 15
        self.lock_monitor: bool = True
        self.double_press_interval: float = 0.3
        self.keys: Dict[str, KeyDefinition] = {}
        self.layouts: Dict[str, Layout] = {}
        self.window_rules: Dict[str, WindowRule] = {}
    
    def load_from_file(self, filepath: str):
        """Load configuration from YAML file"""
        path = Path(filepath)
        if not path.exists():
            return
        
        with open(filepath, 'r') as f:
            data = yaml.safe_load(f)
        
        if not data or 'streamdock' not in data:
            return
        
        config = data['streamdock']
        
        # Load settings
        settings = config.get('settings', {})
        self.brightness = settings.get('brightness', 15)
        self.lock_monitor = settings.get('lock_monitor', True)
        self.double_press_interval = settings.get('double_press_interval', 0.3)
        
        # Load keys
        keys_data = config.get('keys', {})
        self.keys = {}
        for key_name, key_data in keys_data.items():
            self.keys[key_name] = KeyDefinition(key_name, key_data)
        
        # Load layouts
        layouts_data = config.get('layouts', {})
        self.layouts = {}
        for layout_name, layout_data in layouts_data.items():
            self.layouts[layout_name] = Layout(layout_name, layout_data)
        
        # Load window rules
        rules_data = config.get('windows_rules', {})
        self.window_rules = {}
        for rule_name, rule_data in rules_data.items():
            self.window_rules[rule_name] = WindowRule(rule_name, rule_data)
    
    def save_to_file(self, filepath: str):
        """Save configuration to YAML file"""
        data = {
            'streamdock': {
                'settings': {
                    'brightness': self.brightness,
                    'lock_monitor': self.lock_monitor,
                    'double_press_interval': self.double_press_interval
                },
                'keys': {},
                'layouts': {},
                'windows_rules': {}
            }
        }
        
        # Add keys
        for key_name, key_def in self.keys.items():
            data['streamdock']['keys'][key_name] = key_def.to_dict()
        
        # Add layouts
        for layout_name, layout in self.layouts.items():
            data['streamdock']['layouts'][layout_name] = layout.to_dict()
        
        # Add window rules
        for rule_name, rule in self.window_rules.items():
            data['streamdock']['windows_rules'][rule_name] = rule.to_dict()
        
        with open(filepath, 'w') as f:
            yaml.dump(data, f, default_flow_style=False, sort_keys=False, allow_unicode=True)
    
    def add_key(self, key_name: str, key_def: KeyDefinition):
        """Add or update a key definition"""
        key_def.name = key_name
        self.keys[key_name] = key_def
    
    def remove_key(self, key_name: str):
        """Remove a key definition"""
        if key_name in self.keys:
            del self.keys[key_name]
    
    def add_layout(self, layout_name: str, layout: Layout):
        """Add or update a layout"""
        layout.name = layout_name
        self.layouts[layout_name] = layout
    
    def remove_layout(self, layout_name: str):
        """Remove a layout"""
        if layout_name in self.layouts:
            del self.layouts[layout_name]
    
    def get_default_layout(self) -> Optional[Layout]:
        """Get the default layout"""
        for layout in self.layouts.values():
            if layout.is_default:
                return layout
        return None
    
    def set_default_layout(self, layout_name: str):
        """Set a layout as default"""
        # Clear all other defaults
        for layout in self.layouts.values():
            layout.is_default = False
        
        # Set the new default
        if layout_name in self.layouts:
            self.layouts[layout_name].is_default = True
