#!/usr/bin/env python3
"""
Dialogs for StreamDock Configuration Editor
Handles key editing, action editing, and layout management
"""

import copy
import html
import os
import re
import shlex
from pathlib import Path

from StreamDock.application.config_document import (
    DEFAULT_DOUBLE_PRESS_INTERVAL, DEFAULT_LONG_PRESS_DURATION, DEFAULT_TEXT_POSITION,
    KeyDefinition)
from StreamDock.business_logic.action_type import ActionType
from StreamDock.application.configuration_manager import (
    MAX_FONT_SIZE,
    MIN_FONT_SIZE,
    relativize_icon_path,
    resolve_icon_path,
)
from StreamDock.ui.chrome import ThemedDialog, make_button
from StreamDock.ui.widgets import (
    ActionListContainer,
    ActionListItem,
    SIDEBAR_CAPTION_ROLE,
    KeySquare,
    SegmentedControl,
    SidebarRowDelegate,
    ToggleSwitch,
    _font_size,
    glyph_button,
)
from StreamDock.ui.styles import get_colors
from StreamDock.ui.widget_support import (
    WidgetImagesForm,
    WidgetOptionsForm,
    describe_spec,
    shared_previews,
    shared_registry,
)
from StreamDock.ui.theme import Flavor, current_theme, themed_icon
from PIL import Image
from PyQt6.QtCore import QRect, QSize, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import (QColor, QFont, QFontMetrics, QIcon, QImage, QKeySequence, QPalette,
                         QPixmap, QShortcut)
