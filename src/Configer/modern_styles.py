"""
Modern UI Styles for StreamDock Configuration Editor
"""

# Modern Color Palette - Dark Mode
COLORS = {
    # Primary colors
    "primary": "#3B82F6",  # Blue
    "primary_hover": "#60A5FA",  # Lighter blue for dark mode
    "primary_dark": "#1E40AF",
    # Secondary colors
    "secondary": "#8B5CF6",  # Purple
    "secondary_hover": "#A78BFA",
    # Success/Add
    "success": "#10B981",  # Green
    "success_hover": "#34D399",
    # Danger/Delete
    "danger": "#EF4444",  # Red
    "danger_hover": "#F87171",
    # Warning
    "warning": "#F59E0B",  # Orange
    "warning_hover": "#FBBF24",
    # Info/Edit
    "info": "#06B6D4",  # Cyan
    "info_hover": "#22D3EE",
    # Neutral colors - Dark Mode
    "bg_primary": "#0F1419",  # Very dark (main background)
    "bg_secondary": "#1A1F26",  # Dark (cards)
    "bg_tertiary": "#252A31",  # Medium dark (inputs, squares)
    "bg_hover": "#2D333B",  # Hover state
    "bg_light": "#1A1F26",  # Slightly lighter dark
    "bg_card": "#1A1F26",  # Dark cards
    # Text colors - Dark Mode
    "text_primary": "#E6EDF3",  # Light text
    "text_secondary": "#8B949E",  # Gray text
    "text_light": "#E6EDF3",  # Light text
    "text_dark": "#111827",  # Dark text (for light backgrounds)
    # Border colors - Dark Mode
    "border": "#30363D",  # Dark border
    "border_focus": "#3B82F6",  # Blue focus
}

