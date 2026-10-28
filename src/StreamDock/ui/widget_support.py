"""
Widget pieces of the editor: previews, the options form and the manager dialog.

Previews are snapshots, drawn once per (widget, options) off the GUI thread:
a built-in in a worker thread, a third-party widget in a throwaway child
process, the same way it would run on the device.
"""

import html
import json
import logging
import math
import os
from collections import OrderedDict
from concurrent.futures import Future, ThreadPoolExecutor
from decimal import Decimal
from typing import Any, Dict, List, Mapping, Optional, Tuple

from PIL import Image
from PyQt6.QtCore import QCoreApplication, QObject, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QImage, QPixmap
from PyQt6.QtWidgets import (
    QApplication,
    QCheckBox,
    QColorDialog,
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from streamdock_sdk import Option
from streamdock_sdk.options import OptionError, resolve_options
from streamdock_sdk.scheduler import WidgetDriver
from StreamDock.application.configuration_manager import relativize_icon_path
from StreamDock.ui.chrome import ThemedDialog, make_button
from StreamDock.ui.widgets import ToggleSwitch
from StreamDock.widgets.appearance import BADGE_POSITIONS, Appearance, BadgeStyle, compose
from StreamDock.widgets.host import KEY_SIZE, error_tile
from StreamDock.widgets.installer import InstallError, StagedWidget, WidgetInstaller
from StreamDock.widgets.registry import CHANGED_PROBLEM, ENTRY_FILE, WidgetRegistry, WidgetSpec
from StreamDock.widgets.runners import render_in_subprocess
from StreamDock.widgets.validator import ValidationReport

logger = logging.getLogger(__name__)

PREVIEW_TIMEOUT = 3.0
PREVIEW_CACHE_SIZE = 256
# The most decimals a float option's editor shows.
MAX_DECIMALS = 6
DEFAULT_BADGE = {'position': BadgeStyle.position, 'color': BadgeStyle.color, 'text_color': BadgeStyle.text_color}

_registry: Optional[WidgetRegistry] = None


def shared_registry() -> WidgetRegistry:
    """The editor's widget catalog; one per process so every dialog agrees."""
    global _registry  # pylint: disable=global-statement
    if _registry is None:
        _registry = WidgetRegistry()
    return _registry


def pil_to_pixmap(image: Image.Image) -> QPixmap:
    rgba = image.convert('RGBA')
    qimage = QImage(rgba.tobytes('raw', 'RGBA'), rgba.width, rgba.height, QImage.Format.Format_RGBA8888)
    return QPixmap.fromImage(qimage.copy())


# Shown in the editor when the widget has no badge at that moment, so the user
# can see where one will go.
SAMPLE_BADGE = '3'


def _mtime(path: str) -> Optional[float]:
    try:
        return os.path.getmtime(path)
    except OSError:
        return None


def _cache_key(widget_id: str, options: Mapping[str, Any], appearance: Optional[Appearance]) -> str:
    # The images' mtimes are part of the key, so re-saving an icon under the
    # same name shows up without restarting the editor.
    paths = [] if appearance is None else [appearance.icon] + [path for _, path in appearance.state_icons]
    mtimes = [_mtime(path) for path in paths if path]
    return json.dumps([widget_id, dict(options), repr(appearance), mtimes], sort_keys=True, default=str)


def render_preview(spec: Optional[WidgetSpec], widget_id: str, options: Mapping[str, Any],
                   appearance: Optional[Appearance] = None) -> Image.Image:
    """One frame for the editor, composed as the device would; any failure is the error tile."""
    if spec is None or not spec.runnable:
        return error_tile(widget_id)
    try:
        resolved, _ = resolve_options(spec.options, options)
        if spec.builtin:
            driver = WidgetDriver(spec.widget_cls, resolved, KEY_SIZE)
            frame, state, badge = driver.render_once(), driver.state, driver.badge
        else:
            if spec.changed_since_approval():
                logger.warning("Preview of widget '%s' refused: %s", widget_id, CHANGED_PROBLEM)
                return error_tile(widget_id)
            snapshot = render_in_subprocess(spec.script_path, resolved, KEY_SIZE, PREVIEW_TIMEOUT)
            frame, state, badge = snapshot.frame, snapshot.state, snapshot.badge
        if appearance is None or not appearance.uses_images:
            return frame
        if badge is None and spec.supports_badge:
            badge = SAMPLE_BADGE
        return compose(appearance, state, badge, frame, KEY_SIZE) or frame
    except Exception:  # pylint: disable=broad-exception-caught
        logger.warning("Preview of widget '%s' failed", widget_id, exc_info=True)
        return error_tile(widget_id)


class WidgetPreviewService(QObject):
    """
    Cached widget snapshots; ``preview_ready`` fires when a requested one arrives.

    Every request ends in ``preview_ready`` - with the error tile if drawing
    failed - so a caller showing a placeholder never waits forever.
    """

    preview_ready = pyqtSignal(str)
    _rendered = pyqtSignal(str, object, object)

    def __init__(self, registry: Optional[WidgetRegistry] = None, parent=None):
        super().__init__(parent)
        self._registry = registry or shared_registry()
        self._cache: 'OrderedDict[str, QPixmap]' = OrderedDict()
        self._pending = set()
        # Bumped by clear(): a snapshot drawn before it is stale.
        self._generation = 0
        # The queued request of each requester, cancelled when it asks again.
        self._queued: Dict[int, Tuple[str, Future]] = {}
        self._closed = False
        self._pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix='widget-preview')
        self._rendered.connect(self._store)

    @staticmethod
    def key(widget_id: str, options: Mapping[str, Any], appearance: Optional[Appearance] = None) -> str:
        return _cache_key(widget_id, options, appearance)

    def pixmap(self, widget_id: str, options: Mapping[str, Any],
               appearance: Optional[Appearance] = None, requester: Any = None) -> Optional[QPixmap]:
        """
        The cached snapshot, or None after starting to draw one.

        A ``requester`` (e.g. the key editor) that asks for a new snapshot
        drops its earlier one if that hasn't started drawing yet, so typing
        in an option doesn't queue a preview per keystroke.
        """
        key = _cache_key(widget_id, options, appearance)
        if key in self._cache:
            self._cache.move_to_end(key)
            return self._cache[key]
        if key not in self._pending and not self._closed:
            self._supersede(requester, key)
            self._pending.add(key)
            spec = self._registry.get(widget_id)
            options = dict(options)
            generation = self._generation
            future = self._pool.submit(self._render, key, generation, spec, widget_id, options, appearance)
            if requester is not None:
                self._queued[id(requester)] = (key, future)
        return None

    def _supersede(self, requester: Any, key: str) -> None:
        queued = self._queued.pop(id(requester), None) if requester is not None else None
        if queued is None or queued[0] == key or not queued[1].cancel():
            return
        self._pending.discard(queued[0])
        # Another caller may be waiting on the same snapshot; let it ask again.
        QTimer.singleShot(0, lambda: self.preview_ready.emit(queued[0]))

    def _render(self, key: str, generation: int, spec, widget_id: str, options, appearance) -> None:
        """Runs on the pool; always answers, so the key never stays pending."""
        if generation != self._generation:
            return
        try:
            image = render_preview(spec, widget_id, options, appearance)
        except Exception:  # pylint: disable=broad-exception-caught
            logger.warning("Preview of widget '%s' failed", widget_id, exc_info=True)
            image = error_tile(widget_id)
        self._rendered.emit(key, generation, image)

    def clear(self) -> None:
        """Forget every snapshot, e.g. after a widget was installed or removed."""
        self._generation += 1
        self._cache.clear()
        self._pending.clear()

    def shutdown(self) -> None:
        """Drop queued previews and stop the workers; called when the app quits."""
        self._closed = True
        self._pool.shutdown(wait=False, cancel_futures=True)

    def _store(self, key: str, generation: int, image: Image.Image) -> None:
        if generation != self._generation:
            return
        self._pending.discard(key)
        try:
            pixmap = pil_to_pixmap(image)
        except Exception:  # pylint: disable=broad-exception-caught
            logger.warning('Preview could not be shown', exc_info=True)
            pixmap = pil_to_pixmap(error_tile(''))
        self._cache[key] = pixmap
        self._cache.move_to_end(key)
        while len(self._cache) > PREVIEW_CACHE_SIZE:
            self._cache.popitem(last=False)
        self.preview_ready.emit(key)


