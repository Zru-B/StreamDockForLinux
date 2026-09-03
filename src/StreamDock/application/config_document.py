"""
Editable configuration document.

The runtime consumes StreamDockConfig: a validated, frozen snapshot with icon
paths already expanded. The editor needs the opposite - a mutable model that
round-trips the user's file without losing anything it does not understand.

This module provides that model. It sits upstream of StreamDockConfig and is
deliberately free of Qt, so it can be tested without a display.
"""

import copy
import os
import tempfile
from typing import Any, Dict, List, Optional, Union

import yaml

from StreamDock.application.configuration_manager import (
    ConfigurationManager,
    ConfigValidationError,
    StreamDockConfig,
    read_streamdock_section,
)

# Single source of truth. The editor used to default to 15 and the runtime to
# 50, so a config written by the editor changed brightness on first save.
DEFAULT_BRIGHTNESS = 50
# The device ignores anything dimmer than this, so the editor does not
# offer values below it.
MIN_BRIGHTNESS = 15
DEFAULT_TEXT_COLOR = "white"
DEFAULT_BACKGROUND_COLOR = "black"
DEFAULT_FONT_SIZE = 20
DEFAULT_BOLD = True
DEFAULT_TEXT_POSITION = "bottom"
DEFAULT_MATCH_FIELD = "class"
DEFAULT_LOCK_VERIFICATION_DELAY = 2.0
DEFAULT_DOUBLE_PRESS_INTERVAL = 0.3

ACTION_FIELDS = ('on_press_actions', 'on_release_actions', 'on_double_press_actions')


def _extras(data: Dict[str, Any], known: tuple) -> Dict[str, Any]:
    """Everything in data that this model does not represent explicitly."""
    return {k: copy.deepcopy(v) for k, v in data.items() if k not in known}


def _section(streamdock: Dict[str, Any], name: str) -> Dict[str, Any]:
    """
    Fetch one top-level section as a mapping.

    Args:
        streamdock: The 'streamdock' subtree
        name: Section name

    Returns:
        The section, or {} when absent or null

    Raises:
        ConfigValidationError: If the section is present but not a mapping
    """
    value = streamdock.get(name)
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ConfigValidationError(
            f"'{name}' must be a dictionary, not {type(value).__name__}")
    return value


def _entry(data: Any, section: str, name: str) -> Dict[str, Any]:
    """
    Fetch one entry of a section as a mapping.

    Args:
        data: The entry's value
        section: Section it came from, for the error message
        name: Entry name, for the error message

    Returns:
        The entry, or {} when null

    Raises:
        ConfigValidationError: If the entry is present but not a mapping
    """
    if data is None:
        return {}
    if not isinstance(data, dict):
        raise ConfigValidationError(
            f"'{section}.{name}' must be a dictionary, not {type(data).__name__}")
    return data


