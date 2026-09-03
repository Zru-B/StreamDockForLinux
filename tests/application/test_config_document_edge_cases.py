"""
Edge-case configuration files, from the editor's point of view.

ConfigDocument is what the GUI loads and, crucially, what it writes back. A
file it mangles is a file the user loses, so the emphasis here is on round
trips and on failing cleanly rather than half-loading.
"""

import os
import tempfile

import pytest
import yaml

from StreamDock.application.config_document import ConfigDocument, KeyDefinition
from StreamDock.application.configuration_manager import ConfigValidationError


@pytest.fixture
def workdir():
    with tempfile.TemporaryDirectory() as tmpdir:
        yield tmpdir


def write(workdir, text, name="config.yml"):
    path = os.path.join(workdir, name)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)
    return path


def write_config(workdir, streamdock, name="config.yml"):
    path = os.path.join(workdir, name)
    with open(path, "w", encoding="utf-8") as f:
        yaml.dump({"streamdock": streamdock}, f, sort_keys=False)
    return path


def reload(workdir, streamdock):
    """Round-trip a subtree through load -> save and return the result."""
    path = write_config(workdir, streamdock)
    ConfigDocument.load(path).save()
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)["streamdock"]


BASE = {
    "settings": {"brightness": 30},
    "keys": {"KeyA": {"text": "A", "on_press_actions": [{"KEY_PRESS": "a"}]}},
    "layouts": {"Main": {"Default": True, "keys": [{1: "KeyA"}]}},
}


class TestLoadFailsCleanly:
    """The editor and the runtime must reject the same files the same way."""

    @pytest.mark.parametrize("text, fragment", [
        ("", "empty"),
        ("[]\n", "empty"),
        ("streamdock\n", "must be a mapping"),
        ("- streamdock\n", "must be a mapping"),
        ("streamdock:\n", "'streamdock' section is empty"),
        ("streamdock: text\n", "'streamdock' must be a dictionary"),
        ("streamdock:\n  keys: [unclosed\n", "Could not parse"),
        ("other:\n  a: 1\n", "must contain 'streamdock'"),
    ])
    def test_bad_file(self, workdir, text, fragment):
        with pytest.raises(ConfigValidationError) as excinfo:
            ConfigDocument.load(write(workdir, text))
        assert fragment in str(excinfo.value), str(excinfo.value)

    def test_missing_file(self, workdir):
        with pytest.raises(FileNotFoundError):
            ConfigDocument.load(os.path.join(workdir, "nope.yml"))

    def test_non_utf8_bytes(self, workdir):
        path = os.path.join(workdir, "latin1.yml")
        with open(path, "wb") as f:
            f.write("streamdock:\n  keys:\n    K\xe9y: {text: 'A'}\n".encode("latin-1"))

        with pytest.raises(ConfigValidationError) as excinfo:
            ConfigDocument.load(path)

        assert "not valid UTF-8" in str(excinfo.value)


class TestSectionShapes:
    """from_dict is reached directly by Apply, with unsaved edits."""

    @pytest.mark.parametrize("streamdock, fragment", [
        (None, "'streamdock' must be a dictionary"),
        ("text", "'streamdock' must be a dictionary"),
        ([1], "'streamdock' must be a dictionary"),
        ({"settings": "x"}, "'settings' must be a dictionary"),
        ({"settings": [1]}, "'settings' must be a dictionary"),
        ({"keys": "x"}, "'keys' must be a dictionary"),
        ({"keys": ["a"]}, "'keys' must be a dictionary"),
        ({"layouts": "x"}, "'layouts' must be a dictionary"),
        ({"windows_rules": "x"}, "'windows_rules' must be a dictionary"),
        ({"keys": {"K": "not a dict"}}, "'keys.K' must be a dictionary"),
        ({"layouts": {"L": [1]}}, "'layouts.L' must be a dictionary"),
        ({"windows_rules": {"R": "x"}}, "'windows_rules.R' must be a dictionary"),
    ])
    def test_rejected(self, streamdock, fragment):
        with pytest.raises(ConfigValidationError) as excinfo:
            ConfigDocument.from_dict(streamdock)
        assert fragment in str(excinfo.value), str(excinfo.value)

    @pytest.mark.parametrize("streamdock", [
        {},
        {"settings": None},
        {"keys": None},
        {"layouts": None},
        {"windows_rules": None},
        {"keys": {"K": None}},
        {"layouts": {"L": None}},
    ])
    def test_null_sections_mean_defaults(self, streamdock):
        """A section present but empty is a normal thing to write by hand."""
        document = ConfigDocument.from_dict(streamdock)

        assert isinstance(document.keys, dict)
        assert isinstance(document.layouts, dict)

    def test_a_non_numeric_layout_position_is_reported(self):
        with pytest.raises(ConfigValidationError) as excinfo:
            ConfigDocument.from_dict({"layouts": {"L": {"keys": [{"one": "K"}]}}})
        assert "is not a number" in str(excinfo.value)


