#!/usr/bin/env python3
"""
Custom widgets for StreamDock Configuration Editor
"""

from PyQt6.QtWidgets import (QFrame, QLabel, QVBoxLayout, QWidget, QPushButton,
                              QListWidget, QListWidgetItem, QHBoxLayout, QSizePolicy, QMenu)
from PyQt6.QtCore import Qt, pyqtSignal, QSize, QMimeData, QPoint
from PyQt6.QtGui import QPixmap, QPalette, QColor, QFont, QPainter, QDrag, QAction
from config_editor_models import KeyDefinition
from modern_styles import get_colors
from pathlib import Path

COLORS = get_colors()


class KeySquare(QFrame):
    """A single key square widget representing a 112x112px LCD screen key"""
    
    clicked = pyqtSignal(int)  # Emits key position when clicked
    key_moved = pyqtSignal(int, int)  # Emits (from_position, to_position)
    
    def __init__(self, position: int, parent=None):
        super().__init__(parent)
        self.position = position
        self.key_definition: KeyDefinition = None
        self.key_name: str = None
        self.drag_start_position = None
        
        # Fixed size matching physical device screen
        self.setFixedSize(112, 112)
        self.setFrameStyle(QFrame.Shape.NoFrame)
        
        # Enable drag and drop
        self.setAcceptDrops(True)
        
        # Label fills entire square
        self.label = QLabel(self)
        self.label.setGeometry(0, 0, 112, 112)
        self.label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.label.setWordWrap(True)
        self.label.setScaledContents(False)
        
        # Set default empty appearance
        self.set_empty()
        
        # Make clickable - will change cursor based on state
        self._update_cursor()
    
    def set_empty(self):
        """Set the square to empty state"""
        self.key_definition = None
        self.key_name = None
        
        # Clear both text and pixmap
        self.label.setText("")
        self.label.setPixmap(QPixmap())
        
        # Completely reset label stylesheet
        self.label.setStyleSheet("background-color: transparent; color: white;")
        
        # Empty state: dark with dashed border
        self.setStyleSheet(f"""
            KeySquare {{
                background-color: #1A1A1A !important;
                border: 1px dashed #444444 !important;
            }}
            KeySquare:hover {{
                background-color: #252525 !important;
                border: 1px solid {COLORS['primary']} !important;
            }}
        """)
        
        self._update_cursor()
        
        # Force repaint
        self.repaint()
        self.label.repaint()
    
    def set_key(self, key_name: str, key_def: KeyDefinition):
        """Set the square to display a key"""
        self.key_name = key_name
        self.key_definition = key_def
        
        if key_def.is_icon_based():
            # Icon mode: fill entire square with icon
            icon_path = Path(key_def.icon)
            if not icon_path.is_absolute():
                icon_path = Path(__file__).parent.parent / icon_path
            
            if icon_path.exists():
                original_pixmap = QPixmap(str(icon_path))
                
                if not original_pixmap.isNull():
                    # Scale icon to fill entire 112x112 square
                    scaled_pixmap = original_pixmap.scaled(
                        112, 112,
                        Qt.AspectRatioMode.KeepAspectRatio,
                        Qt.TransformationMode.SmoothTransformation
                    )
                    
                    # Create canvas and fill with black
                    canvas = QPixmap(112, 112)
                    canvas.fill(QColor(0, 0, 0))
                    
                    # Center the icon
                    x = (112 - scaled_pixmap.width()) // 2
                    y = (112 - scaled_pixmap.height()) // 2
                    
                    painter = QPainter(canvas)
                    painter.drawPixmap(x, y, scaled_pixmap)
                    painter.end()
                    
                    self.label.setPixmap(canvas)
                    
                    # No border, no padding - just the icon
                    self.setStyleSheet("""
                        KeySquare {
                            background-color: #000000;
                            border: none;
                        }
                        KeySquare:hover {
                            background-color: #000000;
                        }
                    """)
                    self.label.setStyleSheet("background-color: #000000; padding: 0px; margin: 0px;")
                else:
                    # Failed to load
                    self._show_error("Error")
            else:
                # Icon not found
                self._show_error("Not Found")
        
        elif key_def.is_text_based():
            # Text mode: centered text with specified colors
            self.label.setPixmap(QPixmap())  # Clear any pixmap
            self.label.setText(key_def.text)
            
            # Set font
            font = QFont()
            font.setPointSize(key_def.font_size)
            font.setBold(key_def.bold)
            self.label.setFont(font)
            
            # Fill entire square with background color
            bg_color = key_def.background_color
            text_color = key_def.text_color
            
            self.setStyleSheet(f"""
                KeySquare {{
                    background-color: {bg_color};
                    border: none;
                }}
                KeySquare:hover {{
                    background-color: {bg_color};
                }}
            """)
            
            self.label.setStyleSheet(f"""
                QLabel {{
                    color: {text_color};
                    background-color: {bg_color};
                    padding: 0px;
                    margin: 0px;
                }}
            """)
        
        # Update cursor for drag capability
        self._update_cursor()
        
        # Force repaint
        self.update()
        self.label.update()
    
    def _show_error(self, message: str):
        """Show error message on square"""
        self.label.setText(message)
        font = QFont()
        font.setPointSize(8)
        self.label.setFont(font)
        
        self.setStyleSheet("""
            KeySquare {
                background-color: #1A1A1A;
                border: 1px solid #FF0000;
            }
        """)
        self.label.setStyleSheet("color: #FF0000; background-color: #1A1A1A;")
    
    def mousePressEvent(self, event):
        """Handle mouse clicks and prepare for potential drag"""
        if event.button() == Qt.MouseButton.LeftButton:
            # Store position for both click and drag detection
            self.drag_start_position = event.pos()
        super().mousePressEvent(event)
    
    def mouseReleaseEvent(self, event):
        """Handle mouse release - emit click if not dragged"""
        if event.button() == Qt.MouseButton.LeftButton:
            if self.drag_start_position is not None:
                # Check if mouse moved significantly
                moved_distance = (event.pos() - self.drag_start_position).manhattanLength()
                
                if moved_distance < 10:
                    # Short click - emit clicked signal
                    self.clicked.emit(self.position)
                
                self.drag_start_position = None
        super().mouseReleaseEvent(event)
    
    def mouseMoveEvent(self, event):
        """Start drag operation if key is defined"""
        if not (event.buttons() & Qt.MouseButton.LeftButton):
            return
        if self.is_empty():
            return
        if self.drag_start_position is None:
            return
        
        # Check if moved enough to start drag
        if (event.pos() - self.drag_start_position).manhattanLength() < 10:
            return
        
        # Start drag
        drag = QDrag(self)
        mime_data = QMimeData()
        mime_data.setText(str(self.position))
        drag.setMimeData(mime_data)
        
        # Create drag pixmap (snapshot of this square)
        pixmap = self.grab()
        drag.setPixmap(pixmap)
        drag.setHotSpot(event.pos())
        
        # Execute drag
        drag.exec(Qt.DropAction.MoveAction)
        self.drag_start_position = None
    
    def dragEnterEvent(self, event):
        """Accept drag if this square is empty"""
        if self.is_empty() and event.mimeData().hasText():
            event.acceptProposedAction()
            # Highlight empty square when dragging over
            self.setStyleSheet(f"""
                KeySquare {{
                    background-color: #252525;
                    border: 2px solid {COLORS['success']};
                }}
            """)
        else:
            event.ignore()
    
    def dragLeaveEvent(self, event):
        """Remove highlight when drag leaves"""
        if self.is_empty():
            self.set_empty()
    
    def dropEvent(self, event):
        """Handle drop - move key from source to this empty square"""
        if self.is_empty() and event.mimeData().hasText():
            from_position = int(event.mimeData().text())
            to_position = self.position
            
            event.acceptProposedAction()
            
            # Emit signal to notify parent to update layout
            # Parent will handle setting the key on this square
            self.key_moved.emit(from_position, to_position)
        else:
            event.ignore()
    
    def _update_cursor(self):
        """Update cursor based on whether key is defined"""
        if self.is_empty():
            self.setCursor(Qt.CursorShape.PointingHandCursor)
        else:
            self.setCursor(Qt.CursorShape.OpenHandCursor)
    
    def is_empty(self) -> bool:
        """Check if this square is empty"""
        return self.key_definition is None