_shared_previews: Optional[WidgetPreviewService] = None


def shared_previews() -> WidgetPreviewService:
    global _shared_previews  # pylint: disable=global-statement
    if _shared_previews is None:
        _shared_previews = WidgetPreviewService(shared_registry())
        app = QCoreApplication.instance()
        if app is not None:
            app.aboutToQuit.connect(_shared_previews.shutdown)
    return _shared_previews


class WidgetOptionsForm(QWidget):
    """
    A form built from a widget's option schema.

    ``values()`` returns only what belongs in config.yml: options the user
    changed from their default, options the file already spelled out, and
    unknown options carried through untouched.
    """

    changed = pyqtSignal()

    def __init__(self, options: List[Option], values: Optional[Mapping[str, Any]] = None, parent=None):
        super().__init__(parent)
        self._options = options
        self._initial = dict(values or {})
        self._editors: Dict[str, QWidget] = {}
        form = QFormLayout(self)
        form.setContentsMargins(0, 0, 0, 0)
        for option in options:
            editor = self._editor_for(option)
            # Tooltips and labels would render a widget's own text as rich text.
            if option.description:
                editor.setToolTip(rich_text(option.description))
            label = QLabel(f'{option.display_label}:')
            label.setTextFormat(Qt.TextFormat.PlainText)
            form.addRow(label, editor)
        if not options:
            form.addRow(QLabel('This widget has no options.'))

    def _editor_for(self, option: Option) -> QWidget:
        value = self._initial.get(option.key, option.default)
        try:
            value = option.coerce(value)
        except OptionError:
            value = option.default
        kind = option.type

        if kind == 'bool':
            editor = ToggleSwitch()
            editor.setChecked(bool(value))
            editor.toggled.connect(self.changed)
        elif kind == 'int':
            editor = QSpinBox()
            # int() would truncate a fractional bound towards zero, admitting a value outside it.
            editor.setRange(math.ceil(option.minimum) if option.minimum is not None else -1_000_000,
                            math.floor(option.maximum) if option.maximum is not None else 1_000_000)
            editor.setValue(int(value))
            editor.valueChanged.connect(self.changed)
        elif kind == 'float':
            editor = QDoubleSpinBox()
            # Enough places to show the default and the value exactly, or an
            # untouched form would round them and write the result to config.yml.
            editor.setDecimals(_decimals(option.default, option.minimum, option.maximum, value))
            editor.setRange(option.minimum if option.minimum is not None else -1e6,
                            option.maximum if option.maximum is not None else 1e6)
            editor.setValue(float(value))
            editor.valueChanged.connect(self.changed)
        elif kind == 'choice':
            editor = QComboBox()
            editor.addItems(list(option.choices))
            editor.setCurrentText(value)
            editor.currentTextChanged.connect(self.changed)
        elif kind == 'color':
            editor = color_field(value, self.changed)
        else:
            editor = QLineEdit(value)
            editor.textChanged.connect(self.changed)

        self._editors[option.key] = editor
        return editor

    def _raw(self, option: Option) -> Any:
        editor = self._editors[option.key]
        if option.type == 'bool':
            return editor.isChecked()
        if option.type in ('int', 'float'):
            return editor.value()
        if option.type == 'choice':
            return editor.currentText()
        if option.type == 'color':
            return editor.line_edit.text().strip()
        return editor.text()

    def set_raw(self, key: str, value: Any) -> None:
        """Set one option's editor, for tests and programmatic edits."""
        option = next(o for o in self._options if o.key == key)
        editor = self._editors[key]
        if option.type == 'bool':
            editor.setChecked(bool(value))
        elif option.type in ('int', 'float'):
            editor.setValue(value)
        elif option.type == 'choice':
            editor.setCurrentText(value)
        elif option.type == 'color':
            editor.line_edit.setText(value)
        else:
            editor.setText(value)

    def errors(self) -> List[str]:
        problems = []
        for option in self._options:
            try:
                option.coerce(self._raw(option))
            except OptionError as exc:
                problems.append(str(exc))
        return problems

    def values(self) -> Dict[str, Any]:
        known = {option.key for option in self._options}
        result = {key: value for key, value in self._initial.items() if key not in known}
        for option in self._options:
            value = self._raw(option)
            if option.type == 'float' and option.key not in self._initial and \
                    _same_shown(value, option.default, self._editors[option.key].decimals()):
                continue
            if value != option.default or option.key in self._initial:
                result[option.key] = value
        return result


