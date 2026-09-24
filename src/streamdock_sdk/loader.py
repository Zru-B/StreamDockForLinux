"""Import a widget script and find its Widget subclass."""

import importlib.util
import os
import sys
from typing import Type

from streamdock_sdk.widget import Widget


class WidgetLoadError(Exception):
    """The script doesn't define exactly one Widget subclass."""


def load_widget_class(script_path: str) -> Type[Widget]:
    """
    Execute ``script_path`` and return the one Widget subclass it defines.

    Runs the script's top-level code, so only call this where that code is
    allowed to run: in the widget's own process, or on a built-in.
    """
    script_path = os.path.abspath(script_path)
    # A folder widget may import its own helper modules.
    folder = os.path.dirname(script_path)
    if folder not in sys.path:
        sys.path.insert(0, folder)

    module_name = f'streamdock_widget_{abs(hash(script_path))}'
    spec = importlib.util.spec_from_file_location(module_name, script_path)
    if spec is None or spec.loader is None:
        raise WidgetLoadError(f'cannot load {script_path}')
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return find_widget_class(module)


def find_widget_class(module) -> Type[Widget]:
    found = [
        value for value in vars(module).values()
        if isinstance(value, type) and issubclass(value, Widget) and value is not Widget
        and value.__module__ == module.__name__
    ]
    if len(found) != 1:
        raise WidgetLoadError(f'{module.__name__} must define exactly one Widget subclass, found {len(found)}')
    return found[0]
