"""
Renaming, deleting, duplicating and tracing keys in a ConfigDocument.

A key is referenced by name from layouts and from other keys' CHANGE_KEY
actions; the risk is an edit leaving either pointing at a key that is gone.
"""

from StreamDock.application.config_document import ConfigDocument, KeyDefinition


def document() -> ConfigDocument:
    return ConfigDocument.from_dict({
        "keys": {
            "Mute": {"text": "M", "on_press_actions": [{"CHANGE_KEY": "Unmute"}]},
            "Unmute": {"text": "U", "on_long_press_actions": [{"CHANGE_KEY": "Mute"}, {"KEY_PRESS": "a"}]},
            "Spare": {"text": "S"},
        },
        "layouts": {"Main": {"Default": True, "keys": [{1: "Mute"}, {3: "Mute"}]},
                    "Other": {"keys": [{2: "Mute"}]}},
    })


def test_usage_counts_layouts_and_change_key_but_not_itself():
    doc = document()
    assert doc.key_usage("Mute").layouts == ["Main", "Other"]
    assert doc.key_usage("Mute").changed_to_by == ["Unmute"]
    # Reachable only by CHANGE_KEY still counts as used.
    assert doc.key_usage("Unmute").layouts == []
    assert not doc.key_usage("Unmute").unused
    assert doc.key_usage("Spare").unused


def test_rename_follows_into_layouts_and_change_key():
    doc = document()
    edited = KeyDefinition("Silence", doc.keys["Mute"].to_dict())
    doc.replace_key("Mute", edited)
    assert "Mute" not in doc.keys and "Silence" in doc.keys
    assert doc.layouts["Main"].keys == {1: "Silence", 3: "Silence"}
    assert doc.layouts["Other"].keys == {2: "Silence"}
    assert doc.keys["Unmute"].on_long_press_actions[0] == {"CHANGE_KEY": "Silence"}


def test_delete_clears_slots_and_only_the_actions_targeting_it():
    doc = document()
    doc.delete_key("Mute")
    assert "Mute" not in doc.keys
    assert doc.layouts["Main"].keys == {} and doc.layouts["Other"].keys == {}
    assert doc.keys["Unmute"].on_long_press_actions == [{"KEY_PRESS": "a"}]


def test_duplicate_picks_a_free_name_and_copies_deeply():
    doc = document()
    assert doc.duplicate_key("Mute") == "MuteCopy"
    assert doc.duplicate_key("Mute") == "MuteCopy2"
    doc.keys["MuteCopy"].on_press_actions.append({"KEY_PRESS": "b"})
    assert doc.keys["Mute"].on_press_actions == [{"CHANGE_KEY": "Unmute"}]
    assert doc.key_usage("MuteCopy").unused


def test_all_key_usage_matches_key_usage_for_every_key():
    """Manage Keys builds usage in one pass; it must agree with the per-key answer."""
    doc = document()
    doc.keys["Spare"].on_press_actions = [{"CHANGE_KEY": "Spare"}, {"CHANGE_KEY": ["odd"]}]

    all_usage = doc.all_key_usage()

    assert all_usage == {name: doc.key_usage(name) for name in doc.keys}
