"""
Unit tests for ConfigDocument.

The editor writes the user's configuration file. These tests pin down the one
guarantee that matters: saving must not lose or silently change anything.
"""

import os
import tempfile

import pytest
import yaml

from StreamDock.application.config_document import (
    DEFAULT_BRIGHTNESS,
    ConfigDocument,
    KeyDefinition,
    Layout,
    WindowRule,
)
from StreamDock.application.configuration_manager import ConfigValidationError


@pytest.fixture
def workdir():
    """Temporary directory to load and save configs in."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield tmpdir


@pytest.fixture
def icon(workdir):
    """A real icon file inside the config directory."""
    path = os.path.join(workdir, "icon.png")
    with open(path, "wb") as f:
        f.write(b"\x89PNG\r\n\x1a\n")
    return path


def write_config(workdir, streamdock, name="config.yml"):
    """Write a 'streamdock' subtree to a YAML file and return its path."""
    path = os.path.join(workdir, name)
    with open(path, 'w') as f:
        yaml.dump({'streamdock': streamdock}, f, sort_keys=False)
    return path


def reload(workdir, streamdock):
    """Round-trip a subtree through load -> save -> YAML and return the result."""
    path = write_config(workdir, streamdock)
    ConfigDocument.load(path).save()
    with open(path) as f:
        return yaml.safe_load(f)['streamdock']


BASE = {
    'settings': {'brightness': 30},
    'keys': {'Key1': {'text': 'A', 'on_press_actions': [{'KEY_PRESS': 'a'}]}},
    'layouts': {'Main': {'Default': True, 'keys': [{1: 'Key1'}]}},
}


class TestRoundTrip:
    """Load -> save must preserve everything."""

    def test_preserves_a_plain_config(self, workdir):
        assert reload(workdir, BASE)['keys']['Key1']['text'] == 'A'

    def test_preserves_unknown_root_sections(self, workdir):
        source = dict(BASE, future_section={'anything': [1, 2]})
        assert reload(workdir, source)['future_section'] == {'anything': [1, 2]}

    def test_preserves_unknown_key_fields(self, workdir):
        source = {**BASE, 'keys': {'Key1': {**BASE['keys']['Key1'], 'wat': 7}}}
        assert reload(workdir, source)['keys']['Key1']['wat'] == 7

    def test_preserves_unknown_layout_fields(self, workdir):
        source = {**BASE, 'layouts': {'Main': {**BASE['layouts']['Main'], 'wat': 7}}}
        assert reload(workdir, source)['layouts']['Main']['wat'] == 7

    def test_preserves_unknown_settings(self, workdir):
        source = {**BASE, 'settings': {'brightness': 30, 'wat': 7}}
        assert reload(workdir, source)['settings']['wat'] == 7

    def test_preserves_lock_verification_delay(self, workdir):
        """The old editor model had no field for this and dropped it."""
        source = {**BASE, 'settings': {'brightness': 30, 'lock_verification_delay': 5.5}}
        assert reload(workdir, source)['settings']['lock_verification_delay'] == 5.5

    def test_preserves_window_rule_priority(self, workdir):
        """Application reads priority; the old editor model dropped it."""
        source = dict(BASE, windows_rules={
            'R': {'window_name': 'firefox', 'layout': 'Main', 'priority': 10}})
        assert reload(workdir, source)['windows_rules']['R']['priority'] == 10

    def test_preserves_window_name_as_a_list(self, workdir):
        """The old editor model collapsed a list of patterns to a string."""
        source = dict(BASE, windows_rules={
            'R': {'window_name': ['firefox', 'chromium'], 'layout': 'Main'}})
        assert reload(workdir, source)['windows_rules']['R']['window_name'] == \
            ['firefox', 'chromium']

    def test_preserves_is_regex(self, workdir):
        """Not offered in the UI, but must survive a save."""
        source = dict(BASE, windows_rules={
            'R': {'window_name': '^fire', 'layout': 'Main', 'is_regex': True}})
        assert reload(workdir, source)['windows_rules']['R']['is_regex'] is True

    def test_preserves_relative_icon_paths(self, workdir, icon):
        """Saving must not absolutise what the user wrote."""
        source = {**BASE, 'keys': {'Key1': {
            'icon': 'icon.png', 'on_press_actions': [{'KEY_PRESS': 'a'}]}}}
        assert reload(workdir, source)['keys']['Key1']['icon'] == 'icon.png'

    def test_preserves_text_position(self, workdir):
        source = {**BASE, 'keys': {'Key1': {
            'text': 'A', 'text_position': 'top',
            'on_press_actions': [{'KEY_PRESS': 'a'}]}}}
        assert reload(workdir, source)['keys']['Key1']['text_position'] == 'top'

    def test_preserves_all_three_action_lists(self, workdir):
        source = {**BASE, 'keys': {'Key1': {
            'text': 'A',
            'on_press_actions': [{'KEY_PRESS': 'a'}],
            'on_release_actions': [{'KEY_PRESS': 'b'}],
            'on_double_press_actions': [{'KEY_PRESS': 'c'}]}}}
        key = reload(workdir, source)['keys']['Key1']
        assert key['on_release_actions'] == [{'KEY_PRESS': 'b'}]
        assert key['on_double_press_actions'] == [{'KEY_PRESS': 'c'}]

    def test_preserves_layout_key_positions(self, workdir):
        source = {**BASE, 'layouts': {'Main': {
            'Default': True, 'keys': [{3: 'Key1'}, {1: 'Key1'}]}}}
        assert reload(workdir, source)['layouts']['Main']['keys'] == \
            [{1: 'Key1'}, {3: 'Key1'}]

    def test_default_styling_is_not_written_unless_it_was_there(self, workdir):
        """Opening and saving must not churn the file with implicit defaults."""
        source = {**BASE, 'keys': {'Key1': {
            'text': 'A', 'on_press_actions': [{'KEY_PRESS': 'a'}]}}}

        assert reload(workdir, source)['keys']['Key1'] == source['keys']['Key1']

    def test_explicit_defaults_are_kept(self, workdir):
        """A field the user spelled out stays spelled out, even at its default."""
        source = {**BASE, 'keys': {'Key1': {
            'text': 'A', 'text_color': 'white',
            'on_press_actions': [{'KEY_PRESS': 'a'}]}}}

        assert reload(workdir, source)['keys']['Key1']['text_color'] == 'white'

    def test_changed_styling_is_written(self, workdir):
        path = write_config(workdir, BASE)
        document = ConfigDocument.load(path)
        document.keys['Key1'].font_size = 44
        document.save()

        with open(path) as f:
            assert yaml.safe_load(f)['streamdock']['keys']['Key1']['font_size'] == 44

    def test_settings_absent_from_the_file_stay_absent(self, workdir):
        """A real config omitting lock_verification_delay must not gain one."""
        source = {**BASE, 'settings': {'brightness': 30}}

        assert reload(workdir, source)['settings'] == {'brightness': 30}

    def test_a_saved_config_still_validates(self, workdir):
        path = write_config(workdir, BASE)
        document = ConfigDocument.load(path)
        document.save()
        assert ConfigDocument.load(path).validate() == []


class TestDefaults:
    """Editor and runtime must agree on defaults."""

    def test_brightness_default_matches_the_runtime(self):
        from StreamDock.application.configuration_manager import StreamDockConfig
        assert DEFAULT_BRIGHTNESS == StreamDockConfig().brightness

    def test_new_empty_has_no_path(self):
        document = ConfigDocument.new_empty()
        assert document.path is None
        assert document.keys == {}


class TestKeyDefinition:
    """Icon and text are mutually exclusive, matching the runtime validator."""

    def test_icon_wins_when_both_are_set(self):
        key = KeyDefinition('K', {'icon': 'a.png', 'text': 'A'})
        assert key.to_dict() == {'icon': 'a.png'}

    def test_text_key_writes_its_styling(self):
        result = KeyDefinition('K', {'text': 'A', 'font_size': 30}).to_dict()
        assert result['text'] == 'A'
        assert result['font_size'] == 30

    def test_empty_action_lists_are_omitted(self):
        assert 'on_press_actions' not in KeyDefinition('K', {'text': 'A'}).to_dict()


class TestWindowRule:
    """patterns() normalises both YAML forms."""

    def test_single_pattern(self):
        assert WindowRule('R', {'window_name': 'firefox'}).patterns() == ['firefox']

    def test_list_of_patterns(self):
        assert WindowRule('R', {'window_name': ['a', 'b']}).patterns() == ['a', 'b']

    def test_empty(self):
        assert WindowRule('R', {}).patterns() == []


class TestSave:
    """Saving is atomic and does not leave debris."""

    def test_save_to_a_new_path_updates_the_document(self, workdir):
        document = ConfigDocument.load(write_config(workdir, BASE))
        target = os.path.join(workdir, 'other.yml')

        document.save(target)

        assert document.path == target
        assert os.path.exists(target)

    def test_save_without_a_path_is_refused(self):
        with pytest.raises(ValueError):
            ConfigDocument.new_empty().save()

    def test_save_leaves_no_temporary_files(self, workdir):
        ConfigDocument.load(write_config(workdir, BASE)).save()
        assert [f for f in os.listdir(workdir) if f.startswith('.config-')] == []

    def test_save_clears_the_dirty_flag(self, workdir):
        document = ConfigDocument.load(write_config(workdir, BASE))
        document.mark_dirty()
        document.save()
        assert not document.dirty


class TestLoadErrors:
    """Failures are reported, not swallowed."""

    def test_missing_file(self, workdir):
        with pytest.raises(FileNotFoundError):
            ConfigDocument.load(os.path.join(workdir, 'nope.yml'))

    def test_malformed_yaml(self, workdir):
        path = os.path.join(workdir, 'bad.yml')
        with open(path, 'w') as f:
            f.write("streamdock: [unclosed\n")
        with pytest.raises(ConfigValidationError):
            ConfigDocument.load(path)

    def test_missing_root_element(self, workdir):
        path = os.path.join(workdir, 'bad.yml')
        with open(path, 'w') as f:
            yaml.dump({'something_else': {}}, f)
        with pytest.raises(ConfigValidationError):
            ConfigDocument.load(path)


class TestValidationBridge:
    """The document reports the runtime's own verdict."""

    def test_valid_config_reports_nothing(self, workdir):
        assert ConfigDocument.load(write_config(workdir, BASE)).validate() == []

    def test_invalid_config_reports_the_problem(self, workdir):
        source = {**BASE, 'keys': {'Key1': {'text': 'A'}}}  # no actions
        issues = ConfigDocument.load(write_config(workdir, source)).validate()
        assert len(issues) == 1
        assert 'at least one action' in issues[0]

    def test_to_stream_dock_config_expands_icons(self, workdir, icon):
        source = {**BASE, 'keys': {'Key1': {
            'icon': 'icon.png', 'on_press_actions': [{'KEY_PRESS': 'a'}]}}}
        document = ConfigDocument.load(write_config(workdir, source))

        config = document.to_stream_dock_config()

        assert config.keys_config['Key1']['icon'] == icon
        assert document.keys['Key1'].icon == 'icon.png'
