"""
The widgets the app can run: the built-ins plus the installed third-party ones.

Third-party widgets are listed from the ``manifest.json`` written when they
were installed, so browsing the list never executes their code.
"""

import hashlib
import importlib
import json
import logging
import os
import pkgutil
import re
import stat
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple, Type

from streamdock_sdk import Option, Widget
from streamdock_sdk.loader import find_widget_class

logger = logging.getLogger(__name__)

MANIFEST_FILE = 'manifest.json'
ENTRY_FILE = 'widget.py'
PYCACHE = '__pycache__'
ID_PATTERN = re.compile(r'[a-z][a-z0-9_]{2,40}')
CHANGED_PROBLEM = 'files changed since it was approved; approve it again to run it'
HASH_CHUNK = 1024 * 1024


def data_home() -> str:
    return os.environ.get('XDG_DATA_HOME') or os.path.expanduser('~/.local/share')


def default_install_dir() -> str:
    return os.path.join(data_home(), 'streamdock', 'widgets')


def default_state_dir() -> str:
    state = os.environ.get('XDG_STATE_HOME') or os.path.expanduser('~/.local/state')
    return os.path.join(state, 'streamdock', 'widgets')


def file_digests(folder: str) -> Dict[str, str]:
    """
    sha256 of every file under ``folder``, by relative path.

    Anything that isn't a plain file - a symbolic link to a file or folder, a
    pipe - is listed with a marker instead of being opened, so it can never
    match an approved record. So is a ``__pycache__`` folder: widgets run
    without reading or writing bytecode there, so one appearing is a change.
    """
    digests = {}
    for root, dirs, files in os.walk(folder):
        dirs.sort()
        odd = [d for d in dirs if d == PYCACHE or os.path.islink(os.path.join(root, d))]
        for name in odd + sorted(files):
            if name == MANIFEST_FILE and root == folder:
                continue
            path = os.path.join(root, name)
            relative = os.path.relpath(path, folder)
            if not stat.S_ISREG(os.lstat(path).st_mode):
                digests[relative] = 'not a plain file'
                continue
            digest = hashlib.sha256()
            with open(path, 'rb') as handle:
                for chunk in iter(lambda: handle.read(HASH_CHUNK), b''):
                    digest.update(chunk)
            digests[relative] = digest.hexdigest()
    return digests


@dataclass
class WidgetSpec:
    """One runnable widget as the app sees it."""

    manifest: Dict[str, Any]
    builtin: bool
    widget_cls: Optional[Type[Widget]] = None
    script_path: Optional[str] = None
    folder: Optional[str] = None
    capabilities: List[str] = field(default_factory=list)
    # The approved sha256 of each file; None for built-ins.
    files: Optional[Dict[str, str]] = None
    # Why a third-party widget can't run, e.g. its files changed after approval.
    problem: Optional[str] = None

    @property
    def id(self) -> str:
        return self.manifest['id']

    @property
    def name(self) -> str:
        return self.manifest.get('name') or self.id

    @property
    def version(self) -> str:
        return self.manifest.get('version', '')

    @property
    def description(self) -> str:
        return self.manifest.get('description', '')

    @property
    def options(self) -> List[Option]:
        return [Option.from_dict(data) for data in self.manifest.get('options', [])]

    @property
    def events(self) -> Tuple[str, ...]:
        return tuple(self.manifest.get('events', ()))

    @property
    def states(self) -> Tuple[str, ...]:
        return tuple(self.manifest.get('states', ()))

    @property
    def supports_badge(self) -> bool:
        return bool(self.manifest.get('supports_badge', False))

    @property
    def run_while_hidden(self) -> bool:
        return bool(self.manifest.get('run_while_hidden', False))

    @property
    def window_focus(self) -> bool:
        return bool(self.manifest.get('window_focus', False))

    @property
    def runnable(self) -> bool:
        return self.problem is None

    def changed_since_approval(self) -> bool:
        """Re-hash the files now; the registry's check is only as fresh as its last refresh."""
        if self.files is None:
            return False
        try:
            return file_digests(self.folder) != self.files
        except OSError:
            return True