class KeyDefinition:
    """A single key definition."""

    STYLE_FIELDS = ('text_color', 'background_color', 'font_size', 'bold', 'text_position')
    KNOWN_FIELDS = ('icon', 'text') + STYLE_FIELDS + ACTION_FIELDS

    def __init__(self, name: str, data: Optional[Dict[str, Any]] = None):
        self.name = name
        self.icon: Optional[str] = None
        self.text: Optional[str] = None
        self.text_color: str = DEFAULT_TEXT_COLOR
        self.background_color: str = DEFAULT_BACKGROUND_COLOR
        self.font_size: int = DEFAULT_FONT_SIZE
        self.bold: bool = DEFAULT_BOLD
        self.text_position: str = DEFAULT_TEXT_POSITION
        self.on_press_actions: List[Dict[str, Any]] = []
        self.on_release_actions: List[Dict[str, Any]] = []
        self.on_double_press_actions: List[Dict[str, Any]] = []
        self.extra: Dict[str, Any] = {}
        # Styling fields the source file spelled out. Written back even when
        # they equal the default, so opening and saving does not churn the
        # user's file in either direction.
        self._explicit: set = set()

        if data:
            self.load_from_dict(data)

    def load_from_dict(self, data: Dict[str, Any]) -> None:
        """Populate from a YAML key definition."""
        self.icon = data.get('icon')
        self.text = data.get('text')
        self.text_color = data.get('text_color', DEFAULT_TEXT_COLOR)
        self.background_color = data.get('background_color', DEFAULT_BACKGROUND_COLOR)
        self.font_size = data.get('font_size', DEFAULT_FONT_SIZE)
        self.bold = data.get('bold', DEFAULT_BOLD)
        self.text_position = data.get('text_position', DEFAULT_TEXT_POSITION)
        self.on_press_actions = copy.deepcopy(data.get('on_press_actions', []))
        self.on_release_actions = copy.deepcopy(data.get('on_release_actions', []))
        self.on_double_press_actions = copy.deepcopy(data.get('on_double_press_actions', []))
        self.extra = _extras(data, self.KNOWN_FIELDS)
        self._explicit = {f for f in self.STYLE_FIELDS if f in data}

    def to_dict(self) -> Dict[str, Any]:
        """Serialise back to a YAML key definition, preserving unknown fields."""
        result: Dict[str, Any] = dict(self.extra)

        # icon and text are mutually exclusive: the runtime validator rejects a
        # key carrying both.
        if self.icon:
            result['icon'] = self.icon
        elif self.text:
            result['text'] = self.text
            for field, default in (('text_color', DEFAULT_TEXT_COLOR),
                                   ('background_color', DEFAULT_BACKGROUND_COLOR),
                                   ('font_size', DEFAULT_FONT_SIZE),
                                   ('bold', DEFAULT_BOLD),
                                   ('text_position', DEFAULT_TEXT_POSITION)):
                value = getattr(self, field)
                if value != default or field in self._explicit:
                    result[field] = value

        for field in ACTION_FIELDS:
            actions = getattr(self, field)
            if actions:
                result[field] = copy.deepcopy(actions)

        return result

    def has_icon(self) -> bool:
        """True if this key renders an icon."""
        return bool(self.icon)

    def has_text(self) -> bool:
        """True if this key renders text."""
        return bool(self.text)

    def is_text_based(self) -> bool:
        """True if this key renders text and no icon."""
        return self.text is not None and self.icon is None

    def is_icon_based(self) -> bool:
        """True if this key renders an icon and no text."""
        return self.icon is not None and self.text is None


class Layout:
    """A layout: which key definition sits at each of the 15 positions."""

    KNOWN_FIELDS = ('Default', 'clear_all', 'keys')

    def __init__(self, name: str, data: Optional[Dict[str, Any]] = None):
        self.name = name
        self.is_default: bool = False
        self.clear_all: bool = False
        self.keys: Dict[int, Optional[str]] = {}
        self.extra: Dict[str, Any] = {}

        if data:
            self.load_from_dict(data)

    def load_from_dict(self, data: Dict[str, Any]) -> None:
        """Populate from a YAML layout definition."""
        self.is_default = data.get('Default', False)
        self.clear_all = data.get('clear_all', False)
        self.extra = _extras(data, self.KNOWN_FIELDS)

        self.keys = {}
        for item in data.get('keys', []) or []:
            if isinstance(item, dict):
                for key_num, key_name in item.items():
                    try:
                        position = int(key_num)
                    except (TypeError, ValueError) as e:
                        raise ConfigValidationError(
                            f"Layout '{self.name}': key position {key_num!r} "
                            "is not a number") from e
                    self.keys[position] = key_name

    def to_dict(self) -> Dict[str, Any]:
        """Serialise back to a YAML layout definition, preserving unknown fields."""
        result: Dict[str, Any] = dict(self.extra)

        if self.is_default:
            result['Default'] = True
        if self.clear_all:
            result['clear_all'] = True

        result['keys'] = [{num: self.keys[num]} for num in sorted(self.keys)]
        return result

    def get_key_at_position(self, position: int) -> Optional[str]:
        """Name of the key at a position (1-15), or None."""
        return self.keys.get(position)

    def set_key_at_position(self, position: int, key_name: Optional[str]) -> None:
        """Place a key at a position, or clear it when key_name is None."""
        if key_name is None:
            self.keys.pop(position, None)
        else:
            self.keys[position] = key_name

    def remove_key_at_position(self, position: int) -> None:
        """Clear a position."""
        self.keys.pop(position, None)