from PyQt6.QtWidgets import (
    QApplication,
    QButtonGroup,
    QCheckBox,
    QColorDialog,
    QComboBox,
    QDialog,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QRadioButton,
    QScrollArea,
    QSizePolicy,
    QSpinBox,
    QStyle,
    QStyledItemDelegate,
    QStyleOptionViewItem,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

COLORS = get_colors()

# The ways a key can be drawn, as the segmented control spells them.
DISPLAY_ICON = "Icon"
DISPLAY_TEXT = "Text"
DISPLAY_WIDGET = "Widget"

# Where a label sits over an icon, as the runtime's renderer names it.
TEXT_POSITIONS = ("bottom", "center", "top")


# Labels that Title Case gets wrong. Everything else is derived from
# ActionType, so an action added to the runtime cannot go missing from the
# editor - CHANGE_KEY_TEXT was absent from the hand-written list for exactly
# that reason.
_ACTION_TYPE_LABEL_OVERRIDES = {
    "DBUS": "D-Bus",
    "CHANGE_KEY_IMAGE": "Change Key Image",
    "CHANGE_KEY_TEXT": "Change Key Text",
}

_ACTION_TYPE_DISPLAY = {
    action.name: _ACTION_TYPE_LABEL_OVERRIDES.get(
        action.name, action.name.replace("_", " ").title())
    for action in ActionType
}


def _as_text(value) -> str:
    """
    Render an action payload as editable text.

    Payloads are only loosely validated - `KEY_PRESS: ["ctrl","c"]` and
    `TYPE_TEXT: 42` both pass - and a QLineEdit accepts nothing but a string.

    Args:
        value: Whatever the configuration held

    Returns:
        A string safe to put in a text field
    """
    if value is None:
        return ""
    return value if isinstance(value, str) else str(value)


def _as_int(value, default: int) -> int:
    """
    Coerce an action payload into a spin-box value.

    Args:
        value: Whatever the configuration held
        default: Used when the value is missing or not a number

    Returns:
        An int
    """
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _as_float(value, default: float) -> float:
    """
    Coerce an action payload into a double spin-box value.

    Args:
        value: Whatever the configuration held
        default: Used when the value is missing or not a number

    Returns:
        A float
    """
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _split_command(text: str):
    """
    Split a typed command line into argv, shell-style.

    Quotes keep an argument with spaces whole; unbalanced quotes fall back to
    whitespace splitting rather than losing the text.

    Returns:
        A list for several arguments, a plain string for one
    """
    try:
        parts = shlex.split(text)
    except ValueError:
        parts = text.split()
    if not parts:
        return text
    return parts if len(parts) > 1 else parts[0]


def _join_command(command) -> str:
    """Show a list command as a line _split_command reads back to the same list."""
    if isinstance(command, list):
        return shlex.join(str(part) for part in command)
    return _as_text(command)


def _clear_layout(layout) -> None:
    """
    Empty a layout now, sub-layouts included.

    Unparenting takes each widget out of the dialog at once: deleteLater alone
    left the old radio buttons alive beside the new ones until the event loop
    ran, sharing their auto-exclusive group, and nested layouts' widgets were
    never removed at all.
    """
    while layout.count():
        item = layout.takeAt(0)
        widget = item.widget()
        child = item.layout()
        if widget is not None:
            widget.hide()
            widget.setParent(None)
            widget.deleteLater()
        elif child is not None:
            _clear_layout(child)
            child.setParent(None)
            child.deleteLater()


def _fill_names(combo: QComboBox, names: list, placeholder: str) -> None:
    """Offer names, each carrying itself as data; a disabled placeholder when there are none."""
    for name in names:
        combo.addItem(name, name)
    if not names:
        combo.addItem(placeholder)
        combo.setEnabled(False)


def _select_name(combo: QComboBox, name) -> None:
    """
    Select a target, listing it as missing when the config no longer has it.

    Silently falling back to the first entry would retarget the action on OK.
    """
    if not isinstance(name, str) or not name:
        return
    index = combo.findData(name)
    if index < 0:
        if not combo.isEnabled():
            combo.clear()
            combo.setEnabled(True)
        combo.addItem(f"{name} (missing)", name)
        index = combo.count() - 1
    combo.setCurrentIndex(index)


def create_styled_button(text: str, primary: bool = False) -> QPushButton:
    """Create a dialog button at the size the active design uses

    Args:
        text: Button text
        primary: If True, use the accent colour

    Returns:
        The button
    """
    return make_button(text, "primary" if primary else "")


class KeyEditorDialog(ThemedDialog):
    """Dialog for creating or editing a key"""
    
    def __init__(self, key_def: KeyDefinition = None, existing_keys: list = None, 
                 available_layouts: list = None, available_keys: list = None,
                 config_dir: str = None, parent=None, widget_registry=None, widget_previews=None):
        super().__init__(parent=parent)
        self.key_def = key_def or KeyDefinition("NewKey")
        self.widget_registry = widget_registry or shared_registry()
        self.widget_previews = widget_previews or shared_previews()
        self.widget_options_form = None
        self.widget_images_form = None
        self.existing_keys = existing_keys or []
        self.available_layouts = available_layouts or []
        self.available_keys = available_keys or []
        self.selected_icon_path = None
        # Directory relative icon paths resolve against.
        self.config_dir = config_dir or os.getcwd()
        
        self.setWindowTitle("Edit Key" if key_def else "Create New Key")
        self.setMinimumSize(600, 750)
        self.resize(650, 860)
        
        self.setup_ui()
        self.load_key_data()
    
    def setup_ui(self):
        """Setup the UI"""
        layout = self.content_layout
        
        # Key name and display type, in a form so their labels line up
        # with the rows underneath
        header_form = QFormLayout()
        self.name_edit = QLineEdit(self.key_def.name)
        header_form.addRow("Key Name:", self.name_edit)
        
        # Display type: three choices, so one pill rather than a box of radios
        self.display_type = SegmentedControl([DISPLAY_ICON, DISPLAY_TEXT, DISPLAY_WIDGET])
        header_form.addRow("Display Type:", self.display_type)
        layout.addLayout(header_form)
        
        # Icon settings (in a container for show/hide)
        self.icon_widget = QWidget()
        icon_layout = QVBoxLayout(self.icon_widget)
        
        icon_select_layout = QHBoxLayout()
        self.icon_path_label = QLabel("No icon selected")
        icon_select_layout.addWidget(self.icon_path_label)
        self.icon_select_btn = create_styled_button("Select Icon...")
        self.icon_select_btn.clicked.connect(self.select_icon)
        icon_select_layout.addWidget(self.icon_select_btn)
        icon_layout.addLayout(icon_select_layout)
        
        # Icon preview with dark mode styling
        self.icon_preview = QLabel()
        self.icon_preview.setFixedSize(112, 112)
        self.icon_preview.setStyleSheet(f"""
            QLabel {{
                border: {current_theme().metrics.border_width}px solid {COLORS['border']};
                background-color: {COLORS['bg_input']};
                border-radius: {current_theme().metrics.radius}px;
            }}
        """)
        self.icon_preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon_layout.addWidget(self.icon_preview)
        
        layout.addWidget(self.icon_widget)
        
        # Text settings (in a container for show/hide). An icon key shares
        # them for its optional label, drawn over the icon on the device.
        self.text_widget = QWidget()
        text_layout = QFormLayout(self.text_widget)
        self.text_form = text_layout
        
        self.text_edit = QLineEdit()
        self.text_row_label = QLabel("Text:")
        text_layout.addRow(self.text_row_label, self.text_edit)

        self.text_position_combo = QComboBox()
        self.text_position_combo.addItems(TEXT_POSITIONS)
        text_layout.addRow("Label Position:", self.text_position_combo)
        
        text_color_layout = QHBoxLayout()
        self.text_color_edit = QLineEdit("white")
        text_color_layout.addWidget(self.text_color_edit)
        self.text_color_btn = create_styled_button("Choose...")
        self.text_color_btn.clicked.connect(self.choose_text_color)
        text_color_layout.addWidget(self.text_color_btn)
        text_layout.addRow("Text Color:", text_color_layout)
        
        bg_color_layout = QHBoxLayout()
        self.bg_color_edit = QLineEdit("black")
        bg_color_layout.addWidget(self.bg_color_edit)
        self.bg_color_btn = create_styled_button("Choose...")
        self.bg_color_btn.clicked.connect(self.choose_bg_color)
        bg_color_layout.addWidget(self.bg_color_btn)
        text_layout.addRow("Background Color:", bg_color_layout)
        
        self.font_size_spin = QSpinBox()
        # The validator's bounds, so a size the file may hold is never
        # clamped by merely opening the key.
        self.font_size_spin.setRange(MIN_FONT_SIZE, MAX_FONT_SIZE)
        self.font_size_spin.setValue(20)
        text_layout.addRow("Font Size:", self.font_size_spin)
        
        self.bold_toggle = ToggleSwitch()
        self.bold_toggle.setChecked(True)
        text_layout.addRow("Bold:", self.bold_toggle)
        self.text_edit.textChanged.connect(self._update_text_rows)
        
        layout.addWidget(self.text_widget)

        self._build_widget_section(layout)
        
        # Actions tabs
        self.tabs = QTabWidget()
        
        self.press_actions_widget = ActionEditorWidget(self.available_layouts, self.available_keys,
                                                config_dir=self.config_dir)
        self.tabs.addTab(self.press_actions_widget, "On Press")
        
        self.release_actions_widget = ActionEditorWidget(self.available_layouts, self.available_keys,
                                                config_dir=self.config_dir)
        self.tabs.addTab(self.release_actions_widget, "On Release")
        
        self.double_press_actions_widget = ActionEditorWidget(self.available_layouts, self.available_keys,
                                                config_dir=self.config_dir)
        self.tabs.addTab(self.double_press_actions_widget, "On Double Press")
        
        self.long_press_actions_widget = ActionEditorWidget(self.available_layouts, self.available_keys,
                                                config_dir=self.config_dir)
        self.tabs.addTab(self.long_press_actions_widget, "On Long Press")
        
        layout.addWidget(self.tabs)
        
        self.add_actions("Save", self.accept)
        
        self.display_type.selection_changed.connect(self.update_display_type)
    
    def _build_widget_section(self, layout):
        """The widget picker, its options form and a preview of the result."""
        self.widget_widget = QWidget()
        widget_layout = QVBoxLayout(self.widget_widget)
        widget_layout.setContentsMargins(0, 0, 0, 0)

        picker = QFormLayout()
        self.widget_combo = QComboBox()
        for spec in self.widget_registry.all():
            label = f"{spec.name} ({spec.version})"
            if not spec.builtin:
                label += " — third-party"
            self.widget_combo.addItem(label, spec.id)
        picker.addRow("Widget:", self.widget_combo)
        widget_layout.addLayout(picker)

        row = QHBoxLayout()
        self.widget_description = QLabel()
        # Third-party manifests supply this text; rich text would let one
        # inject links and markup into the dialog.
        self.widget_description.setTextFormat(Qt.TextFormat.PlainText)
        self.widget_description.setWordWrap(True)
        self.widget_description.setAlignment(Qt.AlignmentFlag.AlignTop)
        row.addWidget(self.widget_description, stretch=1)
        self.widget_preview = QLabel()
        self.widget_preview.setFixedSize(112, 112)
        self.widget_preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.widget_preview.setStyleSheet("background-color: #000000;")
        row.addWidget(self.widget_preview)
        widget_layout.addLayout(row)

        # Options and the key's own images, as tabs so the dialog stays short.
        self.widget_tabs = QTabWidget()
        self.widget_tabs.setMinimumHeight(240)
        holders = []
        for title in ("Options", "Images"):
            page = QWidget()
            holder = QVBoxLayout(page)
            holder.addStretch()
            holders.append(holder)
            scroll = QScrollArea()
            scroll.setWidgetResizable(True)
            scroll.setFrameShape(QScrollArea.Shape.NoFrame)
            scroll.setWidget(page)
            self.widget_tabs.addTab(scroll, title)
        self.widget_options_holder, self.widget_images_holder = holders
        widget_layout.addWidget(self.widget_tabs)
        layout.addWidget(self.widget_widget)

        # Options change on every keystroke; draw once typing pauses.
        self._preview_timer = QTimer(self)
        self._preview_timer.setSingleShot(True)
        self._preview_timer.setInterval(300)
        self._preview_timer.timeout.connect(self.update_widget_preview)
        self.widget_previews.preview_ready.connect(self._on_preview_ready)
        self.widget_combo.currentIndexChanged.connect(lambda _index: self._rebuild_widget_options({}))

    @staticmethod
    def _discard(form, holder):
        if form is not None:
            # deleteLater only acts back in the event loop; hide it now so the
            # old form never shows through the new one.
            form.hide()
            holder.removeWidget(form)
            form.deleteLater()

    def select_widget(self, widget_id: str) -> None:
        """Pick a widget by id, listing it as not installed when it is unknown."""
        index = self.widget_combo.findData(widget_id)
        if index < 0:
            self.widget_combo.addItem(f"{widget_id} (not installed)", widget_id)
            index = self.widget_combo.count() - 1
        self.widget_combo.setCurrentIndex(index)

    def current_widget_id(self):
        return self.widget_combo.currentData()

    def _rebuild_widget_options(self, values, images=None):
        """
        Build the forms for the chosen widget.

        ``images`` is (icon, state_icons, badge); by default the base image and
        badge carry over from the previous widget, and state images - named
        after the previous widget's states - do not.
        """
        if images is None:
            icon, _, badge = self.widget_images_form.values() if self.widget_images_form else (None, {}, None)
            images = (icon, {}, badge)
        self._discard(self.widget_options_form, self.widget_options_holder)
        self._discard(self.widget_images_form, self.widget_images_holder)
        self.widget_options_form = None
        spec = self.widget_registry.get(self.current_widget_id() or "")
        self.widget_description.setText(describe_spec(spec) if spec else
                                        "This widget is not installed. Its settings are kept as they are.")
        self._unknown_widget_options = dict(values) if spec is None else {}
        if spec is not None:
            self.widget_options_form = WidgetOptionsForm(spec.options, values)
            self.widget_options_form.changed.connect(self._preview_timer.start)
            self.widget_options_holder.insertWidget(0, self.widget_options_form)
        self.widget_images_form = WidgetImagesForm(spec, *images, self.config_dir)
        self.widget_images_form.changed.connect(self._preview_timer.start)
        self.widget_images_holder.insertWidget(0, self.widget_images_form)
        self.update_widget_preview()

    def widget_options(self) -> dict:
        if self.widget_options_form is None:
            return dict(getattr(self, "_unknown_widget_options", {}))
        return self.widget_options_form.values()

    def widget_appearance(self):
        return self.widget_images_form.appearance() if self.widget_images_form else None

    def update_widget_preview(self):
        widget_id = self.current_widget_id()
        if not widget_id:
            return
        pixmap = self.widget_previews.pixmap(widget_id, self.widget_options(), self.widget_appearance())
        if pixmap is None:
            self.widget_preview.setText("…")
        else:
            self.widget_preview.setPixmap(pixmap)

    def _on_preview_ready(self, key: str):
        widget_id = self.current_widget_id()
        if widget_id and key == self.widget_previews.key(widget_id, self.widget_options(),
                                                         self.widget_appearance()):
            self.update_widget_preview()

    def update_display_type(self):
        """Update visible widgets based on display type"""
        current = self.display_type.current()
        self.icon_widget.setVisible(current == DISPLAY_ICON)
        self.text_widget.setVisible(current in (DISPLAY_ICON, DISPLAY_TEXT))
        self.widget_widget.setVisible(current == DISPLAY_WIDGET)
        self._update_text_rows()
        if current == DISPLAY_WIDGET and self.widget_images_form is None:
            self._rebuild_widget_options({})

    def _update_text_rows(self, *_args):
        """
        Text mode shows the text and its style. Icon mode shows an optional
        label, with its position and style only once there is one.
        """
        icon = self.display_type.current() == DISPLAY_ICON
        self.text_row_label.setText("Label:" if icon else "Text:")
        self.text_edit.setPlaceholderText("Optional, drawn over the icon" if icon else "")
        styled = not icon or bool(self.text_edit.text().strip())
        self.text_form.setRowVisible(self.text_position_combo, icon and styled)
        for row in range(2, self.text_form.rowCount()):
            self.text_form.setRowVisible(row, styled)
    
    def select_icon(self):
        """Select an icon file"""
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Select Icon",
            "",
            "Images (*.png *.jpg *.jpeg *.gif *.svg *.bmp)"
        )
        
        if file_path:
            # Store relative when the icon lives under the config directory,
            # so the configuration stays portable.
            self.selected_icon_path = relativize_icon_path(file_path, self.config_dir)
            self.icon_path_label.setText(Path(file_path).name)
            self.load_icon_preview(self.selected_icon_path)
    
    def load_icon_preview(self, icon_path: str):
        """Load and display icon preview"""
        if not icon_path:
            return
        
        # Relative paths resolve against the config file's directory, the
        # same rule the runtime applies.
        icon_file = Path(resolve_icon_path(icon_path, self.config_dir))
        
        if not icon_file.exists():
            self.icon_preview.setText(f"Icon not found:\n{icon_path}")
            return
        
        try:
            # Check if it's an SVG file
            if icon_file.suffix.lower() == '.svg':
                # Use QPixmap directly for SVG files
                pixmap = QPixmap(str(icon_file))
                if pixmap.isNull():
                    self.icon_preview.setText(f"Error loading SVG:\n{icon_path}")
                    return
                
                # Scale to 112x112 while maintaining aspect ratio
                pixmap = pixmap.scaled(112, 112, Qt.AspectRatioMode.KeepAspectRatio, 
                                      Qt.TransformationMode.SmoothTransformation)
                self.icon_preview.setPixmap(pixmap)
            else:
                # Use PIL for raster images (PNG, JPG, etc.)
                img = Image.open(str(icon_file))
                img.thumbnail((112, 112), Image.Resampling.LANCZOS)
                
                # Convert to QPixmap
                img = img.convert("RGBA")
                data = img.tobytes("raw", "RGBA")
                qimg = QImage(data, img.width, img.height, QImage.Format.Format_RGBA8888)
                pixmap = QPixmap.fromImage(qimg)
                
                self.icon_preview.setPixmap(pixmap)
        except Exception as e:
            self.icon_preview.setText(f"Error: {str(e)}")
    
    def choose_text_color(self):
        """Choose text color"""
        color = QColorDialog.getColor()
        if color.isValid():
            self.text_color_edit.setText(color.name())
    
    def choose_bg_color(self):
        """Choose background color"""
        color = QColorDialog.getColor()
        if color.isValid():
            self.bg_color_edit.setText(color.name())
    
    def load_key_data(self):
        """Load existing key data into the dialog"""
        if self.key_def.is_widget():
            self.widget_combo.blockSignals(True)
            self.select_widget(self.key_def.widget)
            self.widget_combo.blockSignals(False)
            self._rebuild_widget_options(self.key_def.widget_options,
                                         (self.key_def.icon, self.key_def.state_icons, self.key_def.badge))
            self.display_type.set_current(DISPLAY_WIDGET)
        elif self.key_def.icon:
            self.display_type.set_current(DISPLAY_ICON)
            self.icon_path_label.setText(self.key_def.icon)
            self.selected_icon_path = self.key_def.icon
            # Load and display the icon preview
            self.load_icon_preview(self.key_def.icon)
        elif self.key_def.text is not None:
            self.display_type.set_current(DISPLAY_TEXT)
        else:
            # Default to icon
            self.display_type.set_current(DISPLAY_ICON)

        if not self.key_def.is_widget():
            # Values straight from the YAML - `text: 42`, `font_size: 20.5`,
            # `bold: "yes"` all load - and Qt's setters take exact types only;
            # coerced the way KeySquare draws them.
            self.text_edit.setText(_as_text(self.key_def.text))
            self.text_color_edit.setText(_as_text(self.key_def.text_color))
            self.bg_color_edit.setText(_as_text(self.key_def.background_color))
            self.font_size_spin.setValue(_font_size(self.key_def.font_size))
            self.bold_toggle.setChecked(bool(self.key_def.bold))
            position = _as_text(self.key_def.text_position) or DEFAULT_TEXT_POSITION
            if self.text_position_combo.findText(position) < 0:
                # Kept as written; the validator decides whether it is valid.
                self.text_position_combo.addItem(position)
            self.text_position_combo.setCurrentText(position)
        
        self.update_display_type()
        
        # Load actions
        self.press_actions_widget.set_actions(self.key_def.on_press_actions)
        self.release_actions_widget.set_actions(self.key_def.on_release_actions)
        self.double_press_actions_widget.set_actions(self.key_def.on_double_press_actions)
        self.long_press_actions_widget.set_actions(self.key_def.on_long_press_actions)
    
    def widget_option_errors(self) -> list:
        """Problems with the widget options as entered, empty when fine."""
        if self.display_type.current() != DISPLAY_WIDGET or self.widget_options_form is None:
            return []
        return self.widget_options_form.errors()

    def accept(self):
        """
        Refuse to close on a name or widget options the runtime would reject.

        Checked here rather than after exec() so a refusal keeps the dialog
        and everything typed into it open.
        """
        name = self.name_edit.text()
        if not name.strip():
            QMessageBox.warning(self, "Invalid key name", "Enter a name for the key.")
            return
        if name in self.existing_keys:
            QMessageBox.warning(self, "Invalid key name",
                                f"A key named '{name}' already exists.")
            return
        errors = self.widget_option_errors()
        if errors:
            QMessageBox.warning(self, "Invalid widget option", errors[0])
            return
        super().accept()

    def done(self, result: int) -> None:
        # The preview service is shared and outlives the dialog; left
        # connected, every later preview would call into a deleted dialog.
        try:
            self.widget_previews.preview_ready.disconnect(self._on_preview_ready)
        except TypeError:
            pass
        super().done(result)

    def get_key_definition(self) -> KeyDefinition:
        """
        Get the key definition from the dialog.

        Starts from the key as loaded, so fields the dialog doesn't show -
        text_position, fields this version doesn't know - survive an edit.
        """
        key_def = copy.deepcopy(self.key_def)
        key_def.name = self.name_edit.text()
        
        if self.display_type.current() == DISPLAY_WIDGET:
            key_def.widget = self.current_widget_id()
            key_def.widget_options = self.widget_options()
            key_def.icon, key_def.state_icons, key_def.badge = self.widget_images_form.values()
            key_def.text = None
        elif self.display_type.current() == DISPLAY_ICON:
            key_def.icon = self.selected_icon_path or self.key_def.icon
            label = self.text_edit.text()
            if label.strip():
                key_def.text = label
                self._store_text_style(key_def)
                key_def.text_position = self.text_position_combo.currentText()
            else:
                key_def.text = None
            key_def.widget = None
            key_def.widget_options = {}
            key_def.state_icons, key_def.badge = {}, None
        else:
            key_def.text = self.text_edit.text()
            self._store_text_style(key_def)
            key_def.icon = None
            key_def.widget = None
            key_def.widget_options = {}
            key_def.state_icons, key_def.badge = {}, None
        
        key_def.on_press_actions = self.press_actions_widget.get_actions()
        key_def.on_release_actions = self.release_actions_widget.get_actions()
        key_def.on_double_press_actions = self.double_press_actions_widget.get_actions()
        key_def.on_long_press_actions = self.long_press_actions_widget.get_actions()
        
        return key_def

    def _store_text_style(self, key_def: KeyDefinition) -> None:
        key_def.text_color = self.text_color_edit.text()
        key_def.background_color = self.bg_color_edit.text()
        key_def.font_size = self.font_size_spin.value()
        key_def.bold = self.bold_toggle.isChecked()


