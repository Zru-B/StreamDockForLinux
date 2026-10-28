"""
The focus history behind the rule editor's window picker: newest first, no repeats.
"""

from unittest.mock import Mock

from StreamDock.business_logic.system_event_monitor import RECENT_WINDOW_COUNT, SystemEventMonitor
from StreamDock.domain.Models import WindowInfo


def monitor() -> SystemEventMonitor:
    return SystemEventMonitor(Mock(), Mock())


def test_newest_first_and_refocus_moves_to_front():
    m = monitor()
    for cls in ("a", "b", "a"):
        m._remember_window(WindowInfo(title=cls.upper(), class_=cls))
    assert [w.class_ for w in m.recent_windows] == ["a", "b"]


def test_history_is_bounded_and_skips_blank_windows():
    m = monitor()
    m._remember_window(WindowInfo(title="", class_=""))
    for n in range(RECENT_WINDOW_COUNT + 5):
        m._remember_window(WindowInfo(title=str(n), class_="c"))
    assert len(m.recent_windows) == RECENT_WINDOW_COUNT
    assert m.recent_windows[0].title == str(RECENT_WINDOW_COUNT + 4)


def test_regex_rules_match_as_regex_and_plain_rules_as_text():
    # is_regex used to be validated and then ignored, so "^Chrom.*" never matched.
    from StreamDock.business_logic.layout_manager import rule_patterns, window_matches
    chrome = WindowInfo(title="x", class_="Chromium-browser")
    assert window_matches(chrome, rule_patterns("^chrom.*", True))
    assert not window_matches(chrome, rule_patterns("^chrom.*", False))
    assert window_matches(chrome, rule_patterns(["^firefox", "browser$"], True))