class TestRoundTripEdgeCases:
    """Unusual but legitimate content must survive a save."""

    def test_unicode_and_emoji(self, workdir):
        source = {
            "settings": {"brightness": 30},
            "keys": {"Ключ 🎹": {"text": "日本語 🚀",
                                 "on_press_actions": [{"TYPE_TEXT": "café ☕"}]}},
            "layouts": {"Основной": {"Default": True, "keys": [{1: "Ключ 🎹"}]}},
        }

        assert reload(workdir, source) == source

    def test_a_very_long_string(self, workdir):
        source = {**BASE, "keys": {"KeyA": {
            "text": "x" * 5000, "on_press_actions": [{"TYPE_TEXT": "y" * 5000}]}}}

        assert reload(workdir, source)["keys"]["KeyA"]["text"] == "x" * 5000

    def test_a_full_fifteen_key_layout(self, workdir):
        source = {**BASE, "layouts": {"Main": {
            "Default": True, "keys": [{n: "KeyA"} for n in range(1, 16)]}}}

        assert len(reload(workdir, source)["layouts"]["Main"]["keys"]) == 15

    def test_null_slots_survive(self, workdir):
        source = {**BASE, "layouts": {"Main": {
            "Default": True, "keys": [{1: "KeyA"}, {2: None}]}}}

        assert reload(workdir, source)["layouts"]["Main"]["keys"] == [
            {1: "KeyA"}, {2: None}]

    def test_many_layouts_and_rules(self, workdir):
        source = {**BASE,
                  "layouts": {f"L{n}": {"keys": [{1: "KeyA"}]} for n in range(50)},
                  "windows_rules": {f"R{n}": {"window_name": f"app{n}", "layout": "L0"}
                                    for n in range(50)}}
        source["layouts"]["L0"]["Default"] = True

        result = reload(workdir, source)

        assert len(result["layouts"]) == 50
        assert len(result["windows_rules"]) == 50

    def test_a_file_without_settings_does_not_gain_them(self, workdir):
        """Opening and saving must not add sections the file never had."""
        source = {"keys": BASE["keys"], "layouts": BASE["layouts"]}

        result = reload(workdir, source)

        assert "settings" not in result
        assert "windows_rules" not in result

    def test_an_empty_windows_rules_section_is_preserved(self, workdir):
        source = {**BASE, "windows_rules": {}}

        assert reload(workdir, source)["windows_rules"] == {}

    def test_brightness_extremes(self, workdir):
        for value in (0, 100):
            assert reload(workdir, {**BASE, "settings": {"brightness": value}}
                          )["settings"]["brightness"] == value

    def test_a_key_used_by_no_layout_survives(self, workdir):
        source = {**BASE, "keys": {
            **BASE["keys"],
            "Orphan": {"text": "O", "on_press_actions": [{"KEY_PRESS": "o"}]}}}

        assert "Orphan" in reload(workdir, source)["keys"]

    def test_a_dangling_key_reference_survives_a_round_trip(self, workdir):
        """The editor must not quietly drop it; validation is what complains."""
        source = {**BASE, "layouts": {"Main": {
            "Default": True, "keys": [{1: "KeyA"}, {2: "Missing"}]}}}

        result = reload(workdir, source)

        assert {2: "Missing"} in result["layouts"]["Main"]["keys"]
        assert ConfigDocument.from_dict(result).validate() != []


class TestFalsyFields:
    """Truthiness tests in to_dict() used to delete data."""

    def test_a_zero_font_size_is_kept(self, workdir):
        source = {**BASE, "keys": {"KeyA": {
            "text": "A", "font_size": 0, "on_press_actions": [{"KEY_PRESS": "a"}]}}}

        assert reload(workdir, source)["keys"]["KeyA"]["font_size"] == 0

    def test_bold_false_is_kept(self, workdir):
        source = {**BASE, "keys": {"KeyA": {
            "text": "A", "bold": False, "on_press_actions": [{"KEY_PRESS": "a"}]}}}

        assert reload(workdir, source)["keys"]["KeyA"]["bold"] is False

    def test_a_key_with_neither_icon_nor_text_round_trips_its_actions(self):
        """It is invalid, but the editor must not silently discard the rest."""
        key = KeyDefinition("K", {"on_press_actions": [{"KEY_PRESS": "a"}]})

        assert key.to_dict()["on_press_actions"] == [{"KEY_PRESS": "a"}]


class TestSaveFailures:
    """save() is the operation that can destroy a working configuration."""

    def test_saving_into_an_unwritable_directory_reports_an_error(self, workdir):
        document = ConfigDocument.load(write_config(workdir, BASE))
        blocked = os.path.join(workdir, "blocked")
        os.mkdir(blocked)
        os.chmod(blocked, 0o500)
        try:
            if os.access(blocked, os.W_OK):
                pytest.skip("running as a user that ignores file permissions")
            with pytest.raises(OSError):
                document.save(os.path.join(blocked, "out.yml"))
        finally:
            os.chmod(blocked, 0o700)

    def test_a_failed_save_leaves_the_original_intact(self, workdir):
        """The write is atomic, so a crash must not truncate the old file."""
        path = write_config(workdir, BASE)
        document = ConfigDocument.load(path)
        document.keys["KeyA"].extra["bad"] = object()  # not representable in YAML

        with pytest.raises(Exception):
            document.save()

        with open(path, encoding="utf-8") as f:
            assert yaml.safe_load(f)["streamdock"]["keys"]["KeyA"]["text"] == "A"

    def test_a_failed_save_leaves_no_temporary_files(self, workdir):
        path = write_config(workdir, BASE)
        document = ConfigDocument.load(path)
        document.keys["KeyA"].extra["bad"] = object()

        with pytest.raises(Exception):
            document.save()

        assert [f for f in os.listdir(workdir) if f.startswith(".config-")] == []

    def test_saving_an_invalid_document_is_allowed(self, workdir):
        """Work in progress is worth keeping; validation gates Apply, not Save."""
        document = ConfigDocument.from_dict({**BASE, "settings": {"brightness": 500}})
        target = os.path.join(workdir, "wip.yml")

        document.save(target)

        assert ConfigDocument.load(target).validate() != []
