"""
Edge-case configuration files, from the runtime's point of view.

The messages here are what the editor shows the user verbatim, so they are
asserted rather than just the exception type. Everything a hand-edited file
can do should surface as a ConfigValidationError, never a TypeError from deep
inside a loader.
"""

import os
import tempfile

import pytest
import yaml

from StreamDock.application.configuration_manager import (
    MAX_FONT_SIZE,
    ConfigurationManager,
    ConfigValidationError,
)


@pytest.fixture
def workdir():
    with tempfile.TemporaryDirectory() as tmpdir:
        yield tmpdir


@pytest.fixture
def icon(workdir):
    path = os.path.join(workdir, "icon.png")
    with open(path, "wb") as f:
        f.write(b"\x89PNG\r\n\x1a\n")
    return path


def write(workdir, text, name="config.yml"):
    """Write raw YAML text and return its path."""
    path = os.path.join(workdir, name)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)
    return path


def write_config(workdir, streamdock, name="config.yml"):
    """Write a 'streamdock' subtree as YAML and return its path."""
    path = os.path.join(workdir, name)
    with open(path, "w", encoding="utf-8") as f:
        yaml.dump({"streamdock": streamdock}, f, sort_keys=False)
    return path


def load(workdir, streamdock):
    """Validate an in-memory subtree the way the runtime would."""
    return ConfigurationManager(os.path.join(workdir, "config.yml")).from_data(
        streamdock, os.path.join(workdir, "config.yml"))._validate_config()


def expect(workdir, streamdock, fragment):
    """Assert validating this subtree fails with `fragment` in the message."""
    with pytest.raises(ConfigValidationError) as excinfo:
        ConfigurationManager.validate_data(
            streamdock, os.path.join(workdir, "config.yml"))
    assert fragment in str(excinfo.value), str(excinfo.value)
    return str(excinfo.value)


# A minimal configuration every case below mutates.
def base():
    return {
        "keys": {"KeyA": {"text": "A", "on_press_actions": [{"KEY_PRESS": "a"}]}},
        "layouts": {"Main": {"Default": True, "keys": [{1: "KeyA"}]}},
    }


class TestFileShape:
    """Whole-file hazards, exercised through ConfigurationManager.load()."""

    @pytest.mark.parametrize("text, fragment", [
        ("", "empty"),
        ("---\n", "empty"),
        ("{}\n", "empty"),
        ("[]\n", "empty"),
        ("0\n", "empty"),
        ("false\n", "empty"),
        ("hello\n", "must be a mapping"),
        ("streamdock\n", "must be a mapping"),
        ("- streamdock\n", "must be a mapping"),
        ("- a\n- b\n", "must be a mapping"),
        ("other_root:\n  a: 1\n", "must contain 'streamdock'"),
        ("streamdock:\n", "'streamdock' section is empty"),
        ("streamdock: some text\n", "'streamdock' must be a dictionary"),
        ("streamdock:\n  - a\n", "'streamdock' must be a dictionary"),
        ("streamdock:\n  keys: [unclosed\n", "Could not parse"),
        ("streamdock:\n\tkeys: {}\n", "Could not parse"),
    ])
    def test_bad_file_gives_a_clean_error(self, workdir, text, fragment):
        with pytest.raises(ConfigValidationError) as excinfo:
            ConfigurationManager(write(workdir, text)).load()
        assert fragment in str(excinfo.value), str(excinfo.value)

    def test_missing_file_raises_file_not_found(self, workdir):
        with pytest.raises(FileNotFoundError):
            ConfigurationManager(os.path.join(workdir, "nope.yml")).load()

    def test_non_utf8_bytes_give_a_clean_error(self, workdir):
        path = os.path.join(workdir, "latin1.yml")
        with open(path, "wb") as f:
            f.write("streamdock:\n  keys:\n    K\xe9y: {text: 'A'}\n".encode("latin-1"))

        with pytest.raises(ConfigValidationError) as excinfo:
            ConfigurationManager(path).load()

        assert "not valid UTF-8" in str(excinfo.value)

    def test_utf8_content_loads(self, workdir):
        """The counterpart: non-ASCII text is fine when it really is UTF-8."""
        config = base()
        config["keys"] = {
            "Ключ": {"text": "日本", "on_press_actions": [{"KEY_PRESS": "a"}]}}
        config["layouts"] = {"Main": {"Default": True, "keys": [{1: "Ключ"}]}}

        loaded = ConfigurationManager(write_config(workdir, config)).load()

        assert loaded.keys_config["Ключ"]["text"] == "日本"

    def test_duplicate_yaml_keys_keep_the_last(self, workdir):
        """PyYAML does not reject them; pin the behaviour so it is not a surprise."""
        path = write(workdir, """
streamdock:
  keys:
    KeyA:
      text: "first"
      on_press_actions: [{KEY_PRESS: "a"}]
    KeyA:
      text: "second"
      on_press_actions: [{KEY_PRESS: "b"}]
  layouts:
    Main:
      Default: true
      keys: [{1: "KeyA"}]
""")

        config = ConfigurationManager(path).load()

        assert config.keys_config["KeyA"]["text"] == "second"


