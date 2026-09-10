"""
The application stylesheet, generated from a palette and a set of metrics.

One template produces both designs. Where Breeze and Adwaita genuinely
disagree - outlined versus filled buttons, an accent underline versus a pill,
a status bar versus a toast - the difference is a branch here rather than a
second copy of eight hundred lines of QSS.
"""

from StreamDock.ui.theme import assets
from StreamDock.ui.theme import color as c
from StreamDock.ui.theme.detection import Flavor
from StreamDock.ui.theme.metrics import Metrics
from StreamDock.ui.theme.palette import Palette


def build_stylesheet(palette: Palette, metrics: Metrics, flavor: Flavor) -> str:
    """
    Render the whole application stylesheet.

    Args:
        palette: Colours to paint with
        metrics: Shapes and sizes to paint to
        flavor: Which design's tells to apply

    Returns:
        A stylesheet ready for ``QApplication.setStyleSheet``
    """
    sections = (
        _base(palette, metrics),
        _menus(palette, metrics, flavor),
        _buttons(palette, metrics),
        _inputs(palette, metrics),
        _views(palette, metrics, flavor),
        _containers(palette, metrics, flavor),
        _indicators(palette, metrics),
        _chrome(palette, metrics),
        _application(palette, metrics, flavor),
    )
    return "\n".join(sections)


# ── foundations ──────────────────────────────────────────────────────────────


def _base(p: Palette, m: Metrics) -> str:
    return f"""
/* ── foundations ─────────────────────────────────────────────────────── */

QWidget {{
    color: {p.text_primary};
    font-size: {m.font_pt}pt;
}}

QMainWindow, QDialog {{
    background-color: {p.bg_primary};
    color: {p.text_primary};
}}

QWidget:disabled {{
    color: {p.text_disabled};
}}

QLabel {{
    background: transparent;
    color: {p.text_primary};
}}

QLabel:disabled {{
    color: {p.text_disabled};
}}

QLabel[headingLevel="1"] {{
    font-size: {m.title_pt}pt;
    font-weight: 700;
}}

QLabel[headingLevel="2"] {{
    font-size: {m.heading_pt}pt;
    font-weight: 600;
}}

QLabel[textRole="caption"] {{
    color: {p.text_secondary};
    font-size: {m.font_small_pt}pt;
}}

QToolTip {{
    background-color: {p.bg_tooltip};
    color: {p.text_tooltip};
    border: {m.border_width}px solid {p.border};
    border-radius: {m.radius}px;
    padding: 6px 10px;
    font-size: {m.font_small_pt}pt;
}}
"""


def _menus(p: Palette, m: Metrics, flavor: Flavor) -> str:
    breeze = flavor is Flavor.KDE
    # Breeze highlights a menu entry with the selection colour; an Adwaita
    # popover only tints it, keeping the accent for the action that matters.
    item_selected_bg = p.bg_selection if breeze else p.bg_hover
    item_selected_fg = p.text_selection if breeze else p.text_primary
    separator = (f"border-bottom: {m.border_width}px solid {p.separator};"
                 if m.header_separator else "border: none;")
    chevron = assets.glyph_path('chevron-right', p.text_secondary)

    return f"""
/* ── menus ───────────────────────────────────────────────────────────── */

QMenuBar {{
    background-color: {p.bg_header};
    color: {p.text_primary};
    padding: 2px 4px;
    {separator}
}}

QMenuBar::item {{
    background: transparent;
    padding: 5px 10px;
    border-radius: {m.radius}px;
}}

QMenuBar::item:selected {{
    background-color: {p.bg_hover};
}}

QMenuBar::item:pressed {{
    background-color: {item_selected_bg};
    color: {item_selected_fg};
}}

QMenu {{
    background-color: {p.bg_menu};
    color: {p.text_primary};
    border: {m.border_width}px solid {p.border};
    border-radius: {m.radius_large}px;
    padding: {m.spacing_tight}px;
}}

QMenu::item {{
    padding: {m.menu_item_padding}px 28px {m.menu_item_padding}px 14px;
    border-radius: {m.radius}px;
    color: {p.text_primary};
}}

QMenu::item:selected {{
    background-color: {item_selected_bg};
    color: {item_selected_fg};
}}

QMenu::item:disabled {{
    color: {p.text_disabled};
    background: transparent;
}}

QMenu::separator {{
    height: {m.border_width}px;
    background-color: {p.separator};
    margin: {m.spacing_tight}px 6px;
}}

QMenu::right-arrow {{
    image: url({chevron});
    width: 12px;
    height: 12px;
    margin-right: 8px;
}}

QMenu::icon {{
    margin-left: 8px;
}}
"""


