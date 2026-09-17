"""
Unit tests for icon path resolution.

Relative icon paths must mean the same thing to the editor preview and to the
runtime, and validating a configuration must never rewrite it.
"""

import copy
import os
import tempfile

import pytest

from StreamDock.application.configuration_manager import (
    ConfigurationManager,
    ConfigValidationError,
    expand_icon_paths,
    relativize_icon_path,
    resolve_icon_path,
)


@pytest.fixture
def config_dir():
    """Temporary directory standing in for a config file's directory."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield tmpdir


@pytest.fixture
def icon(config_dir):
    """A real icon file inside the config directory."""
    path = os.path.join(config_dir, "icon.png")
    with open(path, "wb") as f:
        f.write(b"\x89PNG\r\n\x1a\n")
    return path


def make_config(icon_value):
    """Minimal valid 'streamdock' subtree using the given icon path."""
    return {
        'keys': {
            'Key1': {
                'icon': icon_value,
                'on_press_actions': [{'KEY_PRESS': 'a'}],
            }
        },
        'layouts': {
            'Main': {'Default': True, 'keys': [{1: 'Key1'}]},
        },
    }


class TestResolveIconPath:
    """resolve_icon_path()."""

    def test_relative_resolves_against_config_dir(self, config_dir):
        assert resolve_icon_path("img/a.png", config_dir) == os.path.join(config_dir, "img/a.png")

    def test_absolute_is_unchanged(self, config_dir):
        assert resolve_icon_path("/opt/icons/a.png", config_dir) == "/opt/icons/a.png"

    def test_user_home_is_expanded(self, config_dir):
        assert resolve_icon_path("~/a.png", config_dir) == os.path.expanduser("~/a.png")

    def test_environment_variable_is_expanded(self, config_dir, monkeypatch):
        monkeypatch.setenv("ICONS", "/srv/icons")
        assert resolve_icon_path("$ICONS/a.png", config_dir) == "/srv/icons/a.png"

    def test_surrounding_whitespace_is_stripped(self, config_dir):
        assert resolve_icon_path("  a.png  ", config_dir) == os.path.join(config_dir, "a.png")

    def test_does_not_resolve_against_cwd(self, config_dir, tmp_path, monkeypatch):
        """A config must mean the same thing wherever the app is launched from."""
        monkeypatch.chdir(tmp_path)
        assert resolve_icon_path("a.png", config_dir) == os.path.join(config_dir, "a.png")


class TestRelativizeIconPath:
    """relativize_icon_path()."""

    def test_path_under_config_dir_becomes_relative(self, config_dir):
        absolute = os.path.join(config_dir, "img", "a.png")
        assert relativize_icon_path(absolute, config_dir) == os.path.join("img", "a.png")

    def test_path_outside_config_dir_stays_absolute(self, config_dir):
        assert relativize_icon_path("/opt/icons/a.png", config_dir) == "/opt/icons/a.png"

    def test_round_trip(self, config_dir):
        absolute = os.path.join(config_dir, "img", "a.png")
        stored = relativize_icon_path(absolute, config_dir)
        assert resolve_icon_path(stored, config_dir) == absolute


class TestExpandIconPaths:
    """expand_icon_paths()."""

    def test_expands_every_key(self, config_dir):
        data = make_config("a.png")
        expand_icon_paths(data, config_dir)
        assert data['keys']['Key1']['icon'] == os.path.join(config_dir, "a.png")

    def test_ignores_text_only_keys(self, config_dir):
        data = {'keys': {'K': {'text': 'hi'}}}
        expand_icon_paths(data, config_dir)
        assert data['keys']['K'] == {'text': 'hi'}


class TestValidationDoesNotMutate:
    """The editor validates the dictionary it is about to save."""

    def test_validate_data_leaves_config_untouched(self, config_dir, icon):
        data = make_config("icon.png")
        before = copy.deepcopy(data)

        ConfigurationManager.validate_data(data, os.path.join(config_dir, "config.yml"))

        assert data == before
        assert data['keys']['Key1']['icon'] == "icon.png"

    def test_parse_data_leaves_input_untouched_but_expands_output(self, config_dir, icon):
        data = make_config("icon.png")

        config = ConfigurationManager.parse_data(data, os.path.join(config_dir, "config.yml"))

        assert data['keys']['Key1']['icon'] == "icon.png"
        assert config.keys_config['Key1']['icon'] == icon

    def test_load_leaves_the_file_relative_but_expands_the_parsed_config(self, config_dir, icon):
        import yaml

        config_path = os.path.join(config_dir, "config.yml")
        with open(config_path, 'w') as f:
            yaml.dump({'streamdock': make_config("icon.png")}, f)

        config = ConfigurationManager(config_path).load()

        assert config.keys_config['Key1']['icon'] == icon
        with open(config_path) as f:
            assert yaml.safe_load(f)['streamdock']['keys']['Key1']['icon'] == "icon.png"


class TestCollectIssues:
    """collect_issues() backs the editor's pre-save check."""

    def test_valid_config_reports_nothing(self, config_dir, icon):
        issues = ConfigurationManager.collect_issues(
            make_config("icon.png"), os.path.join(config_dir, "config.yml"))
        assert issues == []

    def test_missing_icon_is_reported_with_the_resolved_path(self, config_dir):
        issues = ConfigurationManager.collect_issues(
            make_config("nope.png"), os.path.join(config_dir, "config.yml"))

        assert len(issues) == 1
        assert "Icon file not found" in issues[0]
        assert os.path.join(config_dir, "nope.png") in issues[0]

    def test_never_raises(self, config_dir):
        assert ConfigurationManager.collect_issues({}, os.path.join(config_dir, "config.yml"))

    def test_validate_data_still_raises(self, config_dir):
        with pytest.raises(ConfigValidationError):
            ConfigurationManager.validate_data(
                make_config("nope.png"), os.path.join(config_dir, "config.yml"))