def _decimals(*values: Any) -> int:
    """The decimal places needed to show every finite number in ``values``, between 2 and MAX_DECIMALS."""
    places = 2
    for value in values:
        if isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value):
            exponent = Decimal(repr(float(value))).as_tuple().exponent
            places = max(places, -exponent)
    return min(places, MAX_DECIMALS)


def _same_shown(value: float, default: Any, decimals: int) -> bool:
    """Whether ``value`` is ``default`` as rounded for an editor with ``decimals`` places."""
    try:
        return round(float(default), decimals) == round(value, decimals)
    except (TypeError, ValueError, OverflowError):
        return False


def color_field(value: str, on_change) -> QWidget:
    """A colour's text field with a picker button; the field is ``.line_edit``."""
    field = QWidget()
    row = QHBoxLayout(field)
    row.setContentsMargins(0, 0, 0, 0)
    line = QLineEdit(value)
    line.textChanged.connect(on_change)
    button = make_button('Choose...')

    def choose():
        color = QColorDialog.getColor(parent=field)
        if color.isValid():
            line.setText(color.name())

    button.clicked.connect(choose)
    row.addWidget(line)
    row.addWidget(button)
    field.line_edit = line
    return field


class ImagePathField(QWidget):
    """An optional image file: its name, Choose... and Clear."""

    changed = pyqtSignal()

    def __init__(self, path: Optional[str], config_dir: str, parent=None):
        super().__init__(parent)
        self._config_dir = config_dir
        self._path = path or None
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        self.label = QLineEdit()
        self.label.setReadOnly(True)
        self.label.setPlaceholderText('None')
        choose = make_button('Choose...')
        choose.clicked.connect(self.choose)
        clear = make_button('Clear')
        clear.clicked.connect(lambda: self.set_path(None))
        row.addWidget(self.label, stretch=1)
        row.addWidget(choose)
        row.addWidget(clear)
        self.set_path(self._path)

    def path(self) -> Optional[str]:
        return self._path

    def set_path(self, path: Optional[str]) -> None:
        self._path = path or None
        self.label.setText(self._path or '')
        self.changed.emit()

    def choose(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, 'Select Image', '',
                                              'Images (*.png *.jpg *.jpeg *.gif *.svg *.bmp)')
        if path:
            # Relative when under the config folder, like any key icon.
            self.set_path(relativize_icon_path(path, self._config_dir))