# ── controls ─────────────────────────────────────────────────────────────────


def _buttons(p: Palette, m: Metrics) -> str:
    if m.flat_buttons:
        rest = f"background-color: {p.bg_tertiary};\n    border: none;"
        hover = f"background-color: {p.bg_hover};"
        pressed = f"background-color: {p.bg_pressed};"
    else:
        rest = (f"background-color: {p.bg_tertiary};\n"
                f"    border: {m.border_width}px solid {p.border};")
        hover = (f"background-color: {p.bg_hover};\n"
                 f"    border-color: {p.border_focus};")
        pressed = (f"background-color: {p.bg_pressed};\n"
                   f"    border-color: {p.border_focus};")

    def accent(name: str, fill: str, fill_hover: str, text: str) -> str:
        return f"""
QPushButton[buttonType="{name}"] {{
    background-color: {fill};
    color: {text};
    border: {m.border_width}px solid {fill};
    font-weight: 600;
}}

QPushButton[buttonType="{name}"]:hover {{
    background-color: {fill_hover};
    border-color: {fill_hover};
}}

QPushButton[buttonType="{name}"]:pressed {{
    background-color: {c.darken(fill, 0.18)};
    border-color: {c.darken(fill, 0.18)};
}}

QPushButton[buttonType="{name}"]:disabled {{
    background-color: {p.bg_tertiary};
    color: {p.text_disabled};
    border-color: {p.border};
}}"""

    return f"""
/* ── buttons ─────────────────────────────────────────────────────────── */

/* Quiet by default: a dialog full of accent blocks reads as a wall of
   alerts. buttonType picks a louder variant for the one action that leads. */
QPushButton {{
    {rest}
    color: {p.text_primary};
    border-radius: {m.radius}px;
    padding: 0 {m.button_padding}px;
    min-height: {m.control_height}px;
    font-weight: 500;
}}

QPushButton:hover {{
    {hover}
}}

QPushButton:pressed {{
    {pressed}
}}

QPushButton:focus {{
    border: {m.focus_width}px solid {p.border_focus};
}}

QPushButton:disabled {{
    background-color: {p.bg_tertiary};
    color: {p.text_disabled};
    border-color: {p.border};
}}

QPushButton:flat {{
    background: transparent;
    border: none;
}}
{accent("primary", p.primary, p.primary_hover, p.on_primary)}
{accent("success", p.success, p.success_hover, c.readable_on(p.success))}
{accent("danger", p.danger, p.danger_hover, c.readable_on(p.danger))}

/* Borderless glyph buttons: the add, edit and remove affordances on rows. */
QPushButton[buttonType="glyph"] {{
    background: transparent;
    border: none;
    padding: 0;
    min-height: 0;
    font-weight: bold;
}}

QPushButton[buttonType="glyph"]:hover {{
    background-color: {p.bg_hover};
    border-radius: {m.radius_small}px;
}}

QPushButton[glyphRole="add"]     {{ color: {p.success}; }}
QPushButton[glyphRole="edit"]    {{ color: {p.info}; }}
QPushButton[glyphRole="remove"]  {{ color: {p.danger}; }}
QPushButton[glyphRole="neutral"] {{ color: {p.text_secondary}; }}

QPushButton[glyphRole="add"]:hover     {{ color: {p.success_hover}; }}
QPushButton[glyphRole="edit"]:hover    {{ color: {p.info_hover}; }}
QPushButton[glyphRole="remove"]:hover  {{ color: {p.danger_hover}; }}
QPushButton[glyphRole="neutral"]:hover {{ color: {p.text_primary}; }}
"""


