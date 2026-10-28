"""
Check a third-party widget before it is installed.

Two passes. The static pass reads the source without running it: the script
must define exactly one Widget subclass whose manifest and options are plain
literals, so the app can list and configure the widget without executing it.
The dry run then imports the script in a throwaway child process and draws one
frame, which catches everything a parse can't.

Neither pass makes a script safe - it runs with the user's permissions - so
the imports that reach beyond drawing a key are reported as capabilities for
the user to agree to, not refused.
"""

import ast
import os
import re
import time
import unicodedata
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional, Tuple

from streamdock_sdk import SDK_VERSION
from streamdock_sdk.options import TYPES, Option, OptionError
from StreamDock.widgets.registry import ENTRY_FILE, ID_PATTERN, PYCACHE
from StreamDock.widgets.runners import WidgetProcessError, render_in_subprocess

STATE_PATTERN = re.compile(r'[a-z][a-z0-9_]{0,30}')
MAX_FILE_BYTES = 256 * 1024
MAX_TOTAL_BYTES = 5 * 1024 * 1024
MAX_FILES = 200
DRY_RUN_TIMEOUT = 5.0
SLOW_RENDER = 2.0
# Shown on one line in the list and the consent prompt.
TEXT_LIMITS = {'name': 80, 'author': 200}
# literal_eval and parse raise more than ValueError on hostile input: an
# unhashable dict key is a TypeError, deep nesting a RecursionError.
LITERAL_ERRORS = (ValueError, TypeError, SyntaxError, MemoryError, RecursionError)

MANIFEST_FIELDS = ('id', 'name', 'version', 'sdk_version', 'description', 'author', 'states', 'supports_badge',
                   'run_while_hidden')

RUNS_PROGRAMS = 'runs other programs'
OS_PROGRAM_CALLS = ('system', 'popen', 'exec', 'spawn', 'posix_spawn')
CAPABILITY_MODULES = {
    RUNS_PROGRAMS: {'subprocess', 'pty', 'multiprocessing'},
    'uses the network': {'socket', 'ssl', 'urllib', 'http', 'requests', 'httpx', 'aiohttp', 'websocket',
                         'websockets', 'ftplib', 'smtplib'},
    'loads native code': {'ctypes', 'cffi'},
    'talks to D-Bus': {'dbus', 'gi', 'pydbus', 'jeepney', 'dbus_next'},
}

DYNAMIC_CODE = 'runs code built at runtime'
APP_INTERNALS = "uses the app's own code"
# Importing these is as good as calling eval: they reach any module or builtin by name.
DYNAMIC_MODULES = {'importlib', 'builtins'}
# Modules whose attributes include system/popen/exec*/spawn*.
OS_MODULES = {'os', 'posix'}
WINDOW_FOCUS = 'sees which window you focus, and its title'


@dataclass
class ValidationReport:
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    capabilities: List[str] = field(default_factory=list)
    manifest: Optional[Dict[str, Any]] = None
    entry_path: Optional[str] = None

    @property
    def ok(self) -> bool:
        return not self.errors


def entry_file(source: str) -> str:
    """The script to run: the file itself, or widget.py inside a folder."""
    return os.path.join(source, ENTRY_FILE) if os.path.isdir(source) else source


def validate_widget(source: str, reserved_ids: Iterable[str] = (), dry_run: bool = True) -> ValidationReport:
    report = ValidationReport()
    source = os.path.abspath(source)
    entry = entry_file(source)
    report.entry_path = entry

    if not os.path.isfile(entry):
        report.errors.append(f'{ENTRY_FILE} not found in the folder' if os.path.isdir(source)
                             else 'file not found')
        return report
    if not entry.endswith('.py'):
        report.errors.append('a widget must be a .py file or a folder with widget.py')
        return report

    python_files = _check_sizes(source, report)
    if report.errors:
        return report

    trees = {}
    for path in python_files:
        try:
            with open(path, encoding='utf-8') as handle:
                trees[path] = ast.parse(handle.read(), filename=path)
        except (UnicodeDecodeError, *LITERAL_ERRORS) as exc:
            report.errors.append(f'{os.path.relpath(path, os.path.dirname(entry))}: cannot parse: {exc}')
    if report.errors:
        return report

    report.manifest = _static_manifest(trees[entry], report)
    for tree in trees.values():
        _collect_capabilities(tree, report.capabilities)
    report.capabilities = sorted(set(report.capabilities))

    manifest = report.manifest
    if manifest and manifest['id'] in set(reserved_ids):
        report.errors.append(f"id '{manifest['id']}' is already used by a built-in widget")
    if dry_run:
        dry_run_widget(report)
    return report


def dry_run_widget(report: ValidationReport) -> None:
    """
    Run the script a static pass accepted; adds any failure to ``report``.

    Kept apart from the static pass because it executes the widget: the
    installer asks for consent in between.
    """
    if report.ok and report.manifest is not None:
        _dry_run(report.entry_path, report)