class WidgetImagesForm(QWidget):
    """
    A widget key's own images: one base image, one per state, and the badge style.

    ``values()`` returns ``(icon, state_icons, badge)`` as config.yml spells
    them; a badge in its default style is left out.
    """

    changed = pyqtSignal()

    def __init__(self, spec: Optional[WidgetSpec], icon: Optional[str], state_icons: Mapping[str, str],
                 badge: Any, config_dir: str, parent=None):
        super().__init__(parent)
        self._config_dir = config_dir
        self._spec = spec
        states = spec.states if spec else ()
        # State images for states this widget doesn't declare (e.g. after a
        # widget upgrade) are kept untouched rather than dropped silently.
        self._kept_states = {k: v for k, v in (state_icons or {}).items() if k not in states}
        self._initial_badge = badge
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        intro = QLabel('Show your own images instead of what the widget draws. A state without '
                       'an image uses the base image; with no base image, the widget\'s drawing.')
        intro.setWordWrap(True)
        layout.addWidget(intro)
        form = QFormLayout()
        layout.addLayout(form)

        self.base = ImagePathField(icon, config_dir)
        self.base.changed.connect(self.changed)
        form.addRow('Base image:', self.base)
        self.state_fields: Dict[str, ImagePathField] = {}
        for state in states:
            field = ImagePathField((state_icons or {}).get(state), config_dir)
            field.changed.connect(self.changed)
            self.state_fields[state] = field
            form.addRow(f"When {state.replace('_', ' ')}:", field)

        self.badge_show = None
        if spec is not None and spec.supports_badge:
            style = badge if isinstance(badge, Mapping) else {}
            self.badge_show = QCheckBox('Draw the widget\'s badge on the image')
            self.badge_show.setChecked(badge is not False)
            self.badge_show.toggled.connect(self.changed)
            form.addRow('Badge:', self.badge_show)
            self.badge_position = QComboBox()
            for position in BADGE_POSITIONS:
                self.badge_position.addItem(position.replace('_', ' ').capitalize(), position)
            self.badge_position.setCurrentIndex(max(0, self.badge_position.findData(
                style.get('position', 'top_right'))))
            self.badge_position.currentIndexChanged.connect(self.changed)
            form.addRow('Badge corner:', self.badge_position)
            self.badge_color = color_field(style.get('color', DEFAULT_BADGE['color']), self.changed)
            form.addRow('Badge colour:', self.badge_color)
            self.badge_text_color = color_field(style.get('text_color', DEFAULT_BADGE['text_color']), self.changed)
            form.addRow('Badge text:', self.badge_text_color)

    def badge_value(self) -> Any:
        if self.badge_show is None:
            return self._initial_badge
        if not self.badge_show.isChecked():
            return False
        chosen = {'position': self.badge_position.currentData(),
                  'color': self.badge_color.line_edit.text().strip(),
                  'text_color': self.badge_text_color.line_edit.text().strip()}
        style = {key: value for key, value in chosen.items() if value != DEFAULT_BADGE[key]}
        return style or None

    def values(self):
        state_icons = dict(self._kept_states)
        state_icons.update({state: field.path() for state, field in self.state_fields.items() if field.path()})
        return self.base.path(), state_icons, self.badge_value()

    def appearance(self) -> Appearance:
        icon, state_icons, badge = self.values()
        return Appearance.from_key_config({'icon': icon, 'state_icons': state_icons,
                                           'badge': True if badge is None else badge}, self._config_dir)


