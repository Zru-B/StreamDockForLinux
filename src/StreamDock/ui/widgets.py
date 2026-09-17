#!/usr/bin/env python3
"""
Custom widgets for StreamDock Configuration Editor
"""

import os
from pathlib import Path
from typing import Optional, Tuple

from StreamDock.application.config_document import (
    DEFAULT_FONT_SIZE,
    KeyDefinition,
)
from StreamDock.application.configuration_manager import resolve_icon_path
from StreamDock.ui.styles import get_colors
from StreamDock.ui.theme import Flavor, current_theme, theme_manager, themed_icon
from PyQt6.QtCore import (
    QEasingCurve,
    QMimeData,
    QPropertyAnimation,
    QRectF,
    QSize,
    Qt,
    pyqtProperty,
    pyqtSignal,
)
from PyQt6.QtGui import (
    QAction,
    QColor,
    QDrag,
    QFont,
    QIcon,
    QPainter,
    QPen,
    QPixmap,
)
from PyQt6.QtWidgets import (
    QAbstractButton,
    QAbstractScrollArea,
    QApplication,
    QButtonGroup,
    QFrame,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

COLORS = get_colors()

# Carried by a row being dragged to a new position in its list. Its own
# format, so a row cannot be dropped on anything else that takes text.
ACTION_MIME_TYPE = "application/x-streamdock-action"


def _font_size(value) -> int:
    """
    Coerce a configured font size into something QFont accepts.

    Args:
        value: Whatever the configuration held

    Returns:
        A usable point size, falling back to the default
    """
    try:
        size = int(value)
    except (TypeError, ValueError):
        return DEFAULT_FONT_SIZE
    return size if size > 0 else DEFAULT_FONT_SIZE


def _rgba(color: str, alpha: int) -> str:
    """
    A stylesheet rgba() string for a colour at a given transparency.

    Args:
        color: Any colour QColor understands
        alpha: 0 (invisible) to 255 (solid)

    Returns:
        The rgba(...) text
    """
    rgb = QColor(color)
    return f"rgba({rgb.red()}, {rgb.green()}, {rgb.blue()}, {alpha})"


def _mix(start: str, end: str, ratio: float) -> QColor:
    """
    Blend two colours, with ratio 0 giving start and 1 giving end.

    Args:
        start: Colour at ratio 0
        end: Colour at ratio 1
        ratio: Position between the two

    Returns:
        The blended colour
    """
    first, second = QColor(start), QColor(end)
    return QColor(
        *(round(a + (b - a) * ratio)
          for a, b in zip(first.getRgb(), second.getRgb())))


class ElidedLabel(QLabel):
    """
    A label that shortens its own text instead of widening its row.

    A QLabel reports the full text as its minimum width, so one long action
    description would push the whole list wider than the box holding it.
    """

    def __init__(self, text: str = "", parent=None):
        super().__init__(parent)
        self._full_text = ""
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self.setText(text)

    def setText(self, text: str) -> None:
        self._full_text = text
        self._elide()

    def full_text(self) -> str:
        """The text as given, before any shortening."""
        return self._full_text

    def minimumSizeHint(self) -> QSize:
        # Keep the height, drop the width: the row decides how much it gets.
        return QSize(0, super().minimumSizeHint().height())

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._elide()

    def _elide(self) -> None:
        shown = self.fontMetrics().elidedText(
            self._full_text, Qt.TextElideMode.ElideRight, max(0, self.width()))
        super().setText(shown)
        # Only worth a tooltip when something is actually hidden.
        self.setToolTip("" if shown == self._full_text else self._full_text)


def glyph_button(glyph: str, role: str, tooltip: str,
                 size: int = 22, icon: Tuple[str, ...] = ()) -> QPushButton:
    """
    Build a borderless icon button.

    The desktop's own icon is used when it has one for the job; the glyph is
    what is drawn on a system without an icon theme. The colour of a glyph
    comes from the role rather than from the caller, so the same add or
    remove affordance stays recognisable across both designs and both colour
    schemes.

    Args:
        glyph: The character to show when no icon can be found
        role: 'add', 'edit', 'remove' or 'neutral'
        tooltip: Hover text
        size: Width and height in pixels
        icon: freedesktop icon names to try, most specific first

    Returns:
        The button
    """
    button = QPushButton()
    button.setFixedSize(size, size)
    button.setCursor(Qt.CursorShape.PointingHandCursor)
    button.setToolTip(tooltip)
    button.setProperty("buttonType", "glyph")
    button.setProperty("glyphRole", role)

    themed = themed_icon(*icon) if icon else QIcon()
    if themed.isNull():
        button.setText(glyph)
        # Set here rather than in the sheet: the caller picks the size, and a
        # glyph has to grow with its button to stay centred.
        button.setStyleSheet(f"font-size: {size - 6}px;")
    else:
        button.setIcon(themed)
        button.setIconSize(QSize(max(12, size - 8), max(12, size - 8)))
    return button


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
        # Drawn over the key image while a drag hovers here. A border on the
        # square itself would sit under the icon, which covers all 112px.
        self._overlay = None
        # Directory relative icon paths resolve against; set by the main
        # window whenever the open configuration changes.
        self.config_dir: str = os.getcwd()
        
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
        
        theme_manager().changed.connect(self._on_theme_changed)
    
    def _on_theme_changed(self) -> None:
        """
        Redraw an empty slot in the new theme.

        A filled square is a picture of the device's own screen, which no
        desktop theme has any say over, so it is left alone.
        """
        if self.is_empty():
            self.set_empty()
    
    def set_empty(self):
        """Set the square to empty state"""
        self.key_definition = None
        self.key_name = None
        
        # Clear both text and pixmap
        self.label.setText("")
        self.label.setPixmap(QPixmap())
        
        # Completely reset label stylesheet
        self.label.setStyleSheet(
            f"background-color: transparent; color: {COLORS['text_secondary']};")
        
        # Empty state: an outlined slot, drawn in the theme's own colours so a
        # light desktop does not get a black hole in the middle of the grid.
        self.setStyleSheet(f"""
            KeySquare {{
                background-color: {COLORS['bg_alternate']};
                border: 1px dashed {COLORS['border_strong']};
                border-radius: {current_theme().metrics.radius}px;
            }}
            KeySquare:hover {{
                background-color: {COLORS['bg_hover']};
                border: 1px solid {COLORS['primary']};
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
            # Icon mode: fill entire square with icon.
            # Relative paths resolve against the config file's directory, the
            # same rule the runtime applies, so the preview matches the device.
            icon_path = Path(resolve_icon_path(key_def.icon, self.config_dir))
            
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
        
        elif key_def.has_text():
            # Text mode: centered text with specified colors.
            # has_text() rather than is_text_based() so a key carrying both an
            # icon and text still renders something; the icon branch above
            # already handled the case where the icon loaded.
            self.label.setPixmap(QPixmap())  # Clear any pixmap
            self.label.setText(str(key_def.text))
            
            # Set font. font_size comes straight from the file, and QFont
            # rejects anything but an int - which would raise out of a Qt slot
            # and take the window down.
            font = QFont()
            font.setPointSize(_font_size(key_def.font_size))
            font.setBold(bool(key_def.bold))
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
        
        else:
            # Neither field usable. Without this the square keeps its empty
            # styling while key_name is set, so is_empty() disagrees with what
            # the user sees.
            self._show_error("No icon\nor text")
        
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
        
        self.setStyleSheet(f"""
            KeySquare {{
                background-color: {COLORS['bg_input']};
                border: 1px solid {COLORS['danger']};
                border-radius: {current_theme().metrics.radius}px;
            }}
        """)
        self.label.setStyleSheet(
            f"color: {COLORS['danger']}; background-color: {COLORS['bg_input']};")
    
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
    
    def dragged_position(self, mime) -> Optional[int]:
        """
        The square a drag started from, or None if it did not start here.

        Args:
            mime: The drag's mime data

        Returns:
            A key position, or None when the drag is not one of ours or
            started on this very square
        """
        if not mime.hasText():
            return None
        try:
            position = int(mime.text())
        except ValueError:
            return None
        return None if position == self.position else position

    def dragEnterEvent(self, event):
        """Take any key dragged from another square"""
        if self.dragged_position(event.mimeData()) is None:
            event.ignore()
            return

        event.acceptProposedAction()
        # Green where the key would land on its own, blue where two keys
        # would trade places - the outcome differs, so the colour does too.
        color = COLORS['success'] if self.is_empty() else COLORS['primary']
        self._highlight(color)
    
    def dragLeaveEvent(self, event):
        """Remove highlight when drag leaves"""
        self._clear_highlight()
    
    def dropEvent(self, event):
        """Move the dragged key here, trading places with whatever is here"""
        self._clear_highlight()
        from_position = self.dragged_position(event.mimeData())
        if from_position is None:
            event.ignore()
            return

        event.acceptProposedAction()
        # The window owns the layout, so it decides whether this is a move
        # into an empty square or a swap.
        self.key_moved.emit(from_position, self.position)

    def _highlight(self, color: str) -> None:
        """
        Outline the square while a drag hovers over it.

        Args:
            color: Border colour; the fill is the same colour, faint
        """
        if self._overlay is None:
            self._overlay = QWidget(self)
            self._overlay.setAttribute(
                Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self._overlay.setGeometry(self.rect())
        self._overlay.setStyleSheet(
            f"background-color: {_rgba(color, 45)}; border: 2px solid {color};")
        self._overlay.raise_()
        self._overlay.show()

    def _clear_highlight(self) -> None:
        """Put the square back to how it looked before the drag."""
        if self._overlay is not None:
            self._overlay.hide()
    
    def _update_cursor(self):
        """Update cursor based on whether key is defined"""
        if self.is_empty():
            self.setCursor(Qt.CursorShape.PointingHandCursor)
        else:
            self.setCursor(Qt.CursorShape.OpenHandCursor)
    
    def is_empty(self) -> bool:
        """Check if this square is empty"""
        return self.key_definition is None


class SidebarSection(QWidget):
    """
    One titled list in the sidebar: a heading with an add button, then the rows.

    On Plasma this is drawn the way Dolphin draws its Places panel - a
    heading ruled off from the rows beneath it, sitting straight on the
    window - and on GNOME as a card. The stylesheet decides; the widget only
    names its parts.
    """

    def __init__(self, title: str, add_tooltip: str, parent=None):
        super().__init__(parent)
        self.setObjectName("sidePanel")
        # A plain QWidget ignores a stylesheet background without this.
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)

        self._layout = QVBoxLayout(self)

        header = QHBoxLayout()
        header.setContentsMargins(0, 0, 0, 0)
        header.setSpacing(4)

        self.title = QLabel(title)
        self.title.setObjectName("sidebarHeading")
        header.addWidget(self.title)
        header.addStretch()

        self.add_btn = glyph_button("+", "add", add_tooltip, size=24,
                                    icon=('list-add', 'list-add-symbolic'))
        header.addWidget(self.add_btn)
        self._layout.addLayout(header)

        # The hairline under the heading; the GNOME card has no use for it.
        self.rule = QFrame()
        self.rule.setObjectName("sidebarRule")
        self.rule.setFixedHeight(1)
        self._layout.addWidget(self.rule)

        self.list_widget = QListWidget()
        self.list_widget.setObjectName("sidebarList")
        self.list_widget.setFrameShape(QFrame.Shape.NoFrame)
        self.list_widget.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.list_widget.itemClicked.connect(self._on_item_clicked)
        self.list_widget.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.list_widget.customContextMenuRequested.connect(self._show_context_menu)
        self._layout.addWidget(self.list_widget)

        theme_manager().changed.connect(self._apply_metrics)
        self._apply_metrics()

    def _apply_metrics(self) -> None:
        """Lay the section out for the active design."""
        theme = current_theme()
        metrics = theme.metrics
        breeze = theme.flavor is Flavor.KDE

        if breeze:
            self._layout.setContentsMargins(metrics.card_padding, metrics.card_padding,
                                            metrics.card_padding, metrics.spacing_tight)
            self._layout.setSpacing(metrics.spacing_tight)
        else:
            self._layout.setContentsMargins(metrics.card_padding, metrics.card_padding,
                                            metrics.card_padding, metrics.card_padding)
            self._layout.setSpacing(metrics.spacing)
        self.rule.setVisible(breeze)
        self.list_widget.setIconSize(QSize(metrics.icon_size, metrics.icon_size))
        for index in range(self.list_widget.count()):
            self.list_widget.item(index).setSizeHint(QSize(0, metrics.list_row_height))

    def _add_row(self, text: str, key: str, icon: QIcon = None,
                 bold: bool = False, tooltip: str = "") -> QListWidgetItem:
        """
        Append one row.

        Args:
            text: What the row says
            key: What the row stands for, returned by the selection methods
            icon: The picture at its left, if any
            bold: Whether to weight the text
            tooltip: Hover text

        Returns:
            The item
        """
        item = QListWidgetItem(icon if icon is not None else QIcon(), text)
        item.setData(Qt.ItemDataRole.UserRole, key)
        item.setSizeHint(QSize(0, current_theme().metrics.list_row_height))
        if bold:
            font = item.font()
            font.setBold(True)
            item.setFont(font)
        if tooltip:
            item.setToolTip(tooltip)
        self.list_widget.addItem(item)
        return item

    def _add_placeholder(self, text: str) -> None:
        """
        Say that the list is empty, in the list.

        Args:
            text: The explanation
        """
        item = QListWidgetItem(text)
        item.setFlags(Qt.ItemFlag.NoItemFlags)
        item.setSizeHint(QSize(0, current_theme().metrics.list_row_height))
        self.list_widget.addItem(item)

    def select(self, key: str) -> None:
        """
        Highlight the row standing for this key, if there is one.

        Args:
            key: The row's key
        """
        for index in range(self.list_widget.count()):
            if self.list_widget.item(index).data(Qt.ItemDataRole.UserRole) == key:
                self.list_widget.setCurrentRow(index)
                return

    def _selected_key(self) -> Optional[str]:
        current = self.list_widget.currentItem()
        return current.data(Qt.ItemDataRole.UserRole) if current else None

    def _on_item_clicked(self, item: QListWidgetItem) -> None:
        raise NotImplementedError

    def _show_context_menu(self, position) -> None:
        raise NotImplementedError


class LayoutListWidget(SidebarSection):
    """The layouts a configuration holds, with the default marked."""

    layout_selected = pyqtSignal(str)  # Emits layout name
    add_layout_clicked = pyqtSignal()
    delete_layout_clicked = pyqtSignal(str)  # Emits layout name
    set_default_clicked = pyqtSignal(str)  # Emits layout name to set as default
    edit_layout_clicked = pyqtSignal(str)  # Emits layout name to edit

    def __init__(self, parent=None):
        super().__init__("Layouts", "Add new layout", parent)
        self.add_btn.clicked.connect(self.add_layout_clicked.emit)

    def _show_context_menu(self, position):
        """Show context menu for layout items"""
        item = self.list_widget.itemAt(position)
        if not item:
            return

        layout_name = item.data(Qt.ItemDataRole.UserRole)
        if not layout_name:
            return

        menu = QMenu(self)

        edit_action = QAction(themed_icon('document-edit', 'edit-entry'), "Edit Layout", self)
        edit_action.triggered.connect(lambda: self.edit_layout_clicked.emit(layout_name))
        menu.addAction(edit_action)

        menu.addSeparator()

        set_default_action = QAction(themed_icon('starred-symbolic', 'rating', 'emblem-favorite'),
                                     "Set as Default", self)
        set_default_action.triggered.connect(lambda: self.set_default_clicked.emit(layout_name))
        menu.addAction(set_default_action)

        delete_action = QAction(themed_icon('edit-delete', 'edit-delete-symbolic'), "Delete", self)
        delete_action.triggered.connect(lambda: self.delete_layout_clicked.emit(layout_name))
        menu.addAction(delete_action)

        menu.exec(self.list_widget.mapToGlobal(position))

    def set_layouts(self, layout_names: list, default_layout: str = None):
        """Set the list of layouts"""
        selected = self._selected_key()
        self.list_widget.clear()

        layout_icon = themed_icon('view-grid', 'view-grid-symbolic')
        default_icon = themed_icon('starred-symbolic', 'rating', 'emblem-favorite')
        for name in layout_names:
            is_default = name == default_layout
            self._add_row(name, name,
                          icon=default_icon if is_default and not default_icon.isNull() else layout_icon,
                          bold=is_default,
                          tooltip="Default layout" if is_default else "")

        if selected is not None:
            self.select(selected)

    def get_selected_layout(self) -> str:
        """Get currently selected layout name"""
        return self._selected_key()

    def _on_item_clicked(self, item: QListWidgetItem):
        """Handle item click"""
        layout_name = item.data(Qt.ItemDataRole.UserRole)
        if layout_name:
            self.layout_selected.emit(layout_name)


class ActionListItem(QWidget):
    """Widget representing a single action in the action list"""
    
    remove_clicked = pyqtSignal(int)  # Emits index
    edit_clicked = pyqtSignal(int)  # Emits index

    ROW_HEIGHT = 32
    # Grip dots. DejaVu and Noto both carry this one; a dedicated drag glyph
    # would be tofu on a bare system.
    GRIP = "⠿"

    def __init__(self, index: int, action_dict: dict, parent=None):
        super().__init__(parent)
        self.index = index
        self.action_dict = action_dict
        self._drag_start = None
        self.setup_ui()

    def setup_ui(self):
        """Setup the UI"""
        self.setObjectName("actionRow")
        # A plain QWidget ignores a stylesheet background without this.
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setFixedHeight(self.ROW_HEIGHT)

        # Rows are reordered by dragging them, so say so with the pointer.
        self.setCursor(Qt.CursorShape.OpenHandCursor)
        self.setToolTip("Drag to reorder")

        layout = QHBoxLayout(self)
        layout.setContentsMargins(6, 0, 4, 0)
        layout.setSpacing(4)

        grip = QLabel(self.GRIP)
        grip.setObjectName("actionGrip")
        layout.addWidget(grip)

        # Position in the sequence: actions run in order, so it is worth
        # numbering them.
        self.number = QLabel(f"{self.index + 1}")
        self.number.setObjectName("actionIndex")
        self.number.setFixedWidth(16)
        self.number.setAlignment(Qt.AlignmentFlag.AlignRight
                                 | Qt.AlignmentFlag.AlignVCenter)
        layout.addWidget(self.number)

        self.label = ElidedLabel(self._format_action())
        self.label.setObjectName("actionText")
        layout.addWidget(self.label, stretch=1)

        for glyph, role, tooltip, signal in (
                ("✎", "edit", "Edit action", self.edit_clicked),
                ("✕", "remove", "Remove action", self.remove_clicked)):
            button = glyph_button(glyph, role, tooltip)
            # The buttons keep the normal pointer; only the row is draggable.
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.clicked.connect(
                lambda _checked, emit=signal: emit.emit(self.index))
            layout.addWidget(button)

    # ── dragging the row to a new position ───────────────────────────────

    def mousePressEvent(self, event):
        """Remember where a press started, in case it becomes a drag"""
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_start = event.pos()
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        """A press that never moved far enough was not a drag"""
        self._drag_start = None
        super().mouseReleaseEvent(event)

    def mouseMoveEvent(self, event):
        """Carry the row to wherever it is dropped"""
        if self._drag_start is None:
            return
        if not (event.buttons() & Qt.MouseButton.LeftButton):
            return
        if ((event.pos() - self._drag_start).manhattanLength()
                < QApplication.startDragDistance()):
            return

        mime = QMimeData()
        mime.setData(ACTION_MIME_TYPE, str(self.index).encode())

        drag = QDrag(self)
        drag.setMimeData(mime)
        # A snapshot of the row itself, so what you carry is what you moved.
        drag.setPixmap(self.grab())
        drag.setHotSpot(event.pos())
        drag.exec(Qt.DropAction.MoveAction)
        self._drag_start = None

    def _format_action(self) -> str:
        """Format action dictionary for display"""
        if not self.action_dict:
            return "Empty action"

        # The validator accepts a bare string action, e.g. "- WAIT".
        if isinstance(self.action_dict, str):
            return str(self.action_dict)
        if not isinstance(self.action_dict, dict):
            return str(self.action_dict)
        
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
            # The payload is not guaranteed to be a string: `TYPE_TEXT: 42`
            # passes validation.
            text = action_value if isinstance(action_value, str) else str(action_value)
            preview = text[:30] + "..." if len(text) > 30 else text
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


class ActionListContainer(QWidget):
    """
    Holds the action rows and reorders them by drag and drop.

    Owns the drop arithmetic: which gap the pointer is nearest, the line
    drawn there while a drag is in flight, and the move that results.
    """

    action_moved = pyqtSignal(int, int)  # Emits (from_index, to_index)

    # How close to an edge the pointer has to be before the list scrolls.
    SCROLL_MARGIN = 24
    SCROLL_STEP = 12

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("actionsContainer")
        # A plain QWidget ignores a stylesheet background without this.
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setAcceptDrops(True)
        # The gap the indicator sits in, or None when no drag is in flight.
        self._drop_gap = None

    def rows(self) -> list:
        """The action rows, top to bottom."""
        layout = self.layout()
        if layout is None:
            return []
        widgets = (layout.itemAt(i).widget() for i in range(layout.count()))
        return [w for w in widgets if isinstance(w, ActionListItem)]

    def gap_at(self, y: float) -> int:
        """
        The gap a drop at this height would land in.

        Gap 0 is above the first row, gap len(rows) is below the last.

        Args:
            y: Height within this widget

        Returns:
            The gap index
        """
        rows = self.rows()
        for index, row in enumerate(rows):
            if y < row.geometry().center().y():
                return index
        return len(rows)

    # ── drop handling ────────────────────────────────────────────────────

    def dragEnterEvent(self, event):
        """Take rows from this list and nothing else"""
        if event.mimeData().hasFormat(ACTION_MIME_TYPE):
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragMoveEvent(self, event):
        """Track where the row would land"""
        if not event.mimeData().hasFormat(ACTION_MIME_TYPE):
            event.ignore()
            return
        self._set_drop_gap(self.gap_at(event.position().y()))
        self._scroll_towards(event.position().y())
        event.acceptProposedAction()

    def dragLeaveEvent(self, event):
        """Drop the indicator when the drag goes elsewhere"""
        self._set_drop_gap(None)
        super().dragLeaveEvent(event)

    def dropEvent(self, event):
        """Move the dragged row into the gap it was dropped on"""
        if not event.mimeData().hasFormat(ACTION_MIME_TYPE):
            event.ignore()
            return

        source = int(bytes(event.mimeData().data(ACTION_MIME_TYPE)).decode())
        gap = self.gap_at(event.position().y())
        self._set_drop_gap(None)
        event.acceptProposedAction()

        # The gaps either side of a row are where it already is.
        if gap in (source, source + 1):
            return
        # Removing the row first shifts every later gap up by one.
        self.action_moved.emit(source, gap - 1 if gap > source else gap)

    def _set_drop_gap(self, gap) -> None:
        if gap != self._drop_gap:
            self._drop_gap = gap
            self.update()

    def _scroll_towards(self, y: float) -> None:
        """
        Scroll when the pointer nears an edge, so a long list can be crossed.

        Args:
            y: Height within this widget
        """
        area = self._scroll_area()
        if area is None:
            return
        bar = area.verticalScrollBar()
        offset = y - bar.value()
        if offset < self.SCROLL_MARGIN:
            bar.setValue(bar.value() - self.SCROLL_STEP)
        elif offset > area.viewport().height() - self.SCROLL_MARGIN:
            bar.setValue(bar.value() + self.SCROLL_STEP)

    def _scroll_area(self):
        widget = self.parentWidget()
        while widget is not None:
            if isinstance(widget, QAbstractScrollArea):
                return widget
            widget = widget.parentWidget()
        return None

    def paintEvent(self, event):
        """Draw the line marking where the row would land"""
        super().paintEvent(event)
        if self._drop_gap is None:
            return

        rows = self.rows()
        spacing = self.layout().spacing() if self.layout() else 0
        margins = self.contentsMargins()
        if not rows:
            y = margins.top()
        elif self._drop_gap < len(rows):
            y = rows[self._drop_gap].geometry().top() - spacing / 2
        else:
            y = rows[-1].geometry().bottom() + spacing / 2

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(QPen(QColor(COLORS['primary']), 2,
                            Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        painter.drawLine(margins.left(), int(y),
                         self.width() - margins.right(), int(y))


class WindowRulesWidget(SidebarSection):
    """The window rules a configuration holds."""

    rule_selected = pyqtSignal(str)  # Emits rule name
    add_rule_clicked = pyqtSignal()
    delete_rule_clicked = pyqtSignal(str)  # Emits rule name
    edit_rule_clicked = pyqtSignal(str)  # Emits rule name to edit

    def __init__(self, parent=None):
        super().__init__("Window Rules", "Add new window rule", parent)
        self.add_btn.clicked.connect(self.add_rule_clicked.emit)

    def _show_context_menu(self, position):
        """Show context menu for window rule items"""
        item = self.list_widget.itemAt(position)
        if not item:
            return

        rule_name = item.data(Qt.ItemDataRole.UserRole)
        if not rule_name:
            return

        menu = QMenu(self)

        edit_action = QAction(themed_icon('document-edit', 'edit-entry'), "Edit Rule", self)
        edit_action.triggered.connect(lambda: self.edit_rule_clicked.emit(rule_name))
        menu.addAction(edit_action)

        menu.addSeparator()

        delete_action = QAction(themed_icon('edit-delete', 'edit-delete-symbolic'), "Delete", self)
        delete_action.triggered.connect(lambda: self.delete_rule_clicked.emit(rule_name))
        menu.addAction(delete_action)

        menu.exec(self.list_widget.mapToGlobal(position))

    def set_rules(self, rules: dict):
        """Set the list of window rules"""
        selected = self._selected_key()
        self.list_widget.clear()
        if not rules:
            self._add_placeholder("No rules defined")
            return

        icon = themed_icon('preferences-system-windows', 'window', 'window-symbolic')
        for rule_name, rule in rules.items():
            target = getattr(rule, 'layout', '') or ''
            pattern = getattr(rule, 'window_name', '') or ''
            tooltip = f"{pattern} → {target}" if pattern and target else ""
            self._add_row(rule_name, rule_name, icon=icon, tooltip=tooltip)

        if selected is not None:
            self.select(selected)

    def get_selected_rule(self) -> str:
        """Get currently selected rule name"""
        return self._selected_key()

    def _on_item_clicked(self, item: QListWidgetItem):
        """Handle item click"""
        rule_name = item.data(Qt.ItemDataRole.UserRole)
        if rule_name:
            self.rule_selected.emit(rule_name)


class ToggleSwitch(QAbstractButton):
    """
    A compact on/off switch with its own label.

    Stands in for a QCheckBox where a 20px box with a tick reads as heavy: it
    is checkable, emits toggled(bool) and answers isChecked() the same way.
    """

    TRACK_WIDTH = 34
    TRACK_HEIGHT = 18
    KNOB_MARGIN = 2
    TEXT_SPACING = 10

    # Breeze's switch is a little larger, and outlined rather than filled
    # while off.
    BREEZE_TRACK_WIDTH = 36
    BREEZE_TRACK_HEIGHT = 20

    def __init__(self, text: str = "", parent=None):
        super().__init__(parent)
        self.setCheckable(True)
        self.setText(text)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

        self._knob = 0.0
        self._hovered = False
        # Painted by hand, so a theme change has to be repainted by hand.
        theme_manager().changed.connect(self.update)
        self._slide = QPropertyAnimation(self, b"knob_position", self)
        self._slide.setDuration(120)
        self._slide.setEasingCurve(QEasingCurve.Type.InOutCubic)

    def _get_knob_position(self) -> float:
        return self._knob

    def _set_knob_position(self, value: float) -> None:
        self._knob = value
        self.update()

    # Animated by _slide; Qt needs it as a property to drive it.
    knob_position = pyqtProperty(float, _get_knob_position, _set_knob_position)

    def _slide_knob(self) -> None:
        """Run the knob to whichever end the current state calls for."""
        self._slide.stop()
        self._slide.setStartValue(self._knob)
        self._slide.setEndValue(1.0 if self.isChecked() else 0.0)
        self._slide.start()

    def checkStateSet(self):
        """Qt calls this when the state is set in code (setChecked)."""
        self._slide_knob()

    def nextCheckState(self):
        """Qt calls this when the user clicks or presses space."""
        super().nextCheckState()
        self._slide_knob()

    def _track_size(self) -> tuple:
        """
        The track's width and height for the active design.

        Returns:
            (width, height) in pixels
        """
        if current_theme().flavor is Flavor.KDE:
            return self.BREEZE_TRACK_WIDTH, self.BREEZE_TRACK_HEIGHT
        return self.TRACK_WIDTH, self.TRACK_HEIGHT

    def sizeHint(self) -> QSize:
        metrics = self.fontMetrics()
        track_width, track_height = self._track_size()
        width = track_width
        if self.text():
            width += self.TEXT_SPACING + metrics.horizontalAdvance(self.text())
        return QSize(width, max(track_height, metrics.height()))

    def minimumSizeHint(self) -> QSize:
        return self.sizeHint()

    def enterEvent(self, event):
        self._hovered = True
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._hovered = False
        self.update()
        super().leaveEvent(event)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        track_width, track_height = self._track_size()
        top = (self.height() - track_height) / 2
        if current_theme().flavor is Flavor.KDE:
            self._paint_breeze_track(painter, top, track_width, track_height)
        else:
            self._paint_adwaita_track(painter, top, track_width, track_height)

        if self.hasFocus():
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.setPen(QColor(COLORS['border_focus']))
            painter.drawRoundedRect(
                QRectF(-1.0, top - 1.0, track_width + 2.0, track_height + 2.0),
                (track_height + 2) / 2, (track_height + 2) / 2)

        if self.text():
            painter.setPen(QColor(COLORS['text_primary'] if self.isEnabled()
                                  else COLORS['text_secondary']))
            painter.drawText(
                QRectF(track_width + self.TEXT_SPACING, 0,
                       self.width() - track_width - self.TEXT_SPACING,
                       self.height()),
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                self.text())

    def _paint_adwaita_track(self, painter: QPainter, top: float,
                             track_width: int, track_height: int) -> None:
        """
        The GNOME switch: a filled pill whose colour follows the knob.

        Args:
            painter: Where to draw
            top: Vertical offset of the track
            track_width: Track width
            track_height: Track height
        """
        painter.setPen(Qt.PenStyle.NoPen)
        # Off, the track has to stand out from a card that may be the same
        # colour as any raised control, so it starts from the border shade.
        track_color = _mix(COLORS['border_strong'],
                           COLORS['primary_hover'] if self._hovered
                           else COLORS['primary'],
                           self._knob)
        painter.setBrush(track_color)
        painter.drawRoundedRect(
            QRectF(0, top, track_width, track_height),
            track_height / 2, track_height / 2)

        diameter = track_height - 2 * self.KNOB_MARGIN
        travel = track_width - diameter - 2 * self.KNOB_MARGIN
        painter.setBrush(_mix(COLORS['text_secondary'], 'white', self._knob))
        painter.drawEllipse(
            QRectF(self.KNOB_MARGIN + travel * self._knob,
                   top + self.KNOB_MARGIN, diameter, diameter))

    def _paint_breeze_track(self, painter: QPainter, top: float,
                            track_width: int, track_height: int) -> None:
        """
        The Plasma switch: an outlined pill that fills with the accent.

        Off, it is an outline on the view colour with a button-coloured knob;
        on, the track is the accent and the knob is white. Hovering colours
        the outline with the accent, the way every Breeze control answers
        the pointer.

        Args:
            painter: Where to draw
            top: Vertical offset of the track
            track_width: Track width
            track_height: Track height
        """
        accent = COLORS['primary']
        outline = COLORS['border_focus'] if self._hovered else COLORS['border_strong']
        painter.setPen(QPen(_mix(outline, accent, self._knob), 1))
        painter.setBrush(_mix(COLORS['bg_input'], accent, self._knob))
        painter.drawRoundedRect(
            QRectF(0.5, top + 0.5, track_width - 1, track_height - 1),
            (track_height - 1) / 2, (track_height - 1) / 2)

        diameter = track_height - 2 * self.KNOB_MARGIN - 1
        travel = track_width - diameter - 2 * self.KNOB_MARGIN - 1
        painter.setPen(QPen(_mix(outline, accent, self._knob), 1))
        painter.setBrush(_mix(COLORS['bg_tertiary'], COLORS['on_primary'], self._knob))
        painter.drawEllipse(
            QRectF(self.KNOB_MARGIN + 0.5 + travel * self._knob,
                   top + self.KNOB_MARGIN + 0.5, diameter, diameter))


class SegmentedControl(QWidget):
    """
    A short list of mutually exclusive options drawn as one pill.

    Stands in for a group of radio buttons where there are only two or three
    choices: the selection reads at a glance and costs one row, not one per
    option.
    """

    selection_changed = pyqtSignal(str)

    def __init__(self, options, parent=None):
        super().__init__(parent)
        self.setObjectName("segmentedControl")
        # A plain QWidget ignores a stylesheet background without this.
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)

        row = QHBoxLayout(self)
        row.setContentsMargins(2, 2, 2, 2)
        row.setSpacing(2)

        self._group = QButtonGroup(self)
        self._group.setExclusive(True)
        self._buttons = {}

        for option in options:
            button = QPushButton(option)
            button.setCheckable(True)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.setProperty("segment", "true")
            self._group.addButton(button)
            row.addWidget(button)
            self._buttons[option] = button

        if self._buttons:
            next(iter(self._buttons.values())).setChecked(True)
        self._group.buttonToggled.connect(self._on_button_toggled)

    def _on_button_toggled(self, button, checked: bool) -> None:
        # Switching selection toggles two buttons; only report the new one.
        if checked:
            self.selection_changed.emit(button.text())

    def current(self) -> str:
        """The selected option."""
        button = self._group.checkedButton()
        return button.text() if button else ""

    def set_current(self, option: str) -> None:
        """
        Select an option.

        Args:
            option: One of the options the control was built with; anything
                else leaves the selection alone
        """
        button = self._buttons.get(option)
        if button:
            button.setChecked(True)