def _inputs(p: Palette, m: Metrics) -> str:
    down = assets.glyph_path('chevron-down', p.text_secondary)
    up = assets.glyph_path('chevron-up', p.text_secondary)

    return f"""
/* ── text fields, combo boxes, spin boxes ────────────────────────────── */

QLineEdit, QTextEdit, QPlainTextEdit, QComboBox, QSpinBox, QDoubleSpinBox {{
    background-color: {p.bg_input};
    color: {p.text_primary};
    border: {m.border_width}px solid {p.border};
    border-radius: {m.radius}px;
    padding: 2px 10px;
    min-height: {m.control_height - 4}px;
    selection-background-color: {p.bg_selection};
    selection-color: {p.text_selection};
}}

QLineEdit:hover, QTextEdit:hover, QPlainTextEdit:hover,
QComboBox:hover, QSpinBox:hover, QDoubleSpinBox:hover {{
    border-color: {p.border_strong};
}}

QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus,
QComboBox:focus, QSpinBox:focus, QDoubleSpinBox:focus {{
    border: {m.focus_width}px solid {p.border_focus};
}}

QLineEdit:disabled, QTextEdit:disabled, QPlainTextEdit:disabled,
QComboBox:disabled, QSpinBox:disabled, QDoubleSpinBox:disabled {{
    background-color: {p.bg_primary};
    color: {p.text_disabled};
}}

QLineEdit[readOnly="true"] {{
    background-color: {p.bg_primary};
    color: {p.text_secondary};
}}

QComboBox::drop-down {{
    border: none;
    width: 22px;
}}

/* A CSS-border triangle cannot be rotated into a chevron - Qt renders it as
   an L - so every arrow in the sheet is a themed asset. */
QComboBox::down-arrow {{
    image: url({down});
    width: 14px;
    height: 14px;
    margin-right: 6px;
}}

QComboBox QAbstractItemView {{
    background-color: {p.bg_menu};
    color: {p.text_primary};
    border: {m.border_width}px solid {p.border};
    border-radius: {m.radius_large}px;
    padding: 4px;
    outline: none;
    selection-background-color: {p.bg_selection};
    selection-color: {p.text_selection};
}}

QComboBox QAbstractItemView::item {{
    min-height: {m.control_height - 6}px;
    padding: 2px 8px;
    border-radius: {m.radius_small}px;
}}

QSpinBox::up-button, QDoubleSpinBox::up-button,
QSpinBox::down-button, QDoubleSpinBox::down-button {{
    subcontrol-origin: border;
    background: transparent;
    border: none;
    width: 18px;
    height: {max(10, (m.control_height - 4) // 2)}px;
}}

QSpinBox::up-button, QDoubleSpinBox::up-button {{
    subcontrol-position: top right;
    margin: 1px 4px 0 0;
}}

QSpinBox::down-button, QDoubleSpinBox::down-button {{
    subcontrol-position: bottom right;
    margin: 0 4px 1px 0;
}}

QSpinBox::up-arrow, QDoubleSpinBox::up-arrow {{
    image: url({up});
    width: 12px;
    height: 12px;
}}

QSpinBox::down-arrow, QDoubleSpinBox::down-arrow {{
    image: url({down});
    width: 12px;
    height: 12px;
}}
"""


