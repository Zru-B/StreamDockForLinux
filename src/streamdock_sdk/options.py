"""
Typed widget options.

A widget declares its options as a list of ``Option`` values. The app builds
the key editor's form from them and checks config.yml values against them, so
a widget never sees a value of the wrong type.
"""

# The Option.int/float/bool constructors shadow the builtins inside the class
# body, so annotations there must not be evaluated.
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Mapping, Optional, Tuple

from PIL import ImageColor

TYPES = ('string', 'int', 'float', 'bool', 'color', 'choice')


class OptionError(ValueError):
    """An option value doesn't match its declared type or range."""


@dataclass(frozen=True)
class Option:
    """One configurable widget setting. Build with the typed constructors."""

    key: str
    type: str
    default: Any
    label: str = ''
    description: str = ''
    choices: Tuple[str, ...] = field(default_factory=tuple)
    minimum: Optional[float] = None
    maximum: Optional[float] = None

    @classmethod
    def string(cls, key: str, default: str = '', label: str = '', description: str = '') -> 'Option':
        return cls(key, 'string', default, label, description)

    @classmethod
    def int(cls, key: str, default: int = 0, minimum: Optional[int] = None,
            maximum: Optional[int] = None, label: str = '', description: str = '') -> 'Option':
        return cls(key, 'int', default, label, description, minimum=minimum, maximum=maximum)

    @classmethod
    def float(cls, key: str, default: float = 0.0, minimum: Optional[float] = None,
              maximum: Optional[float] = None, label: str = '', description: str = '') -> 'Option':
        return cls(key, 'float', default, label, description, minimum=minimum, maximum=maximum)

    @classmethod
    def bool(cls, key: str, default: bool = False, label: str = '', description: str = '') -> 'Option':
        return cls(key, 'bool', default, label, description)

    @classmethod
    def color(cls, key: str, default: str = '#ffffff', label: str = '', description: str = '') -> 'Option':
        return cls(key, 'color', default, label, description)

    @classmethod
    def choice(cls, key: str, choices: Iterable[str], default: Optional[str] = None,
               label: str = '', description: str = '') -> 'Option':
        choices = tuple(choices)
        return cls(key, 'choice', choices[0] if default is None and choices else default,
                   label, description, choices=choices)

    @property
    def display_label(self) -> str:
        return self.label or self.key.replace('_', ' ').capitalize()

    def coerce(self, value: Any) -> Any:
        """Return ``value`` as this option's type, or raise ``OptionError``."""
        kind = self.type
        if kind == 'bool':
            if isinstance(value, bool):
                return value
            raise OptionError(f"'{self.key}' must be true or false")
        if kind in ('int', 'float'):
            # bool is an int subclass; a YAML 'yes' must not pass as 1.
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise OptionError(f"'{self.key}' must be a number")
            if kind == 'int':
                if isinstance(value, float) and not value.is_integer():
                    raise OptionError(f"'{self.key}' must be a whole number")
                value = int(value)
            else:
                value = float(value)
                # NaN compares false with every bound, so it would pass the range check.
                if not math.isfinite(value):
                    raise OptionError(f"'{self.key}' must be a finite number")
            if self.minimum is not None and value < self.minimum:
                raise OptionError(f"'{self.key}' must be at least {self.minimum}")
            if self.maximum is not None and value > self.maximum:
                raise OptionError(f"'{self.key}' must be at most {self.maximum}")
            return value
        if not isinstance(value, str):
            raise OptionError(f"'{self.key}' must be text")
        if kind == 'color':
            try:
                ImageColor.getrgb(value)
            except ValueError as exc:
                raise OptionError(f"'{self.key}' is not a colour: {value!r}") from exc
        if kind == 'choice' and value not in self.choices:
            raise OptionError(f"'{self.key}' must be one of: {', '.join(self.choices)}")
        return value

    def to_dict(self) -> Dict[str, Any]:
        data: Dict[str, Any] = {'key': self.key, 'type': self.type, 'default': self.default}
        for name in ('label', 'description'):
            if getattr(self, name):
                data[name] = getattr(self, name)
        if self.choices:
            data['choices'] = list(self.choices)
        for name in ('minimum', 'maximum'):
            if getattr(self, name) is not None:
                data[name] = getattr(self, name)
        return data

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> 'Option':
        if data.get('type') not in TYPES:
            raise OptionError(f"unknown option type {data.get('type')!r}")
        return cls(
            key=data['key'], type=data['type'], default=data.get('default'),
            label=data.get('label', ''), description=data.get('description', ''),
            choices=tuple(data.get('choices', ())),
            minimum=data.get('minimum'), maximum=data.get('maximum'),
        )


def resolve_options(schema: Iterable[Option], values: Optional[Mapping[str, Any]]) -> Tuple[Dict[str, Any], List[str]]:
    """
    Merge configured values over the schema defaults.

    Returns the full option dict and warnings for keys the schema doesn't
    declare. Raises ``OptionError`` for a value of the wrong type: an unknown
    key is harmless, a mistyped one would reach the widget.
    """
    schema = list(schema)
    values = dict(values or {})
    resolved = {}
    for option in schema:
        resolved[option.key] = option.coerce(values.pop(option.key)) if option.key in values else option.default
    warnings = [f"unknown option '{key}' is ignored" for key in values]
    return resolved, warnings