class ActionEditorWidget(QWidget):
    """Widget for editing a list of actions"""
    
    def __init__(self, available_layouts: list = None, available_keys: list = None,
                 config_dir: str = None, parent=None):
        super().__init__(parent)
        self.actions = []
        self.available_layouts = available_layouts or []
        self.available_keys = available_keys or []
        # Directory relative icon paths resolve against.
        self.config_dir = config_dir or os.getcwd()
        self.setup_ui()
    
    def setup_ui(self):
        """Setup the UI"""
        metrics = current_theme().metrics
        layout = QVBoxLayout(self)
        layout.setContentsMargins(metrics.spacing_tight, metrics.spacing_tight,
                                  metrics.spacing_tight, metrics.spacing_tight)
        layout.setSpacing(metrics.spacing)
        
        # Scroll area for actions list
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setMinimumHeight(150)
        self.scroll.setMaximumHeight(320)
        self.scroll.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.scroll.setFrameShape(QScrollArea.Shape.StyledPanel)
        # The container has to carry the colour too: a bare QScrollArea rule
        # leaves the viewport on the default palette, which is white.
        surface = (COLORS['bg_input'] if current_theme().flavor is Flavor.KDE
                   else COLORS['bg_secondary'])
        self.scroll.setStyleSheet(f"""
            QScrollArea {{
                border: 1px solid {COLORS['border']};
                border-radius: {current_theme().metrics.radius}px;
                background-color: {surface};
            }}
            QWidget#actionsContainer {{
                background-color: {surface};
            }}
        """)
        
        self.actions_container = ActionListContainer()
        self.actions_container.action_moved.connect(self.move_action)
        self.actions_layout = QVBoxLayout(self.actions_container)
        self.actions_layout.setContentsMargins(6, 6, 6, 6)
        self.actions_layout.setSpacing(6)
        
        self.scroll.setWidget(self.actions_container)
        layout.addWidget(self.scroll)
        
        # Add action button - smaller and centered, completely separate
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        add_btn = create_styled_button("Add Action", primary=True)
        add_btn.setMinimumWidth(120)
        add_btn.clicked.connect(self.add_action)
        btn_layout.addWidget(add_btn)
        btn_layout.addStretch()
        layout.addLayout(btn_layout)
    
    def set_actions(self, actions: list):
        """Set the actions list"""
        self.actions = actions.copy()
        self.rebuild_actions_list()
    
    def get_actions(self) -> list:
        """Get the current actions list"""
        return self.actions.copy()
    
    def rebuild_actions_list(self):
        """Rebuild the actions list UI"""
        # Clear existing widgets and stretch items
        while self.actions_layout.count() > 0:
            item = self.actions_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        
        if not self.actions:
            empty = QLabel("No actions yet")
            empty.setObjectName("actionsEmpty")
            empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.actions_layout.addWidget(empty)
            return
        
        # Add action widgets
        for i, action in enumerate(self.actions):
            action_widget = ActionListItem(i, action)
            action_widget.remove_clicked.connect(self.remove_action)
            action_widget.edit_clicked.connect(self.edit_action)
            self.actions_layout.addWidget(action_widget)
        
        # Rows keep their own height; the spare space goes here rather than
        # being shared out among them.
        self.actions_layout.addStretch()
    
    def add_action(self):
        """Add a new action"""
        dialog = ActionDialog(None, self.available_layouts, self.available_keys,
                              config_dir=self.config_dir)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            action = dialog.get_action()
            if action:
                self.actions.append(action)
                self.rebuild_actions_list()
    
    def edit_action(self, index: int):
        """Edit an existing action"""
        if 0 <= index < len(self.actions):
            dialog = ActionDialog(self.actions[index], self.available_layouts,
                                  self.available_keys, config_dir=self.config_dir)
            if dialog.exec() == QDialog.DialogCode.Accepted:
                action = dialog.get_action()
                if action:
                    self.actions[index] = action
                    self.rebuild_actions_list()
    
    def remove_action(self, index: int):
        """Remove an action"""
        if 0 <= index < len(self.actions):
            self.actions.pop(index)
            self.rebuild_actions_list()
    
    def move_action(self, source: int, target: int):
        """
        Move an action to another position in the sequence

        Args:
            source: Index the action is at now
            target: Index it should end up at
        """
        if not 0 <= source < len(self.actions):
            return
        action = self.actions.pop(source)
        self.actions.insert(max(0, min(target, len(self.actions))), action)
        self.rebuild_actions_list()