class WindowRule:
    """A rule mapping a focused window to a layout."""

    KNOWN_FIELDS = ('window_name', 'layout', 'match_field', 'priority')

    def __init__(self, name: str, data: Optional[Dict[str, Any]] = None):
        self.name = name
        self.window_name: Union[str, List[str]] = ""
        self.layout: str = ""
        self.match_field: str = DEFAULT_MATCH_FIELD
        self.priority: int = 0
        self.extra: Dict[str, Any] = {}

        if data:
            self.load_from_dict(data)

    def load_from_dict(self, data: Dict[str, Any]) -> None:
        """Populate from a YAML window rule."""
        # window_name may be a single pattern or a list of them.
        self.window_name = copy.deepcopy(data.get('window_name', ""))
        self.layout = data.get('layout', "")
        self.match_field = data.get('match_field', DEFAULT_MATCH_FIELD)
        self.priority = data.get('priority', 0)
        self.extra = _extras(data, self.KNOWN_FIELDS)

    def to_dict(self) -> Dict[str, Any]:
        """Serialise back to a YAML window rule, preserving unknown fields."""
        result: Dict[str, Any] = dict(self.extra)
        result['window_name'] = copy.deepcopy(self.window_name)
        result['layout'] = self.layout
        result['match_field'] = self.match_field
        if self.priority:
            result['priority'] = self.priority
        return result

    def patterns(self) -> List[str]:
        """window_name as a list, whichever form it takes in the YAML."""
        if isinstance(self.window_name, list):
            return list(self.window_name)
        return [self.window_name] if self.window_name else []


class Settings:
    """The 'settings' section."""

    KNOWN_FIELDS = ('brightness', 'lock_monitor', 'lock_verification_delay',
                    'double_press_interval')

    def __init__(self, data: Optional[Dict[str, Any]] = None):
        self.brightness: int = DEFAULT_BRIGHTNESS
        self.lock_monitor: bool = True
        self.lock_verification_delay: float = DEFAULT_LOCK_VERIFICATION_DELAY
        self.double_press_interval: float = DEFAULT_DOUBLE_PRESS_INTERVAL
        self.extra: Dict[str, Any] = {}
        # Settings the source file spelled out, so opening and saving does not
        # add entries the user never wrote.
        self._explicit: set = set()

        if data:
            self.load_from_dict(data)

    def load_from_dict(self, data: Dict[str, Any]) -> None:
        """Populate from a YAML settings section."""
        self.brightness = data.get('brightness', DEFAULT_BRIGHTNESS)
        self.lock_monitor = data.get('lock_monitor', True)
        self.lock_verification_delay = data.get(
            'lock_verification_delay', DEFAULT_LOCK_VERIFICATION_DELAY)
        self.double_press_interval = data.get(
            'double_press_interval', DEFAULT_DOUBLE_PRESS_INTERVAL)
        self.extra = _extras(data, self.KNOWN_FIELDS)
        self._explicit = {f for f in self.KNOWN_FIELDS if f in data}

    def to_dict(self) -> Dict[str, Any]:
        """Serialise back to a YAML settings section, preserving unknown fields."""
        result: Dict[str, Any] = dict(self.extra)
        for field, default in (('brightness', DEFAULT_BRIGHTNESS),
                               ('lock_monitor', True),
                               ('lock_verification_delay',
                                DEFAULT_LOCK_VERIFICATION_DELAY),
                               ('double_press_interval',
                                DEFAULT_DOUBLE_PRESS_INTERVAL)):
            value = getattr(self, field)
            if value != default or field in self._explicit:
                result[field] = value
        return result


