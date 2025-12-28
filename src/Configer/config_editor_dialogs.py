#!/usr/bin/env python3
"""
Dialogs for StreamDock Configuration Editor
Handles key editing, action editing, and layout management
"""

from pathlib import Path

from config_editor_models import KeyDefinition
from config_editor_widgets import ActionListItem
from modern_styles import get_colors
from PIL import Image
from PyQt6.QtCore import QSize, Qt
from PyQt6.QtGui import QImage, QPixmap
from PyQt6.QtWidgets import (QButtonGroup, QCheckBox, QColorDialog, QComboBox,
                             QDialog, QDoubleSpinBox, QFileDialog, QFormLayout,
                             QGroupBox, QHBoxLayout, QLabel, QLineEdit,
                             QListWidget, QListWidgetItem, QMessageBox,
                             QPushButton, QRadioButton, QScrollArea,
                             QSizePolicy, QSpinBox, QTabWidget, QTextEdit,
                             QVBoxLayout, QWidget)

COLORS = get_colors()


def create_styled_button(text: str, icon: str = None, primary: bool = False) -> QPushButton:
    """Create a consistently styled button with optional icon
    
    Args:
        text: Button text
        icon: Unicode icon character (optional)
        primary: If True, use primary (blue) styling
    """
    if icon:
        button_text = f"{icon}  {text}"
    else:
        button_text = text
    
    btn = QPushButton(button_text)
    btn.setMinimumHeight(32)
    btn.setMinimumWidth(90)
    
    if primary:
        btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {COLORS['primary']};
                color: white;
                border: none;
                border-radius: 6px;
                padding: 6px 16px;
                font-weight: 500;
            }}
            QPushButton:hover {{
                background-color: {COLORS['primary_hover']};
            }}
            QPushButton:pressed {{
                background-color: {COLORS['primary']};
            }}
        """)
    else:
        btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {COLORS['bg_tertiary']};
                color: {COLORS['text_primary']};
                border: 1px solid {COLORS['border']};
                border-radius: 6px;
                padding: 6px 16px;
                font-weight: 500;
            }}
            QPushButton:hover {{
                background-color: {COLORS['bg_hover']};
                border-color: {COLORS['primary']};
            }}
            QPushButton:pressed {{
                background-color: {COLORS['bg_tertiary']};
            }}
        """)
    
    return btn


