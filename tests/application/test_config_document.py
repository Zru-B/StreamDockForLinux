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
    DEFAULT_DOUBLE_PRESS_INTERVAL,
    DEFAULT_LONG_PRESS_DURATION,
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

    def test_preserves_all_four_action_lists(self, workdir):
        source = {**BASE, 'keys': {'Key1': {
            'text': 'A',
            'on_press_actions': [{'KEY_PRESS': 'a'}],
            'on_release_actions': [{'KEY_PRESS': 'b'}],
            'on_double_press_actions': [{'KEY_PRESS': 'c'}],
            'on_long_press_actions': [{'KEY_PRESS': 'd'}]}}}
        key = reload(workdir, source)['keys']['Key1']
        assert key['on_release_actions'] == [{'KEY_PRESS': 'b'}]
        assert key['on_double_press_actions'] == [{'KEY_PRESS': 'c'}]
        assert key['on_long_press_actions'] == [{'KEY_PRESS': 'd'}]

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

    def test_explicit_default_long_press_duration_is_kept(self, workdir):
        source = {**BASE, 'settings': {'long_press_duration': DEFAULT_LONG_PRESS_DURATION}}

        assert reload(workdir, source)['settings'] == source['settings']

    def test_changed_long_press_duration_is_written(self, workdir):
        path = write_config(workdir, BASE)
        document = ConfigDocument.load(path)
        document.settings.long_press_duration = 1.25
        document.save()

        with open(path) as f:
            assert yaml.safe_load(f)['streamdock']['settings']['long_press_duration'] == 1.25

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

    def test_gesture_timing_defaults_match_the_runtime_and_the_device(self):
        from StreamDock.application.configuration_manager import StreamDockConfig
        from StreamDock.devices import stream_dock
        assert DEFAULT_LONG_PRESS_DURATION == StreamDockConfig().long_press_duration \
            == stream_dock.DEFAULT_LONG_PRESS_DURATION
        assert DEFAULT_DOUBLE_PRESS_INTERVAL == StreamDockConfig().double_press_interval \
            == stream_dock.DEFAULT_DOUBLE_PRESS_INTERVAL

    def test_new_empty_has_no_path(self):
        document = ConfigDocument.new_empty()
        assert document.path is None
        assert document.keys == {}


class TestKeyDefinition:
    """Serialising one key definition."""

    def test_an_icon_keeps_its_text_label(self):
        """The runtime draws the text over the icon; saving used to drop it."""
        key = KeyDefinition('K', {'icon': 'a.png', 'text': 'A'})
        assert key.to_dict() == {'icon': 'a.png', 'text': 'A'}

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


class TestSaveAsElsewhere:
    """Relative paths mean the config's directory, so moving the file rebases them."""

    SOURCE = {**BASE, 'keys': {
        'Key1': {'icon': 'icons/a.png',
                 'on_press_actions': [{'CHANGE_KEY_IMAGE': 'icons/b.png'},
                                      {'CHANGE_KEY_TEXT': {'text': 'x', 'icon': 'icons/c.png'}}]},
        'W': {'widget': 'clock', 'icon': '/abs/base.png',
              'state_icons': {'on': 'icons/on.png', 'off': '~/off.png'}},
    }}

    def saved_elsewhere(self, workdir):
        """From workdir/sub up to workdir: the icons stay under the new directory."""
        os.makedirs(os.path.join(workdir, 'sub'))
        document = ConfigDocument.load(
            write_config(os.path.join(workdir, 'sub'), self.SOURCE))
        target = os.path.join(workdir, 'moved.yml')
        document.save(target)
        with open(target) as f:
            return document, yaml.safe_load(f)['streamdock']['keys']

    def test_relative_paths_point_at_the_same_files(self, workdir):
        _, keys = self.saved_elsewhere(workdir)

        assert keys['Key1']['icon'] == 'sub/icons/a.png'
        assert keys['Key1']['on_press_actions'][0]['CHANGE_KEY_IMAGE'] == 'sub/icons/b.png'
        assert keys['Key1']['on_press_actions'][1]['CHANGE_KEY_TEXT']['icon'] == 'sub/icons/c.png'
        assert keys['W']['state_icons']['on'] == 'sub/icons/on.png'

    def test_a_path_outside_the_new_directory_becomes_absolute(self, workdir):
        """relativize_icon_path's rule: nothing is stored as ../"""
        document = ConfigDocument.load(write_config(workdir, self.SOURCE))
        target = os.path.join(workdir, 'other', 'moved.yml')

        document.save(target)

        assert document.keys['Key1'].icon == os.path.join(workdir, 'icons', 'a.png')

    def test_absolute_and_home_paths_are_left_alone(self, workdir):
        _, keys = self.saved_elsewhere(workdir)

        assert keys['W']['icon'] == '/abs/base.png'
        assert keys['W']['state_icons']['off'] == '~/off.png'

    def test_the_document_follows_so_a_second_save_is_stable(self, workdir):
        document, _ = self.saved_elsewhere(workdir)
        document.save()

        with open(document.path) as f:
            assert yaml.safe_load(f)['streamdock']['keys']['Key1']['icon'] == 'sub/icons/a.png'

    def test_saving_in_place_changes_nothing(self, workdir):
        assert reload(workdir, self.SOURCE)['keys']['Key1']['icon'] == 'icons/a.png'


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