class ActionDialog(ThemedDialog):
    """Dialog for creating or editing a single action"""
    
    # Mapping from backend keys to user-friendly display names
    ACTION_TYPE_DISPLAY = _ACTION_TYPE_DISPLAY
    
    # Reverse mapping for quick lookup
    ACTION_TYPE_BACKEND = {v: k for k, v in ACTION_TYPE_DISPLAY.items()}
    
    def __init__(self, action_dict: dict = None, available_layouts: list = None, 
                 available_keys: list = None, config_dir: str = None, parent=None):
        super().__init__(parent=parent)
        # A parameterless action may be written as a bare string in the
        # file - "- DEVICE_BRIGHTNESS_UP" - which has no keys() to read.
        if isinstance(action_dict, str):
            action_dict = {action_dict: ""}
        self.action_dict = action_dict or {}
        self.available_layouts = available_layouts or []
        self.available_keys = available_keys or []
        # Directory relative icon paths resolve against.
        self.config_dir = config_dir or os.getcwd()
        
        self.setWindowTitle("Edit Action" if action_dict else "Add Action")
        self.setMinimumWidth(500)
        
        self.setup_ui()
        self.load_action_data()
    
    def _get_backend_action_type(self) -> str:
        """Get the backend action type key from the selected display name"""
        display_name = self.action_type_combo.currentText()
        return self.ACTION_TYPE_BACKEND.get(display_name, display_name)
    
    def setup_ui(self):
        """Setup the UI"""
        layout = self.content_layout
        
        # Action type selection
        type_layout = QHBoxLayout()
        type_layout.addWidget(QLabel("Action Type:"))
        self.action_type_combo = QComboBox()
        # Add display names sorted alphabetically
        display_names = sorted(self.ACTION_TYPE_DISPLAY.values())
        self.action_type_combo.addItems(display_names)
        self.action_type_combo.currentTextChanged.connect(self.update_action_fields)
        type_layout.addWidget(self.action_type_combo)
        layout.addLayout(type_layout)
        
        # Container for dynamic fields
        self.fields_widget = QWidget()
        self.fields_layout = QVBoxLayout(self.fields_widget)
        layout.addWidget(self.fields_widget)
        
        self.add_actions("OK", self.accept)
    
    def update_action_fields(self):
        """Update fields based on selected action type"""
        _clear_layout(self.fields_layout)
        
        # Get backend action type from display name
        action_type = self._get_backend_action_type()
        
        if action_type == "EXECUTE_COMMAND":
            label = QLabel("Command (one argument per line):")
            self.fields_layout.addWidget(label)
            self.command_text = QTextEdit()
            self.command_text.setPlaceholderText("firefox\n--new-window")
            self.command_text.setMaximumHeight(100)
            self.fields_layout.addWidget(self.command_text)
        
        elif action_type == "LAUNCH_APPLICATION":
            # Radio buttons for simple vs advanced
            self.launch_simple_radio = QRadioButton("Simple (command or desktop file)")
            self.launch_advanced_radio = QRadioButton("Advanced (custom settings)")
            # Each pair in its own group, so exclusivity never depends on
            # which other radios happen to share the parent.
            self._launch_mode = QButtonGroup(self.launch_simple_radio)
            self._launch_mode.addButton(self.launch_simple_radio)
            self._launch_mode.addButton(self.launch_advanced_radio)
            self.launch_simple_radio.setChecked(True)
            self.fields_layout.addWidget(self.launch_simple_radio)
            self.fields_layout.addWidget(self.launch_advanced_radio)
            
            # Simple mode
            self.launch_simple_widget = QWidget()
            simple_layout = QVBoxLayout(self.launch_simple_widget)
            simple_layout.addWidget(QLabel("Command or Desktop File:"))
            self.launch_simple_edit = QLineEdit()
            self.launch_simple_edit.setPlaceholderText("firefox or firefox.desktop")
            self.launch_simple_edit.setToolTip(
                "A name ending in .desktop starts that desktop entry; anything else "
                "is a command line, split like a shell would (quote arguments with spaces).")
            simple_layout.addWidget(self.launch_simple_edit)
            self.fields_layout.addWidget(self.launch_simple_widget)
            
            # Advanced mode
            self.launch_advanced_widget = QWidget()
            adv_layout = QFormLayout(self.launch_advanced_widget)
            
            self.launch_command_edit = QLineEdit()
            adv_layout.addRow("Command:", self.launch_command_edit)
            
            self.launch_desktop_edit = QLineEdit()
            adv_layout.addRow("Desktop File:", self.launch_desktop_edit)
            
            self.launch_class_edit = QLineEdit()
            adv_layout.addRow("Class Name:", self.launch_class_edit)
            
            self.launch_match_combo = QComboBox()
            self.launch_match_combo.addItems(["contains", "exact"])
            adv_layout.addRow("Match Type:", self.launch_match_combo)
            
            self.launch_force_check = QCheckBox()
            adv_layout.addRow("Force New:", self.launch_force_check)
            
            self.fields_layout.addWidget(self.launch_advanced_widget)
            self.launch_advanced_widget.setVisible(False)
            
            # Connect radio buttons
            self.launch_simple_radio.toggled.connect(
                lambda checked: self.launch_simple_widget.setVisible(checked))
            self.launch_simple_radio.toggled.connect(
                lambda checked: self.launch_advanced_widget.setVisible(not checked))
        
        elif action_type == "KEY_PRESS":
            label = QLabel("Key combination (e.g., CTRL+C, SUPER+L):")
            self.fields_layout.addWidget(label)
            self.key_combo_edit = QLineEdit()
            self.key_combo_edit.setPlaceholderText("CTRL+ALT+T")
            self.fields_layout.addWidget(self.key_combo_edit)
        
        elif action_type == "TYPE_TEXT":
            label = QLabel("Text to type:")
            self.fields_layout.addWidget(label)
            self.type_text_edit = QTextEdit()
            self.type_text_edit.setMaximumHeight(100)
            self.fields_layout.addWidget(self.type_text_edit)
        
        elif action_type == "WAIT":
            label = QLabel("Wait duration (seconds):")
            self.fields_layout.addWidget(label)
            # Fractions matter here: 0.5 s is a common pause.
            self.wait_spin = QDoubleSpinBox()
            self.wait_spin.setDecimals(2)
            self.wait_spin.setSingleStep(0.1)
            self.wait_spin.setRange(0, 3600)
            self.wait_spin.setValue(1)
            self.wait_spin.setSuffix(" seconds")
            self.fields_layout.addWidget(self.wait_spin)
        
        elif action_type == "CHANGE_KEY_IMAGE":
            label = QLabel("New image path:")
            self.fields_layout.addWidget(label)
            img_layout = QHBoxLayout()
            self.image_path_edit = QLineEdit()
            img_layout.addWidget(self.image_path_edit)
            browse_btn = create_styled_button("Browse...")
            browse_btn.clicked.connect(self.browse_image)
            img_layout.addWidget(browse_btn)
            self.fields_layout.addLayout(img_layout)
        
        elif action_type == "CHANGE_KEY_TEXT":
            self.fields_layout.addWidget(QLabel("Text:"))
            self.key_text_edit = QLineEdit()
            self.fields_layout.addWidget(self.key_text_edit)

            style_layout = QFormLayout()

            self.key_text_color_edit = QLineEdit("white")
            style_layout.addRow("Text color:", self.key_text_color_edit)

            self.key_text_bg_edit = QLineEdit("black")
            style_layout.addRow("Background:", self.key_text_bg_edit)

            self.key_text_size_spin = QSpinBox()
            self.key_text_size_spin.setRange(MIN_FONT_SIZE, MAX_FONT_SIZE)
            self.key_text_size_spin.setValue(20)
            style_layout.addRow("Font size:", self.key_text_size_spin)

            self.key_text_position_combo = QComboBox()
            self.key_text_position_combo.addItems(["bottom", "center", "top"])
            style_layout.addRow("Position:", self.key_text_position_combo)

            self.fields_layout.addLayout(style_layout)

            self.key_text_bold_check = QCheckBox("Bold")
            self.key_text_bold_check.setChecked(True)
            self.fields_layout.addWidget(self.key_text_bold_check)

            self.fields_layout.addWidget(QLabel("Background image (optional):"))
            icon_row = QHBoxLayout()
            self.key_text_icon_edit = QLineEdit()
            icon_row.addWidget(self.key_text_icon_edit)
            icon_browse = create_styled_button("Browse...")
            icon_browse.clicked.connect(self.browse_key_text_icon)
            icon_row.addWidget(icon_browse)
            self.fields_layout.addLayout(icon_row)

        elif action_type == "CHANGE_KEY":
            label = QLabel("Change to Key:")
            self.fields_layout.addWidget(label)
            self.change_key_combo = QComboBox()
            _fill_names(self.change_key_combo, self.available_keys, "No keys available")
            self.fields_layout.addWidget(self.change_key_combo)
        
        elif action_type == "CHANGE_LAYOUT":
            self.layout_simple_radio = QRadioButton("Simple (layout name only)")
            self.layout_advanced_radio = QRadioButton("Advanced (with options)")
            self._layout_mode = QButtonGroup(self.layout_simple_radio)
            self._layout_mode.addButton(self.layout_simple_radio)
            self._layout_mode.addButton(self.layout_advanced_radio)
            self.layout_simple_radio.setChecked(True)
            self.fields_layout.addWidget(self.layout_simple_radio)
            self.fields_layout.addWidget(self.layout_advanced_radio)
            
            # Simple
            self.layout_simple_widget = QWidget()
            simple_layout = QVBoxLayout(self.layout_simple_widget)
            simple_layout.addWidget(QLabel("Layout:"))
            self.layout_name_combo = QComboBox()
            _fill_names(self.layout_name_combo, self.available_layouts, "No layouts available")
            simple_layout.addWidget(self.layout_name_combo)
            self.fields_layout.addWidget(self.layout_simple_widget)
            
            # Advanced
            self.layout_advanced_widget = QWidget()
            adv_layout = QFormLayout(self.layout_advanced_widget)
            self.layout_name_adv_combo = QComboBox()
            _fill_names(self.layout_name_adv_combo, self.available_layouts, "No layouts available")
            adv_layout.addRow("Layout:", self.layout_name_adv_combo)
            self.layout_clear_check = QCheckBox()
            adv_layout.addRow("Clear All:", self.layout_clear_check)
            self.fields_layout.addWidget(self.layout_advanced_widget)
            self.layout_advanced_widget.setVisible(False)
            
            # Connect
            self.layout_simple_radio.toggled.connect(
                lambda checked: self.layout_simple_widget.setVisible(checked))
            self.layout_simple_radio.toggled.connect(
                lambda checked: self.layout_advanced_widget.setVisible(not checked))
        
        elif action_type == "DBUS":
            label = QLabel("D-Bus Action:")
            self.fields_layout.addWidget(label)
            
            # Predefined actions
            self.dbus_preset_radio = QRadioButton("Predefined action")
            self.dbus_custom_radio = QRadioButton("Custom command")
            self._dbus_mode = QButtonGroup(self.dbus_preset_radio)
            self._dbus_mode.addButton(self.dbus_preset_radio)
            self._dbus_mode.addButton(self.dbus_custom_radio)
            self.dbus_preset_radio.setChecked(True)
            self.fields_layout.addWidget(self.dbus_preset_radio)
            self.fields_layout.addWidget(self.dbus_custom_radio)
            
            # Preset widget
            self.dbus_preset_widget = QWidget()
            preset_layout = QVBoxLayout(self.dbus_preset_widget)
            self.dbus_action_combo = QComboBox()
            self.dbus_action_combo.addItems([
                "play_pause", "next", "previous",
                "volume_up", "volume_down", "mute"
            ])
            preset_layout.addWidget(self.dbus_action_combo)
            self.fields_layout.addWidget(self.dbus_preset_widget)
            
            # Custom widget
            self.dbus_custom_widget = QWidget()
            custom_layout = QVBoxLayout(self.dbus_custom_widget)
            custom_layout.addWidget(QLabel("Custom D-Bus command:"))
            self.dbus_custom_edit = QLineEdit()
            # The runtime runs a bare string through the shell; only the
            # predefined names go in the {action: ...} form.
            self.dbus_custom_edit.setPlaceholderText(
                "e.g., dbus-send --session --dest=org.mpris.MediaPlayer2.spotify ...")
            self.dbus_custom_edit.setToolTip("Run through the shell when the key is pressed")
            custom_layout.addWidget(self.dbus_custom_edit)
            self.fields_layout.addWidget(self.dbus_custom_widget)
            self.dbus_custom_widget.setVisible(False)
            
            # Connect
            self.dbus_preset_radio.toggled.connect(
                lambda checked: self.dbus_preset_widget.setVisible(checked))
            self.dbus_preset_radio.toggled.connect(
                lambda checked: self.dbus_custom_widget.setVisible(not checked))
        
        elif action_type in ["DEVICE_BRIGHTNESS_UP", "DEVICE_BRIGHTNESS_DOWN"]:
            label = QLabel("No additional parameters needed")
            self.fields_layout.addWidget(label)
    
    def browse_key_text_icon(self):
        """Pick a background image for a CHANGE_KEY_TEXT action."""
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Select Background Image", "",
            "Images (*.png *.jpg *.jpeg *.gif *.svg *.bmp)")
        if file_path:
            self.key_text_icon_edit.setText(
                relativize_icon_path(file_path, self.config_dir))

    def browse_image(self):
        """Browse for an image file"""
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Select Image", "", "Images (*.png *.jpg *.jpeg *.gif *.svg)"
        )
        if file_path:
            self.image_path_edit.setText(file_path)
    
    def load_action_data(self):
        """Load existing action data"""
        if not self.action_dict:
            # No existing action, initialize fields for default action type
            self.update_action_fields()
            return
        
        # Get action type (backend key). The runtime takes any case, so a
        # hand-written `key_press:` opens as KEY_PRESS and is saved that way.
        raw_type = list(self.action_dict.keys())[0]
        action_value = self.action_dict[raw_type]
        action_type = raw_type.upper() if isinstance(raw_type, str) else raw_type
        
        # Convert backend key to display name and set in combo. Blocked, and
        # the fields built once below: setCurrentIndex only emits when the
        # index changes, so the first type alphabetically would otherwise get
        # no fields, and every other type would get them twice.
        display_name = self.ACTION_TYPE_DISPLAY.get(action_type, action_type)
        index = self.action_type_combo.findText(display_name)
        if index >= 0:
            self.action_type_combo.blockSignals(True)
            self.action_type_combo.setCurrentIndex(index)
            self.action_type_combo.blockSignals(False)
        self.update_action_fields()
        
        # Load specific fields based on type
        if action_type == "EXECUTE_COMMAND":
            if isinstance(action_value, list):
                self.command_text.setPlainText("\n".join(action_value))
            else:
                self.command_text.setPlainText(str(action_value))
        
        elif action_type == "LAUNCH_APPLICATION":
            if isinstance(action_value, (str, list)):
                self.launch_simple_radio.setChecked(True)
                self.launch_simple_edit.setText(_join_command(action_value))
            elif isinstance(action_value, dict):
                self.launch_advanced_radio.setChecked(True)
                if 'command' in action_value:
                    self.launch_command_edit.setText(_join_command(action_value['command']))
                if 'desktop_file' in action_value:
                    self.launch_desktop_edit.setText(_as_text(action_value['desktop_file']))
                if 'class_name' in action_value:
                    self.launch_class_edit.setText(_as_text(action_value['class_name']))
                if 'match_type' in action_value:
                    self.launch_match_combo.setCurrentText(_as_text(action_value['match_type']))
                if 'force_new' in action_value:
                    self.launch_force_check.setChecked(bool(action_value['force_new']))
            # What the fields showed on opening, so get_action can hand back
            # the original value untouched when nothing was edited.
            self._launch_loaded = self._launch_fields()
        
        elif action_type == "KEY_PRESS":
            self.key_combo_edit.setText(_as_text(action_value))
        
        elif action_type == "TYPE_TEXT":
            self.type_text_edit.setPlainText(_as_text(action_value))
        
        elif action_type == "WAIT":
            self.wait_spin.setValue(_as_float(action_value, 1.0))
        
        elif action_type == "CHANGE_KEY_IMAGE":
            self.image_path_edit.setText(_as_text(action_value))
        
        elif action_type == "CHANGE_KEY_TEXT":
            # The runtime accepts a bare string or the full styled dict.
            values = action_value if isinstance(action_value, dict) else {'text': action_value}
            self.key_text_edit.setText(str(values.get('text', '')))
            self.key_text_color_edit.setText(str(values.get('text_color', 'white')))
            self.key_text_bg_edit.setText(str(values.get('background_color', 'black')))
            self.key_text_size_spin.setValue(_as_int(values.get('font_size'), 20))
            self.key_text_bold_check.setChecked(bool(values.get('bold', True)))
            self.key_text_icon_edit.setText(str(values.get('icon', '')))
            index = self.key_text_position_combo.findText(
                str(values.get('text_position', 'bottom')))
            if index >= 0:
                self.key_text_position_combo.setCurrentIndex(index)

        elif action_type == "CHANGE_KEY":
            _select_name(self.change_key_combo, action_value)
        
        elif action_type == "CHANGE_LAYOUT":
            if isinstance(action_value, str):
                self.layout_simple_radio.setChecked(True)
                _select_name(self.layout_name_combo, action_value)
            elif isinstance(action_value, dict):
                self.layout_advanced_radio.setChecked(True)
                _select_name(self.layout_name_adv_combo, action_value.get('layout', ''))
                self.layout_clear_check.setChecked(action_value.get('clear_all', False))
        
        elif action_type == "DBUS":
            # The runtime reads a dict as a named shortcut and a string as a
            # shell command, so the form must keep them apart: a string is
            # always a custom command, whatever it says.
            if isinstance(action_value, dict):
                action = _as_text(action_value.get('action', ''))
                index = self.dbus_action_combo.findText(action)
                if index < 0 and action:
                    # A shortcut the list does not offer (stop, play_pause_any).
                    self.dbus_action_combo.addItem(action)
                    index = self.dbus_action_combo.count() - 1
                self.dbus_preset_radio.setChecked(True)
                if index >= 0:
                    self.dbus_action_combo.setCurrentIndex(index)
            elif isinstance(action_value, str):
                self.dbus_custom_radio.setChecked(True)
                self.dbus_custom_edit.setText(action_value)
    
    def get_action(self) -> dict:
        """Get the action dictionary from the dialog"""
        # Get backend action type from display name
        action_type = self._get_backend_action_type()
        
        if action_type == "EXECUTE_COMMAND":
            command = self.command_text.toPlainText().strip().split("\n")
            command = [c.strip() for c in command if c.strip()]
            if not command:
                return None
            return {action_type: command if len(command) > 1 else command[0]}
        
        elif action_type == "LAUNCH_APPLICATION":
            return self._launch_action(action_type)
        
        elif action_type == "KEY_PRESS":
            value = self.key_combo_edit.text().strip()
            if not value:
                return None
            return {action_type: value}
        
        elif action_type == "TYPE_TEXT":
            value = self.type_text_edit.toPlainText()
            if not value:
                return None
            return {action_type: value}
        
        elif action_type == "WAIT":
            seconds = self.wait_spin.value()
            # A whole number stays an int, as a hand-written file spells it.
            return {action_type: int(seconds) if seconds.is_integer() else seconds}
        
        elif action_type == "CHANGE_KEY_IMAGE":
            value = self.image_path_edit.text().strip()
            if not value:
                return None
            return {action_type: value}
        
        elif action_type == "CHANGE_KEY_TEXT":
            text = self.key_text_edit.text()
            if not text:
                return None

            value = {
                'text': text,
                'text_color': self.key_text_color_edit.text().strip() or 'white',
                'background_color': self.key_text_bg_edit.text().strip() or 'black',
                'font_size': self.key_text_size_spin.value(),
                'bold': self.key_text_bold_check.isChecked(),
                'text_position': self.key_text_position_combo.currentText(),
            }
            icon = self.key_text_icon_edit.text().strip()
            if icon:
                value['icon'] = icon
            return {action_type: value}

        elif action_type == "CHANGE_KEY":
            value = self.change_key_combo.currentData()
            if not value:
                return None
            return {action_type: value}
        
        elif action_type == "CHANGE_LAYOUT":
            if self.layout_simple_radio.isChecked():
                value = self.layout_name_combo.currentData()
                if not value:
                    return None
                return {action_type: value}
            else:
                value = self.layout_name_adv_combo.currentData()
                if not value:
                    return None
                result = {'layout': value}
                if self.layout_clear_check.isChecked():
                    result['clear_all'] = True
                return {action_type: result}
        
        elif action_type == "DBUS":
            if self.dbus_preset_radio.isChecked():
                return {action_type: {'action': self.dbus_action_combo.currentText()}}
            command = self.dbus_custom_edit.text().strip()
            if not command:
                return None
            return {action_type: command}
        
        elif action_type in ["DEVICE_BRIGHTNESS_UP", "DEVICE_BRIGHTNESS_DOWN"]:
            return {action_type: ""}
        
        return None

    def _launch_fields(self) -> tuple:
        """Everything the LAUNCH_APPLICATION form shows, for spotting an edit."""
        return (self.launch_simple_radio.isChecked(),
                self.launch_simple_edit.text(),
                self.launch_command_edit.text(),
                self.launch_desktop_edit.text(),
                self.launch_class_edit.text(),
                self.launch_match_combo.currentText(),
                self.launch_force_check.isChecked())

    def _original_launch_value(self):
        """The LAUNCH_APPLICATION value the dialog opened with, or None."""
        if not self.action_dict:
            return None
        action_type = list(self.action_dict.keys())[0]
        is_launch = isinstance(action_type, str) and action_type.upper() == "LAUNCH_APPLICATION"
        return self.action_dict[action_type] if is_launch else None

    def _launch_action(self, action_type: str):
        """
        LAUNCH_APPLICATION from the form.

        An untouched form returns the original value as it was: the fields
        cannot show every spelling (process_name, unknown keys, a one-item
        list), and re-deriving it would rewrite the file on an unrelated edit.
        """
        original = self._original_launch_value()
        if original is not None and self._launch_fields() == getattr(self, '_launch_loaded', None):
            return {action_type: copy.deepcopy(original)}

        if self.launch_simple_radio.isChecked():
            value = self.launch_simple_edit.text().strip()
            if not value:
                return None
            if value.endswith('.desktop'):
                return {action_type: {'desktop_file': value}}
            return {action_type: _split_command(value)}

        # Advanced: overlay the edited fields on the original, so keys the
        # form has no field for (process_name, anything newer) survive.
        result = copy.deepcopy(original) if isinstance(original, dict) else {}

        desktop = self.launch_desktop_edit.text().strip()
        command = self.launch_command_edit.text().strip()
        if not desktop and not command:
            return None
        if desktop:
            result['desktop_file'] = desktop
        else:
            result.pop('desktop_file', None)
        if command:
            unchanged = (isinstance(original, dict) and 'command' in original
                         and command == _join_command(original['command']).strip())
            result['command'] = original['command'] if unchanged else _split_command(command)
        else:
            result.pop('command', None)

        class_name = self.launch_class_edit.text().strip()
        if class_name:
            result['class_name'] = class_name
        else:
            result.pop('class_name', None)

        match_type = self.launch_match_combo.currentText()
        if match_type != "contains" or 'match_type' in result:
            result['match_type'] = match_type

        if self.launch_force_check.isChecked():
            result['force_new'] = True
        elif 'force_new' in result:
            result['force_new'] = False

        return {action_type: result}