class TestSections:
    """Top-level sections with the wrong shape."""

    @pytest.mark.parametrize("mutate, fragment", [
        (lambda c: c.pop("keys"), "must contain 'keys'"),
        (lambda c: c.pop("layouts"), "must contain 'layouts'"),
        (lambda c: c.update(settings=None), "'settings' must be a dictionary"),
        (lambda c: c.update(settings="hi"), "'settings' must be a dictionary"),
        (lambda c: c.update(settings=[1]), "'settings' must be a dictionary"),
        (lambda c: c.update(keys=None), "'keys' must be a dictionary"),
        (lambda c: c.update(keys=["a"]), "'keys' must be a dictionary"),
        (lambda c: c.update(keys={}), "cannot be empty"),
        (lambda c: c.update(layouts=None), "'layouts' must be a dictionary"),
        (lambda c: c.update(layouts="x"), "'layouts' must be a dictionary"),
        (lambda c: c.update(layouts={}), "cannot be empty"),
        (lambda c: c.update(windows_rules="x"), "'windows_rules' must be a dictionary"),
        (lambda c: c.update(windows_rules=[1]), "'windows_rules' must be a dictionary"),
    ])
    def test_bad_section(self, workdir, mutate, fragment):
        config = base()
        mutate(config)
        expect(workdir, config, fragment)


class TestSettings:
    """The settings block."""

    @pytest.mark.parametrize("settings, fragment", [
        ({"brightness": 101}, "brightness must be a number between 0 and 100"),
        ({"brightness": -1}, "brightness must be a number between 0 and 100"),
        ({"brightness": "high"}, "brightness must be a number between 0 and 100"),
        ({"brightness": None}, "brightness must be a number between 0 and 100"),
        ({"lock_monitor": "yes please"}, "lock_monitor must be true or false"),
        ({"lock_monitor": 1}, "lock_monitor must be true or false"),
        ({"lock_verification_delay": 0.0}, "lock_verification_delay"),
        ({"lock_verification_delay": 30.1}, "lock_verification_delay"),
        ({"lock_verification_delay": "soon"}, "lock_verification_delay"),
        ({"double_press_interval": 0}, "double_press_interval"),
        ({"double_press_interval": 2.1}, "double_press_interval"),
        ({"double_press_interval": "fast"}, "double_press_interval"),
    ])
    def test_rejected(self, workdir, settings, fragment):
        expect(workdir, {**base(), "settings": settings}, fragment)

    @pytest.mark.parametrize("settings", [
        {"brightness": 0},
        {"brightness": 100},
        {"brightness": 50.5},
        {"lock_verification_delay": 0.1},
        {"lock_verification_delay": 30.0},
        {"double_press_interval": 2.0},
        {"lock_monitor": False},
        {},
    ])
    def test_accepted(self, workdir, settings):
        ConfigurationManager.validate_data(
            {**base(), "settings": settings}, os.path.join(workdir, "config.yml"))


