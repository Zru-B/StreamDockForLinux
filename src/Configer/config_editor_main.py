#!/usr/bin/env python3
"""
Main window for StreamDock Configuration Editor
"""

from PyQt6.QtWidgets import (QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, 
                              QGridLayout, QPushButton, QFileDialog, QMessageBox,
                              QInputDialog, QMenuBar, QMenu, QLabel, QSpinBox,
                              QCheckBox, QGroupBox, QFormLayout, QDialog)
from PyQt6.QtCore import Qt, QPoint
from PyQt6.QtGui import QAction, QKeySequence, QCursor
from config_editor_models import StreamDockConfig, KeyDefinition, Layout, WindowRule
from config_editor_widgets import KeySquare, LayoutListWidget, WindowRulesWidget
from config_editor_dialogs import KeyEditorDialog, ManageKeysDialog, WindowRuleDialog, LayoutEditorDialog, AdvancedSettingsDialog
from modern_styles import get_stylesheet, get_colors
from pathlib import Path


class KeySelectionDialog(QMessageBox):
    """Dialog for selecting an existing key or creating a new one"""
    
    def __init__(self, available_keys: list, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Select or Create Key")
        self.setText("Choose an option:")
        self.available_keys = available_keys
        self.selected_key = None
        self.create_new = False
        
        self.select_btn = self.addButton("Select Existing", QMessageBox.ButtonRole.ActionRole)
        self.create_btn = self.addButton("Create New", QMessageBox.ButtonRole.ActionRole)
        self.cancel_btn = self.addButton("Cancel", QMessageBox.ButtonRole.RejectRole)
        
        self.buttonClicked.connect(self.on_button_clicked)
    
    def on_button_clicked(self, button):
        """Handle button clicks"""
        if button == self.select_btn:
            self.select_existing_key()
        elif button == self.create_btn:
            self.create_new = True
            self.accept()
    
    def select_existing_key(self):
        """Show dialog to select an existing key"""
        if not self.available_keys:
            QMessageBox.warning(self, "No Keys", "No existing keys available. Create a new one.")
            return
        
        key_name, ok = QInputDialog.getItem(
            self,
            "Select Key",
            "Choose a key:",
            self.available_keys,
            0,
            False
        )
        
        if ok and key_name:
            self.selected_key = key_name
            self.accept()


class KeyActionDialog(QMessageBox):
    """Dialog for actions on an existing key square"""
    
    EDIT = 1
    REPLACE = 2
    CREATE_NEW = 3
    REMOVE = 4
    CANCEL = 5
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Key Actions")
        self.setText("What would you like to do?")
        self.action = self.CANCEL
        
        self.edit_btn = self.addButton("Edit Key", QMessageBox.ButtonRole.ActionRole)
        self.replace_btn = self.addButton("Replace with Existing", QMessageBox.ButtonRole.ActionRole)
        self.create_btn = self.addButton("Create & Replace", QMessageBox.ButtonRole.ActionRole)
        self.remove_btn = self.addButton("Remove from Layout", QMessageBox.ButtonRole.ActionRole)
        self.cancel_btn = self.addButton("Cancel", QMessageBox.ButtonRole.RejectRole)
        
        self.buttonClicked.connect(self.on_button_clicked)
    
    def on_button_clicked(self, button):
        """Handle button clicks"""
        if button == self.edit_btn:
            self.action = self.EDIT
        elif button == self.replace_btn:
            self.action = self.REPLACE
        elif button == self.create_btn:
            self.action = self.CREATE_NEW
        elif button == self.remove_btn:
            self.action = self.REMOVE
        else:
            self.action = self.CANCEL


class ConfigEditorMainWindow(QMainWindow):
    """Main window for the configuration editor"""
    
    def __init__(self):
        super().__init__()
        self.config = StreamDockConfig()
        self.current_layout = None
        self.config_file_path = None
        self.key_squares = []
        self.modified = False  # Track if config has unsaved changes
        
        self.setWindowTitle("StreamDock Configuration Editor")
        self.setMinimumSize(1200, 800)
        
        # Apply modern stylesheet
        self.setStyleSheet(get_stylesheet())
        
        self.setup_ui()
        self.setup_menu()
        
        # Try to load default config as template (don't set as current file)
        default_config = Path(__file__).parent.parent / "config.yml"
        if default_config.exists():
            self.load_config(str(default_config), set_as_current_file=False)
    
    def setup_ui(self):
        """Setup the user interface"""
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        main_layout = QHBoxLayout(central_widget)
        main_layout.setSpacing(16)
        main_layout.setContentsMargins(16, 16, 16, 16)
        
        # Left panel - Split vertically for layouts and window rules
        left_panel = QWidget()
        left_panel.setMaximumWidth(300)
        left_layout = QVBoxLayout(left_panel)
        left_layout.setSpacing(16)
        left_layout.setContentsMargins(0, 0, 0, 0)
        
        # Layout list (upper half)
        self.layout_list = LayoutListWidget()
        self.layout_list.layout_selected.connect(self.on_layout_selected)
        self.layout_list.add_layout_clicked.connect(self.add_layout)
        self.layout_list.delete_layout_clicked.connect(self.delete_layout)
        self.layout_list.set_default_clicked.connect(self.set_default_layout)
        self.layout_list.edit_layout_clicked.connect(self.edit_layout)
        left_layout.addWidget(self.layout_list)
        
        # Window rules widget (lower half)
        self.window_rules_widget = WindowRulesWidget()
        self.window_rules_widget.add_rule_clicked.connect(self.add_window_rule)
        self.window_rules_widget.delete_rule_clicked.connect(self.delete_window_rule)
        self.window_rules_widget.edit_rule_clicked.connect(self.edit_window_rule)
        left_layout.addWidget(self.window_rules_widget)
        
        main_layout.addWidget(left_panel)
        
        # Center panel - Key grid with modern card design
        center_widget = QWidget()
        center_layout = QVBoxLayout(center_widget)
        center_layout.setSpacing(16)
        
        # Settings panel with modern card design
        settings_group = QGroupBox("Device Settings")
        settings_layout = QFormLayout()
        settings_layout.setSpacing(12)
        
        self.brightness_spin = QSpinBox()
        self.brightness_spin.setRange(0, 100)
        self.brightness_spin.setValue(15)
        self.brightness_spin.setSuffix("%")
        self.brightness_spin.valueChanged.connect(self.on_settings_changed)
        settings_layout.addRow("Brightness:", self.brightness_spin)
        
        self.lock_monitor_check = QCheckBox()
        self.lock_monitor_check.setChecked(True)
        self.lock_monitor_check.stateChanged.connect(self.on_settings_changed)
        settings_layout.addRow("Lock Monitor:", self.lock_monitor_check)
        
        settings_group.setLayout(settings_layout)
        center_layout.addWidget(settings_group)
        
        # Key grid container with dark mode styling
        grid_container = QWidget()
        grid_container.setStyleSheet(f"""
            QWidget {{
                background-color: {get_colors()['bg_secondary']};
                border-radius: 12px;
                padding: 20px;
            }}
        """)
        grid_container_layout = QVBoxLayout(grid_container)
        grid_container_layout.setContentsMargins(0, 0, 0, 0)
        
        # Grid title
        grid_title = QLabel("StreamDock Keys")
        grid_title.setProperty("headingLevel", "2")
        grid_title.setStyleSheet(f"color: {get_colors()['text_primary']}; margin-bottom: 12px;")
        grid_container_layout.addWidget(grid_title)
        
        # Key grid (3 rows x 5 columns)
        grid_widget = QWidget()
        grid_layout = QGridLayout(grid_widget)
        grid_layout.setSpacing(12)
        
        # Create 15 key squares (3x5)
        position = 1
        for row in range(3):
            for col in range(5):
                key_square = KeySquare(position)
                key_square.clicked.connect(self.on_key_square_clicked)
                key_square.key_moved.connect(self.on_key_moved)
                grid_layout.addWidget(key_square, row, col)
                self.key_squares.append(key_square)
                position += 1
        
        grid_container_layout.addWidget(grid_widget)
        center_layout.addWidget(grid_container)
        center_layout.addStretch()
        
        main_layout.addWidget(center_widget, stretch=1)
    
    def setup_menu(self):
        """Setup the menu bar"""
        menubar = self.menuBar()
        
        # File menu
        file_menu = menubar.addMenu("&File")
        
        new_action = QAction("&New Configuration", self)
        new_action.setShortcut(QKeySequence.StandardKey.New)
        new_action.triggered.connect(self.new_config)
        file_menu.addAction(new_action)
        
        open_action = QAction("&Open...", self)
        open_action.setShortcut(QKeySequence.StandardKey.Open)
        open_action.triggered.connect(self.open_config)
        file_menu.addAction(open_action)
        
        save_action = QAction("&Save", self)
        save_action.setShortcut(QKeySequence.StandardKey.Save)
        save_action.triggered.connect(self.save_config)
        file_menu.addAction(save_action)
        
        save_as_action = QAction("Save &As...", self)
        save_as_action.setShortcut(QKeySequence.StandardKey.SaveAs)
        save_as_action.triggered.connect(self.save_config_as)
        file_menu.addAction(save_as_action)
        
        file_menu.addSeparator()
        
        exit_action = QAction("E&xit", self)
        exit_action.setShortcut(QKeySequence("Ctrl+Q"))
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)
        
        # Keys menu
        keys_menu = menubar.addMenu("Keys")
        
        manage_keys_action = QAction("Manage All Keys...", self)
        manage_keys_action.triggered.connect(self.manage_all_keys)
        keys_menu.addAction(manage_keys_action)
        
        # Settings menu
        settings_menu = menubar.addMenu("&Settings")
        
        advanced_settings_action = QAction("&Advanced Settings...", self)
        advanced_settings_action.triggered.connect(self.show_advanced_settings)
        settings_menu.addAction(advanced_settings_action)
    
    def new_config(self):
        """Create a new configuration"""
        reply = QMessageBox.question(
            self,
            "New Configuration",
            "Create a new configuration? Unsaved changes will be lost.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        
        if reply == QMessageBox.StandardButton.Yes:
            self.config = StreamDockConfig()
            self.config_file_path = None  # No file path for new config
            self.current_layout = None
            self.modified = False  # Start as unmodified
            self.update_layout_list()
            self.update_window_rules_list()
            self.clear_key_grid()
            self.update_window_title()
    
    def open_config(self):
        """Open a configuration file"""
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Open Configuration",
            str(Path.home()),
            "YAML Files (*.yml *.yaml);;All Files (*)"
        )
        
        if file_path:
            self.load_config(file_path)
    
    def load_config(self, file_path: str, set_as_current_file: bool = True):
        """Load configuration from file
        
        Args:
            file_path: Path to the config file
            set_as_current_file: If True, set this as the current file path for saving
        """
        try:
            self.config.load_from_file(file_path)
            
            if set_as_current_file:
                self.config_file_path = file_path
                self.modified = False
                self.update_window_title()
            else:
                # Loading as template - no file path set
                self.config_file_path = None
                self.modified = False
                self.setWindowTitle("StreamDock Configuration Editor - Unsaved")
            
            # Block signals to prevent mark_modified from being called during load
            self.brightness_spin.blockSignals(True)
            self.lock_monitor_check.blockSignals(True)
            
            self.brightness_spin.setValue(self.config.brightness)
            self.lock_monitor_check.setChecked(self.config.lock_monitor)
            
            self.brightness_spin.blockSignals(False)
            self.lock_monitor_check.blockSignals(False)
            
            self.update_layout_list()
            self.update_window_rules_list()
            
            # Select default layout
            default_layout = self.config.get_default_layout()
            if default_layout:
                self.current_layout = default_layout
                self.display_layout(default_layout)
            
            # Ensure modified flag is correct after loading
            if set_as_current_file:
                self.modified = False
                self.update_window_title()
            else:
                self.modified = False
                self.setWindowTitle("StreamDock Configuration Editor - Unsaved")
            
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to load configuration:\n{str(e)}")
    
    def save_config(self) -> bool:
        """Save configuration to current file. Returns True if saved successfully."""
        if not self.config_file_path:
            return self.save_config_as()
        else:
            return self.save_config_to_file(self.config_file_path)
    
    def save_config_as(self) -> bool:
        """Save configuration to a new file. Returns True if saved successfully."""
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Save Configuration As",
            str(Path.home() / "config.yml"),
            "YAML Files (*.yml *.yaml);;All Files (*)"
        )
        
        if file_path:
            return self.save_config_to_file(file_path)
        return False  # User cancelled
    
    def save_config_to_file(self, file_path: str) -> bool:
        """Save configuration to specified file. Returns True if saved successfully."""
        try:
            self.config.save_to_file(file_path)
            self.config_file_path = file_path
            self.modified = False  # Clear modified flag after save
            self.update_window_title()
            QMessageBox.information(self, "Success", "Configuration saved successfully!")
            return True
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to save configuration:\n{str(e)}")
            return False
    
    def mark_modified(self):
        """Mark the configuration as modified"""
        self.modified = True
        self.update_window_title()
    
    def update_window_title(self):
        """Update window title to reflect current file and modified state"""
        if self.config_file_path:
            title = f"StreamDock Configuration Editor - {Path(self.config_file_path).name}"
        else:
            title = "StreamDock Configuration Editor - Unsaved"
        
        if self.modified:
            title += " *"
        
        self.setWindowTitle(title)
    
    def closeEvent(self, event):
        """Handle window close event - warn about unsaved changes"""
        if self.modified:
            reply = QMessageBox.question(
                self,
                "Unsaved Changes",
                "You have unsaved changes. Do you want to save before closing?",
                QMessageBox.StandardButton.Save | 
                QMessageBox.StandardButton.Discard | 
                QMessageBox.StandardButton.Cancel,
                QMessageBox.StandardButton.Save
            )
            
            if reply == QMessageBox.StandardButton.Save:
                # Try to save, only close if successful
                if self.save_config():
                    event.accept()
                else:
                    event.ignore()
            elif reply == QMessageBox.StandardButton.Discard:
                event.accept()
            else:  # Cancel
                event.ignore()
        else:
            event.accept()
    
    def on_settings_changed(self):
        """Handle settings changes"""
        self.config.brightness = self.brightness_spin.value()
        self.config.lock_monitor = self.lock_monitor_check.isChecked()
        self.mark_modified()
    
    def show_advanced_settings(self):
        """Show the advanced settings dialog"""
        dialog = AdvancedSettingsDialog(self.config, parent=self)
        
        if dialog.exec() == QDialog.DialogCode.Accepted:
            settings = dialog.get_settings()
            self.config.double_press_interval = settings['double_press_interval']
            self.mark_modified()
    
    def update_layout_list(self):
        """Update the layout list widget"""
        layout_names = list(self.config.layouts.keys())
        default_layout = self.config.get_default_layout()
        default_name = default_layout.name if default_layout else None
        self.layout_list.set_layouts(layout_names, default_name)
    
    def on_layout_selected(self, layout_name: str):
        """Handle layout selection"""
        if layout_name in self.config.layouts:
            self.current_layout = self.config.layouts[layout_name]
            self.display_layout(self.current_layout)
    
    def display_layout(self, layout: Layout):
        """Display a layout on the key grid"""
        # Clear all squares first
        for square in self.key_squares:
            square.set_empty()
        
        # Set keys according to layout
        for position, key_name in layout.keys.items():
            if key_name and 1 <= position <= 15:
                square = self.key_squares[position - 1]
                if key_name in self.config.keys:
                    key_def = self.config.keys[key_name]
                    square.set_key(key_name, key_def)
    
    def clear_key_grid(self):
        """Clear all key squares"""
        for square in self.key_squares:
            square.set_empty()
    
    def add_layout(self):
        """Add a new layout"""
        existing_layouts = list(self.config.layouts.keys())
        dialog = LayoutEditorDialog(existing_layouts=existing_layouts, parent=self)
        
        if dialog.exec() == QDialog.DialogCode.Accepted:
            layout_data = dialog.get_layout_data()
            name = layout_data['name']
            clear_all = layout_data['clear_all']
            
            if name in self.config.layouts:
                QMessageBox.warning(self, "Error", "Layout name already exists!")
                return
            
            layout = Layout(name)
            layout.clear_all = clear_all
            
            # If this is the first layout, make it default
            if not self.config.layouts:
                layout.is_default = True
            
            self.config.add_layout(name, layout)
            self.mark_modified()
            self.update_layout_list()
            self.current_layout = layout
            self.display_layout(layout)
    
    def edit_layout(self, layout_name: str):
        """Edit an existing layout"""
        if layout_name not in self.config.layouts:
            return
        
        layout = self.config.layouts[layout_name]
        existing_layouts = [name for name in self.config.layouts.keys() if name != layout_name]
        
        dialog = LayoutEditorDialog(
            layout_name=layout_name,
            clear_all=layout.clear_all,
            existing_layouts=existing_layouts,
            parent=self
        )
        
        if dialog.exec() == QDialog.DialogCode.Accepted:
            layout_data = dialog.get_layout_data()
            new_name = layout_data['name']
            clear_all = layout_data['clear_all']
            
            # Update clear_all setting
            layout.clear_all = clear_all
            
            # If name changed, rename the layout and update all references
            if new_name != layout_name:
                # Update the layout object's name
                layout.name = new_name
                
                # Remove old entry and add new one
                del self.config.layouts[layout_name]
                self.config.layouts[new_name] = layout
                
                # Update all references to this layout
                self._update_layout_references(layout_name, new_name)
                
                # Update current layout reference if it was the one being edited
                if self.current_layout and self.current_layout.name == layout_name:
                    self.current_layout.name = new_name
            
            self.mark_modified()
            self.update_layout_list()
            self.update_window_rules_list()
            
            # Refresh display if this is the current layout
            if self.current_layout and self.current_layout.name == new_name:
                self.display_layout(self.current_layout)
    
    def _update_layout_references(self, old_name: str, new_name: str):
        """Update all references to a layout when it's renamed"""
        # Update CHANGE_LAYOUT actions in keys
        for key_name, key_def in self.config.keys.items():
            for action_list in [key_def.on_press_actions, key_def.on_release_actions, key_def.on_double_press_actions]:
                for action in action_list:
                    if "CHANGE_LAYOUT" in action:
                        layout_value = action["CHANGE_LAYOUT"]
                        # Check both string and dict formats
                        if isinstance(layout_value, str) and layout_value == old_name:
                            action["CHANGE_LAYOUT"] = new_name
                        elif isinstance(layout_value, dict) and layout_value.get('layout') == old_name:
                            layout_value['layout'] = new_name
        
        # Update window rules
        for rule_name, rule in self.config.window_rules.items():
            if rule.layout == old_name:
                rule.layout = new_name
    
    def delete_layout(self, layout_name: str):
        """Delete a layout"""
        if layout_name not in self.config.layouts:
            return
        
        layout = self.config.layouts[layout_name]
        
        # Check if it's the default layout
        if layout.is_default and len(self.config.layouts) > 1:
            QMessageBox.warning(
                self,
                "Cannot Delete",
                "Cannot delete the default layout. Set another layout as default first."
            )
            return
        
        # Find keys with CHANGE_LAYOUT actions referencing this layout
        keys_with_actions = []
        for key_name, key_def in self.config.keys.items():
            if self._key_has_layout_reference(key_def, layout_name):
                keys_with_actions.append(key_name)
        
        # Find window rules referencing this layout
        rules_using_layout = []
        for rule_name, rule in self.config.window_rules.items():
            if rule.layout == layout_name:
                rules_using_layout.append(rule_name)
        
        # Build warning message
        warning_parts = []
        if keys_with_actions:
            warning_parts.append(f"Keys with CHANGE_LAYOUT actions: {', '.join(keys_with_actions)}")
        if rules_using_layout:
            warning_parts.append(f"Window rules: {', '.join(rules_using_layout)}")
        
        if warning_parts:
            warning_msg = (
                f"Layout '{layout_name}' is referenced by:\n\n" +
                "\n".join(f"• {part}" for part in warning_parts) +
                "\n\nDeleting this layout will remove all these references.\n\nContinue?"
            )
            reply = QMessageBox.question(
                self,
                "Delete Layout",
                warning_msg,
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
        else:
            reply = QMessageBox.question(
                self,
                "Delete Layout",
                f"Are you sure you want to delete layout '{layout_name}'?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
        
        if reply == QMessageBox.StandardButton.Yes:
            # Remove CHANGE_LAYOUT actions from keys
            for key_name in keys_with_actions:
                key_def = self.config.keys[key_name]
                key_def.on_press_actions = self._remove_layout_from_actions(
                    key_def.on_press_actions, layout_name)
                key_def.on_release_actions = self._remove_layout_from_actions(
                    key_def.on_release_actions, layout_name)
                key_def.on_double_press_actions = self._remove_layout_from_actions(
                    key_def.on_double_press_actions, layout_name)
            
            # Remove window rules
            for rule_name in rules_using_layout:
                del self.config.window_rules[rule_name]
            
            # Remove the layout
            self.config.remove_layout(layout_name)
            
            # If we deleted the current layout, clear the display
            if self.current_layout and self.current_layout.name == layout_name:
                self.current_layout = None
                self.clear_key_grid()
            
            self.mark_modified()
            self.update_layout_list()
    
    def set_default_layout(self, layout_name: str):
        """Set a layout as the default layout"""
        if layout_name not in self.config.layouts:
            return
        
        # Unset all other layouts as default
        for layout in self.config.layouts.values():
            layout.is_default = False
        
        # Set this layout as default
        self.config.layouts[layout_name].is_default = True
        
        # Refresh the layout list to show the new default
        self.update_layout_list()
    
    def _key_has_layout_reference(self, key_def: KeyDefinition, layout_name: str) -> bool:
        """Check if a key has CHANGE_LAYOUT actions referencing the layout"""
        all_actions = (key_def.on_press_actions + 
                      key_def.on_release_actions + 
                      key_def.on_double_press_actions)
        
        for action in all_actions:
            if "CHANGE_LAYOUT" in action:
                layout_value = action["CHANGE_LAYOUT"]
                # Check both string and dict formats
                if isinstance(layout_value, str) and layout_value == layout_name:
                    return True
                elif isinstance(layout_value, dict) and layout_value.get('layout') == layout_name:
                    return True
        return False
    
    def _remove_layout_from_actions(self, actions: list, layout_name: str) -> list:
        """Remove CHANGE_LAYOUT actions that reference the given layout"""
        filtered_actions = []
        for action in actions:
            if "CHANGE_LAYOUT" in action:
                layout_value = action["CHANGE_LAYOUT"]
                # Check both string and dict formats
                if isinstance(layout_value, str) and layout_value == layout_name:
                    continue  # Skip this action
                elif isinstance(layout_value, dict) and layout_value.get('layout') == layout_name:
                    continue  # Skip this action
            filtered_actions.append(action)
        return filtered_actions
    
    def on_key_square_clicked(self, position: int):
        """Handle key square clicks"""
        if not self.current_layout:
            QMessageBox.warning(self, "No Layout", "Please select or create a layout first.")
            return
        
        square = self.key_squares[position - 1]
        
        if square.is_empty():
            # Empty square - select or create key
            self.handle_empty_square_click(position, square)
        else:
            # Filled square - edit, replace, or remove
            self.handle_filled_square_click(position, square)
    
    def handle_empty_square_click(self, position: int, square: KeySquare):
        """Handle click on empty square - show context menu"""
        available_keys = list(self.config.keys.keys())
        
        menu = QMenu(self)
        
        # Create New Key action
        create_action = QAction("Create New Key", self)
        create_action.triggered.connect(lambda: self.create_and_assign_key(position, square))
        menu.addAction(create_action)
        
        # Add separator if there are existing keys
        if available_keys:
            menu.addSeparator()
            
            # Add existing keys submenu
            for key_name in available_keys:
                assign_action = QAction(f"Assign: {key_name}", self)
                assign_action.triggered.connect(
                    lambda checked, k=key_name: self.assign_key_to_position(position, square, k)
                )
                menu.addAction(assign_action)
        
        # Show menu at cursor position
        menu.exec(QCursor.pos())
    
    def handle_filled_square_click(self, position: int, square: KeySquare):
        """Handle click on filled square - show context menu"""
        menu = QMenu(self)
        
        # Edit Key action
        edit_action = QAction("Edit Key", self)
        edit_action.triggered.connect(lambda: self.edit_key(square.key_name))
        menu.addAction(edit_action)
        
        # Replace with Existing action
        replace_action = QAction("Replace with Existing", self)
        replace_action.triggered.connect(lambda: self.replace_key(position, square))
        menu.addAction(replace_action)
        
        # Create & Replace action
        create_replace_action = QAction("Create & Replace", self)
        create_replace_action.triggered.connect(lambda: self.create_and_assign_key(position, square))
        menu.addAction(create_replace_action)
        
        menu.addSeparator()
        
        # Remove from Layout action
        remove_action = QAction("Remove from Layout", self)
        remove_action.triggered.connect(lambda: self.remove_key_from_position(position, square))
        menu.addAction(remove_action)
        
        # Show menu at cursor position
        menu.exec(QCursor.pos())
    
    def create_and_assign_key(self, position: int, square: KeySquare):
        """Create a new key and assign it to a position"""
        existing_keys = list(self.config.keys.keys())
        available_layouts = list(self.config.layouts.keys())
        available_keys = list(self.config.keys.keys())
        editor = KeyEditorDialog(existing_keys=existing_keys, 
                                available_layouts=available_layouts,
                                available_keys=available_keys,
                                parent=self)
        
        if editor.exec() == editor.DialogCode.Accepted:
            key_def = editor.get_key_definition()
            
            # Check if key name already exists
            if key_def.name in self.config.keys:
                QMessageBox.warning(self, "Error", "Key name already exists!")
                return
            
            # Add key to config
            self.config.add_key(key_def.name, key_def)
            
            # Assign to layout
            self.assign_key_to_position(position, square, key_def.name)
    
    def assign_key_to_position(self, position: int, square: KeySquare, key_name: str):
        """Assign an existing key to a position"""
        if key_name not in self.config.keys:
            return
        
        key_def = self.config.keys[key_name]
        self.current_layout.set_key_at_position(position, key_name)
        square.set_key(key_name, key_def)
        self.mark_modified()
    
    def edit_key(self, key_name: str):
        """Edit an existing key definition"""
        if key_name not in self.config.keys:
            return
        
        key_def = self.config.keys[key_name]
        existing_keys = [k for k in self.config.keys.keys() if k != key_name]
        available_layouts = list(self.config.layouts.keys())
        available_keys = [k for k in self.config.keys.keys() if k != key_name]
        
        editor = KeyEditorDialog(key_def, existing_keys, available_layouts, available_keys, self)
        
        if editor.exec() == editor.DialogCode.Accepted:
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
            
            # Refresh display
            self.display_layout(self.current_layout)
    
    def rename_key_in_layouts(self, old_name: str, new_name: str):
        """Rename a key in all layouts"""
        for layout in self.config.layouts.values():
            for position, key_name in list(layout.keys.items()):
                if key_name == old_name:
                    layout.keys[position] = new_name
    
    def replace_key(self, position: int, square: KeySquare):
        """Replace key at position with another existing key"""
        available_keys = list(self.config.keys.keys())
        
        if not available_keys:
            QMessageBox.warning(self, "No Keys", "No keys available.")
            return
        
        key_name, ok = QInputDialog.getItem(
            self,
            "Replace Key",
            "Select replacement key:",
            available_keys,
            0,
            False
        )
        
        if ok and key_name:
            self.assign_key_to_position(position, square, key_name)
    
    def remove_key_from_position(self, position: int, square: KeySquare):
        """Remove key from layout position (does not delete key definition)"""
        self.current_layout.remove_key_at_position(position)
        square.set_empty()
        self.mark_modified()
    
    def on_key_moved(self, from_position: int, to_position: int):
        """Handle drag and drop of key from one position to another"""
        if not self.current_layout:
            return
        
        # Get key name from source position
        key_name = self.current_layout.keys.get(from_position)
        if not key_name:
            return
        
        # Get the key definition before clearing
        key_def = self.config.keys.get(key_name)
        if not key_def:
            return
        
        # Move key in layout
        self.current_layout.remove_key_at_position(from_position)
        self.current_layout.keys[to_position] = key_name
        
        # Get references to the squares
        from_square = self.key_squares[from_position - 1]
        to_square = self.key_squares[to_position - 1]
        
        # Clear source square first
        from_square.set_empty()
        
        # Then set destination square
        to_square.set_key(key_name, key_def)
        
        self.mark_modified()
    
    def manage_all_keys(self):
        """Show dialog to manage all key definitions"""
        dialog = ManageKeysDialog(self.config, self)
        dialog.exec()
        
        # If keys were modified, refresh the current layout display
        if dialog.was_modified():
            self.mark_modified()
            if self.current_layout:
                self.display_layout(self.current_layout)
    
    def update_window_rules_list(self):
        """Update the window rules list widget"""
        self.window_rules_widget.set_rules(self.config.window_rules)
    
    def add_window_rule(self):
        """Add a new window rule"""
        if not self.config.layouts:
            QMessageBox.warning(self, "No Layouts", "Create at least one layout before adding window rules.")
            return
        
        available_layouts = list(self.config.layouts.keys())
        existing_rules = list(self.config.window_rules.keys())
        dialog = WindowRuleDialog(available_layouts, existing_rules=existing_rules, parent=self)
        
        if dialog.exec() == QDialog.DialogCode.Accepted:
            rule_data = dialog.get_rule_data()
            
            # Check if rule name already exists
            if rule_data['name'] in self.config.window_rules:
                QMessageBox.warning(self, "Error", "A rule with this name already exists!")
                return
            
            # Create the window rule
            rule = WindowRule(rule_data['name'], {
                'window_name': rule_data['window_name'],
                'layout': rule_data['layout'],
                'match_field': rule_data.get('match_field', 'class')
            })
            
            # Add to config
            self.config.window_rules[rule_data['name']] = rule
            self.mark_modified()
            self.update_window_rules_list()
    
    def edit_window_rule(self, rule_name: str):
        """Edit an existing window rule"""
        if rule_name not in self.config.window_rules:
            return
        
        rule = self.config.window_rules[rule_name]
        available_layouts = list(self.config.layouts.keys())
        existing_rules = [name for name in self.config.window_rules.keys() if name != rule_name]
        
        if not available_layouts:
            QMessageBox.warning(self, "No Layouts", "No layouts available.")
            return
        
        dialog = WindowRuleDialog(
            available_layouts=available_layouts,
            rule_name=rule_name,
            window_rule=rule,
            existing_rules=existing_rules,
            parent=self
        )
        
        if dialog.exec() == QDialog.DialogCode.Accepted:
            rule_data = dialog.get_rule_data()
            new_name = rule_data['name']
            
            # Update the window rule properties
            rule.window_name = rule_data['window_name']
            rule.layout = rule_data['layout']
            rule.match_field = rule_data.get('match_field', 'class')
            
            # If name changed, rename the rule in the config
            if new_name != rule_name:
                rule.name = new_name
                del self.config.window_rules[rule_name]
                self.config.window_rules[new_name] = rule
            
            self.mark_modified()
            self.update_window_rules_list()
    
    def delete_window_rule(self, rule_name: str):
        """Delete a window rule"""
        if rule_name not in self.config.window_rules:
            return
        
        reply = QMessageBox.question(
            self,
            "Delete Window Rule",
            f"Are you sure you want to delete the window rule '{rule_name}'?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        
        if reply == QMessageBox.StandardButton.Yes:
            del self.config.window_rules[rule_name]
            self.mark_modified()
            self.update_window_rules_list()