def load_builtin_specs() -> Dict[str, WidgetSpec]:
    from StreamDock.widgets import builtin  # pylint: disable=import-outside-toplevel

    specs = {}
    for info in pkgutil.iter_modules(builtin.__path__):
        if info.name.startswith('_'):
            continue
        module = importlib.import_module(f'{builtin.__name__}.{info.name}')
        widget_cls = find_widget_class(module)
        specs[widget_cls.id] = WidgetSpec(manifest=widget_cls.manifest(), builtin=True, widget_cls=widget_cls)
    return specs


def load_installed_spec(folder: str) -> Optional[WidgetSpec]:
    """Read an installed widget's manifest and check its files still match it."""
    try:
        with open(os.path.join(folder, MANIFEST_FILE), encoding='utf-8') as handle:
            record = json.load(handle)
        if not isinstance(record, dict) or not isinstance(record.get('manifest'), dict):
            raise ValueError('manifest.json is not a widget record')
        files = record.get('files')
        spec = WidgetSpec(
            manifest=record['manifest'], builtin=False,
            script_path=os.path.join(folder, ENTRY_FILE), folder=folder,
            capabilities=list(record.get('capabilities', [])),
            files=files if isinstance(files, dict) else {},
        )
        # Removing and approving act on the id, so it must name this folder.
        if not isinstance(spec.id, str) or not ID_PATTERN.fullmatch(spec.id) \
                or spec.id != os.path.basename(folder):
            raise ValueError(f'manifest id {spec.id!r} does not match the folder')
        for option in spec.manifest.get('options', []):
            Option.from_dict(option)
        # Read by the widget list; a non-string would break sorting it.
        for text_field in ('name', 'version', 'description', 'author'):
            if not isinstance(spec.manifest.get(text_field, ''), str):
                raise ValueError(f"manifest '{text_field}' is not text")
        if spec.changed_since_approval():
            spec.problem = CHANGED_PROBLEM
    except (OSError, ValueError, KeyError, TypeError, AttributeError, RecursionError) as exc:
        logger.warning('Ignoring widget folder %s: %s', folder, exc)
        return None
    return spec


class WidgetRegistry:
    """Looks up widgets by id. Built-ins win: an installed widget can't replace one."""

    def __init__(self, install_dir: Optional[str] = None, builtins: Optional[Dict[str, WidgetSpec]] = None):
        self.install_dir = install_dir or default_install_dir()
        self._builtins = load_builtin_specs() if builtins is None else builtins
        self._installed: Dict[str, WidgetSpec] = {}
        self.refresh()

    def refresh(self) -> None:
        self._installed = {}
        if not os.path.isdir(self.install_dir):
            return
        for name in sorted(os.listdir(self.install_dir)):
            folder = os.path.join(self.install_dir, name)
            if not os.path.isdir(folder) or name.startswith('.'):
                continue
            try:
                spec = load_installed_spec(folder)
            except Exception:  # pylint: disable=broad-exception-caught
                # One broken folder must not hide every other widget.
                logger.exception('Ignoring widget folder %s', folder)
                continue
            if spec is None:
                continue
            if spec.id in self._builtins:
                logger.warning('Installed widget %s clashes with a built-in and is ignored', spec.id)
                continue
            self._installed[spec.id] = spec

    def get(self, widget_id: str) -> Optional[WidgetSpec]:
        return self._builtins.get(widget_id) or self._installed.get(widget_id)

    def all(self) -> List[WidgetSpec]:
        builtins = sorted(self._builtins.values(), key=lambda spec: spec.name.lower())
        installed = sorted(self._installed.values(), key=lambda spec: spec.name.lower())
        return builtins + installed

    def builtin_ids(self) -> List[str]:
        return list(self._builtins)