class LayoutListWidget(QWidget):
    """Widget for managing layouts list"""
    
    layout_selected = pyqtSignal(str)  # Emits layout name
    add_layout_clicked = pyqtSignal()
    delete_layout_clicked = pyqtSignal(str)  # Emits layout name
    set_default_clicked = pyqtSignal(str)  # Emits layout name to set as default
    edit_layout_clicked = pyqtSignal(str)  # Emits layout name to edit
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setup_ui()
    
    def setup_ui(self):
        """Setup the UI"""
        # Add card styling to the widget itself
        self.setStyleSheet(f"""
            LayoutListWidget {{
                background-color: {COLORS['bg_card']};
                border-radius: 12px;
                padding: 16px;
            }}
        """)
        
        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(0, 0, 0, 0)
        
        # Title bar with add button
        title_layout = QHBoxLayout()
        
        title = QLabel("Layouts")
        title.setProperty("headingLevel", "2")
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
        self.add_btn.setToolTip("Add new layout")
        self.add_btn.clicked.connect(self.add_layout_clicked.emit)
        title_layout.addWidget(self.add_btn)
        
        layout.addLayout(title_layout)
        
        # List widget with modern styling
        self.list_widget = QListWidget()
        self.list_widget.itemClicked.connect(self._on_item_clicked)
        self.list_widget.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.list_widget.customContextMenuRequested.connect(self._show_context_menu)
        layout.addWidget(self.list_widget)
    
    def _show_context_menu(self, position):
        """Show context menu for layout items"""
        item = self.list_widget.itemAt(position)
        if not item:
            return
        
        layout_name = item.data(Qt.ItemDataRole.UserRole)
        if not layout_name:
            return
        
        menu = QMenu(self)
        
        # Edit Layout action
        edit_action = QAction("Edit Layout", self)
        edit_action.triggered.connect(lambda: self.edit_layout_clicked.emit(layout_name))
        menu.addAction(edit_action)
        
        menu.addSeparator()
        
        # Set as Default action
        set_default_action = QAction("Set as Default", self)
        set_default_action.triggered.connect(lambda: self.set_default_clicked.emit(layout_name))
        menu.addAction(set_default_action)
        
        # Delete action
        delete_action = QAction("Delete", self)
        delete_action.triggered.connect(lambda: self.delete_layout_clicked.emit(layout_name))
        menu.addAction(delete_action)
        
        menu.exec(self.list_widget.mapToGlobal(position))
    
    def set_layouts(self, layout_names: list, default_layout: str = None):
        """Set the list of layouts"""
        self.list_widget.clear()
        for name in layout_names:
            # Create list item
            item = QListWidgetItem(self.list_widget)
            
            # Create custom widget for layout name
            widget = QWidget()
            widget_layout = QHBoxLayout(widget)
            widget_layout.setContentsMargins(8, 0, 8, 0)
            widget_layout.setSpacing(8)
            
            # Layout name label
            label_text = f"{name} (Default)" if name == default_layout else name
            label = QLabel(label_text)
            if name == default_layout:
                font = label.font()
                font.setBold(True)
                label.setFont(font)
            widget_layout.addWidget(label, alignment=Qt.AlignmentFlag.AlignVCenter)
            
            widget_layout.addStretch()
            
            # Set the widget for the item with proper height
            widget.setMinimumHeight(40)
            item.setSizeHint(QSize(widget.sizeHint().width(), 40))
            self.list_widget.setItemWidget(item, widget)
            
            # Store layout name in item data for selection
            item.setData(Qt.ItemDataRole.UserRole, name)
    
    def get_selected_layout(self) -> str:
        """Get currently selected layout name"""
        current_item = self.list_widget.currentItem()
        if current_item:
            return current_item.data(Qt.ItemDataRole.UserRole)
        return None
    
    def _on_item_clicked(self, item: QListWidgetItem):
        """Handle item click"""
        layout_name = item.data(Qt.ItemDataRole.UserRole)
        if layout_name:
            self.layout_selected.emit(layout_name)