# Modern stylesheet - Dark Mode
MODERN_STYLESHEET = f"""
QMainWindow {{
    background-color: {COLORS['bg_primary']};
    color: {COLORS['text_primary']};
}}

/* Menu Bar */
QMenuBar {{
    background-color: {COLORS['bg_secondary']};
    color: {COLORS['text_light']};
    padding: 6px;
    border-bottom: 2px solid {COLORS['primary']};
}}

QMenuBar::item {{
    background-color: transparent;
    padding: 8px 16px;
    border-radius: 4px;
}}

QMenuBar::item:selected {{
    background-color: {COLORS['bg_hover']};
}}

QMenu {{
    background-color: {COLORS['bg_secondary']};
    color: {COLORS['text_primary']};
    border: 1px solid {COLORS['border']};
    border-radius: 8px;
    padding: 8px;
}}

QMenu::item {{
    padding: 8px 24px;
    border-radius: 4px;
    color: {COLORS['text_primary']};
}}

QMenu::item:selected {{
    background-color: {COLORS['primary']};
    color: white;
}}

/* Push Buttons */
QPushButton {{
    background-color: {COLORS['primary']};
    color: white;
    border: none;
    padding: 10px 20px;
    border-radius: 6px;
    font-weight: 500;
    font-size: 14px;
    min-height: 36px;
}}

QPushButton:hover {{
    background-color: {COLORS['primary_hover']};
}}

QPushButton:pressed {{
    background-color: {COLORS['primary_dark']};
}}

QPushButton:disabled {{
    background-color: {COLORS['bg_tertiary']};
    color: {COLORS['text_secondary']};
}}

/* Success buttons (Add, Save) */
QPushButton[buttonType="success"] {{
    background-color: {COLORS['success']};
}}

QPushButton[buttonType="success"]:hover {{
    background-color: {COLORS['success_hover']};
}}

/* Danger buttons (Delete, Remove) */
QPushButton[buttonType="danger"] {{
    background-color: {COLORS['danger']};
}}

QPushButton[buttonType="danger"]:hover {{
    background-color: {COLORS['danger_hover']};
}}

/* Secondary buttons */
QPushButton[buttonType="secondary"] {{
    background-color: {COLORS['bg_secondary']};
    color: white;
}}

QPushButton[buttonType="secondary"]:hover {{
    background-color: {COLORS['bg_tertiary']};
}}

/* Text Input Fields */
QLineEdit, QTextEdit, QPlainTextEdit {{
    background-color: {COLORS['bg_tertiary']};
    border: 2px solid {COLORS['border']};
    border-radius: 6px;
    padding: 8px 12px;
    font-size: 14px;
    color: {COLORS['text_primary']};
}}

QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus {{
    border-color: {COLORS['border_focus']};
    outline: none;
    background-color: {COLORS['bg_hover']};
}}

/* ComboBox (Dropdowns) */
QComboBox {{
    background-color: {COLORS['bg_tertiary']};
    border: 2px solid {COLORS['border']};
    border-radius: 6px;
    padding: 8px 12px;
    font-size: 14px;
    min-height: 36px;
    color: {COLORS['text_primary']};
}}

QComboBox:hover {{
    border-color: {COLORS['primary']};
    background-color: {COLORS['bg_hover']};
}}

QComboBox:focus {{
    border-color: {COLORS['border_focus']};
}}

QComboBox::drop-down {{
    border: none;
    padding-right: 8px;
}}

QComboBox::down-arrow {{
    image: none;
    border: 2px solid {COLORS['text_secondary']};
    border-top: none;
    border-left: none;
    width: 8px;
    height: 8px;
    margin-right: 8px;
}}

QComboBox QAbstractItemView {{
    background-color: {COLORS['bg_secondary']};
    color: {COLORS['text_primary']};
    border: 2px solid {COLORS['border']};
    border-radius: 6px;
    selection-background-color: {COLORS['primary']};
    selection-color: white;
    padding: 4px;
}}

/* List Widgets */
QListWidget {{
    background-color: {COLORS['bg_tertiary']};
    border: 2px solid {COLORS['border']};
    border-radius: 8px;
    padding: 8px;
    outline: none;
    color: {COLORS['text_primary']};
}}

QListWidget::item {{
    padding: 8px;
    border-radius: 6px;
    margin: 2px 0;
    min-height: 24px;
}}

QListWidget::item:hover {{
    background-color: {COLORS['bg_hover']};
}}

QListWidget::item:selected {{
    background-color: {COLORS['primary']};
    color: white;
}}

/* Group Boxes */
QGroupBox {{
    background-color: {COLORS['bg_secondary']};
    border: 2px solid {COLORS['border']};
    border-radius: 8px;
    margin-top: 12px;
    padding: 16px;
    font-weight: 600;
    font-size: 14px;
    color: {COLORS['text_primary']};
}}

QGroupBox::title {{
    subcontrol-origin: margin;
    subcontrol-position: top left;
    padding: 0 8px;
    background-color: {COLORS['bg_secondary']};
    color: {COLORS['text_primary']};
}}

/* Labels */
QLabel {{
    color: {COLORS['text_primary']};
    font-size: 14px;
}}

QLabel[headingLevel="1"] {{
    font-size: 24px;
    font-weight: 700;
    color: {COLORS['text_primary']};
}}

QLabel[headingLevel="2"] {{
    font-size: 18px;
    font-weight: 600;
    color: {COLORS['text_primary']};
}}

/* Checkboxes */
QCheckBox {{
    spacing: 8px;
    color: {COLORS['text_primary']};
}}

QCheckBox::indicator {{
    width: 20px;
    height: 20px;
    border: 2px solid {COLORS['border']};
    border-radius: 4px;
    background-color: white;
}}

QCheckBox::indicator:hover {{
    border-color: {COLORS['primary']};
}}

QCheckBox::indicator:checked {{
    background-color: {COLORS['primary']};
    border-color: {COLORS['primary']};
    image: url(data:image/svg+xml;base64,PHN2ZyB3aWR0aD0iMTIiIGhlaWdodD0iOSIgdmlld0JveD0iMCAwIDEyIDkiIGZpbGw9Im5vbmUiIHhtbG5zPSJodHRwOi8vd3d3LnczLm9yZy8yMDAwL3N2ZyI+CjxwYXRoIGQ9Ik0xIDQuNUw0LjUgOEwxMSAxIiBzdHJva2U9IndoaXRlIiBzdHJva2Utd2lkdGg9IjIiIHN0cm9rZS1saW5lY2FwPSJyb3VuZCIgc3Ryb2tlLWxpbmVqb2luPSJyb3VuZCIvPgo8L3N2Zz4K);
}}

/* Radio Buttons */
QRadioButton {{
    spacing: 8px;
    color: {COLORS['text_primary']};
}}

QRadioButton::indicator {{
    width: 20px;
    height: 20px;
    border: 2px solid {COLORS['border']};
    border-radius: 10px;
    background-color: white;
}}

QRadioButton::indicator:hover {{
    border-color: {COLORS['primary']};
}}

QRadioButton::indicator:checked {{
    background-color: white;
    border-color: {COLORS['primary']};
}}

QRadioButton::indicator:checked::after {{
    width: 12px;
    height: 12px;
    border-radius: 6px;
    background-color: {COLORS['primary']};
}}

/* Spin Boxes */
QSpinBox, QDoubleSpinBox {{
    background-color: {COLORS['bg_tertiary']};
    border: 2px solid {COLORS['border']};
    border-radius: 6px;
    padding: 8px 12px;
    font-size: 14px;
    min-height: 36px;
    color: {COLORS['text_primary']};
}}

QSpinBox:focus, QDoubleSpinBox:focus {{
    border-color: {COLORS['border_focus']};
    background-color: {COLORS['bg_hover']};
}}

/* Scroll Bars */
QScrollBar:vertical {{
    background-color: {COLORS['bg_light']};
    width: 12px;
    border-radius: 6px;
}}

QScrollBar::handle:vertical {{
    background-color: {COLORS['bg_tertiary']};
    border-radius: 6px;
    min-height: 30px;
}}

QScrollBar::handle:vertical:hover {{
    background-color: {COLORS['text_secondary']};
}}

QScrollBar:horizontal {{
    background-color: {COLORS['bg_light']};
    height: 12px;
    border-radius: 6px;
}}

QScrollBar::handle:horizontal {{
    background-color: {COLORS['bg_tertiary']};
    border-radius: 6px;
    min-width: 30px;
}}

QScrollBar::handle:horizontal:hover {{
    background-color: {COLORS['text_secondary']};
}}

QScrollBar::add-line, QScrollBar::sub-line {{
    background: none;
    border: none;
}}

/* Tab Widget */
QTabWidget::pane {{
    background-color: {COLORS['bg_secondary']};
    border: 2px solid {COLORS['border']};
    border-radius: 8px;
    padding: 16px;
    margin-top: -2px;
}}

QTabBar::tab {{
    background-color: {COLORS['bg_tertiary']};
    color: {COLORS['text_secondary']};
    padding: 10px 20px;
    border-top-left-radius: 6px;
    border-top-right-radius: 6px;
    margin-right: 4px;
    font-weight: 500;
}}

QTabBar::tab:hover {{
    background-color: {COLORS['bg_hover']};
}}

QTabBar::tab:selected {{
    background-color: {COLORS['bg_secondary']};
    color: {COLORS['text_primary']};
    border: 2px solid {COLORS['border']};
    border-bottom: 2px solid {COLORS['bg_secondary']};
}}

/* Scroll Area */
QScrollArea {{
    border: none;
    background-color: transparent;
}}

/* Dialogs */
QDialog {{
    background-color: {COLORS['bg_primary']};
    color: {COLORS['text_primary']};
}}

/* Tool Tips */
QToolTip {{
    background-color: {COLORS['bg_primary']};
    color: {COLORS['text_light']};
    border: none;
    border-radius: 4px;
    padding: 8px 12px;
    font-size: 13px;
}}
"""


def get_stylesheet():
    """Get the modern stylesheet"""
    return MODERN_STYLESHEET


def get_colors():
    """Get the color palette"""
    return COLORS