def run_key_editor(parent, config, key_name: str = None):
    """
    Edit ``key_name`` (or create a key when None) and store the result in ``config``.

    Both the grid and Manage Keys go through here, so a key is edited with the
    same icon directory and the same rename rules wherever it is opened from.

    Returns:
        The stored key's name, or None when cancelled or refused
    """
    key_def = config.keys.get(key_name) if key_name else None
    others = [name for name in config.keys if name != key_name]
    editor = KeyEditorDialog(key_def, others, list(config.layouts), others,
                             config_dir=config.config_dir, parent=parent)
    if editor.exec() != QDialog.DialogCode.Accepted:
        return None
    # KeyEditorDialog.accept() has already refused a duplicate or blank name.
    new_def = editor.get_key_definition()
    if key_name:
        config.replace_key(key_name, new_def)
    else:
        config.add_key(new_def.name, new_def)
    return new_def.name


def describe_key(key_def: KeyDefinition) -> str:
    """What the key shows, in a few words."""
    if key_def.is_widget():
        return f"Widget: {key_def.widget}"
    if key_def.has_icon():
        icon = f"Icon: {Path(key_def.icon).name}"
        return f"{icon} + text '{key_def.text}'" if key_def.has_text() else icon
    if key_def.has_text():
        return f"Text: {key_def.text}"
    return "No icon or text"


CAPTION_ROLE = Qt.ItemDataRole.UserRole + 1


class _ThumbnailDelegate(QStyledItemDelegate):
    """Thumbnail over the key's name, and an optional usage line in a quieter colour."""

    def paint(self, painter, option, index):
        # The view hands every item the same option object, and
        # initStyleOption writes the item's foreground into its palette; a
        # copy keeps one dimmed key from dimming the next.
        option = QStyleOptionViewItem(option)
        self.initStyleOption(option, index)
        style = option.widget.style() if option.widget else QApplication.style()
        painter.save()
        style.drawPrimitive(QStyle.PrimitiveElement.PE_PanelItemViewItem, option, painter, option.widget)
        rect = option.rect.adjusted(4, 4, -4, -4)
        size = option.decorationSize
        icon_rect = QRect(rect.x() + (rect.width() - size.width()) // 2, rect.y(),
                          size.width(), size.height())
        option.icon.paint(painter, icon_rect)
        metrics = option.fontMetrics
        selected = bool(option.state & QStyle.StateFlag.State_Selected)
        text_rect = QRect(rect.x(), icon_rect.bottom() + 4, rect.width(), metrics.height())
        painter.setPen(option.palette.color(
            QPalette.ColorRole.HighlightedText if selected else QPalette.ColorRole.Text))
        painter.drawText(text_rect, Qt.AlignmentFlag.AlignHCenter,
                         metrics.elidedText(index.data(Qt.ItemDataRole.DisplayRole),
                                            Qt.TextElideMode.ElideRight, rect.width()))
        caption = index.data(CAPTION_ROLE)
        if caption:
            font = QFont(option.font)
            font.setPointSizeF(max(6.0, option.font.pointSizeF() * 0.85))
            painter.setFont(font)
            small = QFontMetrics(font)
            painter.setPen(option.palette.color(QPalette.ColorRole.HighlightedText) if selected
                           else QColor(COLORS['text_secondary']))
            painter.drawText(QRect(rect.x(), text_rect.bottom() + 2, rect.width(), small.height()),
                             Qt.AlignmentFlag.AlignHCenter,
                             small.elidedText(caption, Qt.TextElideMode.ElideRight, rect.width()))
        painter.restore()


