"""
The application stylesheet, generated from a palette and a set of metrics.

One template produces both designs. Where Breeze and Adwaita genuinely
disagree - outlined versus filled buttons, a tools area versus a header bar,
a status bar versus a toast - the difference is a branch here rather than a
second copy of nine hundred lines of QSS.

The Breeze branch follows Plasma 6: every control sits flat with a thin
outline drawn by pulling the surface towards the text colour, hovering
recolours that outline with the accent, and pressing or checking washes the
control with a translucent layer of it. Nothing is filled solid with the
accent except a selection.
"""

from StreamDock.ui.theme import assets
from StreamDock.ui.theme import color as c
from StreamDock.ui.theme.detection import Flavor
from StreamDock.ui.theme.metrics import Metrics
from StreamDock.ui.theme.palette import Palette

# How strongly Breeze washes a control with the accent.
_PRESSED_ALPHA = 0.33      # pressed or checked
_HOVER_ROW_ALPHA = 0.2     # a hovered row in a list
_DEFAULT_MIX = 0.15        # the default button in a dialog
_PENDING_ALPHA = 0.2       # an Apply button with changes waiting


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
        _base(palette, metrics, flavor),
        _menus(palette, metrics, flavor),
        _toolbars(palette, metrics, flavor),
        _buttons(palette, metrics, flavor),
        _inputs(palette, metrics, flavor),
        _views(palette, metrics, flavor),
        _containers(palette, metrics, flavor),
        _indicators(palette, metrics, flavor),
        _chrome(palette, metrics, flavor),
        _application(palette, metrics, flavor),
    )
    return "\n".join(sections)


# ── foundations ──────────────────────────────────────────────────────────────


def _base(p: Palette, m: Metrics, flavor: Flavor) -> str:
    breeze = flavor is Flavor.KDE
    # Plasma tooltips are set in the body size; Adwaita's are a step smaller.
    tooltip_pt = m.font_pt if breeze else m.font_small_pt
    tooltip_radius = m.radius_large if breeze else m.radius

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
    font-weight: {700 if breeze else 600};
}}

QLabel[textRole="caption"] {{
    color: {p.text_secondary};
    font-size: {m.font_small_pt}pt;
}}

QToolTip {{
    background-color: {p.bg_tooltip};
    color: {p.text_tooltip};
    border: {m.border_width}px solid {p.border};
    border-radius: {tooltip_radius}px;
    padding: 6px 10px;
    font-size: {tooltip_pt}pt;
}}
"""


def _menus(p: Palette, m: Metrics, flavor: Flavor) -> str:
    breeze = flavor is Flavor.KDE
    # Breeze highlights a menu entry with the selection colour; an Adwaita
    # popover only tints it, keeping the accent for the action that matters.
    item_selected_bg = p.bg_selection if breeze else p.bg_hover
    item_selected_fg = p.text_selection if breeze else p.text_primary
    chevron = assets.glyph_path('chevron-right', p.text_secondary)
    chevron_selected = assets.glyph_path('chevron-right', item_selected_fg)

    if breeze:
        # The menu bar is part of the tools area: it shares the header colour
        # and dims with the window, and the rule under the strip belongs to
        # the toolbar beneath it.
        menubar = f"""
QMenuBar {{
    background-color: {p.bg_header};
    color: {p.text_primary};
    padding: 2px 4px;
    border: none;
}}

QMenuBar[windowActive="false"] {{
    background-color: {p.bg_header_inactive};
}}

QMenuBar::item {{
    background: transparent;
    padding: 4px 8px;
    border-radius: {m.radius}px;
}}

QMenuBar::item:selected {{
    background-color: {p.bg_selection};
    color: {p.text_selection};
}}

QMenuBar::item:pressed {{
    background-color: {p.bg_selection};
    color: {p.text_selection};
}}"""
        # Breeze reserves an icon column in every menu, so entries line up
        # whether or not the one above carries a picture.
        item_padding = (f"{m.menu_item_padding}px 24px "
                        f"{m.menu_item_padding}px 8px")
        indicators = f"""

QMenu::icon {{
    margin-left: 4px;
}}

QMenu::indicator {{
    width: {m.icon_size_small}px;
    height: {m.icon_size_small}px;
    margin-left: 4px;
}}