class ConfigDocument:
    """
    A configuration file being edited.

    Round-trips losslessly: anything this model does not represent is carried
    through in an 'extra' dict and written back out unchanged.
    """

    KNOWN_SECTIONS = ('settings', 'keys', 'layouts', 'windows_rules')

    def __init__(self, path: Optional[str] = None):
        self.settings = Settings()
        self.keys: Dict[str, KeyDefinition] = {}
        self.layouts: Dict[str, Layout] = {}
        self.window_rules: Dict[str, WindowRule] = {}
        self.extra: Dict[str, Any] = {}
        # Optional sections the source file actually contained, so opening and
        # saving does not add empty ones it never had.
        self._present_sections: set = set()
        self._path: Optional[str] = path
        self._dirty: bool = False

    # ── construction ──────────────────────────────────────────────────────

    @classmethod
    def load(cls, path: str) -> "ConfigDocument":
        """
        Read a configuration file.

        Args:
            path: Path to the YAML file

        Returns:
            The loaded document

        Raises:
            FileNotFoundError: If the file does not exist
            ConfigValidationError: If the YAML is malformed or has no
                'streamdock' root
        """
        if not os.path.exists(path):
            raise FileNotFoundError(f"Configuration file not found: {path}")

        # Shared with ConfigurationManager so the editor and the runtime
        # reject the same files with the same wording.
        return cls.from_dict(read_streamdock_section(path), path)

    @classmethod
    def from_dict(cls, streamdock: Dict[str, Any],
                  path: Optional[str] = None) -> "ConfigDocument":
        """
        Build a document from an in-memory 'streamdock' subtree.

        Args:
            streamdock: The 'streamdock' subtree
            path: Path the document belongs to, if any

        Returns:
            The document

        Raises:
            ConfigValidationError: If the subtree or one of its sections is
                not a mapping. A section that is null still means "defaults".
        """
        if not isinstance(streamdock, dict):
            raise ConfigValidationError(
                f"'streamdock' must be a dictionary, not {type(streamdock).__name__}")

        document = cls(path)
        document.settings = Settings(_section(streamdock, 'settings'))
        document.keys = {
            name: KeyDefinition(name, _entry(data, 'keys', name))
            for name, data in _section(streamdock, 'keys').items()
        }
        document.layouts = {
            name: Layout(name, _entry(data, 'layouts', name))
            for name, data in _section(streamdock, 'layouts').items()
        }
        document.window_rules = {
            name: WindowRule(name, _entry(data, 'windows_rules', name))
            for name, data in _section(streamdock, 'windows_rules').items()
        }
        document.extra = _extras(streamdock, cls.KNOWN_SECTIONS)
        document._present_sections = {
            name for name in cls.KNOWN_SECTIONS if name in streamdock}
        return document

    @classmethod
    def new_empty(cls) -> "ConfigDocument":
        """An empty document with no backing file."""
        return cls()

    # ── serialisation ─────────────────────────────────────────────────────

    def to_dict(self) -> Dict[str, Any]:
        """
        Serialise to the full {'streamdock': {...}} mapping.

        Returns:
            A dictionary ready to be written as YAML or validated
        """
        streamdock: Dict[str, Any] = dict(self.extra)

        # keys and layouts are required, so they are always written. The
        # optional sections are written when they hold something or when the
        # source file spelled them out.
        settings = self.settings.to_dict()
        if settings or 'settings' in self._present_sections:
            streamdock['settings'] = settings

        streamdock['keys'] = {name: key.to_dict() for name, key in self.keys.items()}
        streamdock['layouts'] = {
            name: layout.to_dict() for name, layout in self.layouts.items()}

        rules = {name: rule.to_dict() for name, rule in self.window_rules.items()}
        if rules or 'windows_rules' in self._present_sections:
            streamdock['windows_rules'] = rules

        return {'streamdock': streamdock}

    def save(self, path: Optional[str] = None) -> None:
        """
        Write the document to disk.

        Written atomically via a temporary file in the same directory, so an
        interrupted save cannot destroy a working configuration.

        Args:
            path: Destination. Defaults to the document's own path.

        Raises:
            ValueError: If no path is known
            OSError: If the file cannot be written
        """
        target = path or self._path
        if not target:
            raise ValueError("No path given and the document has no path of its own")

        target = os.path.abspath(target)
        directory = os.path.dirname(target) or '.'
        os.makedirs(directory, exist_ok=True)

        handle = tempfile.NamedTemporaryFile(
            mode='w', dir=directory, prefix='.config-', suffix='.yml',
            delete=False, encoding='utf-8')
        try:
            with handle:
                # safe_dump, not dump: dump() happily writes !!python/object
                # tags that safe_load() then refuses to read back.
                yaml.safe_dump(self.to_dict(), handle, default_flow_style=False,
                               sort_keys=False, allow_unicode=True)
            os.replace(handle.name, target)
        except BaseException:
            try:
                os.unlink(handle.name)
            except OSError:
                pass
            raise

        self._path = target
        self._dirty = False

    # ── validation ────────────────────────────────────────────────────────

    def validate(self) -> List[str]:
        """
        Check the document against the runtime's rules without raising.

        Returns:
            Problems found, empty when the configuration is valid
        """
        return ConfigurationManager.collect_issues(
            self.to_dict()['streamdock'], self._validation_path)

    def to_stream_dock_config(self) -> StreamDockConfig:
        """
        Parse into the validated snapshot the runtime consumes.

        Returns:
            StreamDockConfig with icon paths expanded

        Raises:
            ConfigValidationError: If the configuration is invalid
        """
        return ConfigurationManager.parse_data(
            self.to_dict()['streamdock'], self._validation_path)

    # ── state ─────────────────────────────────────────────────────────────

    @property
    def path(self) -> Optional[str]:
        """The file this document was loaded from or last saved to."""
        return self._path

    @property
    def config_dir(self) -> str:
        """Directory that relative icon paths resolve against."""
        if self._path:
            return os.path.dirname(os.path.abspath(self._path))
        return os.getcwd()

    @property
    def _validation_path(self) -> str:
        """A config path for validation, even when the document is unsaved."""
        return self._path or os.path.join(os.getcwd(), 'config.yml')

    @property
    def dirty(self) -> bool:
        """True if there are unsaved changes."""
        return self._dirty

    def mark_dirty(self) -> None:
        """Record that the document has unsaved changes."""
        self._dirty = True

    def mark_clean(self) -> None:
        """Record that the document matches what is on disk."""
        self._dirty = False

    # ── convenience ───────────────────────────────────────────────────────

    def add_key(self, key_name: str, key_def: KeyDefinition) -> None:
        """Add or replace a key definition."""
        key_def.name = key_name
        self.keys[key_name] = key_def

    def remove_key(self, key_name: str) -> None:
        """Remove a key definition if present."""
        self.keys.pop(key_name, None)

    def add_layout(self, layout_name: str, layout: Layout) -> None:
        """Add or replace a layout."""
        layout.name = layout_name
        self.layouts[layout_name] = layout

    def remove_layout(self, layout_name: str) -> None:
        """Remove a layout if present."""
        self.layouts.pop(layout_name, None)

    def get_default_layout(self) -> Optional[Layout]:
        """The layout marked Default, if any."""
        for layout in self.layouts.values():
            if layout.is_default:
                return layout
        return None

    def set_default_layout(self, layout_name: str) -> None:
        """Make one layout the default, clearing the flag on the others."""
        for layout in self.layouts.values():
            layout.is_default = False
        if layout_name in self.layouts:
            self.layouts[layout_name].is_default = True
