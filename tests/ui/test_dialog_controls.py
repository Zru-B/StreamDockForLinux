"""
The controls the key and layout editors are built from.

The switch and the segmented control replaced a checkbox and a pair of radio
buttons; what matters is that they still carry the same values in and out.
"""

import pytest

from StreamDock.application.config_document import KeyDefinition
from StreamDock.ui.dialogs import (
    DISPLAY_ICON,
    DISPLAY_TEXT,
    KeyEditorDialog,
    LayoutEditorDialog,
)
from StreamDock.ui.widgets import SegmentedControl


@pytest.fixture
def segments(qtbot):
    control = SegmentedControl(["One", "Two", "Three"])
    qtbot.addWidget(control)
    return control


@pytest.fixture
def text_key():
    key_def = KeyDefinition("Volume")
    key_def.text = "Vol+"
    key_def.bold = False
    return key_def


def open_key_editor(qtbot, key_def=None):
    dialog = KeyEditorDialog(key_def)
    qtbot.addWidget(dialog)
    return dialog


class TestSegmentedControl:
    """One pill, one option lit."""

    def test_it_starts_on_the_first_option(self, segments):
        assert segments.current() == "One"

    def test_choosing_an_option_reports_it_once(self, segments, qtbot):
        with qtbot.waitSignal(segments.selection_changed) as chosen:
            segments.set_current("Three")

        assert chosen.args == ["Three"]
        assert segments.current() == "Three"

    def test_an_unknown_option_leaves_the_selection_alone(self, segments):
        segments.set_current("Four")

        assert segments.current() == "One"

    def test_only_one_option_is_ever_selected(self, segments):
        segments.set_current("Two")
        segments.set_current("Three")

        assert segments.current() == "Three"


class TestKeyEditorDisplayType:
    """The segmented control drives which half of the form is shown."""

    def test_a_new_key_starts_on_icon(self, qtbot):
        dialog = open_key_editor(qtbot)

        assert dialog.display_type.current() == DISPLAY_ICON
        assert not dialog.icon_widget.isHidden()
        assert dialog.text_widget.isHidden()

    def test_a_text_key_opens_on_text(self, qtbot, text_key):
        dialog = open_key_editor(qtbot, text_key)

        assert dialog.display_type.current() == DISPLAY_TEXT
        assert dialog.icon_widget.isHidden()
        assert not dialog.text_widget.isHidden()

    def test_switching_to_text_swaps_the_panels(self, qtbot):
        dialog = open_key_editor(qtbot)

        dialog.display_type.set_current(DISPLAY_TEXT)

        assert dialog.icon_widget.isHidden()
        assert not dialog.text_widget.isHidden()

    def test_the_chosen_type_decides_what_is_saved(self, qtbot, text_key):
        dialog = open_key_editor(qtbot, text_key)
        dialog.display_type.set_current(DISPLAY_ICON)

        key_def = dialog.get_key_definition()

        assert key_def.text is None


class TestKeyEditorBoldSwitch:
    """Bold is a switch now; it must still round-trip."""

    def test_it_loads_the_keys_value(self, qtbot, text_key):
        dialog = open_key_editor(qtbot, text_key)

        assert dialog.bold_toggle.isChecked() is False

    def test_it_reaches_the_saved_key(self, qtbot, text_key):
        dialog = open_key_editor(qtbot, text_key)

        dialog.bold_toggle.setChecked(True)

        assert dialog.get_key_definition().bold is True


class TestLayoutEditorClearAll:
    """The layout editor's checkbox is a switch now."""

    def test_it_opens_on_the_layouts_value(self, qtbot):
        dialog = LayoutEditorDialog("Main", clear_all=True)
        qtbot.addWidget(dialog)

        assert dialog.clear_all_toggle.isChecked()

    def test_it_reaches_the_layout_data(self, qtbot):
        dialog = LayoutEditorDialog("Main", clear_all=False)
        qtbot.addWidget(dialog)

        dialog.clear_all_toggle.setChecked(True)

        assert dialog.get_layout_data()['clear_all'] is True