class KeyEditorDialog(QDialog):
    """Dialog for creating or editing a key"""
    
    def __init__(self, key_def: KeyDefinition = None, existing_keys: list = None, 
                 available_layouts: list = None, available_keys: list = None, parent=None):
        super().__init__(parent)
        self.key_def = key_def or KeyDefinition("NewKey")
        self.existing_keys = existing_keys or []
        self.available_layouts = available_layouts or []
        self.available_keys = available_keys or []
        self.selected_icon_path = None
        
        self.setWindowTitle("Edit Key" if key_def else "Create New Key")
        self.setMinimumSize(600, 750)
        self.resize(650, 800)
        
        self.setup_ui()
        self.load_key_data()
    
    def setup_ui(self):
        """Setup the UI"""
        layout = QVBoxLayout(self)
        
        # Key name
        name_layout = QHBoxLayout()
        name_layout.addWidget(QLabel("Key Name:"))
        self.name_edit = QLineEdit(self.key_def.name)
        name_layout.addWidget(self.name_edit)
        layout.addLayout(name_layout)
        
        # Display type selection
        display_group = QGroupBox("Display Type")
        display_layout = QVBoxLayout()
        
        self.type_group = QButtonGroup(self)
        self.icon_radio = QRadioButton("Icon")
        self.text_radio = QRadioButton("Text")
        self.type_group.addButton(self.icon_radio, 0)
        self.type_group.addButton(self.text_radio, 1)
        display_layout.addWidget(self.icon_radio)
        display_layout.addWidget(self.text_radio)
        
        display_group.setLayout(display_layout)
        layout.addWidget(display_group)
        
        # Icon settings (in a container for show/hide)
        self.icon_widget = QWidget()
        icon_layout = QVBoxLayout(self.icon_widget)
        
        icon_select_layout = QHBoxLayout()
        self.icon_path_label = QLabel("No icon selected")
        icon_select_layout.addWidget(self.icon_path_label)
        self.icon_select_btn = QPushButton("Select Icon...")
        self.icon_select_btn.clicked.connect(self.select_icon)
        icon_select_layout.addWidget(self.icon_select_btn)
        icon_layout.addLayout(icon_select_layout)
        
        # Icon preview with dark mode styling
        self.icon_preview = QLabel()
        self.icon_preview.setFixedSize(112, 112)
        self.icon_preview.setStyleSheet(f"""
            QLabel {{
                border: 2px solid {COLORS['border']};
                background-color: {COLORS['bg_secondary']};
                border-radius: 6px;
            }}
        """)
        self.icon_preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon_layout.addWidget(self.icon_preview)
        
        layout.addWidget(self.icon_widget)
        
        # Text settings (in a container for show/hide)
        self.text_widget = QWidget()
        text_layout = QFormLayout(self.text_widget)
        
        self.text_edit = QLineEdit()
        text_layout.addRow("Text:", self.text_edit)
        
        text_color_layout = QHBoxLayout()
        self.text_color_edit = QLineEdit("white")
        text_color_layout.addWidget(self.text_color_edit)
        self.text_color_btn = QPushButton("Choose...")
        self.text_color_btn.clicked.connect(self.choose_text_color)
        text_color_layout.addWidget(self.text_color_btn)
        text_layout.addRow("Text Color:", text_color_layout)
        
        bg_color_layout = QHBoxLayout()
        self.bg_color_edit = QLineEdit("black")
        bg_color_layout.addWidget(self.bg_color_edit)
        self.bg_color_btn = QPushButton("Choose...")
        self.bg_color_btn.clicked.connect(self.choose_bg_color)
        bg_color_layout.addWidget(self.bg_color_btn)
        text_layout.addRow("Background Color:", bg_color_layout)
        
        self.font_size_spin = QSpinBox()
        self.font_size_spin.setRange(1, 100)
        self.font_size_spin.setValue(20)
        text_layout.addRow("Font Size:", self.font_size_spin)
        
        self.bold_check = QCheckBox()
        self.bold_check.setChecked(True)
        text_layout.addRow("Bold:", self.bold_check)
        
        layout.addWidget(self.text_widget)
        
        # Actions tabs
        self.tabs = QTabWidget()
        
        self.press_actions_widget = ActionEditorWidget(self.available_layouts, self.available_keys)
        self.tabs.addTab(self.press_actions_widget, "On Press Actions")
        
        self.release_actions_widget = ActionEditorWidget(self.available_layouts, self.available_keys)
        self.tabs.addTab(self.release_actions_widget, "On Release Actions")
        
        self.double_press_actions_widget = ActionEditorWidget(self.available_layouts, self.available_keys)
        self.tabs.addTab(self.double_press_actions_widget, "On Double Press Actions")
        
        layout.addWidget(self.tabs)
        
        # Buttons
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        
        cancel_btn = create_styled_button("Cancel")
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(cancel_btn)
        
        save_btn = create_styled_button("Save", "💾", primary=True)
        save_btn.clicked.connect(self.accept)
        btn_layout.addWidget(save_btn)
        
        layout.addLayout(btn_layout)
        
        # Connect type radio buttons
        self.icon_radio.toggled.connect(self.update_display_type)
    
    def update_display_type(self):
        """Update visible widgets based on display type"""
        is_icon = self.icon_radio.isChecked()
        self.icon_widget.setVisible(is_icon)
        self.text_widget.setVisible(not is_icon)
    
    def select_icon(self):
        """Select an icon file"""
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Select Icon",
            "",
            "Images (*.png *.jpg *.jpeg *.gif *.svg *.bmp)"
        )
        
        if file_path:
            self.selected_icon_path = file_path
            self.icon_path_label.setText(Path(file_path).name)
            self.load_icon_preview(file_path)
    
    def load_icon_preview(self, icon_path: str):
        """Load and display icon preview"""
        if not icon_path:
            return
        
        # Handle relative paths
        icon_file = Path(icon_path)
        if not icon_file.is_absolute():
            # Try relative to src directory
            icon_file = Path(__file__).parent / 'src' / icon_path
        
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
        if self.key_def.is_icon_based():
            self.icon_radio.setChecked(True)
            if self.key_def.icon:
                self.icon_path_label.setText(self.key_def.icon)
                self.selected_icon_path = self.key_def.icon
                # Load and display the icon preview
                self.load_icon_preview(self.key_def.icon)
        elif self.key_def.is_text_based():
            self.text_radio.setChecked(True)
            self.text_edit.setText(self.key_def.text or "")
            self.text_color_edit.setText(self.key_def.text_color)
            self.bg_color_edit.setText(self.key_def.background_color)
            self.font_size_spin.setValue(self.key_def.font_size)
            self.bold_check.setChecked(self.key_def.bold)
        else:
            # Default to icon
            self.icon_radio.setChecked(True)
        
        self.update_display_type()
        
        # Load actions
        self.press_actions_widget.set_actions(self.key_def.on_press_actions)
        self.release_actions_widget.set_actions(self.key_def.on_release_actions)
        self.double_press_actions_widget.set_actions(self.key_def.on_double_press_actions)
    
    def get_key_definition(self) -> KeyDefinition:
        """Get the key definition from the dialog"""
        key_def = KeyDefinition(self.name_edit.text())
        
        if self.icon_radio.isChecked():
            key_def.icon = self.selected_icon_path or self.key_def.icon
            key_def.text = None
        else:
            key_def.text = self.text_edit.text()
            key_def.text_color = self.text_color_edit.text()
            key_def.background_color = self.bg_color_edit.text()
            key_def.font_size = self.font_size_spin.value()
            key_def.bold = self.bold_check.isChecked()
            key_def.icon = None
        
        key_def.on_press_actions = self.press_actions_widget.get_actions()
        key_def.on_release_actions = self.release_actions_widget.get_actions()
        key_def.on_double_press_actions = self.double_press_actions_widget.get_actions()
        
        return key_def