class ActionListItem(QWidget):
    """Widget representing a single action in the action list"""
    
    remove_clicked = pyqtSignal(int)  # Emits index
    edit_clicked = pyqtSignal(int)  # Emits index
    move_up_clicked = pyqtSignal(int)  # Emits index
    move_down_clicked = pyqtSignal(int)  # Emits index
    
    def __init__(self, index: int, action_dict: dict, parent=None):
        super().__init__(parent)
        self.index = index
        self.action_dict = action_dict
        self.setup_ui()
    
    def setup_ui(self):
        """Setup the UI"""
        layout = QHBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(6)
        
        # Action description
        action_text = self._format_action()
        self.label = QLabel(action_text)
        layout.addWidget(self.label, stretch=1)
        
        # Buttons with modern styling and proper size
        btn_up = QPushButton("↑")
        btn_up.setFixedSize(28, 28)
        btn_up.setStyleSheet(f"""
            QPushButton {{
                background: transparent;
                color: {COLORS['text_secondary']};
                border: none;
                font-size: 20px;
                font-weight: bold;
                padding: 0px;
            }}
            QPushButton:hover {{
                color: {COLORS['primary']};
            }}
        """)
        btn_up.setToolTip("Move up")
        btn_up.clicked.connect(lambda: self.move_up_clicked.emit(self.index))
        layout.addWidget(btn_up)
        
        btn_down = QPushButton("↓")
        btn_down.setFixedSize(28, 28)
        btn_down.setStyleSheet(f"""
            QPushButton {{
                background: transparent;
                color: {COLORS['text_secondary']};
                border: none;
                font-size: 20px;
                font-weight: bold;
                padding: 0px;
            }}
            QPushButton:hover {{
                color: {COLORS['primary']};
            }}
        """)
        btn_down.setToolTip("Move down")
        btn_down.clicked.connect(lambda: self.move_down_clicked.emit(self.index))
        layout.addWidget(btn_down)
        
        btn_edit = QPushButton("✎")
        btn_edit.setFixedSize(28, 28)
        btn_edit.setStyleSheet(f"""
            QPushButton {{
                background: transparent;
                color: {COLORS['info']};
                border: none;
                font-size: 20px;
                font-weight: bold;
                padding: 0px;
            }}
            QPushButton:hover {{
                color: {COLORS['info_hover']};
            }}
        """)
        btn_edit.setToolTip("Edit action")
        btn_edit.clicked.connect(lambda: self.edit_clicked.emit(self.index))
        layout.addWidget(btn_edit)
        
        btn_remove = QPushButton("✕")
        btn_remove.setFixedSize(28, 28)
        btn_remove.setStyleSheet(f"""
            QPushButton {{
                background: transparent;
                color: {COLORS['danger']};
                border: none;
                font-size: 20px;
                font-weight: bold;
                padding: 0px;
            }}
            QPushButton:hover {{
                color: {COLORS['danger_hover']};
            }}
        """)
        btn_remove.setToolTip("Remove action")
        btn_remove.clicked.connect(lambda: self.remove_clicked.emit(self.index))
        layout.addWidget(btn_remove)
        
        # Set minimum height for the widget
        self.setMinimumHeight(42)
    
    def _format_action(self) -> str:
        """Format action dictionary for display"""
        if not self.action_dict:
            return "Empty action"
        
        # Get the action type (first key in dict)
        action_type = list(self.action_dict.keys())[0]
        action_value = self.action_dict[action_type]
        
        # Format based on action type
        if action_type == "EXECUTE_COMMAND":
            if isinstance(action_value, list):
                return f"Execute: {' '.join(action_value)}"
            return f"Execute: {action_value}"
        
        elif action_type == "LAUNCH_APPLICATION":
            if isinstance(action_value, str):
                return f"Launch: {action_value}"
            elif isinstance(action_value, list):
                return f"Launch: {' '.join(action_value)}"
            elif isinstance(action_value, dict):
                if 'desktop_file' in action_value:
                    return f"Launch: {action_value['desktop_file']}"
                elif 'command' in action_value:
                    cmd = action_value['command']
                    if isinstance(cmd, list):
                        return f"Launch: {' '.join(cmd)}"
                    return f"Launch: {cmd}"
        
        elif action_type == "KEY_PRESS":
            return f"Key Press: {action_value}"
        
        elif action_type == "TYPE_TEXT":
            preview = action_value[:30] + "..." if len(action_value) > 30 else action_value
            return f"Type: {preview}"
        
        elif action_type == "WAIT":
            return f"Wait: {action_value}s"
        
        elif action_type == "CHANGE_KEY_IMAGE":
            return f"Change Image: {action_value}"
        
        elif action_type == "CHANGE_LAYOUT":
            if isinstance(action_value, str):
                return f"Switch Layout: {action_value}"
            elif isinstance(action_value, dict):
                layout_name = action_value.get('layout', '')
                clear = " (clear all)" if action_value.get('clear_all') else ""
                return f"Switch Layout: {layout_name}{clear}"
        
        elif action_type == "DBUS":
            if isinstance(action_value, dict):
                action = action_value.get('action', '')
                return f"D-Bus: {action}"
        
        elif action_type in ["DEVICE_BRIGHTNESS_UP", "DEVICE_BRIGHTNESS_DOWN"]:
            return action_type.replace("_", " ").title()
        
        return f"{action_type}: {action_value}"