class TestKeys:
    """The keys block."""

    @pytest.mark.parametrize("key_def, fragment", [
        ("not a dict", "definition must be a dictionary"),
        ([1, 2], "definition must be a dictionary"),
        ({"on_press_actions": [{"KEY_PRESS": "a"}]}, "must have either 'icon' or 'text'"),
        ({"icon": "a.png", "text": "A"}, "cannot have both 'icon' and 'text'"),
        ({"text": 42, "on_press_actions": [{"KEY_PRESS": "a"}]}, "text field must be a string"),
        ({"text": "", "on_press_actions": [{"KEY_PRESS": "a"}]}, "text field cannot be empty"),
        ({"text": "   ", "on_press_actions": [{"KEY_PRESS": "a"}]}, "text field cannot be empty"),
        ({"text": "A"}, "must have at least one action"),
        ({"text": "A", "on_click_actions": [{"KEY_PRESS": "a"}]}, "is not supported"),
        ({"text": "A", "actions": [{"KEY_PRESS": "a"}]}, "is not supported"),
        ({"text": "A", True: "x", "on_press_actions": [{"KEY_PRESS": "a"}]},
         "non-text field name"),
    ])
    def test_rejected(self, workdir, key_def, fragment):
        config = base()
        config["keys"] = {"KeyA": key_def}
        expect(workdir, config, fragment)

    @pytest.mark.parametrize("font_size, fragment", [
        ("big", "font_size must be a whole number"),
        (20.5, "font_size must be a whole number"),
        (None, "font_size must be a whole number"),
        (True, "font_size must be a whole number"),
        (0, "font_size must be between"),
        (-5, "font_size must be between"),
        (MAX_FONT_SIZE + 1, "font_size must be between"),
    ])
    def test_font_size_rejected(self, workdir, font_size, fragment):
        config = base()
        config["keys"]["KeyA"]["font_size"] = font_size
        expect(workdir, config, fragment)

    @pytest.mark.parametrize("font_size", [1, 20, MAX_FONT_SIZE])
    def test_font_size_accepted(self, workdir, font_size):
        config = base()
        config["keys"]["KeyA"]["font_size"] = font_size
        ConfigurationManager.validate_data(config, os.path.join(workdir, "config.yml"))

    def test_only_release_actions_is_enough(self, workdir):
        config = base()
        config["keys"]["KeyA"] = {"text": "A", "on_release_actions": [{"KEY_PRESS": "a"}]}
        ConfigurationManager.validate_data(config, os.path.join(workdir, "config.yml"))

    def test_a_key_used_by_no_layout_is_allowed(self, workdir):
        config = base()
        config["keys"]["Orphan"] = {"text": "O", "on_press_actions": [{"KEY_PRESS": "o"}]}
        ConfigurationManager.validate_data(config, os.path.join(workdir, "config.yml"))


class TestIcons:
    """Icon paths."""

    def test_null_icon(self, workdir):
        config = base()
        config["keys"]["KeyA"] = {"icon": None, "on_press_actions": [{"KEY_PRESS": "a"}]}
        expect(workdir, config, "cannot be empty")

    def test_non_string_icon(self, workdir):
        config = base()
        config["keys"]["KeyA"] = {"icon": 42, "on_press_actions": [{"KEY_PRESS": "a"}]}
        expect(workdir, config, "must be a string")

    def test_missing_icon_names_the_resolved_path(self, workdir):
        config = base()
        config["keys"]["KeyA"] = {"icon": "gone.png",
                                  "on_press_actions": [{"KEY_PRESS": "a"}]}
        message = expect(workdir, config, "Icon file not found")
        assert os.path.join(workdir, "gone.png") in message

    def test_directory_instead_of_a_file(self, workdir):
        os.mkdir(os.path.join(workdir, "adir.png"))
        config = base()
        config["keys"]["KeyA"] = {"icon": "adir.png",
                                  "on_press_actions": [{"KEY_PRESS": "a"}]}
        expect(workdir, config, "must be a file")

    def test_wrong_extension(self, workdir):
        with open(os.path.join(workdir, "notes.txt"), "w") as f:
            f.write("hi")
        config = base()
        config["keys"]["KeyA"] = {"icon": "notes.txt",
                                  "on_press_actions": [{"KEY_PRESS": "a"}]}
        expect(workdir, config, "must be an image file")

    def test_unreadable_icon(self, workdir, icon):
        os.chmod(icon, 0o000)
        try:
            if os.access(icon, os.R_OK):
                pytest.skip("running as a user that ignores file permissions")
            config = base()
            config["keys"]["KeyA"] = {"icon": "icon.png",
                                      "on_press_actions": [{"KEY_PRESS": "a"}]}
            expect(workdir, config, "must be readable")
        finally:
            os.chmod(icon, 0o644)

    def test_empty_icon_string_resolves_to_the_config_directory(self, workdir):
        """A quirk worth pinning: "" resolves to the directory, so it exists."""
        config = base()
        config["keys"]["KeyA"] = {"icon": "", "on_press_actions": [{"KEY_PRESS": "a"}]}
        expect(workdir, config, "must be a file")


