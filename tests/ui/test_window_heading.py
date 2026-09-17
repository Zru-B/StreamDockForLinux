"""
What the window says about the open document: the title bar, and the heading
over the key grid.
"""

import os
import tempfile

import pytest

from StreamDock.application.config_document import ConfigDocument
from StreamDock.ui.main_window import APP_NAME, NO_LAYOUT_TITLE, UNTITLED, MainWindow


CONFIG = """
streamdock:
  keys:
    KeyA:
      text: "A"
      on_press_actions:
        - KEY_PRESS: "a"
  layouts:
    Main:
      Default: true
      keys:
        - 1: "KeyA"
"""


@pytest.fixture
def config_path():
    with tempfile.TemporaryDirectory() as tmpdir:
        path = os.path.join(tmpdir, "deck.yml")
        with open(path, 'w', encoding='utf-8') as handle:
            handle.write(CONFIG)
        yield path


@pytest.fixture
def window(qtbot):
    built = MainWindow()
    qtbot.addWidget(built)
    return built


class TestTitleBar:
    """"deck.yml — StreamDock", with Qt's modified marker after the name."""

    def test_a_new_document_is_untitled(self, window):
        assert window.windowTitle() == f"{UNTITLED}[*] — {APP_NAME}"
        assert not window.isWindowModified()

    def test_the_open_file_leads_the_title(self, window, config_path):
        window.load_config(config_path)

        assert window.windowTitle() == f"deck.yml[*] — {APP_NAME}"

    def test_unsaved_edits_set_the_modified_marker(self, window, config_path):
        window.load_config(config_path)

        window.mark_modified()

        assert window.isWindowModified()

    def test_saving_clears_it(self, window, config_path):
        window.load_config(config_path)
        window.mark_modified()

        window.save_config_to_file(config_path)

        assert not window.isWindowModified()


class TestGridHeading:
    """The heading over the key view names the layout and counts its keys."""

    def test_nothing_open_says_so(self, window):
        assert window.grid_title.text() == NO_LAYOUT_TITLE

    def test_the_default_layout_is_named_on_load(self, window, config_path):
        window.load_config(config_path)

        assert window.grid_title.text() == "Main"
        assert window.grid_caption.text() == "1 of 15 keys assigned"

    def test_the_count_follows_the_grid(self, window, config_path):
        window.load_config(config_path)

        window.remove_key_from_position(1, window.key_squares[0])

        assert window.grid_caption.text() == "0 of 15 keys assigned"

    def test_the_selected_layout_is_highlighted_in_the_sidebar(self, window, config_path):
        window.load_config(config_path)

        assert window.layout_list.get_selected_layout() == "Main"

    def test_a_configuration_without_layouts_clears_the_heading(self, window, config_path):
        window.load_config(config_path)

        window.config = ConfigDocument.new_empty()
        window.current_layout = None
        window.clear_key_grid()

        assert window.grid_title.text() == NO_LAYOUT_TITLE