class KeyThumbnailGrid(QWidget):
    """
    Keys as the thumbnails the device grid draws, under a name filter.

    Keys are found by how they look on the deck far more often than by name,
    so this is what both the key picker and Manage Keys show.
    """

    THUMBNAIL = 64

    activated = pyqtSignal(str)
    selection_changed = pyqtSignal()

    def __init__(self, config_dir: str, multi_select: bool = False, parent=None):
        super().__init__(parent)
        self._keys = {}
        self._extra_filter = None
        # name -> (signature, icon): set_keys runs after every edit in Manage
        # Keys, and redrawing a hundred keys each time is what made it lag.
        self._thumbnails = {}
        self._renderer = KeySquare(0)
        self._renderer.config_dir = config_dir
        self._renderer.preview_service = shared_previews()
        self._renderer.preview_service.preview_ready.connect(self._refresh_widget_thumbnails)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(current_theme().metrics.spacing)

        self.filter_row = QHBoxLayout()
        self.search = QLineEdit()
        self.search.setPlaceholderText("Filter keys by name")
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(self.apply_filter)
        self.filter_row.addWidget(self.search, stretch=1)
        layout.addLayout(self.filter_row)

        self.list = QListWidget()
        self.list.setViewMode(QListWidget.ViewMode.IconMode)
        self.list.setResizeMode(QListWidget.ResizeMode.Adjust)
        self.list.setMovement(QListWidget.Movement.Static)
        self.list.setUniformItemSizes(True)
        self.list.setWordWrap(True)
        self.list.setSpacing(6)
        self.list.setIconSize(QSize(self.THUMBNAIL, self.THUMBNAIL))
        self.list.setItemDelegate(_ThumbnailDelegate(self.list))
        self._set_cell_height(captioned=False)
        if multi_select:
            self.list.setSelectionMode(QListWidget.SelectionMode.ExtendedSelection)
        self.list.itemActivated.connect(
            lambda item: self.activated.emit(item.data(Qt.ItemDataRole.UserRole)))
        self.list.itemSelectionChanged.connect(self.selection_changed.emit)
        self.list.currentItemChanged.connect(lambda *_: self.selection_changed.emit())
        layout.addWidget(self.list, stretch=1)

        self.empty_label = QLabel("No keys match")
        self.empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty_label.setStyleSheet(f"color: {COLORS['text_secondary']};")
        self.empty_label.hide()
        layout.addWidget(self.empty_label)

    def set_keys(self, keys: dict, captions: dict = None, dimmed=(), tooltips: dict = None) -> None:
        """
        Show ``keys`` (name -> KeyDefinition), keeping the selection by name.

        Args:
            captions: Optional second line under a key's name
            dimmed: Names drawn in the secondary colour
            tooltips: Optional extra tooltip line per name
        """
        selected = set(self.selected_names())
        current = self.current_name()
        self._keys = keys
        self.list.clear()
        captions, tooltips, dimmed = captions or {}, tooltips or {}, set(dimmed)
        self._set_cell_height(captioned=bool(captions))
        for name in sorted(keys, key=str.casefold):
            item = QListWidgetItem(self._thumbnail(name, keys[name]), name)
            item.setData(Qt.ItemDataRole.UserRole, name)
            item.setData(CAPTION_ROLE, captions.get(name))
            item.setToolTip("\n".join(filter(None, [name, describe_key(keys[name]),
                                                     tooltips.get(name)])))
            if name in dimmed:
                item.setForeground(QColor(COLORS['text_secondary']))
            self.list.addItem(item)
            if name == current:
                self.list.setCurrentItem(item)
            item.setSelected(name in selected)
        self.apply_filter()

    def set_extra_filter(self, predicate) -> None:
        """Hide keys for which ``predicate(name)`` is false; None shows all."""
        self._extra_filter = predicate
        self.apply_filter()

    def apply_filter(self, *_args) -> None:
        needle = self.search.text().strip().casefold()
        first_visible = None
        for item in self._items():
            name = item.data(Qt.ItemDataRole.UserRole)
            hidden = needle not in name.casefold() or \
                (self._extra_filter is not None and not self._extra_filter(name))
            item.setHidden(hidden)
            if hidden:
                item.setSelected(False)
            elif first_visible is None:
                first_visible = item
        # Keep a match current, so typing a few letters and pressing Enter acts on it.
        current = self.list.currentItem()
        if current is None or current.isHidden():
            self.list.setCurrentItem(first_visible)
        self.empty_label.setVisible(first_visible is None)
        self.selection_changed.emit()

    def current_name(self):
        item = self.list.currentItem()
        return None if item is None or item.isHidden() else item.data(Qt.ItemDataRole.UserRole)

    def selected_names(self) -> list:
        """The selected keys, or the current one when nothing is selected."""
        names = [item.data(Qt.ItemDataRole.UserRole) for item in self.list.selectedItems()
                 if not item.isHidden()]
        if not names and self.current_name():
            names = [self.current_name()]
        return names

    def visible_names(self) -> list:
        return [item.data(Qt.ItemDataRole.UserRole) for item in self._items() if not item.isHidden()]

    def select(self, name: str) -> None:
        for item in self._items():
            if item.data(Qt.ItemDataRole.UserRole) == name:
                self.list.clearSelection()
                self.list.setCurrentItem(item)
                self.list.scrollToItem(item)
                return

    def release(self) -> None:
        """Stop listening for widget snapshots; the preview service outlives this grid."""
        try:
            self._renderer.preview_service.preview_ready.disconnect(self._refresh_widget_thumbnails)
        except TypeError:
            pass

    def _set_cell_height(self, captioned: bool) -> None:
        lines = self.list.fontMetrics().height() * (2 if captioned else 1) + (2 if captioned else 0)
        self.list.setGridSize(QSize(self.THUMBNAIL + 56, self.THUMBNAIL + lines + 16))

    def _items(self):
        return [self.list.item(row) for row in range(self.list.count())]

    def _signature(self, key_def: KeyDefinition) -> tuple:
        """Everything a thumbnail depends on: the definition, the icon file, the widget snapshot."""
        mtime = None
        if isinstance(key_def.icon, str) and key_def.icon:
            try:
                mtime = os.stat(resolve_icon_path(key_def.icon, self._renderer.config_dir)).st_mtime_ns
            except OSError:
                pass
        return (hash(repr(key_def.to_dict())), mtime, self._preview_key(key_def))

    def _preview_key(self, key_def: KeyDefinition):
        if not key_def.is_widget():
            return None
        return self._renderer.preview_service.key(*self._renderer._widget_preview_args(key_def))

    def _thumbnail(self, name: str, key_def: KeyDefinition, force: bool = False) -> QIcon:
        signature = self._signature(key_def)
        cached = self._thumbnails.get(name)
        if not force and cached is not None and cached[0] == signature:
            return cached[1]
        icon = self._render_thumbnail(name, key_def)
        self._thumbnails[name] = (signature, icon)
        return icon

    def _render_thumbnail(self, name: str, key_def: KeyDefinition) -> QIcon:
        self._renderer.set_key(name, key_def)
        pixmap = self._renderer.grab().scaled(
            self.THUMBNAIL, self.THUMBNAIL, Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation)
        icon = QIcon(pixmap)
        # Without this the selection tints the thumbnail, which then no
        # longer looks like the key.
        icon.addPixmap(pixmap, QIcon.Mode.Selected)
        return icon

    def _refresh_widget_thumbnails(self, key: str) -> None:
        """Widget snapshots arrive after the grid is drawn; redraw the keys this one belongs to."""
        for item in self._items():
            name = item.data(Qt.ItemDataRole.UserRole)
            key_def = self._keys.get(name)
            if key_def is not None and key_def.is_widget() and self._preview_key(key_def) == key:
                item.setIcon(self._thumbnail(name, key_def, force=True))