class TestActions:
    """Action lists - where a hand-edited file most often goes wrong."""

    @pytest.mark.parametrize("actions, fragment", [
        ("KEY_PRESS", "actions must be a list"),
        ({"KEY_PRESS": "a"}, "actions must be a list"),
        (42, "actions must be a list"),
        ([42], "must be a dictionary or string"),
        ([None], "must be a dictionary or string"),
        ([[1, 2]], "must be a dictionary or string"),
        ([{}], "exactly one key-value pair"),
        ([{"KEY_PRESS": "a", "TYPE_TEXT": "b"}], "exactly one key-value pair"),
        ([{"NOT_AN_ACTION": "a"}], "invalid action type"),
        ([{1: "a"}], "action type must be text"),
        ([{True: "a"}], "action type must be text"),
    ])
    def test_rejected(self, workdir, actions, fragment):
        config = base()
        config["keys"]["KeyA"]["on_press_actions"] = actions
        expect(workdir, config, fragment)

    def test_the_error_names_the_key_and_index(self, workdir):
        config = base()
        config["keys"]["KeyA"]["on_press_actions"] = [{"KEY_PRESS": "a"}, {}]
        message = expect(workdir, config, "exactly one key-value pair")
        assert "KeyA" in message and "[1]" in message

    def test_lowercase_action_names_pass_validation(self, workdir):
        """Known gap: the factory is case-sensitive, so this is dropped later."""
        config = base()
        config["keys"]["KeyA"]["on_press_actions"] = [{"key_press": "a"}]
        ConfigurationManager.validate_data(config, os.path.join(workdir, "config.yml"))

    def test_an_empty_action_list_is_allowed(self, workdir):
        config = base()
        config["keys"]["KeyA"]["on_release_actions"] = []
        ConfigurationManager.validate_data(config, os.path.join(workdir, "config.yml"))


class TestLayouts:
    """The layouts block."""

    @pytest.mark.parametrize("layout, fragment", [
        ("not a dict", "definition must be a dictionary"),
        ({"Default": True}, "missing 'keys' field"),
        ({"Default": True, "keys": "abc"}, "keys must be a list"),
        ({"Default": True, "keys": []}, "keys list cannot be empty"),
        ({"Default": True, "keys": ["KeyA"]}, "must be a dictionary"),
        ({"Default": True, "keys": [{1: "KeyA", 2: "KeyA"}]}, "exactly one key-value pair"),
        ({"Default": True, "keys": [{0: "KeyA"}]}, "Must be between 1 and 15"),
        ({"Default": True, "keys": [{16: "KeyA"}]}, "Must be between 1 and 15"),
        ({"Default": True, "keys": [{"one": "KeyA"}]}, "Must be between 1 and 15"),
        ({"Default": True, "keys": [{1: "KeyA"}, {1: "KeyA"}]}, "duplicate key number"),
        ({"Default": True, "keys": [{1: "Missing"}]}, "references undefined key"),
        ({"Default": True, "keys": [{1: ["KeyA"]}]}, "must be text or null"),
        ({"Default": True, "keys": [{1: 42}]}, "must be text or null"),
    ])
    def test_rejected(self, workdir, layout, fragment):
        config = base()
        config["layouts"] = {"Main": layout}
        expect(workdir, config, fragment)

    def test_no_default_layout(self, workdir):
        config = base()
        config["layouts"]["Main"].pop("Default")
        expect(workdir, config, "At least one layout must have 'Default: true'")

    def test_two_default_layouts(self, workdir):
        config = base()
        config["layouts"]["Other"] = {"Default": True, "keys": [{1: "KeyA"}]}
        expect(workdir, config, "Only one layout can have 'Default: true'")

    def test_null_slots_are_accepted(self, workdir):
        """Documented as "explicitly empty key"."""
        config = base()
        config["layouts"]["Main"]["keys"] = [{1: None}, {2: "KeyA"}]
        ConfigurationManager.validate_data(config, os.path.join(workdir, "config.yml"))

    def test_a_layout_of_only_null_slots_is_accepted(self, workdir):
        config = base()
        config["layouts"]["Main"]["keys"] = [{1: None}, {2: None}]
        ConfigurationManager.validate_data(config, os.path.join(workdir, "config.yml"))

    def test_a_full_fifteen_key_layout(self, workdir):
        config = base()
        config["layouts"]["Main"]["keys"] = [{n: "KeyA"} for n in range(1, 16)]
        ConfigurationManager.validate_data(config, os.path.join(workdir, "config.yml"))

    def test_the_same_key_twice_in_one_layout_is_accepted(self, workdir):
        """Duplicate positions are rejected, duplicate names are not."""
        config = base()
        config["layouts"]["Main"]["keys"] = [{1: "KeyA"}, {2: "KeyA"}]
        ConfigurationManager.validate_data(config, os.path.join(workdir, "config.yml"))