def _check_sizes(source: str, report: ValidationReport) -> List[str]:
    if os.path.isfile(source):
        paths = [source]
    else:
        paths = []
        for root, dirs, files in os.walk(source):
            dirs[:] = [d for d in dirs if d != PYCACHE and not d.startswith('.')]
            # os.walk lists a linked folder among dirs and doesn't descend into it.
            paths.extend(os.path.join(root, name) for name in dirs if os.path.islink(os.path.join(root, name)))
            paths.extend(os.path.join(root, name) for name in files)
    if len(paths) > MAX_FILES:
        report.errors.append(f'too many files ({len(paths)}, at most {MAX_FILES})')
        return []
    total = 0
    python_files = []
    for path in paths:
        if os.path.islink(path):
            report.errors.append(f'{os.path.basename(path)}: symbolic links are not allowed')
            continue
        size = os.path.getsize(path)
        total += size
        if path.endswith('.py'):
            python_files.append(path)
            if size > MAX_FILE_BYTES:
                report.errors.append(f'{os.path.basename(path)} is larger than {MAX_FILE_BYTES // 1024} KB')
    if total > MAX_TOTAL_BYTES:
        report.errors.append(f'widget is larger than {MAX_TOTAL_BYTES // (1024 * 1024)} MB')
    return python_files


def _sdk_names(tree: ast.Module) -> Tuple[set, set]:
    """Names bound to streamdock_sdk.Widget / Option, and aliases of the module itself."""
    names = {'Widget': set(), 'Option': set(), 'module': set()}
    for node in tree.body:
        if isinstance(node, ast.ImportFrom) and node.module == 'streamdock_sdk':
            for alias in node.names:
                if alias.name in ('Widget', 'Option'):
                    names[alias.name].add(alias.asname or alias.name)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == 'streamdock_sdk':
                    names['module'].add(alias.asname or alias.name)
    return names


def _refers_to(node: ast.expr, name: str, names: Dict[str, set]) -> bool:
    if isinstance(node, ast.Name):
        return node.id in names[name]
    return (isinstance(node, ast.Attribute) and node.attr == name and isinstance(node.value, ast.Name)
            and node.value.id in names['module'])


def _static_manifest(tree: ast.Module, report: ValidationReport) -> Optional[Dict[str, Any]]:
    names = _sdk_names(tree)
    classes = [node for node in tree.body if isinstance(node, ast.ClassDef)
               and any(_refers_to(base, 'Widget', names) for base in node.bases)]
    if len(classes) != 1:
        report.errors.append('the script must define exactly one class that subclasses '
                             f'streamdock_sdk.Widget directly (found {len(classes)})')
        return None
    cls = classes[0]

    values: Dict[str, Any] = {}
    options_node = None
    has_render = False
    window_focus = False
    for node in cls.body:
        if isinstance(node, ast.FunctionDef) and node.name == 'render':
            has_render = True
        if isinstance(node, ast.FunctionDef) and node.name == 'on_window_focus':
            window_focus = True
            report.capabilities.append(WINDOW_FOCUS)
        targets = []
        if isinstance(node, ast.Assign):
            targets, value = node.targets, node.value
        elif isinstance(node, ast.AnnAssign) and node.value is not None:
            targets, value = [node.target], node.value
        for target in targets:
            if not isinstance(target, ast.Name):
                continue
            if target.id == 'options':
                options_node = value
            elif target.id in MANIFEST_FIELDS:
                try:
                    values[target.id] = ast.literal_eval(value)
                except LITERAL_ERRORS:
                    report.errors.append(f"'{target.id}' must be a plain literal, not an expression")

    if not has_render:
        report.errors.append(f"class {cls.name} must define render(self, ctx)")
    widget_id = values.get('id')
    if not isinstance(widget_id, str) or not ID_PATTERN.fullmatch(widget_id):
        report.errors.append("'id' must be 3-41 characters: a lowercase letter, then lowercase "
                             "letters, digits or underscores")
    if not isinstance(values.get('name'), str) or not values.get('name', '').strip():
        report.errors.append("'name' must be a non-empty string")
    if not isinstance(values.get('version'), str) or not values.get('version', '').strip():
        report.errors.append("'version' must be a string such as '1.0.0'")
    sdk_version = values.get('sdk_version', SDK_VERSION)
    if isinstance(sdk_version, bool) or not isinstance(sdk_version, int) or sdk_version < 1:
        report.errors.append("'sdk_version' must be a whole number")
    elif sdk_version > SDK_VERSION:
        report.errors.append(f'needs SDK version {sdk_version}; this app supports up to {SDK_VERSION}')
    for text_field in ('description', 'author'):
        if text_field in values and not isinstance(values[text_field], str):
            report.errors.append(f"'{text_field}' must be a string")
    for text_field, limit in TEXT_LIMITS.items():
        text = values.get(text_field)
        if isinstance(text, str) and (len(text) > limit or _has_control_chars(text)):
            report.errors.append(f"'{text_field}' must be a single line of at most {limit} characters")
    states = values.get('states', ())
    if not isinstance(states, (list, tuple)) or \
            not all(isinstance(state, str) and STATE_PATTERN.fullmatch(state) for state in states):
        report.errors.append("'states' must be a list of lowercase names such as 'connected'")
    elif len(set(states)) != len(states):
        report.errors.append("'states' lists a state twice")
    for flag in ('supports_badge', 'run_while_hidden'):
        if not isinstance(values.get(flag, False), bool):
            report.errors.append(f"'{flag}' must be True or False")

    options = _static_options(options_node, names, report) if options_node is not None else []
    if report.errors:
        return None
    return {
        'id': widget_id,
        'name': values['name'],
        'version': values['version'],
        'sdk_version': sdk_version,
        'description': values.get('description', ''),
        'author': values.get('author', ''),
        'options': [option.to_dict() for option in options],
        'states': list(states),
        'supports_badge': values.get('supports_badge', False),
        'run_while_hidden': values.get('run_while_hidden', False),
        'window_focus': window_focus,
    }


