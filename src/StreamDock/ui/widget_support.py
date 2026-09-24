"""
Widget pieces of the editor: previews, the options form and the manager dialog.

Previews are snapshots, drawn once per (widget, options) off the GUI thread:
a built-in in a worker thread, a third-party widget in a throwaway child
process, the same way it would run on the device.
"""

import json
import logging
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Dict, List, Mapping, Optional

from PIL import Image
from PyQt6.QtCore import QObject, Qt, pyqtSignal
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
from StreamDock.widgets.installer import InstallError, WidgetInstaller
from StreamDock.widgets.registry import ENTRY_FILE, WidgetRegistry, WidgetSpec
from StreamDock.widgets.runners import render_in_subprocess
from StreamDock.widgets.validator import ValidationReport

logger = logging.getLogger(__name__)

PREVIEW_TIMEOUT = 3.0
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


def _cache_key(widget_id: str, options: Mapping[str, Any], appearance: Optional[Appearance]) -> str:
    return json.dumps([widget_id, dict(options), repr(appearance)], sort_keys=True, default=str)


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
            snapshot = render_in_subprocess(spec.script_path, resolved, KEY_SIZE, PREVIEW_TIMEOUT)
            frame, state, badge = snapshot.frame, snapshot.state, snapshot.badge
    except Exception:  # pylint: disable=broad-exception-caught
        logger.warning("Preview of widget '%s' failed", widget_id, exc_info=True)
        return error_tile(widget_id)
    if appearance is None or not appearance.uses_images:
        return frame
    if badge is None and spec.supports_badge:
        badge = SAMPLE_BADGE
    return compose(appearance, state, badge, frame, KEY_SIZE) or frame


class WidgetPreviewService(QObject):
    """Cached widget snapshots; ``preview_ready`` fires when a requested one arrives."""

    preview_ready = pyqtSignal(str)
    _rendered = pyqtSignal(str, object)

    def __init__(self, registry: Optional[WidgetRegistry] = None, parent=None):
        super().__init__(parent)
        self._registry = registry or shared_registry()
        self._cache: Dict[str, QPixmap] = {}
        self._pending = set()
        self._pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix='widget-preview')
        self._rendered.connect(self._store)

    @staticmethod
    def key(widget_id: str, options: Mapping[str, Any], appearance: Optional[Appearance] = None) -> str:
        return _cache_key(widget_id, options, appearance)

    def pixmap(self, widget_id: str, options: Mapping[str, Any],
               appearance: Optional[Appearance] = None) -> Optional[QPixmap]:
        """The cached snapshot, or None after starting to draw one."""
        key = _cache_key(widget_id, options, appearance)
        if key in self._cache:
            return self._cache[key]
        if key not in self._pending:
            self._pending.add(key)
            spec = self._registry.get(widget_id)
            options = dict(options)
            self._pool.submit(
                lambda: self._rendered.emit(key, render_preview(spec, widget_id, options, appearance)))
        return None

    def clear(self) -> None:
        """Forget every snapshot, e.g. after a widget was installed or removed."""
        self._cache.clear()

    def _store(self, key: str, image: Image.Image) -> None:
        self._pending.discard(key)
        self._cache[key] = pil_to_pixmap(image)
        self.preview_ready.emit(key)


_shared_previews: Optional[WidgetPreviewService] = None


def shared_previews() -> WidgetPreviewService:
    global _shared_previews  # pylint: disable=global-statement
    if _shared_previews is None:
        _shared_previews = WidgetPreviewService(shared_registry())
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
            if option.description:
                editor.setToolTip(option.description)
            form.addRow(f'{option.display_label}:', editor)
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
            editor.setRange(int(option.minimum) if option.minimum is not None else -1_000_000,
                            int(option.maximum) if option.maximum is not None else 1_000_000)
            editor.setValue(int(value))
            editor.valueChanged.connect(self.changed)
        elif kind == 'float':
            editor = QDoubleSpinBox()
            editor.setDecimals(2)
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
            if value != option.default or option.key in self._initial:
                result[option.key] = value
        return result


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
        self.details.setText(f'<b>{spec.name}</b> <i>{spec.id}</i><br>'
                             + describe_spec(spec).replace('\n', '<br>') if spec else '')
        third_party = spec is not None and not spec.builtin
        self.remove_btn.setEnabled(third_party)
        self.approve_btn.setVisible(third_party and spec.problem is not None)

    # ── actions ───────────────────────────────────────────────────────────

    def choose_source(self) -> Optional[str]:
        """A .py file; picking a folder's widget.py installs the whole folder."""
        path, _ = QFileDialog.getOpenFileName(self, 'Install Widget', '', 'Python widget (*.py)')
        if not path:
            return None
        return path.rsplit('/', 1)[0] if path.endswith('/' + ENTRY_FILE) else path

    def install(self) -> None:
        source = self.choose_source()
        if not source:
            return
        report = self._busy(lambda: self.installer.validate(source))
        if not self._report_errors(report, 'Cannot install this widget'):
            return
        manifest = report.manifest
        existing = self.installer.installed(manifest['id'])
        replacing = f"\n\nThis replaces the installed version {existing.version}." if existing else ''
        if not self.confirm_consent(report, f"Install {manifest['name']} {manifest['version']}?", replacing):
            return
        try:
            self.installer.install(source, report)
        except (InstallError, OSError) as exc:
            QMessageBox.critical(self, 'Install failed', str(exc))
            return
        self.refresh(select=manifest['id'])
        self.widgets_changed.emit()

    def approve_again(self) -> None:
        spec = self.selected()
        if spec is None or spec.builtin:
            return
        report = self._busy(lambda: self.installer.revalidate(spec.id))
        if not self._report_errors(report, 'The changed widget does not pass validation'):
            return
        if not self.confirm_consent(report, f'Approve the changed files of {spec.name}?', ''):
            return
        self.installer.approve(spec.id, report)
        self.refresh(select=spec.id)
        self.widgets_changed.emit()

    def remove(self) -> None:
        spec = self.selected()
        if spec is None or spec.builtin:
            return
        answer = QMessageBox.question(
            self, 'Remove Widget',
            f'Remove {spec.name}? Keys that use it will show an error tile until you pick another widget.')
        if answer != QMessageBox.StandardButton.Yes:
            return
        self.installer.remove(spec.id)
        self.refresh()
        self.widgets_changed.emit()

    def confirm_consent(self, report: ValidationReport, question: str, extra: str) -> bool:
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
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Icon.Warning)
        box.setWindowTitle('Third-party Widget')
        box.setText(question)
        box.setInformativeText('\n'.join(lines) + extra)
        box.setStandardButtons(QMessageBox.StandardButton.Cancel)
        accept = box.addButton('Install' if 'Install' in question else 'Approve',
                               QMessageBox.ButtonRole.AcceptRole)
        box.exec()
        return box.clickedButton() is accept

    def _report_errors(self, report: ValidationReport, title: str) -> bool:
        if report.ok:
            return True
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Icon.Critical)
        box.setWindowTitle(title)
        box.setText(report.errors[0])
        box.setDetailedText('\n'.join(report.errors))
        box.exec()
        return False

    @staticmethod
    def _busy(work):
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            return work()
        finally:
            QApplication.restoreOverrideCursor()