def _views(p: Palette, m: Metrics, flavor: Flavor) -> str:
    # Adwaita's boxed lists sit on a card and separate rows with a hairline;
    # Breeze lists are a sunken view with a highlighted selection.
    boxed = flavor is Flavor.GNOME
    list_bg = p.bg_card if boxed else p.bg_input
    list_border = 'none' if boxed else f"{m.border_width}px solid {p.border}"

    return f"""
/* ── lists and scrolling ─────────────────────────────────────────────── */

QListWidget, QListView, QTreeView, QTableView {{
    background-color: {list_bg};
    color: {p.text_primary};
    border: {list_border};
    border-radius: {m.radius_card}px;
    padding: {m.spacing_tight}px;
    outline: none;
    alternate-background-color: {p.bg_alternate};
}}

QListWidget::item, QListView::item {{
    padding: 6px 8px;
    margin: 1px 0;
    border-radius: {m.radius}px;
    min-height: {m.control_height - 6}px;
}}

QListWidget::item:hover, QListView::item:hover {{
    background-color: {p.bg_hover};
}}

QListWidget::item:selected, QListView::item:selected {{
    background-color: {p.bg_selection};
    color: {p.text_selection};
}}

QListWidget::item:disabled {{
    color: {p.text_disabled};
    background: transparent;
}}

QScrollArea {{
    border: none;
    background: transparent;
}}

QScrollBar:vertical {{
    background: transparent;
    width: 12px;
    margin: 2px;
}}

QScrollBar::handle:vertical {{
    background-color: {c.mix(p.text_secondary, p.bg_primary, 0.55)};
    border-radius: 4px;
    min-height: 32px;
}}

QScrollBar::handle:vertical:hover {{
    background-color: {p.text_secondary};
}}

QScrollBar:horizontal {{
    background: transparent;
    height: 12px;
    margin: 2px;
}}

QScrollBar::handle:horizontal {{
    background-color: {c.mix(p.text_secondary, p.bg_primary, 0.55)};
    border-radius: 4px;
    min-width: 32px;
}}

QScrollBar::handle:horizontal:hover {{
    background-color: {p.text_secondary};
}}

QScrollBar::add-line, QScrollBar::sub-line {{
    background: none;
    border: none;
    width: 0;
    height: 0;
}}

QScrollBar::add-page, QScrollBar::sub-page {{
    background: none;
}}
"""


def _containers(p: Palette, m: Metrics, flavor: Flavor) -> str:
    breeze = flavor is Flavor.KDE
    # Adwaita cards carry no outline at all; Breeze frames everything.
    card_border = f"{m.border_width}px solid {p.border}" if breeze else "none"
    if breeze:
        tab_selected = f"""
QTabBar::tab:selected {{
    color: {p.text_primary};
    background-color: {p.bg_secondary};
    border-bottom: 2px solid {p.primary};
}}"""
        tab_rest = f"""
QTabBar::tab {{
    background: transparent;
    color: {p.text_secondary};
    padding: 7px 16px;
    border-bottom: 2px solid transparent;
    margin-right: 2px;
}}"""
    else:
        # Adwaita's view switcher: one rounded strip, the current view a pill.
        tab_rest = f"""
QTabBar::tab {{
    background: transparent;
    color: {p.text_secondary};
    padding: 6px 18px;
    border: none;
    border-radius: {m.radius}px;
    margin: 2px;
}}"""
        tab_selected = f"""
QTabBar::tab:selected {{
    background-color: {p.bg_tertiary};
    color: {p.text_primary};
    font-weight: 600;
}}"""

    return f"""
/* ── cards, group boxes, tabs ────────────────────────────────────────── */

QGroupBox {{
    background-color: {p.bg_card};
    border: {card_border};
    border-radius: {m.radius_card}px;
    margin-top: 14px;
    padding: {m.card_padding}px;
    font-weight: 600;
}}

/* The title sits in the margin above the frame, so it needs the window
   colour behind it or the border runs straight through the words. */
QGroupBox::title {{
    subcontrol-origin: margin;
    subcontrol-position: top left;
    left: {m.card_padding}px;
    padding: 0 6px;
    background-color: {p.bg_primary};
    color: {p.text_primary};
}}

QFrame[frameShape="4"], QFrame[frameShape="5"] {{
    background-color: {p.separator};
    border: none;
    max-height: {m.border_width}px;
}}

QWidget#card {{
    background-color: {p.bg_card};
    border: {card_border};
    border-radius: {m.radius_card}px;
}}

QTabWidget::pane {{
    background-color: {p.bg_card};
    border: {card_border};
    border-radius: {m.radius_card}px;
    padding: {m.card_padding}px;
    top: -1px;
}}

QTabBar {{
    qproperty-drawBase: 0;
}}
{tab_rest}

QTabBar::tab:hover {{
    color: {p.text_primary};
}}
{tab_selected}
"""