QMenu::indicator:non-exclusive:checked {{
    image: url({assets.glyph_path('check', p.primary)});
}}

QMenu::indicator:non-exclusive:checked:selected {{
    image: url({assets.glyph_path('check', p.text_selection)});
}}

QMenu::indicator:exclusive:checked {{
    image: url({assets.glyph_path('dot', p.primary)});
}}

QMenu::indicator:exclusive:checked:selected {{
    image: url({assets.glyph_path('dot', p.text_selection)});
}}
"""
    else:
        separator = (f"border-bottom: {m.border_width}px solid {p.separator};"
                     if m.header_separator else "border: none;")
        menubar = f"""
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
}}"""
        item_padding = (f"{m.menu_item_padding}px 28px "
                        f"{m.menu_item_padding}px 14px")
        indicators = """

QMenu::icon {
    margin-left: 8px;
}
"""

    return f"""
/* ── menus ───────────────────────────────────────────────────────────── */
{menubar}

QMenu {{
    background-color: {p.bg_menu};
    color: {p.text_primary};
    border: {m.border_width}px solid {p.border};
    border-radius: {m.radius_large}px;
    padding: {m.spacing_tight}px;
}}

QMenu::item {{
    padding: {item_padding};
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

QMenu::right-arrow:selected {{
    image: url({chevron_selected});
}}
{indicators}"""


def _toolbars(p: Palette, m: Metrics, flavor: Flavor) -> str:
    breeze = flavor is Flavor.KDE
    if breeze:
        strip = f"""
QToolBar {{
    background-color: {p.bg_header};
    border: none;
    border-bottom: {m.border_width}px solid {p.separator};
    padding: 3px 4px;
    spacing: 2px;
}}

QToolBar[windowActive="false"] {{
    background-color: {p.bg_header_inactive};
}}

QToolBar::separator {{
    width: {m.border_width}px;
    background-color: {p.separator};
    margin: 6px 4px;
}}
"""
        hover = f"border-color: {p.border_focus};"
        pressed = (f"background-color: {c.rgba(p.primary, _PRESSED_ALPHA)};\n"
                   f"    border-color: {p.border_focus};")
    else:
        strip = f"""
QToolBar {{
    background-color: {p.bg_header};
    border: none;
    padding: 4px 6px;
    spacing: 4px;
}}
"""
        hover = f"background-color: {p.bg_hover};"
        pressed = f"background-color: {p.bg_pressed};"

    return f"""
/* ── toolbars ────────────────────────────────────────────────────────── */
{strip}
/* Tool buttons sit flat until the pointer reaches them. */
QToolButton {{
    background: transparent;
    color: {p.text_primary};
    border: {m.border_width}px solid transparent;
    border-radius: {m.radius}px;
    padding: 4px 6px;
}}

QToolButton:hover {{
    {hover}
}}

QToolButton:pressed, QToolButton:checked, QToolButton:open {{
    {pressed}
}}

QToolButton:disabled {{
    color: {p.text_disabled};
}}

/* A button that only opens a menu says so with its own glyph. */
QToolButton::menu-indicator {{
    image: none;
    width: 0;
}}
"""


# ── controls ─────────────────────────────────────────────────────────────────


def _buttons(p: Palette, m: Metrics, flavor: Flavor) -> str:
    breeze = flavor is Flavor.KDE

    if breeze:
        return _breeze_buttons(p, m)

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


def _breeze_buttons(p: Palette, m: Metrics) -> str:
    """
    Plasma 6 buttons: outlined, flat, and never solid accent.

    The button that leads a dialog is the default button, and Breeze marks
    it the way it marks a pressed one, only fainter: a wash of the accent
    behind the label and the accent on the outline.
    """
    disabled_bg = c.mix(p.bg_tertiary, p.bg_primary, 0.5)
    disabled_border = c.mix(p.border, p.bg_primary, 0.5)
    default_bg = c.mix(p.bg_tertiary, p.primary, _DEFAULT_MIX)
    default_hover_bg = c.mix(p.bg_tertiary, p.primary, _DEFAULT_MIX + 0.1)

    def semantic(name: str, colour: str) -> str:
        return f"""
QPushButton[buttonType="{name}"]:hover, QPushButton[buttonType="{name}"]:focus {{
    border-color: {colour};
}}

QPushButton[buttonType="{name}"]:pressed {{
    background-color: {c.mix(p.bg_tertiary, colour, _PRESSED_ALPHA)};
    border-color: {colour};
}}"""

    return f"""
/* ── buttons ─────────────────────────────────────────────────────────── */

QPushButton {{
    background-color: {p.bg_tertiary};
    color: {p.text_primary};
    border: {m.border_width}px solid {p.border};
    border-radius: {m.radius}px;
    padding: 0 {m.button_padding}px;
    min-height: {m.control_height - 2 * m.border_width}px;
}}

QPushButton:hover, QPushButton:focus {{
    border-color: {p.border_focus};
}}

QPushButton:pressed, QPushButton:checked {{
    background-color: {p.bg_pressed};
    border-color: {p.border_focus};
}}

QPushButton:disabled {{
    background-color: {disabled_bg};
    color: {p.text_disabled};
    border-color: {disabled_border};
}}

QPushButton:default, QPushButton[buttonType="primary"] {{
    background-color: {default_bg};
    border-color: {p.border_focus};
}}

QPushButton:default:hover, QPushButton[buttonType="primary"]:hover {{
    background-color: {default_hover_bg};
}}

QPushButton:default:pressed, QPushButton[buttonType="primary"]:pressed {{
    background-color: {p.bg_pressed};
}}

QPushButton:default:disabled, QPushButton[buttonType="primary"]:disabled {{
    background-color: {disabled_bg};
    border-color: {disabled_border};
}}

QPushButton:flat {{
    background: transparent;
    border-color: transparent;
}}

QPushButton:flat:hover {{
    border-color: {p.border_focus};
}}
{semantic("success", p.success)}
{semantic("danger", p.danger)}

/* Borderless glyph buttons: the add, edit and remove affordances on rows.
   They behave like tool buttons - an outline on hover, a wash when held. */
QPushButton[buttonType="glyph"] {{
    background: transparent;
    border: {m.border_width}px solid transparent;
    border-radius: {m.radius}px;
    padding: 0;
    min-height: 0;
    font-weight: bold;
}}

QPushButton[buttonType="glyph"]:hover {{
    border-color: {p.border_focus};
}}

QPushButton[buttonType="glyph"]:pressed {{
    background-color: {c.rgba(p.primary, _PRESSED_ALPHA)};
    border-color: {p.border_focus};
}}

QPushButton[glyphRole="add"]     {{ color: {p.success}; }}
QPushButton[glyphRole="edit"]    {{ color: {p.info}; }}
QPushButton[glyphRole="remove"]  {{ color: {p.danger}; }}
QPushButton[glyphRole="neutral"] {{ color: {p.text_secondary}; }}
"""


def _inputs(p: Palette, m: Metrics, flavor: Flavor) -> str:
    breeze = flavor is Flavor.KDE
    arrow_colour = p.text_primary if breeze else p.text_secondary
    down = assets.glyph_path('chevron-down', arrow_colour)
    up = assets.glyph_path('chevron-up', arrow_colour)
    popup_radius = 0 if breeze else m.radius_large

    if breeze:
        # A Breeze combo box is a button with a chevron, not a text field.
        combo = f"""
QComboBox {{
    background-color: {p.bg_tertiary};
    color: {p.text_primary};
    border: {m.border_width}px solid {p.border};
    border-radius: {m.radius}px;
    padding: 0 4px 0 8px;
    min-height: {m.control_height - 2 * m.border_width}px;
}}

QComboBox:hover, QComboBox:focus {{
    border-color: {p.border_focus};
}}

QComboBox:on {{
    background-color: {p.bg_pressed};
    border-color: {p.border_focus};
}}

QComboBox:disabled {{
    background-color: {c.mix(p.bg_tertiary, p.bg_primary, 0.5)};
    color: {p.text_disabled};
    border-color: {c.mix(p.border, p.bg_primary, 0.5)};
}}
"""
        fields = "QLineEdit, QTextEdit, QPlainTextEdit, QSpinBox, QDoubleSpinBox"
        field_height = m.control_height - 2 * m.border_width - 4
        focus = f"border-color: {p.border_focus};"
        hover = f"border-color: {p.border_focus};"
        disabled_bg = p.bg_primary
    else:
        combo = ""
        fields = ("QLineEdit, QTextEdit, QPlainTextEdit, QComboBox, "
                  "QSpinBox, QDoubleSpinBox")
        field_height = m.control_height - 4
        focus = f"border: {m.focus_width}px solid {p.border_focus};"
        hover = f"border-color: {p.border_strong};"
        disabled_bg = p.bg_primary

    return f"""
/* ── text fields, combo boxes, spin boxes ────────────────────────────── */

{fields} {{
    background-color: {p.bg_input};
    color: {p.text_primary};
    border: {m.border_width}px solid {p.border};
    border-radius: {m.radius}px;
    padding: 2px {6 if breeze else 10}px;
    min-height: {field_height}px;
    selection-background-color: {p.bg_selection};
    selection-color: {p.text_selection};
}}

{', '.join(f'{name}:hover' for name in fields.split(', '))} {{
    {hover}
}}

{', '.join(f'{name}:focus' for name in fields.split(', '))} {{
    {focus}
}}

{', '.join(f'{name}:disabled' for name in fields.split(', '))} {{
    background-color: {disabled_bg};
    color: {p.text_disabled};
}}

QLineEdit[readOnly="true"] {{
    background-color: {p.bg_primary};
    color: {p.text_secondary};
}}
{combo}
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

QComboBox::down-arrow:disabled {{
    image: url({assets.glyph_path('chevron-down', p.text_disabled)});
}}

QComboBox QAbstractItemView {{
    background-color: {p.bg_menu};
    color: {p.text_primary};
    border: {m.border_width}px solid {p.border};
    border-radius: {popup_radius}px;
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
    breeze = flavor is Flavor.KDE
    # Adwaita's boxed lists sit on a card and separate rows with a hairline;
    # Breeze lists are a framed view with a highlighted selection.
    boxed = flavor is Flavor.GNOME
    list_bg = p.bg_card if boxed else p.bg_input
    list_border = 'none' if boxed else f"{m.border_width}px solid {p.border}"
    row_hover = c.rgba(p.primary, _HOVER_ROW_ALPHA) if breeze else p.bg_hover
    row_padding = "4px 6px" if breeze else "6px 8px"
    row_margin = "0" if breeze else "1px 0"
    list_padding = 2 if breeze else m.spacing_tight

    if breeze:
        # Plasma's scroll bars are a thin translucent slider that widens and
        # takes the accent under the pointer, with no arrow buttons.
        handle = c.mix(p.bg_primary, p.text_primary, 0.4)
        scrollbars = f"""
QScrollBar:vertical {{
    background: transparent;
    width: 12px;
    margin: 0;
}}

QScrollBar::handle:vertical {{
    background-color: {handle};
    border-radius: 3px;
    min-height: 24px;
    margin: 2px 3px;
}}

QScrollBar::handle:vertical:hover, QScrollBar::handle:vertical:pressed {{
    background-color: {p.primary};
    margin: 2px 2px;
    border-radius: 4px;
}}

QScrollBar:horizontal {{
    background: transparent;
    height: 12px;
    margin: 0;
}}

QScrollBar::handle:horizontal {{
    background-color: {handle};
    border-radius: 3px;
    min-width: 24px;
    margin: 3px 2px;
}}

QScrollBar::handle:horizontal:hover, QScrollBar::handle:horizontal:pressed {{
    background-color: {p.primary};
    margin: 2px 2px;
    border-radius: 4px;
}}
"""
        sidebar_list = f"""

/* Sidebar lists sit straight on the window, the way Dolphin's Places do. */
QListWidget#sidebarList {{
    background: transparent;
    border: none;
    padding: 0;
}}

QListWidget#sidebarList::item {{
    padding: 4px 8px;
    min-height: {m.list_row_height - 8}px;
}}
"""
    else:
        handle = c.mix(p.text_secondary, p.bg_primary, 0.55)
        scrollbars = f"""
QScrollBar:vertical {{
    background: transparent;
    width: 12px;
    margin: 2px;
}}

QScrollBar::handle:vertical {{
    background-color: {handle};
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
    background-color: {handle};
    border-radius: 4px;
    min-width: 32px;
}}

QScrollBar::handle:horizontal:hover {{
    background-color: {p.text_secondary};
}}
"""
        sidebar_list = """

QListWidget#sidebarList {
    background: transparent;
    border: none;
}
"""

    return f"""
/* ── lists and scrolling ─────────────────────────────────────────────── */

QListWidget, QListView, QTreeView, QTableView {{
    background-color: {list_bg};
    color: {p.text_primary};
    border: {list_border};
    border-radius: {m.radius_card}px;
    padding: {list_padding}px;
    outline: none;
    alternate-background-color: {p.bg_alternate};
}}

QListWidget::item, QListView::item {{
    padding: {row_padding};
    margin: {row_margin};
    border-radius: {m.radius}px;
    min-height: {m.control_height - 6}px;
}}

QListWidget::item:hover, QListView::item:hover {{
    background-color: {row_hover};
}}

QListWidget::item:selected, QListView::item:selected {{
    background-color: {p.bg_selection};
    color: {p.text_selection};
}}

QListWidget::item:disabled {{
    color: {p.text_disabled};
    background: transparent;
}}
{sidebar_list}
QScrollArea {{
    border: none;
    background: transparent;
}}
{scrollbars}
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
        # Plasma 6 tabs: the current one is a raised tab joined to the frame
        # beneath it, the rest are plain labels that gain an outline on hover.
        tabs = f"""
QTabBar::tab {{
    background: transparent;
    color: {p.text_secondary};
    padding: 6px 14px;
    border: {m.border_width}px solid transparent;
    border-bottom: none;
    border-top-left-radius: {m.radius}px;
    border-top-right-radius: {m.radius}px;
    margin-right: 2px;
    margin-top: 2px;
}}

QTabBar::tab:hover {{
    color: {p.text_primary};
    border-color: {p.border_focus};
}}

QTabBar::tab:selected {{
    background-color: {p.bg_card};
    color: {p.text_primary};
    border-color: {p.border};
    border-bottom: {m.border_width}px solid {p.bg_card};
    margin-top: 0;
    margin-bottom: -{m.border_width}px;
}}"""
        group_bg = p.bg_card
        group_weight = "font-weight: 600;"
    else:
        # Adwaita's view switcher: one rounded strip, the current view a pill.
        tabs = f"""
QTabBar::tab {{
    background: transparent;
    color: {p.text_secondary};
    padding: 6px 18px;
    border: none;
    border-radius: {m.radius}px;
    margin: 2px;
}}

QTabBar::tab:hover {{
    color: {p.text_primary};
}}

QTabBar::tab:selected {{
    background-color: {p.bg_tertiary};
    color: {p.text_primary};
    font-weight: 600;
}}"""
        group_bg = p.bg_card
        group_weight = "font-weight: 600;"

    return f"""
/* ── cards, group boxes, tabs ────────────────────────────────────────── */

QGroupBox {{
    background-color: {group_bg};
    border: {card_border};
    border-radius: {m.radius_card}px;
    margin-top: 14px;
    padding: {m.card_padding}px;
    {group_weight}
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

QFrame[frameShape="4"] {{
    background-color: {p.separator};
    border: none;
    max-height: {m.border_width}px;
}}

QFrame[frameShape="5"] {{
    background-color: {p.separator};
    border: none;
    max-width: {m.border_width}px;
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
{tabs}
"""


def _indicators(p: Palette, m: Metrics, flavor: Flavor) -> str:
    breeze = flavor is Flavor.KDE
    tick = assets.glyph_path('check', c.readable_on(p.primary))
    dot = assets.glyph_path('dot', c.readable_on(p.primary))
    partial = assets.glyph_path('dash', c.readable_on(p.primary))

    if breeze:
        # An unchecked Breeze box is an outline on nothing; checking it fills
        # it with the accent. The slider handle is a plain outlined disc on a
        # thin groove, and the groove fills with the accent up to it.
        groove_height = 6
        handle = 18
        groove_bg = c.mix(p.bg_primary, p.text_primary, 0.25)
        return f"""
/* ── check boxes, radios, sliders ────────────────────────────────────── */

QCheckBox, QRadioButton {{
    spacing: 6px;
    background: transparent;
    color: {p.text_primary};
}}

QCheckBox::indicator, QRadioButton::indicator {{
    width: {m.indicator_size - 2}px;
    height: {m.indicator_size - 2}px;
    background-color: transparent;
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
    background-color: transparent;
    border-color: {c.mix(p.border_strong, p.bg_primary, 0.5)};
}}

QCheckBox::indicator:checked:disabled, QRadioButton::indicator:checked:disabled {{
    background-color: {p.text_disabled};
    border-color: {p.text_disabled};
}}

QSlider::groove:horizontal {{
    height: {groove_height}px;
    background-color: {groove_bg};
    border-radius: {groove_height // 2}px;
}}

QSlider::sub-page:horizontal {{
    background-color: {p.primary};
    border-radius: {groove_height // 2}px;
}}

QSlider::handle:horizontal {{
    width: {handle}px;
    height: {handle}px;
    margin: -{(handle + 2 * m.border_width - groove_height) // 2}px 0;
    border-radius: {(handle + 2 * m.border_width) // 2}px;
    background-color: {p.bg_tertiary};
    border: {m.border_width}px solid {p.border_strong};
}}

QSlider::handle:horizontal:hover, QSlider::handle:horizontal:focus {{
    border-color: {p.border_focus};
}}

QSlider::handle:horizontal:pressed {{
    background-color: {p.bg_pressed};
    border-color: {p.border_focus};
}}

QSlider::handle:horizontal:disabled {{
    background-color: {p.bg_primary};
    border-color: {c.mix(p.border_strong, p.bg_primary, 0.5)};
}}

QSlider::sub-page:horizontal:disabled {{
    background-color: {p.text_disabled};
}}

QProgressBar {{
    background-color: {groove_bg};
    border: none;
    border-radius: 3px;
    height: 6px;
    text-align: center;
}}

QProgressBar::chunk {{
    background-color: {p.primary};
    border-radius: 3px;
}}
"""

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


def _chrome(p: Palette, m: Metrics, flavor: Flavor) -> str:
    breeze = flavor is Flavor.KDE
    separator = (f"border-bottom: {m.border_width}px solid {p.separator};"
                 if m.header_separator else "")
    status_fg = p.text_primary if breeze else p.text_secondary

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
    background-color: {p.bg_primary if breeze else p.bg_header};
    color: {status_fg};
    border-top: {m.border_width}px solid {p.separator};
}}

QStatusBar::item {{
    border: none;
}}

QLabel#statusDocument {{
    color: {p.text_secondary};
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

    if breeze:
        return _breeze_application(p, m)

    # Adwaita floats the device controls on a card.
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
    border: {m.border_width}px solid transparent;
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
    border: {m.border_width}px solid transparent;
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
    border: {m.border_width}px solid transparent;
    border-radius: {m.radius_card}px;
}}

QLabel#gridCaption {{
    color: {p.text_secondary};
    font-size: {m.font_small_pt}pt;
}}

QLabel#brightnessValue {{
    color: {p.text_secondary};
}}

/* Sidebar panels: the layout list and the window rules. */
QWidget#sidebar {{
    background: transparent;
    border: none;
}}

QWidget#sidePanel {{
    background-color: {p.bg_light};
    border: {m.border_width}px solid transparent;
    border-radius: {m.radius_card}px;
}}

QLabel#sidebarHeading {{
    font-size: {m.heading_pt}pt;
    font-weight: 600;
}}

QFrame#sidebarRule {{
    background: transparent;
    max-height: 0;
}}

/* The device settings, a card with its heading inside. */
QWidget#settingsPanel {{
    background-color: {p.bg_card};
    border: none;
    border-radius: {m.radius_card}px;
}}
"""


def _breeze_application(p: Palette, m: Metrics) -> str:
    """
    The Plasma arrangement: a tools area, a sidebar, and one framed view.

    The device controls live in the toolbar, so they dress as tool buttons.
    Apply is the one exception: while there are changes to send it carries
    the neutral highlight Plasma puts on an Apply button with work waiting.
    """
    return f"""
/* ── application controls ────────────────────────────────────────────── */

/* Hosted in the toolbar, so it paints nothing of its own. */
QWidget#deviceBar {{
    background: transparent;
    border: none;
}}

QComboBox#deviceCombo {{
    min-height: {m.control_height - 4 - 2 * m.border_width}px;
}}

QPushButton[barButton="normal"], QPushButton[barButton="primary"] {{
    background: transparent;
    color: {p.text_primary};
    border: {m.border_width}px solid transparent;
    border-radius: {m.radius}px;
    padding: 0 8px;
    min-height: {m.control_height - 4 - 2 * m.border_width}px;
}}

QPushButton[barButton="normal"]:hover, QPushButton[barButton="normal"]:focus {{
    border-color: {p.border_focus};
}}

QPushButton[barButton="normal"]:pressed {{
    background-color: {c.rgba(p.primary, _PRESSED_ALPHA)};
    border-color: {p.border_focus};
}}

QPushButton[barButton="normal"]:disabled,
QPushButton[barButton="primary"]:disabled {{
    background: transparent;
    color: {p.text_disabled};
    border-color: transparent;
}}

QPushButton[barButton="primary"]:enabled {{
    background-color: {c.rgba(p.warning, _PENDING_ALPHA)};
    border-color: {p.warning};
}}

QPushButton[barButton="primary"]:enabled:hover,
QPushButton[barButton="primary"]:enabled:focus {{
    background-color: {c.rgba(p.warning, _PENDING_ALPHA + 0.1)};
}}

QPushButton[barButton="primary"]:enabled:pressed {{
    background-color: {c.rgba(p.warning, _PRESSED_ALPHA + 0.1)};
}}

QLabel#connectionStatus {{
    color: {p.text_primary};
}}

QLabel#connectionDot {{
    font-size: {m.font_pt + 1}pt;
    color: {p.text_secondary};
}}
QLabel#connectionDot[state="disconnected"] {{ color: {p.text_secondary}; }}
QLabel#connectionDot[state="connecting"]   {{ color: {p.warning}; }}
QLabel#connectionDot[state="connected"]    {{ color: {p.success}; }}
QLabel#connectionDot[state="error"]        {{ color: {p.danger}; }}

/* One framed row per action, all the same height. */
QWidget#actionRow {{
    background-color: {p.bg_card};
    border: {m.border_width}px solid {p.border};
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

/* A short choice, drawn as a row of buttons with one held down - the way
   Dolphin offers its view modes. */
QWidget#segmentedControl {{
    background: transparent;
    border: none;
}}

QPushButton[segment="true"] {{
    background-color: {p.bg_tertiary};
    color: {p.text_primary};
    border: {m.border_width}px solid {p.border};
    border-radius: {m.radius}px;
    padding: 0 14px;
    min-height: {m.control_height - 6 - 2 * m.border_width}px;
}}

QPushButton[segment="true"]:hover {{
    border-color: {p.border_focus};
}}

QPushButton[segment="true"]:checked {{
    background-color: {p.bg_pressed};
    border-color: {p.border_focus};
}}

/* The 3x5 grid of key screens sits in a view, like Dolphin's files. */
QWidget#keyGrid {{
    background-color: {p.bg_input};
    border: {m.border_width}px solid {p.border};
    border-radius: {m.radius_card}px;
}}

QLabel#gridCaption {{
    color: {p.text_secondary};
    font-size: {m.font_small_pt}pt;
}}

QLabel#brightnessValue {{
    color: {p.text_secondary};
}}

/* The sidebar: one column on the window colour, ruled off from the view. */
QWidget#sidebar {{
    background-color: {p.bg_primary};
    border: none;
    border-right: {m.border_width}px solid {p.separator};
}}

QWidget#sidePanel {{
    background: transparent;
    border: none;
}}

QLabel#sidebarHeading {{
    color: {p.text_secondary};
    font-weight: 600;
}}

QFrame#sidebarRule {{
    background-color: {p.separator};
    border: none;
    max-height: {m.border_width}px;
}}

/* Device settings sit straight on the window as a form. */
QWidget#settingsPanel {{
    background: transparent;
    border: none;
}}
"""