class ActionEditorWidget(QWidget):
    """Widget for editing a list of actions"""
    
    def __init__(self, available_layouts: list = None, available_keys: list = None, parent=None):
        super().__init__(parent)
        self.actions = []
        self.available_layouts = available_layouts or []
        self.available_keys = available_keys or []
        self.setup_ui()
    
    def setup_ui(self):
        """Setup the UI"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(12)
        
        # Scroll area for actions list
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setMinimumHeight(200)
        self.scroll.setMaximumHeight(350)
        self.scroll.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.scroll.setFrameShape(QScrollArea.Shape.StyledPanel)
        self.scroll.setStyleSheet(f"""
            QScrollArea {{
                border: 1px solid {COLORS['border']};
                border-radius: 4px;
                background-color: {COLORS['bg_secondary']};
            }}
        """)
        
        self.actions_container = QWidget()
        self.actions_layout = QVBoxLayout(self.actions_container)
        self.actions_layout.setContentsMargins(4, 4, 4, 4)
        self.actions_layout.setSpacing(4)
        
        self.scroll.setWidget(self.actions_container)
        layout.addWidget(self.scroll)
        
        # Add action button - smaller and centered, completely separate
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        add_btn = create_styled_button("Add Action", "➕", primary=True)
        add_btn.setMinimumWidth(120)
        add_btn.setMaximumWidth(150)
        add_btn.setFixedHeight(32)
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
            elif item.spacerItem():
                # Remove spacer item
                pass
        
        # Add action widgets
        for i, action in enumerate(self.actions):
            action_widget = ActionListItem(i, action)
            action_widget.remove_clicked.connect(self.remove_action)
            action_widget.edit_clicked.connect(self.edit_action)
            action_widget.move_up_clicked.connect(self.move_action_up)
            action_widget.move_down_clicked.connect(self.move_action_down)
            self.actions_layout.addWidget(action_widget)
        
        # Don't add stretch - let the scroll area handle spacing
        # Force container to update its size
        self.actions_container.updateGeometry()
    
    def add_action(self):
        """Add a new action"""
        dialog = ActionDialog(None, self.available_layouts, self.available_keys)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            action = dialog.get_action()
            if action:
                self.actions.append(action)
                self.rebuild_actions_list()
    
    def edit_action(self, index: int):
        """Edit an existing action"""
        if 0 <= index < len(self.actions):
            dialog = ActionDialog(self.actions[index], self.available_layouts, self.available_keys)
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
    
    def move_action_up(self, index: int):
        """Move action up in the list"""
        if index > 0:
            self.actions[index], self.actions[index - 1] = self.actions[index - 1], self.actions[index]
            self.rebuild_actions_list()
    
    def move_action_down(self, index: int):
        """Move action down in the list"""
        if index < len(self.actions) - 1:
            self.actions[index], self.actions[index + 1] = self.actions[index + 1], self.actions[index]
            self.rebuild_actions_list()


class ActionDialog(QDialog):
    """Dialog for creating or editing a single action"""
    
    # Mapping from backend keys to user-friendly display names
    ACTION_TYPE_DISPLAY = {
        "EXECUTE_COMMAND": "Execute Command",
        "LAUNCH_APPLICATION": "Launch Application",
        "KEY_PRESS": "Key Press",
        "TYPE_TEXT": "Type Text",
        "WAIT": "Wait",
        "CHANGE_KEY_IMAGE": "Change Key Image",
        "CHANGE_KEY": "Change Key",
        "CHANGE_LAYOUT": "Change Layout",
        "DBUS": "D-Bus",
        "DEVICE_BRIGHTNESS_UP": "Device Brightness Up",
        "DEVICE_BRIGHTNESS_DOWN": "Device Brightness Down"
    }
    
    # Reverse mapping for quick lookup
    ACTION_TYPE_BACKEND = {v: k for k, v in ACTION_TYPE_DISPLAY.items()}
    
    def __init__(self, action_dict: dict = None, available_layouts: list = None, 
                 available_keys: list = None, parent=None):
        super().__init__(parent)
        self.action_dict = action_dict or {}
        self.available_layouts = available_layouts or []
        self.available_keys = available_keys or []
        
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
        layout = QVBoxLayout(self)
        
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
        
        # Buttons
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        
        cancel_btn = create_styled_button("Cancel")
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(cancel_btn)
        
        save_btn = create_styled_button("OK", "✓", primary=True)
        save_btn.clicked.connect(self.accept)
        btn_layout.addWidget(save_btn)
        
        layout.addLayout(btn_layout)
    
    def update_action_fields(self):
        """Update fields based on selected action type"""
        # Clear existing fields
        while self.fields_layout.count():
            item = self.fields_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        
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
            self.launch_simple_radio.setChecked(True)
            self.fields_layout.addWidget(self.launch_simple_radio)
            self.fields_layout.addWidget(self.launch_advanced_radio)
            
            # Simple mode
            self.launch_simple_widget = QWidget()
            simple_layout = QVBoxLayout(self.launch_simple_widget)
            simple_layout.addWidget(QLabel("Command or Desktop File:"))
            self.launch_simple_edit = QLineEdit()
            self.launch_simple_edit.setPlaceholderText("firefox or firefox.desktop")
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
            self.wait_spin = QSpinBox()
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
            browse_btn = QPushButton("Browse...")
            browse_btn.clicked.connect(self.browse_image)
            img_layout.addWidget(browse_btn)
            self.fields_layout.addLayout(img_layout)
        
        elif action_type == "CHANGE_KEY":
            label = QLabel("Change to Key:")
            self.fields_layout.addWidget(label)
            self.change_key_combo = QComboBox()
            if self.available_keys:
                self.change_key_combo.addItems(self.available_keys)
            else:
                self.change_key_combo.addItem("No keys available")
                self.change_key_combo.setEnabled(False)
            self.fields_layout.addWidget(self.change_key_combo)
        
        elif action_type == "CHANGE_LAYOUT":
            self.layout_simple_radio = QRadioButton("Simple (layout name only)")
            self.layout_advanced_radio = QRadioButton("Advanced (with options)")
            self.layout_simple_radio.setChecked(True)
            self.fields_layout.addWidget(self.layout_simple_radio)
            self.fields_layout.addWidget(self.layout_advanced_radio)
            
            # Simple
            self.layout_simple_widget = QWidget()
            simple_layout = QVBoxLayout(self.layout_simple_widget)
            simple_layout.addWidget(QLabel("Layout:"))
            self.layout_name_combo = QComboBox()
            if self.available_layouts:
                self.layout_name_combo.addItems(self.available_layouts)
            else:
                self.layout_name_combo.addItem("No layouts available")
                self.layout_name_combo.setEnabled(False)
            simple_layout.addWidget(self.layout_name_combo)
            self.fields_layout.addWidget(self.layout_simple_widget)
            
            # Advanced
            self.layout_advanced_widget = QWidget()
            adv_layout = QFormLayout(self.layout_advanced_widget)
            self.layout_name_adv_combo = QComboBox()
            if self.available_layouts:
                self.layout_name_adv_combo.addItems(self.available_layouts)
            else:
                self.layout_name_adv_combo.addItem("No layouts available")
                self.layout_name_adv_combo.setEnabled(False)
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
            self.dbus_custom_edit.setPlaceholderText("e.g., play_pause")
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
        
        # Get action type (backend key)
        action_type = list(self.action_dict.keys())[0]
        action_value = self.action_dict[action_type]
        
        # Convert backend key to display name and set in combo
        display_name = self.ACTION_TYPE_DISPLAY.get(action_type, action_type)
        index = self.action_type_combo.findText(display_name)
        if index >= 0:
            self.action_type_combo.setCurrentIndex(index)
        
        # Load specific fields based on type
        if action_type == "EXECUTE_COMMAND":
            if isinstance(action_value, list):
                self.command_text.setPlainText("\n".join(action_value))
            else:
                self.command_text.setPlainText(str(action_value))
        
        elif action_type == "LAUNCH_APPLICATION":
            if isinstance(action_value, (str, list)):
                self.launch_simple_radio.setChecked(True)
                if isinstance(action_value, list):
                    self.launch_simple_edit.setText(" ".join(action_value))
                else:
                    self.launch_simple_edit.setText(action_value)
            elif isinstance(action_value, dict):
                self.launch_advanced_radio.setChecked(True)
                if 'command' in action_value:
                    cmd = action_value['command']
                    if isinstance(cmd, list):
                        self.launch_command_edit.setText(" ".join(cmd))
                    else:
                        self.launch_command_edit.setText(cmd)
                if 'desktop_file' in action_value:
                    self.launch_desktop_edit.setText(action_value['desktop_file'])
                if 'class_name' in action_value:
                    self.launch_class_edit.setText(action_value['class_name'])
                if 'match_type' in action_value:
                    self.launch_match_combo.setCurrentText(action_value['match_type'])
                if 'force_new' in action_value:
                    self.launch_force_check.setChecked(action_value['force_new'])
        
        elif action_type == "KEY_PRESS":
            self.key_combo_edit.setText(action_value)
        
        elif action_type == "TYPE_TEXT":
            self.type_text_edit.setPlainText(action_value)
        
        elif action_type == "WAIT":
            self.wait_spin.setValue(int(action_value))
        
        elif action_type == "CHANGE_KEY_IMAGE":
            self.image_path_edit.setText(action_value)
        
        elif action_type == "CHANGE_KEY":
            # Set the combo box to the key name
            index = self.change_key_combo.findText(action_value)
            if index >= 0:
                self.change_key_combo.setCurrentIndex(index)
        
        elif action_type == "CHANGE_LAYOUT":
            if isinstance(action_value, str):
                self.layout_simple_radio.setChecked(True)
                index = self.layout_name_combo.findText(action_value)
                if index >= 0:
                    self.layout_name_combo.setCurrentIndex(index)
            elif isinstance(action_value, dict):
                self.layout_advanced_radio.setChecked(True)
                layout_name = action_value.get('layout', '')
                index = self.layout_name_adv_combo.findText(layout_name)
                if index >= 0:
                    self.layout_name_adv_combo.setCurrentIndex(index)
                self.layout_clear_check.setChecked(action_value.get('clear_all', False))
        
        elif action_type == "DBUS":
            if isinstance(action_value, dict):
                action = action_value.get('action', '')
                # Check if it's a predefined action
                index = self.dbus_action_combo.findText(action)
                if index >= 0:
                    self.dbus_preset_radio.setChecked(True)
                    self.dbus_action_combo.setCurrentIndex(index)
                else:
                    self.dbus_custom_radio.setChecked(True)
                    self.dbus_custom_edit.setText(action)
            elif isinstance(action_value, str):
                # Check if it's a predefined action
                index = self.dbus_action_combo.findText(action_value)
                if index >= 0:
                    self.dbus_preset_radio.setChecked(True)
                    self.dbus_action_combo.setCurrentIndex(index)
                else:
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
            if self.launch_simple_radio.isChecked():
                value = self.launch_simple_edit.text().strip()
                if not value:
                    return None
                # Check if it's a desktop file or command
                if value.endswith('.desktop') or '.' in value:
                    return {action_type: value}
                else:
                    # Try to split as command
                    parts = value.split()
                    return {action_type: parts if len(parts) > 1 else value}
            else:
                # Advanced mode
                result = {}
                
                desktop = self.launch_desktop_edit.text().strip()
                command = self.launch_command_edit.text().strip()
                
                if desktop:
                    result['desktop_file'] = desktop
                elif command:
                    parts = command.split()
                    result['command'] = parts if len(parts) > 1 else command
                else:
                    return None
                
                if self.launch_class_edit.text().strip():
                    result['class_name'] = self.launch_class_edit.text().strip()
                if self.launch_match_combo.currentText() != "contains":
                    result['match_type'] = self.launch_match_combo.currentText()
                if self.launch_force_check.isChecked():
                    result['force_new'] = True
                
                return {action_type: result}
        
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
            return {action_type: self.wait_spin.value()}
        
        elif action_type == "CHANGE_KEY_IMAGE":
            value = self.image_path_edit.text().strip()
            if not value:
                return None
            return {action_type: value}
        
        elif action_type == "CHANGE_KEY":
            value = self.change_key_combo.currentText()
            if not value or value == "No keys available":
                return None
            return {action_type: value}
        
        elif action_type == "CHANGE_LAYOUT":
            if self.layout_simple_radio.isChecked():
                value = self.layout_name_combo.currentText()
                if not value or value == "No layouts available":
                    return None
                return {action_type: value}
            else:
                value = self.layout_name_adv_combo.currentText()
                if not value or value == "No layouts available":
                    return None
                result = {'layout': value}
                if self.layout_clear_check.isChecked():
                    result['clear_all'] = True
                return {action_type: result}
        
        elif action_type == "DBUS":
            if self.dbus_preset_radio.isChecked():
                action = self.dbus_action_combo.currentText()
            else:
                action = self.dbus_custom_edit.text().strip()
                if not action:
                    return None
            return {action_type: {'action': action}}
        
        elif action_type in ["DEVICE_BRIGHTNESS_UP", "DEVICE_BRIGHTNESS_DOWN"]:
            return {action_type: ""}
        
        return None


class ManageKeysDialog(QDialog):
    """Dialog for managing all key definitions"""
    
    def __init__(self, config, parent=None):
        super().__init__(parent)
        self.config = config
        self.modified = False
        
        self.setWindowTitle("Manage All Keys")
        self.setMinimumSize(600, 500)
        
        self.setup_ui()
        self.refresh_keys_list()
    
    def setup_ui(self):
        """Setup the UI"""
        layout = QVBoxLayout(self)
        
        # Title bar with add button
        title_layout = QHBoxLayout()
        
        title = QLabel("All Key Definitions")
        title.setStyleSheet("font-size: 14pt; font-weight: bold;")
        title_layout.addWidget(title)
        
        title_layout.addStretch()
        
        # Green + icon
        self.add_btn = QPushButton("+")
        self.add_btn.setFixedSize(24, 24)
        self.add_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent;
                color: {COLORS['success']};
                font-size: 24px;
                font-weight: bold;
                border: none;
                padding: 0px;
            }}
            QPushButton:hover {{
                color: {COLORS['success_hover']};
            }}
        """)
        self.add_btn.setToolTip("Add new key")
        self.add_btn.clicked.connect(self.add_new_key)
        title_layout.addWidget(self.add_btn)
        
        layout.addLayout(title_layout)
        
        # Keys list
        self.keys_list = QListWidget()
        layout.addWidget(self.keys_list)
        
        # Close button at bottom
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        
        self.close_btn = create_styled_button("Close", primary=True)
        self.close_btn.clicked.connect(self.accept)
        btn_layout.addWidget(self.close_btn)
        
        layout.addLayout(btn_layout)
    
    def refresh_keys_list(self):
        """Refresh the keys list display"""
        self.keys_list.clear()
        
        if not self.config.keys:
            item = QListWidgetItem("No keys defined")
            item.setFlags(Qt.ItemFlag.NoItemFlags)
            self.keys_list.addItem(item)
            return
        
        for key_name, key_def in self.config.keys.items():
            # Create list item
            item = QListWidgetItem(self.keys_list)
            
            # Create custom widget with edit and delete buttons
            widget = QWidget()
            widget_layout = QHBoxLayout(widget)
            widget_layout.setContentsMargins(8, 0, 8, 0)
            widget_layout.setSpacing(8)
            
            # Key info label
            if key_def.is_icon_based():
                item_text = f"{key_name} (Icon: {Path(key_def.icon).name})"
            elif key_def.is_text_based():
                item_text = f"{key_name} (Text: {key_def.text})"
            else:
                item_text = key_name
            
            label = QLabel(item_text)
            widget_layout.addWidget(label, alignment=Qt.AlignmentFlag.AlignVCenter)
            
            widget_layout.addStretch()
            
            # Cyan pencil edit icon
            edit_btn = QPushButton("✎")
            edit_btn.setFixedSize(20, 20)
            edit_btn.setStyleSheet(f"""
                QPushButton {{
                    background: transparent;
                    color: {COLORS['info']};
                    font-size: 18px;
                    font-weight: bold;
                    border: none;
                    padding: 0px;
                }}
                QPushButton:hover {{
                    color: {COLORS['info_hover']};
                }}
            """)
            edit_btn.setToolTip("Edit key")
            edit_btn.clicked.connect(lambda checked, n=key_name: self.edit_key_by_name(n))
            widget_layout.addWidget(edit_btn, alignment=Qt.AlignmentFlag.AlignVCenter)
            
            # Red X delete icon
            delete_btn = QPushButton("✕")
            delete_btn.setFixedSize(20, 20)
            delete_btn.setStyleSheet(f"""
                QPushButton {{
                    background: transparent;
                    color: {COLORS['danger']};
                    font-size: 18px;
                    font-weight: bold;
                    border: none;
                    padding: 0px;
                }}
                QPushButton:hover {{
                    color: {COLORS['danger_hover']};
                }}
            """)
            delete_btn.setToolTip("Delete key")
            delete_btn.clicked.connect(lambda checked, n=key_name: self.delete_key_by_name(n))
            widget_layout.addWidget(delete_btn, alignment=Qt.AlignmentFlag.AlignVCenter)
            
            # Set the widget for the item with proper height
            widget.setMinimumHeight(40)
            item.setSizeHint(QSize(widget.sizeHint().width(), 40))
            self.keys_list.setItemWidget(item, widget)
            
            # Store key name in item data
            item.setData(Qt.ItemDataRole.UserRole, key_name)
    
    def add_new_key(self):
        """Add a new key"""
        existing_keys = list(self.config.keys.keys())
        available_layouts = list(self.config.layouts.keys())
        available_keys = list(self.config.keys.keys())
        editor = KeyEditorDialog(existing_keys=existing_keys,
                                available_layouts=available_layouts,
                                available_keys=available_keys,
                                parent=self)
        
        if editor.exec() == QDialog.DialogCode.Accepted:
            key_def = editor.get_key_definition()
            
            # Check if key name already exists
            if key_def.name in self.config.keys:
                QMessageBox.warning(self, "Error", "Key name already exists!")
                return
            
            # Add key to config
            self.config.add_key(key_def.name, key_def)
            self.modified = True
            self.refresh_keys_list()
    
    def edit_key_by_name(self, key_name: str):
        """Edit a key by its name"""
        if not key_name or key_name not in self.config.keys:
            return
        
        key_def = self.config.keys[key_name]
        existing_keys = [k for k in self.config.keys.keys() if k != key_name]
        available_layouts = list(self.config.layouts.keys())
        available_keys = [k for k in self.config.keys.keys() if k != key_name]
        
        editor = KeyEditorDialog(key_def, existing_keys, available_layouts, available_keys, self)
        
        if editor.exec() == QDialog.DialogCode.Accepted:
            new_key_def = editor.get_key_definition()
            
            # Check if name changed and new name already exists
            if new_key_def.name != key_name and new_key_def.name in self.config.keys:
                QMessageBox.warning(self, "Error", "Key name already exists!")
                return
            
            # If name changed, update all layouts
            if new_key_def.name != key_name:
                self.rename_key_in_layouts(key_name, new_key_def.name)
                self.config.remove_key(key_name)
            
            # Update key definition
            self.config.add_key(new_key_def.name, new_key_def)
            self.modified = True
            self.refresh_keys_list()
    
    def delete_key_by_name(self, key_name: str):
        """Delete a key by its name"""
        if not key_name or key_name not in self.config.keys:
            return
        
        # Check which layouts use this key
        using_layouts = []
        for layout_name, layout in self.config.layouts.items():
            for pos, assigned_key in layout.keys.items():
                if assigned_key == key_name:
                    using_layouts.append(layout_name)
                    break
        
        # Confirm deletion
        if using_layouts:
            layouts_str = ", ".join(using_layouts)
            reply = QMessageBox.question(
                self,
                "Confirm Deletion",
                f"Key '{key_name}' is used in the following layout(s):\n{layouts_str}\n\n"
                f"Deleting this key will remove it from all layouts.\n\nContinue?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
        else:
            reply = QMessageBox.question(
                self,
                "Confirm Deletion",
                f"Are you sure you want to delete key '{key_name}'?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
        
        if reply == QMessageBox.StandardButton.Yes:
            # Remove key from all layouts
            for layout in self.config.layouts.values():
                positions_to_remove = []
                for pos, assigned_key in layout.keys.items():
                    if assigned_key == key_name:
                        positions_to_remove.append(pos)
                for pos in positions_to_remove:
                    layout.remove_key_at_position(pos)
            
            # Remove key definition
            self.config.remove_key(key_name)
            self.modified = True
            self.refresh_keys_list()
    
    def rename_key_in_layouts(self, old_name: str, new_name: str):
        """Rename a key in all layouts"""
        for layout in self.config.layouts.values():
            for position, key_name in list(layout.keys.items()):
                if key_name == old_name:
                    layout.keys[position] = new_name
    
    def was_modified(self) -> bool:
        """Check if any modifications were made"""
        return self.modified


class WindowRuleDialog(QDialog):
    """Dialog for adding/editing a window rule"""
    
    def __init__(self, available_layouts: list, rule_name: str = None, window_rule=None, existing_rules: list = None, parent=None):
        super().__init__(parent)
        self.available_layouts = available_layouts
        self.original_rule_name = rule_name
        self.window_rule = window_rule
        self.existing_rules = existing_rules or []
        
        self.setWindowTitle("Add Window Rule" if not rule_name else "Edit Window Rule")
        self.setMinimumWidth(450)
        
        self.setup_ui()
        
        if window_rule:
            self.load_rule(window_rule)
    
    def setup_ui(self):
        """Setup the UI"""
        layout = QVBoxLayout(self)
        
        # Form layout
        form = QFormLayout()
        
        # Rule name
        self.name_input = QLineEdit()
        if self.original_rule_name:
            self.name_input.setText(self.original_rule_name)
        self.name_input.setPlaceholderText("Enter a unique rule name")
        form.addRow("Rule Name:", self.name_input)
        
        # Window name pattern
        self.window_name_input = QLineEdit()
        self.window_name_input.setPlaceholderText("e.g., firefox, kate, konsole")
        form.addRow("Window Pattern:", self.window_name_input)
        
        # Match field selector
        self.match_field_combo = QComboBox()
        self.match_field_combo.addItems(["class", "title", "raw"])
        self.match_field_combo.setCurrentText("class")
        self.match_field_combo.currentTextChanged.connect(self._update_placeholder)
        form.addRow("Match By:", self.match_field_combo)
        
        # Target layout
        self.layout_combo = QComboBox()
        if self.available_layouts:
            self.layout_combo.addItems(self.available_layouts)
        else:
            self.layout_combo.addItem("No layouts available")
            self.layout_combo.setEnabled(False)
        form.addRow("Target Layout:", self.layout_combo)
        
        layout.addLayout(form)
        
        # Help text
        help_label = QLabel(
            "The window rule will automatically switch to the target layout\n"
            "when a window matching the pattern becomes active.\n\n"
            "Match By:\n"
            "• class - Match against window class/application name (recommended)\n"
            "• title - Match against window title text\n"
            "• raw - Match against raw window information"
        )
        help_label.setStyleSheet("color: gray; font-size: 9pt;")
        help_label.setWordWrap(True)
        layout.addWidget(help_label)
        
        # Buttons
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        
        cancel_btn = create_styled_button("Cancel")
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(cancel_btn)
        
        save_btn = create_styled_button("Save", "💾", primary=True)
        save_btn.clicked.connect(self.validate_and_accept)
        save_btn.setDefault(True)
        btn_layout.addWidget(save_btn)
        
        layout.addLayout(btn_layout)
    
    def _update_placeholder(self, match_field: str):
        """Update the placeholder text based on selected match field"""
        placeholders = {
            'class': 'e.g., firefox, kate, konsole, chrome',
            'title': 'e.g., Mozilla Firefox, Document.txt',
            'raw': 'e.g., full window information string'
        }
        self.window_name_input.setPlaceholderText(placeholders.get(match_field, ''))
    
    def validate_and_accept(self):
        """Validate the form before accepting"""
        name = self.name_input.text().strip()
        window_name = self.window_name_input.text().strip()
        
        if not name:
            QMessageBox.warning(self, "Validation Error", "Rule name is required.")
            return
        
        # Check if name already exists (but allow keeping the same name when editing)
        if name != self.original_rule_name and name in self.existing_rules:
            QMessageBox.warning(self, "Validation Error", f"Rule name '{name}' already exists.")
            return
        
        if not window_name:
            QMessageBox.warning(self, "Validation Error", "Window name pattern is required.")
            return
        
        if not self.available_layouts:
            QMessageBox.warning(self, "Validation Error", "No layouts available.")
            return
        
        self.accept()
    
    def load_rule(self, rule):
        """Load rule data into the form"""
        if rule.window_name:
            self.window_name_input.setText(rule.window_name)
        if rule.layout:
            index = self.layout_combo.findText(rule.layout)
            if index >= 0:
                self.layout_combo.setCurrentIndex(index)
        if hasattr(rule, 'match_field') and rule.match_field:
            index = self.match_field_combo.findText(rule.match_field)
            if index >= 0:
                self.match_field_combo.setCurrentIndex(index)
    
    def get_rule_data(self) -> dict:
        """Get the rule data from the form (validation already done)"""
        name = self.name_input.text().strip()
        window_name = self.window_name_input.text().strip()
        layout = self.layout_combo.currentText()
        match_field = self.match_field_combo.currentText()
        
        return {
            'name': name,
            'window_name': window_name,
            'layout': layout,
            'match_field': match_field
        }


class LayoutEditorDialog(QDialog):
    """Dialog for creating or editing a layout"""
    
    def __init__(self, layout_name: str = None, clear_all: bool = False, 
                 existing_layouts: list = None, parent=None):
        super().__init__(parent)
        self.original_name = layout_name
        self.existing_layouts = existing_layouts or []
        
        self.setWindowTitle("Edit Layout" if layout_name else "New Layout")
        self.setMinimumSize(400, 200)
        
        self.setup_ui(layout_name, clear_all)
    
    def setup_ui(self, layout_name: str, clear_all: bool):
        """Setup the UI"""
        layout = QVBoxLayout(self)
        layout.setSpacing(16)
        
        # Layout name
        form_layout = QFormLayout()
        form_layout.setSpacing(12)
        
        self.name_input = QLineEdit()
        if layout_name:
            self.name_input.setText(layout_name)
        self.name_input.setPlaceholderText("Enter layout name")
        form_layout.addRow("Layout Name:", self.name_input)
        
        layout.addLayout(form_layout)
        
        # Clear all icons checkbox
        self.clear_all_check = QCheckBox("Clear all icons when switching to this layout")
        self.clear_all_check.setChecked(clear_all)
        layout.addWidget(self.clear_all_check)
        
        # Help text
        help_label = QLabel(
            "When 'Clear all icons' is enabled, all keys will be cleared\n"
            "before this layout is applied, ensuring a clean slate."
        )
        help_label.setStyleSheet(f"color: {COLORS['text_secondary']}; font-size: 11px;")
        help_label.setWordWrap(True)
        layout.addWidget(help_label)
        
        layout.addStretch()
        
        # Buttons
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        
        cancel_btn = create_styled_button("Cancel")
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(cancel_btn)
        
        save_btn = create_styled_button("Save", "💾", primary=True)
        save_btn.clicked.connect(self.validate_and_accept)
        save_btn.setDefault(True)
        btn_layout.addWidget(save_btn)
        
        layout.addLayout(btn_layout)
    
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
            'clear_all': self.clear_all_check.isChecked()
        }


class AdvancedSettingsDialog(QDialog):
    """Dialog for advanced device settings"""
    
    def __init__(self, config, parent=None):
        super().__init__(parent)
        self.config = config
        
        self.setWindowTitle("Advanced Settings")
        self.setMinimumSize(550, 400)
        self.resize(600, 450)
        
        self.setup_ui()
    
    def setup_ui(self):
        """Setup the UI"""
        layout = QVBoxLayout(self)
        layout.setSpacing(16)
        layout.setContentsMargins(24, 24, 24, 24)
        
        # Title
        title = QLabel("Advanced Device Settings")
        title.setStyleSheet(f"font-size: 18px; font-weight: 600; color: {COLORS['text_primary']};")
        layout.addWidget(title)
        
        # Subtitle
        subtitle = QLabel("Configure advanced device behavior and timings")
        subtitle.setStyleSheet(f"color: {COLORS['text_secondary']}; font-size: 12px;")
        layout.addWidget(subtitle)
        
        # Spacing
        layout.addSpacing(8)
        
        # Settings form - using simple VBox instead of QGroupBox
        settings_container = QWidget()
        settings_container.setStyleSheet(f"""
            QWidget {{
                background-color: {COLORS['bg_secondary']};
                border: 1px solid {COLORS['border']};
                border-radius: 8px;
            }}
        """)
        settings_layout = QVBoxLayout(settings_container)
        settings_layout.setContentsMargins(20, 20, 20, 20)
        settings_layout.setSpacing(16)
        
        # Section title
        section_title = QLabel("Double-Press Detection")
        section_title.setStyleSheet(f"font-size: 14px; font-weight: 600; color: {COLORS['text_primary']};")
        settings_layout.addWidget(section_title)
        
        # Time window setting
        time_layout = QHBoxLayout()
        time_label = QLabel("Time Window:")
        time_label.setStyleSheet(f"color: {COLORS['text_primary']}; font-size: 13px;")
        time_label.setMinimumWidth(100)
        time_layout.addWidget(time_label)
        
        self.interval_spin = QDoubleSpinBox()
        self.interval_spin.setRange(0.1, 2.0)
        self.interval_spin.setSingleStep(0.05)
        self.interval_spin.setDecimals(2)
        self.interval_spin.setValue(self.config.double_press_interval)
        self.interval_spin.setSuffix(" sec")
        self.interval_spin.setMinimumWidth(120)
        self.interval_spin.setMaximumWidth(140)
        self.interval_spin.setMinimumHeight(30)
        time_layout.addWidget(self.interval_spin)
        
        # Default button
        default_btn = QPushButton("Reset to Default")
        default_btn.setMinimumHeight(30)
        default_btn.clicked.connect(lambda: self.interval_spin.setValue(0.3))
        time_layout.addWidget(default_btn)
        time_layout.addStretch()
        
        settings_layout.addLayout(time_layout)
        
        # Help text
        help_text = QLabel(
            "The time window (in seconds) for detecting double-presses on keys. "
            "Lower values require faster double-presses. Higher values are more forgiving "
            "but may delay single-press actions. Default: 0.3 seconds (300ms)."
        )
        help_text.setStyleSheet(f"color: {COLORS['text_secondary']}; font-size: 11px;")
        help_text.setWordWrap(True)
        settings_layout.addWidget(help_text)
        
        layout.addWidget(settings_container)
        layout.addStretch()
        
        # Buttons
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        
        cancel_btn = create_styled_button("Cancel")
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(cancel_btn)
        
        save_btn = create_styled_button("Save", "💾", primary=True)
        save_btn.clicked.connect(self.accept)
        save_btn.setDefault(True)
        btn_layout.addWidget(save_btn)
        
        layout.addLayout(btn_layout)
    
    def get_settings(self) -> dict:
        """Get the settings from the form"""
        return {
            'double_press_interval': self.interval_spin.value()
        }