def _indicators(p: Palette, m: Metrics) -> str:
    tick = assets.glyph_path('check', c.readable_on(p.primary))
    dot = assets.glyph_path('dot', c.readable_on(p.primary))
    partial = assets.glyph_path('dash', c.readable_on(p.primary))
    handle = max(14, m.control_height // 2)

    return f"""
/* ── check boxes, radios, sliders ────────────────────────────────────── */

QCheckBox, QRadioButton {{
    spacing: 8px;
    background: transparent;
    color: {p.text_primary};
}}

QCheckBox::indicator, QRadioButton::indicator {{
    width: {m.indicator_size}px;
    height: {m.indicator_size}px;
    background-color: {p.bg_input};
    border: {m.border_width}px solid {p.border_strong};
}}

QCheckBox::indicator {{
    border-radius: {m.radius_small}px;
}}

QRadioButton::indicator {{
    border-radius: {m.indicator_size // 2}px;
}}

QCheckBox::indicator:hover, QRadioButton::indicator:hover {{
    border-color: {p.border_focus};
}}

QCheckBox::indicator:checked {{
    background-color: {p.primary};
    border-color: {p.primary};
    image: url({tick});
}}

QCheckBox::indicator:indeterminate {{
    background-color: {p.primary};
    border-color: {p.primary};
    image: url({partial});
}}

QRadioButton::indicator:checked {{
    background-color: {p.primary};
    border-color: {p.primary};
    image: url({dot});
}}

QCheckBox::indicator:disabled, QRadioButton::indicator:disabled {{
    background-color: {p.bg_primary};
    border-color: {p.border};
}}

QSlider::groove:horizontal {{
    height: 4px;
    background-color: {p.bg_tertiary};
    border-radius: 2px;
}}

QSlider::sub-page:horizontal {{
    background-color: {p.primary};
    border-radius: 2px;
}}

QSlider::handle:horizontal {{
    width: {handle}px;
    height: {handle}px;
    margin: -{(handle - 4) // 2}px 0;
    border-radius: {handle // 2}px;
    background-color: {p.primary};
    border: 2px solid {p.bg_primary};
}}

QSlider::handle:horizontal:hover {{
    background-color: {p.primary_hover};
}}

QSlider::handle:horizontal:disabled, QSlider::sub-page:horizontal:disabled {{
    background-color: {p.border_strong};
}}

QProgressBar {{
    background-color: {p.bg_tertiary};
    border: none;
    border-radius: 4px;
    height: 8px;
    text-align: center;
}}

QProgressBar::chunk {{
    background-color: {p.primary};
    border-radius: 4px;
}}
"""


# ── window chrome ────────────────────────────────────────────────────────────


def _chrome(p: Palette, m: Metrics) -> str:
    separator = (f"border-bottom: {m.border_width}px solid {p.separator};"
                 if m.header_separator else "")

    return f"""
/* ── header bar, status bar, toast ───────────────────────────────────── */

QWidget#headerBar {{
    background-color: {p.bg_header};
    {separator}
}}

QLabel#headerTitle {{
    font-weight: 700;
    font-size: {m.font_pt}pt;
}}

QLabel#headerSubtitle {{
    color: {p.text_secondary};
    font-size: {m.font_small_pt}pt;
}}

QPushButton#headerMenuButton {{
    min-width: {m.control_height}px;
    padding: 0;
}}

/* The button already says "menu" with its glyph; Qt's arrow doubles it. */
QPushButton#headerMenuButton::menu-indicator {{
    image: none;
    width: 0;
}}

QWidget#dialogHeader {{
    background-color: {p.bg_header};
    {separator}
}}

QLabel#dialogHeaderTitle {{
    font-weight: 700;
}}

QStatusBar {{
    background-color: {p.bg_header};
    color: {p.text_secondary};
    border-top: {m.border_width}px solid {p.separator};
}}

QStatusBar::item {{
    border: none;
}}

/* The GNOME toast: a floating pill over the content, not a chrome strip. */
QFrame#toast {{
    background-color: {p.bg_tooltip};
    border: {m.border_width}px solid {p.border};
    border-radius: {m.radius_card}px;
}}

QLabel#toastText {{
    color: {p.text_tooltip};
    font-size: {m.font_pt}pt;
    background: transparent;
}}
"""


def _application(p: Palette, m: Metrics, flavor: Flavor) -> str:
    breeze = flavor is Flavor.KDE
    # Breeze puts its toolbars on the window colour and rules them off;
    # Adwaita floats the same controls on a card.
    if breeze:
        strip = (f"background-color: {p.bg_header};\n"
                 f"    border: {m.border_width}px solid {p.border};\n"
                 f"    border-radius: {m.radius_card}px;")
    else:
        strip = (f"background-color: {p.bg_card};\n"
                 f"    border: none;\n"
                 f"    border-radius: {m.radius_card}px;")

    return f"""
/* ── application controls ────────────────────────────────────────────── */

QWidget#deviceBar {{
    {strip}
}}

QComboBox#deviceCombo {{
    min-height: {m.control_height - 8}px;
}}

QPushButton[barButton="normal"], QPushButton[barButton="primary"] {{
    padding: 0 {m.spacing_tight}px;
    min-height: 0;
}}

QPushButton[barButton="primary"] {{
    background-color: {p.primary};
    color: {p.on_primary};
    border: {m.border_width}px solid {p.primary};
    font-weight: 600;
}}

QPushButton[barButton="primary"]:hover {{
    background-color: {p.primary_hover};
    border-color: {p.primary_hover};
}}

QPushButton[barButton="primary"]:disabled {{
    background-color: {p.bg_tertiary};
    color: {p.text_disabled};
    border-color: {p.border};
}}

QLabel#connectionStatus {{
    color: {p.text_secondary};
}}

QLabel#connectionDot {{
    font-size: {m.font_pt + 2}pt;
    color: {p.text_secondary};
}}
QLabel#connectionDot[state="disconnected"] {{ color: {p.text_secondary}; }}
QLabel#connectionDot[state="connecting"]   {{ color: {p.warning}; }}
QLabel#connectionDot[state="connected"]    {{ color: {p.success}; }}
QLabel#connectionDot[state="error"]        {{ color: {p.danger}; }}

/* One card per action, all the same height. */
QWidget#actionRow {{
    background-color: {p.bg_tertiary};
    border: {m.border_width}px solid {p.border if breeze else 'transparent'};
    border-radius: {m.radius}px;
}}

QWidget#actionRow:hover {{
    border-color: {p.border_focus};
}}

QLabel#actionGrip {{
    color: {p.border_strong};
}}

QWidget#actionRow:hover QLabel#actionGrip {{
    color: {p.text_secondary};
}}

QLabel#actionIndex {{
    color: {p.text_secondary};
    font-size: {m.font_small_pt}pt;
}}

QLabel#actionsEmpty {{
    color: {p.text_secondary};
}}

/* Segmented control: one pill, one option lit. */
QWidget#segmentedControl {{
    background-color: {p.bg_tertiary};
    border: {m.border_width}px solid {p.border if breeze else 'transparent'};
    border-radius: {m.radius + 2}px;
}}

QPushButton[segment="true"] {{
    background: transparent;
    color: {p.text_secondary};
    border: none;
    border-radius: {m.radius}px;
    padding: 0 16px;
    min-height: {m.control_height - 8}px;
    font-weight: 500;
}}

QPushButton[segment="true"]:hover {{
    color: {p.text_primary};
}}

QPushButton[segment="true"]:checked {{
    background-color: {p.primary};
    color: {p.on_primary};
    font-weight: 600;
}}

/* The 3x5 grid of key screens. */
QWidget#keyGrid {{
    background-color: {p.bg_card};
    border: {m.border_width}px solid {p.border if breeze else 'transparent'};
    border-radius: {m.radius_card}px;
}}

QLabel#brightnessValue {{
    color: {p.text_secondary};
}}

/* Sidebar panels: the layout list and the window rules. */
QWidget#sidePanel {{
    background-color: {p.bg_card if breeze else p.bg_light};
    border: {m.border_width}px solid {p.border if breeze else 'transparent'};
    border-radius: {m.radius_card}px;
}}
"""