class ManageKeysDialog(ThemedDialog):
    """Every key definition, with where each one is used."""

    def __init__(self, config, parent=None):
        super().__init__("Manage All Keys", parent=parent)
        self.config = config
        self.modified = False
        self.setMinimumSize(680, 540)

        layout = self.content_layout
        self.grid = KeyThumbnailGrid(config.config_dir, multi_select=True)
        self.unused_only = QCheckBox("Unused only")
        self.unused_only.setToolTip("Keys on no layout and not swapped in by any CHANGE_KEY action")
        self.unused_only.toggled.connect(self._apply_unused_filter)
        self.grid.filter_row.addWidget(self.unused_only)
        self.grid.activated.connect(self.edit_key_by_name)
        self.grid.search.returnPressed.connect(self.edit_selected)
        self.grid.selection_changed.connect(self._update_buttons)
        layout.addWidget(self.grid, stretch=1)

        buttons = QHBoxLayout()
        self.new_btn = make_button("New…")
        self.new_btn.setIcon(themed_icon('list-add'))
        self.new_btn.clicked.connect(self.add_new_key)
        self.edit_btn = make_button("Edit…")
        self.edit_btn.setIcon(themed_icon('document-edit', 'edit-entry'))
        self.edit_btn.clicked.connect(self.edit_selected)
        self.duplicate_btn = make_button("Duplicate")
        self.duplicate_btn.setIcon(themed_icon('edit-copy'))
        self.duplicate_btn.clicked.connect(self.duplicate_selected)
        self.delete_btn = make_button("Delete")
        self.delete_btn.setIcon(themed_icon('edit-delete', 'edit-delete-symbolic'))
        self.delete_btn.clicked.connect(self.delete_selected)
        for button in (self.new_btn, self.edit_btn, self.duplicate_btn, self.delete_btn):
            button.setAutoDefault(False)
            buttons.addWidget(button)
        buttons.addStretch()
        self.summary = QLabel()
        self.summary.setStyleSheet(f"color: {COLORS['text_secondary']};")
        buttons.addWidget(self.summary)
        layout.addLayout(buttons)

        delete_shortcut = QShortcut(QKeySequence(QKeySequence.StandardKey.Delete), self.grid.list)
        delete_shortcut.activated.connect(self.delete_selected)

        self.add_actions("Close", self.accept, cancel=None)
        self.affirmative_button.setAutoDefault(False)
        self.affirmative_button.setDefault(False)
        self.refresh_keys_list()
        self.grid.search.setFocus()

    def refresh_keys_list(self):
        """Redraw every key with its usage."""
        self._usage = self.config.all_key_usage()
        captions, tooltips = {}, {}
        for name, usage in self._usage.items():
            captions[name] = ", ".join(usage.layouts) if usage.layouts else \
                ("via CHANGE_KEY" if usage.changed_to_by else "unused")
            lines = []
            if usage.layouts:
                lines.append("On layouts: " + ", ".join(usage.layouts))
            if usage.changed_to_by:
                lines.append("Swapped in by: " + ", ".join(usage.changed_to_by))
            tooltips[name] = "\n".join(lines) or "Not used anywhere"
        unused = [name for name, usage in self._usage.items() if usage.unused]
        self.grid.set_keys(self.config.keys, captions, dimmed=unused, tooltips=tooltips)
        self.summary.setText(f"{len(self.config.keys)} keys, {len(unused)} unused")
        self._update_buttons()

    def _apply_unused_filter(self, checked: bool) -> None:
        self.grid.set_extra_filter((lambda name: self._usage[name].unused) if checked else None)

    def _update_buttons(self) -> None:
        count = len(self.grid.selected_names())
        self.edit_btn.setEnabled(count == 1)
        self.duplicate_btn.setEnabled(count == 1)
        self.delete_btn.setEnabled(count > 0)
        self.delete_btn.setText(f"Delete {count}" if count > 1 else "Delete")

    def add_new_key(self):
        name = run_key_editor(self, self.config)
        if name:
            self._changed(select=name)

    def edit_selected(self):
        names = self.grid.selected_names()
        if len(names) == 1:
            self.edit_key_by_name(names[0])

    def edit_key_by_name(self, key_name: str):
        if key_name not in self.config.keys:
            return
        name = run_key_editor(self, self.config, key_name)
        if name:
            self._changed(select=name)

    def duplicate_selected(self):
        names = self.grid.selected_names()
        if len(names) == 1:
            self._changed(select=self.config.duplicate_key(names[0]))

    def delete_selected(self):
        names = self.grid.selected_names()
        if not names:
            return
        used = {name: self._usage[name] for name in names if not self._usage[name].unused}
        subject = f"key '{names[0]}'" if len(names) == 1 else f"{len(names)} keys"
        message = f"Delete {subject}?"
        if used:
            details = []
            for name, usage in used.items():
                places = usage.layouts + [f"CHANGE_KEY in {other}" for other in usage.changed_to_by]
                details.append(f"• {name}: {', '.join(places)}")
            message += ("\n\nStill in use - it will be removed from these layouts and actions:\n"
                        + "\n".join(details))
        reply = QMessageBox.question(self, "Confirm Deletion", message,
                                     QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if reply != QMessageBox.StandardButton.Yes:
            return
        for name in names:
            self.config.delete_key(name)
        self._changed()

    def delete_key_by_name(self, key_name: str):
        self.grid.select(key_name)
        self.delete_selected()

    def _changed(self, select: str = None) -> None:
        self.modified = True
        self.refresh_keys_list()
        if select:
            self.grid.select(select)

    def was_modified(self) -> bool:
        """Check if any modifications were made"""
        return self.modified

    def done(self, result: int) -> None:
        self.grid.release()
        super().done(result)


class KeyPickerDialog(ThemedDialog):
    """Pick an existing key by its thumbnail."""

    def __init__(self, keys: dict, title: str, config_dir: str,
                 in_layout=(), exclude=(), parent=None):
        """
        Args:
            keys: Key name -> KeyDefinition to choose from
            title: Window title, which also names what picking does
            config_dir: Where relative icon paths resolve
            in_layout: Names already on the current layout, marked as such
            exclude: Names not to offer at all
        """
        super().__init__(title, parent)
        self.selected_key = None
        self.setMinimumSize(560, 460)

        self.grid = KeyThumbnailGrid(config_dir)
        self.search = self.grid.search
        self.grid.activated.connect(self._pick)
        self.search.returnPressed.connect(self._pick_current)
        self.grid.selection_changed.connect(self._update_affirmative)
        self.content_layout.addWidget(self.grid, stretch=1)

        excluded = set(exclude)
        in_layout = set(in_layout)
        self.grid.set_keys({name: key_def for name, key_def in keys.items() if name not in excluded},
                           dimmed=in_layout,
                           tooltips={name: "Already on this layout" for name in in_layout})

        self.add_actions("Assign", self._pick_current)
        self._update_affirmative()
        self.search.setFocus()

    def _update_affirmative(self) -> None:
        if self.affirmative_button is not None:
            self.affirmative_button.setEnabled(self.grid.current_name() is not None)

    def _pick_current(self) -> None:
        name = self.grid.current_name()
        if name is not None:
            self._pick(name)

    def _pick(self, name: str) -> None:
        self.selected_key = name
        self.accept()

    def done(self, result: int) -> None:
        self.grid.release()
        super().done(result)


MATCH_FIELD_LABELS = {
    "class": "Application (window class)",
    "title": "Window title",
    "raw": "Raw detector output (advanced)",
}


def split_patterns(text: str):
    """'a, b' -> ['a', 'b']; a single pattern stays a plain string, as the file spells it."""
    patterns = [part.strip() for part in text.split(",") if part.strip()]
    return patterns[0] if len(patterns) == 1 else patterns


class WindowRuleDialog(ThemedDialog):
    """
    Add or edit a window rule.

    The hard part of a rule is knowing what the window calls itself, so the
    dialog lists recently focused windows to take a pattern from, and says
    which of them the pattern matches, through the same matcher the
    runtime uses.
    """

    def __init__(self, available_layouts: list, rule_name: str = None, window_rule=None,
                 existing_rules: list = None, parent=None, recent_windows=(),
                 suggest_name=None, preset_layout: str = None):
        """
        Args:
            recent_windows: WindowInfo objects, newest first
            suggest_name: pattern -> a free rule name, for a name left blank
            preset_layout: Target layout to start from, for a new rule
        """
        super().__init__(parent=parent)
        self.available_layouts = available_layouts
        self.original_rule_name = rule_name
        self.window_rule = window_rule
        self.existing_rules = existing_rules or []
        self.recent_windows = list(recent_windows)
        self.suggest_name = suggest_name or (lambda pattern: "")
        # The pattern text as loaded, to hand back window_name untouched when
        # it was not edited: splitting it again could corrupt it.
        self._loaded_pattern_text = None

        self.setWindowTitle("Add Window Rule" if not rule_name else "Edit Window Rule")
        self.setMinimumWidth(520)

        self.setup_ui()

        if window_rule:
            self.load_rule(window_rule)
        elif preset_layout:
            index = self.layout_combo.findText(preset_layout)
            if index >= 0:
                self.layout_combo.setCurrentIndex(index)
        self._refresh_matches()

    def setup_ui(self):
        """Setup the UI"""
        layout = self.content_layout
        form = QFormLayout()

        self.window_name_input = QLineEdit()
        self.window_name_input.setToolTip("Matched case-insensitively anywhere in the text. "
                                          "Without \"Regular expression\", separate several patterns "
                                          "with commas; any of them matches. A regular expression is "
                                          "taken whole, commas included.")
        self.window_name_input.textChanged.connect(self._refresh_matches)
        form.addRow("When the:", self.match_row())
        self.regex_check = QCheckBox("Regular expression")
        self.regex_check.setToolTip("Treat the text as one case-insensitive regular expression")
        self.regex_check.toggled.connect(self._refresh_matches)
        pattern_row = QHBoxLayout()
        pattern_row.addWidget(self.window_name_input, stretch=1)
        pattern_row.addWidget(self.regex_check)
        form.addRow("contains:", pattern_row)

        self.layout_combo = QComboBox()
        if self.available_layouts:
            self.layout_combo.addItems(self.available_layouts)
        else:
            self.layout_combo.addItem("No layouts available")
            self.layout_combo.setEnabled(False)
        form.addRow("switch to:", self.layout_combo)

        self.name_input = QLineEdit()
        if self.original_rule_name:
            self.name_input.setText(self.original_rule_name)
        self.name_input.textChanged.connect(self._refresh_name_placeholder)
        form.addRow("Rule name:", self.name_input)
        layout.addLayout(form)

        recent_label = QLabel("Recently focused windows - click one to use it:")
        recent_label.setProperty("textRole", "caption")
        layout.addWidget(recent_label)
        self.recent_list = QListWidget()
        self.recent_list.setMinimumHeight(170)
        self.recent_list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.recent_list.setItemDelegate(SidebarRowDelegate(self.recent_list))
        self.recent_list.itemClicked.connect(self._use_recent_window)
        if self.recent_windows:
            for window in self.recent_windows:
                item = QListWidgetItem()
                item.setData(Qt.ItemDataRole.UserRole, window)
                # Rich text on purpose, with the window's own strings escaped:
                # any title is under the control of whatever made the window.
                item.setToolTip(f"<p>Class: {html.escape(str(window.class_ or ''))}<br>"
                                f"Title: {html.escape(str(window.title or ''))}</p>")
                self.recent_list.addItem(item)
        else:
            item = QListWidgetItem("None yet - connect the deck, then switch to the window you "
                                   "mean and back here.")
            item.setFlags(Qt.ItemFlag.NoItemFlags)
            self.recent_list.addItem(item)
        layout.addWidget(self.recent_list, stretch=1)

        self.match_summary = QLabel()
        self.match_summary.setProperty("textRole", "caption")
        self.match_summary.setWordWrap(True)
        layout.addWidget(self.match_summary)

        self.add_actions("Save", self.validate_and_accept)
        self._update_placeholder()
        self.window_name_input.setFocus()

    def match_row(self) -> QComboBox:
        self.match_field_combo = QComboBox()
        # Raw output is detector-specific; offered only to a rule already using it.
        for field_name in ("class", "title"):
            self.match_field_combo.addItem(MATCH_FIELD_LABELS[field_name], field_name)
        self.match_field_combo.currentIndexChanged.connect(self._update_placeholder)
        self.match_field_combo.currentIndexChanged.connect(self._refresh_matches)
        return self.match_field_combo

    def match_field(self) -> str:
        return self.match_field_combo.currentData() or "class"

    def _update_placeholder(self, *_args):
        """Update the placeholder text based on selected match field"""
        placeholders = {
            'class': 'e.g. firefox, konsole, jetbrains-idea',
            'title': 'e.g. Google Meet, - YouTube',
            'raw': 'text from the detector output',
        }
        self.window_name_input.setPlaceholderText(placeholders.get(self.match_field(), ''))

    def _refresh_name_placeholder(self, *_args):
        pattern = self.window_name_input.text().strip()
        suggestion = self.suggest_name(pattern) if pattern else ""
        self.name_input.setPlaceholderText(f"Automatic: {suggestion}" if suggestion
                                           else "Automatic from the pattern")

    def _use_recent_window(self, item: QListWidgetItem):
        window = item.data(Qt.ItemDataRole.UserRole)
        if window is None:
            return
        value = window.title if self.match_field() == "title" else window.class_
        self.window_name_input.setText(value)

    def _refresh_matches(self, *_args):
        from StreamDock.business_logic.layout_manager import rule_patterns, window_matches
        self._refresh_name_placeholder()
        pattern = self.patterns()
        field_name = self.match_field()
        try:
            pattern = rule_patterns(pattern, self.regex_check.isChecked()) if pattern else pattern
        except re.error as e:
            self.match_summary.setText(f"✗ Not a valid regular expression: {e}")
            return
        matched = []
        for row in range(self.recent_list.count()):
            item = self.recent_list.item(row)
            window = item.data(Qt.ItemDataRole.UserRole)
            if window is None:
                continue
            # The field being matched on top, where the eye compares it with the pattern.
            by_title = field_name == "title"
            item.setText(window.title if by_title else window.class_)
            item.setData(SIDEBAR_CAPTION_ROLE, window.class_ if by_title else window.title)
            hit = bool(pattern) and window_matches(window, pattern, field_name)
            font = item.font()
            font.setBold(hit)
            item.setFont(font)
            if hit:
                matched.append(window)
        if not pattern:
            self.match_summary.setText("Type part of the application name or title, "
                                       "or pick a window above.")
        elif not self.recent_windows:
            self.match_summary.setText("")
        elif matched:
            count = len(matched)
            self.match_summary.setText(f"✓ Matches {count} of the recent windows (shown in bold).")
        else:
            self.match_summary.setText("Matches none of the recent windows.")

    def validate_and_accept(self):
        """Validate the form before accepting"""
        name = self.rule_name()
        window_name = self.window_name_input.text().strip()

        if not window_name or not self.patterns():
            QMessageBox.warning(self, "Validation Error", "Enter what the window's name contains.")
            return

        if self.regex_check.isChecked():
            from StreamDock.business_logic.layout_manager import rule_patterns
            try:
                rule_patterns(self.patterns(), True)
            except re.error as e:
                QMessageBox.warning(self, "Validation Error", f"Not a valid regular expression: {e}")
                return

        # Check if name already exists (but allow keeping the same name when editing)
        if name != self.original_rule_name and name in self.existing_rules:
            QMessageBox.warning(self, "Validation Error", f"Rule name '{name}' already exists.")
            return

        if not self.available_layouts:
            QMessageBox.warning(self, "Validation Error", "No layouts available.")
            return

        self.accept()

    def patterns(self):
        """
        window_name as the form means it.

        A comma is legal inside a regex ({2,3}) and a title, so only plain
        patterns are split on it, and an unedited field returns the loaded
        value as it was - list or string.
        """
        text = self.window_name_input.text()
        if self._loaded_pattern_text is not None and text == self._loaded_pattern_text:
            return copy.deepcopy(self.window_rule.window_name)
        if self.regex_check.isChecked():
            return text.strip()
        return split_patterns(text)

    def rule_name(self) -> str:
        return self.name_input.text().strip() or \
            self.suggest_name(self.window_name_input.text().strip()) or "WindowRule"

    def load_rule(self, rule):
        """Load rule data into the form"""
        # window_name may be a list in the file; show it comma-separated.
        patterns = rule.patterns() if hasattr(rule, 'patterns') else [rule.window_name]
        self.window_name_input.setText(", ".join(str(p) for p in patterns if p))
        if getattr(rule, 'window_name', None) is not None:
            self._loaded_pattern_text = self.window_name_input.text()
        if rule.layout:
            index = self.layout_combo.findText(rule.layout)
            if index >= 0:
                self.layout_combo.setCurrentIndex(index)
        self.regex_check.setChecked(bool(getattr(rule, 'is_regex', False)))
        field_name = getattr(rule, 'match_field', None) or "class"
        if self.match_field_combo.findData(field_name) < 0 and field_name in MATCH_FIELD_LABELS:
            self.match_field_combo.addItem(MATCH_FIELD_LABELS[field_name], field_name)
        index = self.match_field_combo.findData(field_name)
        if index >= 0:
            self.match_field_combo.setCurrentIndex(index)

    def get_rule_data(self) -> dict:
        """Get the rule data from the form (validation already done)"""
        return {
            'name': self.rule_name(),
            'window_name': self.patterns(),
            'layout': self.layout_combo.currentText(),
            'match_field': self.match_field(),
            'is_regex': self.regex_check.isChecked(),
        }


class LayoutEditorDialog(ThemedDialog):
    """Dialog for creating or editing a layout"""

    def __init__(self, layout_name: str = None, clear_all: bool = False,
                 existing_layouts: list = None, parent=None, rename_only: bool = False):
        """
        Args:
            rename_only: Show just the name, selected, for F2
        """
        super().__init__(parent=parent)
        self.original_name = layout_name
        self.existing_layouts = existing_layouts or []

        self.setWindowTitle("Rename Layout" if rename_only
                            else "Edit Layout" if layout_name else "New Layout")
        self.setMinimumWidth(400)

        self.setup_ui(layout_name, clear_all)
        self.clear_all_toggle.setVisible(not rename_only)
        self.name_input.selectAll()
        self.name_input.setFocus()

    def setup_ui(self, layout_name: str, clear_all: bool):
        """Setup the UI"""
        layout = self.content_layout
        layout.setSpacing(16)

        form_layout = QFormLayout()
        form_layout.setSpacing(12)

        self.name_input = QLineEdit()
        if layout_name:
            self.name_input.setText(layout_name)
        self.name_input.setPlaceholderText("Enter layout name")
        form_layout.addRow("Layout Name:", self.name_input)

        layout.addLayout(form_layout)

        self.clear_all_toggle = ToggleSwitch(
            "Blank keys this layout leaves empty")
        self.clear_all_toggle.setToolTip(
            "Otherwise a position this layout leaves empty keeps the previous layout's key - "
            "its image and its actions.")
        self.clear_all_toggle.setChecked(clear_all)
        layout.addWidget(self.clear_all_toggle)

        layout.addStretch()

        self.add_actions("Save", self.validate_and_accept)

    def validate_and_accept(self):
        """Validate the form before accepting"""
        name = self.name_input.text().strip()

        if not name:
            QMessageBox.warning(self, "Validation Error", "Layout name is required.")
            return

        # Check if name already exists (but allow keeping the same name when editing)
        if name != self.original_name and name in self.existing_layouts:
            QMessageBox.warning(self, "Validation Error", f"Layout name '{name}' already exists.")
            return

        self.accept()

    def get_layout_data(self) -> dict:
        """Get the layout data from the form"""
        return {
            'name': self.name_input.text().strip(),
            'clear_all': self.clear_all_toggle.isChecked()
        }


class DeleteLayoutDialog(ThemedDialog):
    """
    Confirm deleting a layout, and decide what happens to its window rules.

    A rule may not point at a missing layout - the file would stop loading -
    so its rules either move to another layout or go with it.
    """

    def __init__(self, layout_name: str, usage, other_layouts: list, emptied_keys=(), parent=None):
        """
        Args:
            emptied_keys: Keys left with no action at all, which the user must fix
        """
        super().__init__("Delete Layout", parent=parent)
        self.setMinimumWidth(420)
        layout = self.content_layout

        lines = [f"Delete layout '{layout_name}'?"]
        if usage.keys:
            lines.append(f"\nThe CHANGE_LAYOUT actions switching to it will be removed from: "
                         f"{', '.join(usage.keys)}.")
        if emptied_keys:
            lines.append(f"\n⚠ That leaves {', '.join(emptied_keys)} with no action at all; "
                         "edit or delete them afterwards, or the configuration will not apply.")
        message = QLabel("\n".join(lines))
        message.setWordWrap(True)
        layout.addWidget(message)

        self.move_radio = None
        self.target_combo = None
        if usage.rules:
            rules_label = QLabel(f"Window rules switching to it: {', '.join(usage.rules)}")
            rules_label.setWordWrap(True)
            layout.addWidget(rules_label)
            row = QHBoxLayout()
            self.move_radio = QRadioButton("Move them to")
            self.target_combo = QComboBox()
            self.target_combo.addItems(other_layouts)
            row.addWidget(self.move_radio)
            row.addWidget(self.target_combo, stretch=1)
            layout.addLayout(row)
            self.delete_radio = QRadioButton("Delete them too")
            layout.addWidget(self.delete_radio)
            if other_layouts:
                self.move_radio.setChecked(True)
            else:
                self.move_radio.setEnabled(False)
                self.target_combo.setEnabled(False)
                self.delete_radio.setChecked(True)
            self.move_radio.toggled.connect(self.target_combo.setEnabled)

        self.add_actions("Delete", self.accept, role="danger")

    def move_rules_to(self):
        """The layout to move the rules to, or None to delete them."""
        if self.move_radio is not None and self.move_radio.isChecked():
            return self.target_combo.currentText()
        return None


class AdvancedSettingsDialog(ThemedDialog):
    """Dialog for advanced device settings"""
    
    def __init__(self, config, parent=None):
        super().__init__(parent=parent)
        self.config = config
        
        self.setWindowTitle("Advanced Settings")
        self.setMinimumSize(550, 400)
        self.resize(600, 450)
        
        self.setup_ui()
    
    def setup_ui(self):
        """Setup the UI"""
        metrics = current_theme().metrics
        layout = self.content_layout
        layout.setSpacing(metrics.spacing)
        
        # Title
        title = QLabel("Advanced Device Settings")
        title.setProperty("headingLevel", "1")
        layout.addWidget(title)
        
        # Subtitle
        subtitle = QLabel("Configure advanced device behavior and timings")
        subtitle.setProperty("textRole", "caption")
        layout.addWidget(subtitle)
        
        layout.addSpacing(metrics.spacing)
        
        self.interval_spin = self._add_timing_card(
            layout, "Double-Press Detection", "Time Window:",
            self.config.settings.double_press_interval, 0.01, 2.0,
            DEFAULT_DOUBLE_PRESS_INTERVAL,
            "The time window (in seconds) for detecting double-presses on keys. "
            "Lower values require faster double-presses. Higher values are more forgiving "
            "but may delay single-press actions. Default: 0.3 seconds (300ms).")

        self.long_press_spin = self._add_timing_card(
            layout, "Long-Press Detection", "Hold Time:",
            self.config.settings.long_press_duration, 0.1, 5.0,
            DEFAULT_LONG_PRESS_DURATION,
            "How long (in seconds) a key must be held before its long-press actions run. "
            "On keys that have long-press actions, the press actions run when the key is "
            "released early instead of when it goes down. Default: 0.5 seconds (500ms).")

        layout.addStretch()
        
        self.add_actions("Save", self.accept)
    
    def _add_timing_card(self, layout, title, label, value, minimum, maximum,
                         default, help_text):
        """Add one framed seconds setting and return its spin box."""
        metrics = current_theme().metrics
        card = QWidget()
        card.setObjectName("card")
        card.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(
            metrics.card_padding + 4, metrics.card_padding + 4,
            metrics.card_padding + 4, metrics.card_padding + 4)
        card_layout.setSpacing(metrics.spacing)

        section_title = QLabel(title)
        section_title.setProperty("headingLevel", "2")
        card_layout.addWidget(section_title)

        row = QHBoxLayout()
        row_label = QLabel(label)
        row_label.setMinimumWidth(100)
        row.addWidget(row_label)

        spin = QDoubleSpinBox()
        spin.setRange(minimum, maximum)
        spin.setSingleStep(0.05)
        # Three decimals: a hand-tuned 0.125 must survive opening the dialog.
        spin.setDecimals(3)
        spin.setValue(value)
        spin.setSuffix(" sec")
        spin.setMinimumWidth(120)
        spin.setMaximumWidth(140)
        row.addWidget(spin)

        default_btn = create_styled_button("Reset to Default")
        default_btn.clicked.connect(lambda: spin.setValue(default))
        row.addWidget(default_btn)
        row.addStretch()
        card_layout.addLayout(row)

        help_label = QLabel(help_text)
        help_label.setProperty("textRole", "caption")
        help_label.setWordWrap(True)
        card_layout.addWidget(help_label)

        layout.addWidget(card)
        return spin

    def get_settings(self) -> dict:
        """Get the settings from the form"""
        return {
            'double_press_interval': self.interval_spin.value(),
            'long_press_duration': self.long_press_spin.value(),
        }