class TestWindowRules:
    """The windows_rules block."""

    @pytest.mark.parametrize("rule, fragment", [
        ("not a dict", "definition must be a dictionary"),
        ({"layout": "Main"}, "missing 'window_name'"),
        ({"window_name": "x"}, "missing 'layout'"),
        ({"window_name": 42, "layout": "Main"}, "must be a string or a list of strings"),
        ({"window_name": [], "layout": "Main"}, "list cannot be empty"),
        ({"window_name": ["a", 2], "layout": "Main"}, "must contain only strings"),
        ({"window_name": "x", "layout": "Gone"}, "references undefined layout"),
        ({"window_name": "x", "layout": ["Main"]}, "'layout' must be text"),
        ({"window_name": "x", "layout": "Main", "is_regex": "yes"}, "must be a boolean"),
        ({"window_name": "x", "layout": "Main", "match_field": "colour"}, "invalid match_field"),
    ])
    def test_rejected(self, workdir, rule, fragment):
        expect(workdir, {**base(), "windows_rules": {"R": rule}}, fragment)

    @pytest.mark.parametrize("rule", [
        {"window_name": "firefox", "layout": "Main"},
        {"window_name": ["firefox", "chromium"], "layout": "Main"},
        {"window_name": "x", "layout": "Main", "match_field": "title"},
        {"window_name": "x", "layout": "Main", "match_field": "raw"},
        {"window_name": "x", "layout": "Main", "is_regex": True},
        {"window_name": "x", "layout": "Main", "priority": 10},
    ])
    def test_accepted(self, workdir, rule):
        ConfigurationManager.validate_data(
            {**base(), "windows_rules": {"R": rule}}, os.path.join(workdir, "config.yml"))


class TestCheckedInFixtures:
    """The fixtures under tests/configs/ were orphaned; wire them up."""

    def test_valid_config_loads(self, config_fixture):
        config = ConfigurationManager(config_fixture("valid_config")).load()

        assert config.default_layout_name == "Layout1"
        assert set(config.keys_config) == {"Key1", "Key2"}
        assert config.brightness == 50

    @pytest.mark.parametrize("name, fragment", [
        ("invalid_brightness", "brightness must be a number between 0 and 100"),
        ("invalid_key_def", "must have either 'icon' or 'text'"),
        ("invalid_window_rule", "references undefined layout"),
        ("multiple_defaults", "Only one layout can have 'Default: true'"),
        ("duplicate_key_in_layout", "duplicate key number"),
    ])
    def test_invalid_fixture_is_rejected(self, config_fixture, name, fragment):
        with pytest.raises(ConfigValidationError) as excinfo:
            ConfigurationManager(config_fixture(name)).load()
        assert fragment in str(excinfo.value), str(excinfo.value)