def _has_control_chars(text: str) -> bool:
    """Newlines, other control characters, and invisible ones such as a right-to-left override."""
    return any(unicodedata.category(char).startswith('C') for char in text)


def _static_options(node: ast.expr, names: Dict[str, set], report: ValidationReport) -> List[Option]:
    if not isinstance(node, (ast.List, ast.Tuple)):
        report.errors.append("'options' must be a list of Option.<type>(...) calls")
        return []
    options: List[Option] = []
    for item in node.elts:
        func = item.func if isinstance(item, ast.Call) else None
        if not (isinstance(func, ast.Attribute) and _refers_to(func.value, 'Option', names)
                and func.attr in TYPES):
            report.errors.append("each option must be written as Option.<type>(...) with type one of "
                                 + ', '.join(TYPES))
            continue
        try:
            args = [ast.literal_eval(arg) for arg in item.args]
            kwargs = {kw.arg: ast.literal_eval(kw.value) for kw in item.keywords if kw.arg}
            if any(kw.arg is None for kw in item.keywords):
                raise ValueError
        except LITERAL_ERRORS:
            report.errors.append(f'option #{len(options) + 1}: arguments must be plain literals')
            continue
        try:
            option = getattr(Option, func.attr)(*args, **kwargs)
            if not isinstance(option.key, str) or not option.key:
                raise OptionError('an option needs a name')
            option.coerce(option.default)
        except (TypeError, OptionError) as exc:
            report.errors.append(f'option #{len(options) + 1}: {exc}')
            continue
        if option.key in {existing.key for existing in options}:
            report.errors.append(f"option '{option.key}' is declared twice")
        options.append(option)
    return options


def _collect_capabilities(tree: ast.Module, capabilities: List[str]) -> None:
    """
    Best-effort: reports the obvious spellings, not every way Python can reach them.

    Deliberately conservative - ``import os as x`` makes every ``x.system`` a
    program run, whatever ``x`` is rebound to later.
    """
    os_names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            os_names.update(alias.asname or alias.name for alias in node.names if alias.name in OS_MODULES)

    for node in ast.walk(tree):
        modules = []
        if isinstance(node, ast.Import):
            modules = [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            modules = [node.module]
            if node.module in OS_MODULES and any(
                    alias.name == '*' or alias.name.startswith(OS_PROGRAM_CALLS) for alias in node.names):
                capabilities.append(RUNS_PROGRAMS)
        for module in modules:
            root = module.split('.')[0]
            for capability, roots in CAPABILITY_MODULES.items():
                if root in roots:
                    capabilities.append(capability)
            if root in DYNAMIC_MODULES:
                capabilities.append(DYNAMIC_CODE)
            if root == 'StreamDock':
                capabilities.append(APP_INTERNALS)
        # Any mention, called or not: ``run = os.system`` runs programs too.
        if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name) \
                and node.value.id in os_names and node.attr.startswith(OS_PROGRAM_CALLS):
            capabilities.append(RUNS_PROGRAMS)
        elif isinstance(node, ast.Name) and node.id == '__builtins__':
            capabilities.append(DYNAMIC_CODE)
        elif isinstance(node, ast.Call) and isinstance(node.func, ast.Name) \
                and node.func.id in ('eval', 'exec', 'compile', '__import__'):
            capabilities.append(DYNAMIC_CODE)


def _dry_run(entry: str, report: ValidationReport) -> None:
    defaults = {option['key']: option['default'] for option in report.manifest['options']}
    started = time.monotonic()
    try:
        manifest = render_in_subprocess(entry, defaults, timeout=DRY_RUN_TIMEOUT).manifest
    except WidgetProcessError as exc:
        report.errors.append(f'test run failed: {exc}')
        return
    elapsed = time.monotonic() - started
    if manifest.get('id') != report.manifest['id']:
        report.errors.append('the class that ran is not the one the source declares')
        return
    report.manifest['events'] = manifest.get('events', [])
    if elapsed > SLOW_RENDER:
        report.warnings.append(f'starting and drawing took {elapsed:.1f} s; keep render() fast '
                               'and move slow work to ctx.run_in_background')