class TestIconWithLabel:
    """An icon key may carry text drawn over it; the runtime draws both."""

    def test_the_label_and_its_style_are_written(self):
        key_def = KeyDefinition("Web", {"icon": "web.png"})
        key_def.text = "Web"
        key_def.text_position = "top"
        key_def.font_size = 14

        assert key_def.to_dict() == {"icon": "web.png", "text": "Web",
                                     "font_size": 14, "text_position": "top"}

    def test_an_unchanged_file_does_not_churn(self):
        data = {"icon": "web.png", "text": "Web", "bold": True, "text_position": "bottom"}

        assert KeyDefinition("Web", data).to_dict() == data

    def test_style_without_a_label_is_not_written(self):
        """No label, nothing to style: an icon key stays as small as before."""
        key_def = KeyDefinition("Web", {"icon": "web.png"})
        key_def.text_color = "red"

        assert key_def.to_dict() == {"icon": "web.png"}


class TestSaveHardening:
    """Saving must not break the file's link, permissions or durability."""

    def test_a_symlinked_config_is_written_through(self, workdir):
        real = os.path.join(workdir, "real.yml")
        link = os.path.join(workdir, "config.yml")
        ConfigDocument.new_empty().save(real)
        os.symlink(real, link)
        doc = ConfigDocument.load(link)
        doc.settings.brightness = 77

        doc.save()

        assert os.path.islink(link)
        assert ConfigDocument.load(real).settings.brightness == 77

    def test_the_file_mode_is_kept(self, workdir):
        path = os.path.join(workdir, "config.yml")
        ConfigDocument.new_empty().save(path)
        os.chmod(path, 0o640)

        ConfigDocument.load(path).save()

        assert os.stat(path).st_mode & 0o777 == 0o640


class TestLayoutLoadIssues:
    """What the model normalises away on load must still be reported, as the runtime would."""

    @pytest.mark.parametrize("keys, wording", [
        ([{1: "K"}, "junk"], "must be a dictionary"),
        ([{1: "K"}, {1: "K"}], "duplicate key number 1"),
        ([{"3": "K"}], "invalid key number '3'"),
    ])
    def test_it_is_reported_by_validate(self, keys, wording):
        doc = ConfigDocument.from_dict({
            "keys": {"K": {"text": "k", "on_press_actions": [{"KEY_PRESS": "a"}]}},
            "layouts": {"Main": {"Default": True, "keys": keys}},
        })

        assert any(wording in issue for issue in doc.validate())

    def test_a_save_writes_the_normalised_layout_and_forgets_the_issue(self, workdir):
        doc = ConfigDocument.from_dict({
            "keys": {"K": {"text": "k", "on_press_actions": [{"KEY_PRESS": "a"}]}},
            "layouts": {"Main": {"Default": True, "keys": [{"3": "K"}]}},
        })

        doc.save(os.path.join(workdir, "config.yml"))

        assert doc.validate() == []