def rich_text(text: str) -> str:
    """Plain text for a label that renders rich text, such as a tooltip."""
    return '<p>' + html.escape(text).replace('\n', '<br>') + '</p>'


def describe_spec(spec: WidgetSpec) -> str:
    lines = [spec.description or 'No description.']
    if spec.manifest.get('author'):
        lines.append(f"By {spec.manifest['author']}.")
    if spec.builtin:
        lines.append('Built in.')
    else:
        lines.append('Third-party: runs as a separate program with your permissions.')
        if spec.capabilities:
            lines.append('It ' + ', '.join(spec.capabilities) + '.')
    if spec.problem:
        lines.append(f'Cannot run: {spec.problem}.')
    return '\n'.join(lines)


class WidgetManagerDialog(ThemedDialog):
    """Lists the widgets, and installs, removes and re-approves third-party ones."""

    widgets_changed = pyqtSignal()

    def __init__(self, registry: Optional[WidgetRegistry] = None, parent=None):
        super().__init__(title='Widgets', parent=parent)
        self.registry = registry or shared_registry()
        self.installer = WidgetInstaller(self.registry)
        self.setMinimumSize(640, 460)

        layout = self.content_layout
        intro = QLabel('Widgets are keys that draw themselves: a clock, a mute indicator. '
                       'Choose one in a key\'s editor under Display Type → Widget.')
        intro.setWordWrap(True)
        layout.addWidget(intro)

        body = QHBoxLayout()
        self.list = QListWidget()
        self.list.currentItemChanged.connect(self._show_details)
        body.addWidget(self.list, stretch=1)

        details = QVBoxLayout()
        self.details = QLabel()
        self.details.setWordWrap(True)
        self.details.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.details.setMinimumWidth(260)
        details.addWidget(self.details, stretch=1)
        self.install_btn = make_button('Install...')
        self.install_btn.clicked.connect(self.install)
        self.approve_btn = make_button('Approve Again...')
        self.approve_btn.clicked.connect(self.approve_again)
        self.remove_btn = make_button('Remove', 'danger')
        self.remove_btn.clicked.connect(self.remove)
        for button in (self.install_btn, self.approve_btn, self.remove_btn):
            details.addWidget(button)
        body.addLayout(details, stretch=1)
        layout.addLayout(body)

        self.add_actions('Close', self.accept, cancel=None)
        self.refresh()

    def refresh(self, select: Optional[str] = None) -> None:
        self.list.clear()
        for spec in self.registry.all():
            suffix = '' if spec.builtin else ' — third-party'
            if spec.problem:
                suffix += ' (needs approval)'
            item = QListWidgetItem(f'{spec.name} {spec.version}{suffix}')
            item.setData(Qt.ItemDataRole.UserRole, spec.id)
            self.list.addItem(item)
            if spec.id == select:
                self.list.setCurrentItem(item)
        if self.list.currentItem() is None and self.list.count():
            self.list.setCurrentRow(0)
        self._show_details()

    def selected(self) -> Optional[WidgetSpec]:
        item = self.list.currentItem()
        return self.registry.get(item.data(Qt.ItemDataRole.UserRole)) if item else None

    def _show_details(self, *_args) -> None:
        spec = self.selected()
        self.details.setText(f'<b>{html.escape(spec.name)}</b> <i>{html.escape(spec.id)}</i><br>'
                             + '<br>'.join(html.escape(line) for line in describe_spec(spec).split('\n'))
                             if spec else '')
        third_party = spec is not None and not spec.builtin
        self.remove_btn.setEnabled(third_party)
        self.approve_btn.setVisible(third_party and spec.problem is not None)

    # ── actions ───────────────────────────────────────────────────────────

    def choose_source(self) -> Optional[str]:
        """A .py file; picking a folder's widget.py installs the whole folder, once the user agrees."""
        path, _ = QFileDialog.getOpenFileName(self, 'Install Widget', '', 'Python widget (*.py)')
        if not path:
            return None
        if os.path.basename(path) != ENTRY_FILE:
            return path
        folder = os.path.dirname(path)
        return folder if self.confirm_folder(folder) else None

    def confirm_folder(self, folder: str) -> bool:
        """
        Everything beside a widget.py is copied and approved with it.

        Picking ~/Downloads/widget.py would otherwise take the whole Downloads
        folder along, so the user sees what is about to be copied.
        """
        count = sum(len(files) for _root, _dirs, files in os.walk(folder))
        box = self._box(QMessageBox.Icon.Question, 'Install Widget',
                        f'Install the whole folder {folder} ({count} files)?')
        box.setInformativeText(f'A file named {ENTRY_FILE} is installed together with everything '
                               'in its folder.')
        self._plain(box)
        box.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel)
        return box.exec() == QMessageBox.StandardButton.Yes

    def install(self) -> None:
        source = self.choose_source()
        if not source:
            return
        staged = self._stage(lambda: self.installer.stage(source))
        if staged is None:
            return
        try:
            title = 'Cannot install this widget'
            if not self._report_errors(staged.report, title):
                return
            manifest = staged.report.manifest
            existing = self.installer.installed(manifest['id'])
            replacing = f"\n\nThis replaces the installed version {existing.version}." if existing else ''
            if not self.confirm_consent(staged.report, f"Install {manifest['name']} {manifest['version']}?",
                                        replacing):
                return
            # The test run executes the widget, so it waits for consent.
            self._busy(lambda: self.installer.test_run(staged))
            if not self._report_errors(staged.report, title):
                return
            try:
                self.installer.install(staged)
            except (InstallError, OSError) as exc:
                self._message(QMessageBox.Icon.Critical, 'Install failed', str(exc))
                return
        finally:
            self.installer.discard(staged)
        self.refresh(select=manifest['id'])
        self.widgets_changed.emit()

    def approve_again(self) -> None:
        spec = self.selected()
        if spec is None or spec.builtin:
            return
        staged = self._stage(lambda: self.installer.stage_installed(spec.id))
        if staged is None:
            return
        try:
            title = 'The changed widget does not pass validation'
            if not self._report_errors(staged.report, title):
                return
            if not self.confirm_consent(staged.report, f'Approve the changed files of {spec.name}?', '',
                                        'Approve'):
                return
            self._busy(lambda: self.installer.test_run(staged))
            if not self._report_errors(staged.report, title):
                return
            try:
                self.installer.approve(spec.id, staged)
            except (InstallError, OSError) as exc:
                self._message(QMessageBox.Icon.Critical, 'Approval failed', str(exc))
                return
        finally:
            self.installer.discard(staged)
        self.refresh(select=spec.id)
        self.widgets_changed.emit()

    def remove(self) -> None:
        spec = self.selected()
        if spec is None or spec.builtin:
            return
        box = self._box(QMessageBox.Icon.Question, 'Remove Widget',
                        f'Remove {spec.name}? Keys that use it will show an error tile until you pick another widget.')
        box.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if box.exec() != QMessageBox.StandardButton.Yes:
            return
        try:
            self.installer.remove(spec.id)
        except (InstallError, OSError) as exc:
            self._message(QMessageBox.Icon.Critical, 'Remove failed', str(exc))
        self.refresh()
        self.widgets_changed.emit()

    def _stage(self, work) -> Optional[StagedWidget]:
        try:
            return self._busy(work)
        except (InstallError, OSError) as exc:
            self._message(QMessageBox.Icon.Critical, 'Cannot read this widget', str(exc))
            return None

    def confirm_consent(self, report: ValidationReport, question: str, extra: str,
                        accept_label: str = 'Install') -> bool:
        """Ask before running third-party code; a method so tests can answer it."""
        manifest = report.manifest
        lines = [f"{manifest['name']} by {manifest.get('author') or 'an unknown author'}.",
                 '',
                 'A widget is a program. It runs with your user\'s permissions and can read '
                 'your files; install it only if you trust where it came from.']
        if report.capabilities:
            lines += ['', 'This one also:'] + [f'  • {capability}' for capability in report.capabilities]
        if report.warnings:
            lines += ['', 'Warnings:'] + [f'  • {warning}' for warning in report.warnings]
        box = self._box(QMessageBox.Icon.Warning, 'Third-party Widget', question)
        box.setInformativeText('\n'.join(lines) + extra)
        self._plain(box)
        box.setStandardButtons(QMessageBox.StandardButton.Cancel)
        accept = box.addButton(accept_label, QMessageBox.ButtonRole.AcceptRole)
        box.exec()
        return box.clickedButton() is accept

    def _report_errors(self, report: ValidationReport, title: str) -> bool:
        if report.ok:
            return True
        box = self._box(QMessageBox.Icon.Critical, title, report.errors[0])
        box.setDetailedText('\n'.join(report.errors))
        box.exec()
        return False

    def _box(self, icon: QMessageBox.Icon, title: str, text: str) -> QMessageBox:
        """A message box that shows its text as typed: names and errors come from the widget."""
        box = QMessageBox(self)
        box.setIcon(icon)
        box.setWindowTitle(title)
        box.setText(text)
        self._plain(box)
        return box

    @staticmethod
    def _plain(box: QMessageBox) -> None:
        # The informative label is created lazily and doesn't always follow
        # setTextFormat, so it is set directly as well.
        box.setTextFormat(Qt.TextFormat.PlainText)
        for label in box.findChildren(QLabel):
            label.setTextFormat(Qt.TextFormat.PlainText)

    def _message(self, icon: QMessageBox.Icon, title: str, text: str) -> None:
        self._box(icon, title, text).exec()

    @staticmethod
    def _busy(work):
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            return work()
        finally:
            QApplication.restoreOverrideCursor()