class WindowRulesWidget(QWidget):
    """Widget for managing window rules"""
    
    rule_selected = pyqtSignal(str)  # Emits rule name
    add_rule_clicked = pyqtSignal()
    delete_rule_clicked = pyqtSignal(str)  # Emits rule name
    edit_rule_clicked = pyqtSignal(str)  # Emits rule name to edit
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setup_ui()
    
    def setup_ui(self):
        """Setup the UI"""
        # Add card styling to the widget itself
        self.setStyleSheet(f"""
            WindowRulesWidget {{
                background-color: {COLORS['bg_card']};
                border-radius: 12px;
                padding: 16px;
            }}
        """)
        
        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(0, 0, 0, 0)
        
        # Title bar with add button
        title_layout = QHBoxLayout()
        
        title = QLabel("Window Rules")
        title.setProperty("headingLevel", "2")
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
        self.add_btn.setToolTip("Add new window rule")
        self.add_btn.clicked.connect(self.add_rule_clicked.emit)
        title_layout.addWidget(self.add_btn)
        
        layout.addLayout(title_layout)
        
        # List widget with modern styling
        self.list_widget = QListWidget()
        self.list_widget.itemClicked.connect(self._on_item_clicked)
        self.list_widget.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.list_widget.customContextMenuRequested.connect(self._show_context_menu)
        layout.addWidget(self.list_widget)
    
    def _show_context_menu(self, position):
        """Show context menu for window rule items"""
        item = self.list_widget.itemAt(position)
        if not item:
            return
        
        rule_name = item.data(Qt.ItemDataRole.UserRole)
        if not rule_name:
            return
        
        menu = QMenu(self)
        
        # Edit Rule action
        edit_action = QAction("Edit Rule", self)
        edit_action.triggered.connect(lambda: self.edit_rule_clicked.emit(rule_name))
        menu.addAction(edit_action)
        
        menu.addSeparator()
        
        # Delete action
        delete_action = QAction("Delete", self)
        delete_action.triggered.connect(lambda: self.delete_rule_clicked.emit(rule_name))
        menu.addAction(delete_action)
        
        menu.exec(self.list_widget.mapToGlobal(position))
    
    def set_rules(self, rules: dict):
        """Set the list of window rules"""
        self.list_widget.clear()
        if not rules:
            item = QListWidgetItem("No rules defined")
            item.setFlags(Qt.ItemFlag.NoItemFlags)
            self.list_widget.addItem(item)
            return
        
        for rule_name, rule in rules.items():
            # Create list item
            item = QListWidgetItem(self.list_widget)
            
            # Create custom widget for rule name
            widget = QWidget()
            widget_layout = QHBoxLayout(widget)
            widget_layout.setContentsMargins(8, 0, 8, 0)
            widget_layout.setSpacing(8)
            
            # Rule display label
            label = QLabel(rule_name)
            widget_layout.addWidget(label, alignment=Qt.AlignmentFlag.AlignVCenter)
            
            widget_layout.addStretch()
            
            # Set the widget for the item with proper height
            widget.setMinimumHeight(40)
            item.setSizeHint(QSize(widget.sizeHint().width(), 40))
            self.list_widget.setItemWidget(item, widget)
            
            # Store rule name in item data for selection
            item.setData(Qt.ItemDataRole.UserRole, rule_name)
    
    def get_selected_rule(self) -> str:
        """Get currently selected rule name"""
        current_item = self.list_widget.currentItem()
        if current_item:
            return current_item.data(Qt.ItemDataRole.UserRole)
        return None
    
    def _on_item_clicked(self, item: QListWidgetItem):
        """Handle item click"""
        rule_name = item.data(Qt.ItemDataRole.UserRole)
        if rule_name:
            self.rule_selected.emit(rule_name)
