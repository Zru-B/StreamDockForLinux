"""
Renaming, deleting and duplicating layouts, and ordering window rules.

Layouts are named by rules and CHANGE_LAYOUT actions (in two spellings), and
the runtime tries rules by priority then file order; the risk is an edit
leaving a dangling name, which makes the file fail validation, or silently
changing which rule wins.
"""

from StreamDock.application.config_document import ConfigDocument


def document() -> ConfigDocument:
    return ConfigDocument.from_dict({
        "keys": {
            "ToIde": {"text": "I", "on_press_actions": [{"CHANGE_LAYOUT": "IDE"}],
                      "on_release_actions": [{"KEY_PRESS": "b"}]},
            "OnlyToIde": {"text": "O", "on_press_actions": [{"CHANGE_LAYOUT": "IDE"}]},
            "ToIdeDict": {"text": "D", "on_long_press_actions": [{"CHANGE_LAYOUT": {"layout": "IDE"}},
                                                                 {"KEY_PRESS": "a"}]},
        },
        "layouts": {"Main": {"Default": True, "keys": [{1: "ToIde"}]},
                    "IDE": {"clear_all": True, "keys": [{2: "ToIdeDict"}]},
                    "Orphan": {"keys": [{1: "ToIde"}]}},
        "windows_rules": {
            "Idea": {"window_name": "jetbrains-idea", "layout": "IDE"},
            "Meet": {"window_name": ["Google Meet", "meet.google"], "layout": "Main",
                     "match_field": "title", "priority": 5},
        },
    })


def test_usage_reports_default_rules_and_keys():
    doc = document()
    assert doc.layout_usage("Main").is_default
    ide = doc.layout_usage("IDE")
    assert ide.rules == ["Idea"] and ide.keys == ["ToIde", "OnlyToIde", "ToIdeDict"]
    assert not doc.layout_usage("Orphan").reachable


def test_rename_keeps_position_and_follows_both_action_spellings():
    doc = document()
    doc.rename_layout("IDE", "Code")
    assert list(doc.layouts) == ["Main", "Code", "Orphan"]
    assert doc.layouts["Code"].name == "Code"
    assert doc.keys["ToIde"].on_press_actions == [{"CHANGE_LAYOUT": "Code"}]
    assert doc.keys["ToIdeDict"].on_long_press_actions[0] == {"CHANGE_LAYOUT": {"layout": "Code"}}
    assert doc.window_rules["Idea"].layout == "Code"
    assert doc.validate() == []


def test_keys_left_without_actions_are_named_before_a_delete():
    doc = document()
    assert doc.keys_emptied_by_layout_delete("IDE") == ["OnlyToIde"]


def test_delete_moves_rules_when_asked_and_drops_actions():
    doc = document()
    doc.delete_key("OnlyToIde")
    doc.delete_layout("IDE", move_rules_to="Orphan")
    assert "IDE" not in doc.layouts
    assert doc.window_rules["Idea"].layout == "Orphan"
    assert doc.keys["ToIde"].on_press_actions == []
    assert doc.keys["ToIde"].on_release_actions == [{"KEY_PRESS": "b"}]
    assert doc.keys["ToIdeDict"].on_long_press_actions == [{"KEY_PRESS": "a"}]
    assert doc.validate() == []


def test_delete_without_target_drops_its_rules():
    doc = document()
    doc.delete_key("OnlyToIde")
    doc.delete_layout("IDE")
    assert "Idea" not in doc.window_rules
    assert doc.validate() == []


def test_duplicate_is_placed_after_and_never_default():
    doc = document()
    assert doc.duplicate_layout("Main") == "MainCopy"
    assert list(doc.layouts)[:2] == ["Main", "MainCopy"]
    assert not doc.layouts["MainCopy"].is_default
    assert doc.layouts["MainCopy"].keys == {1: "ToIde"}
    doc.layouts["MainCopy"].keys[3] = "ToIdeDict"
    assert 3 not in doc.layouts["Main"].keys


def test_rules_are_ordered_by_priority_then_file_order():
    doc = document()
    assert [rule.name for rule in doc.ordered_rules()] == ["Meet", "Idea"]


def test_set_rule_order_uses_file_order_and_clears_priorities():
    doc = document()
    doc.set_rule_order(["Idea", "Meet"])
    assert [rule.name for rule in doc.ordered_rules()] == ["Idea", "Meet"]
    assert "priority" not in doc.to_dict()["streamdock"]["windows_rules"]["Meet"]
    assert list(doc.to_dict()["streamdock"]["windows_rules"]) == ["Idea", "Meet"]


def test_rule_rename_keeps_its_place():
    doc = document()
    doc.rename_rule("Idea", "IntelliJ")
    assert list(doc.window_rules) == ["IntelliJ", "Meet"]
    assert doc.window_rules["IntelliJ"].name == "IntelliJ"


def test_suggested_rule_names_are_readable_and_free():
    doc = document()
    assert doc.suggest_rule_name("jetbrains-idea") == "JetbrainsIdeaRule"
    doc.window_rules["JetbrainsIdeaRule"] = doc.window_rules["Idea"]
    assert doc.suggest_rule_name("jetbrains-idea, pycharm") == "JetbrainsIdeaRule2"
    assert doc.suggest_rule_name("jetbrains-idea", exclude="JetbrainsIdeaRule") == "JetbrainsIdeaRule"


def test_is_regex_round_trips_and_bad_regex_fails_validation():
    doc = document()
    doc.window_rules["Idea"].is_regex = True
    doc.window_rules["Idea"].window_name = "^jetbrains-(idea|pycharm)$"
    assert doc.to_dict()["streamdock"]["windows_rules"]["Idea"]["is_regex"] is True
    assert doc.validate() == []
    doc.window_rules["Idea"].window_name = "(["
    assert any("invalid regular expression" in problem for problem in doc.validate())


def test_all_layout_usage_matches_layout_usage_for_every_layout():
    """The sidebar builds usage in one pass; it must agree with the per-layout answer."""
    doc = document()

    assert doc.all_layout_usage() == {name: doc.layout_usage(name) for name in doc.layouts}
