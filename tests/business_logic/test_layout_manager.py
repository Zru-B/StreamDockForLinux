"""
Unit tests for LayoutManager.

Tests pure business logic for layout selection and rule matching.
"""

import pytest
import re
from unittest.mock import Mock

from StreamDock.business_logic.layout_manager import LayoutManager, LayoutRule
from StreamDock.Models import WindowInfo


class TestLayoutRule:
    """Tests for LayoutRule dataclass."""
    
    def test_layout_rule_creation(self):
        """Design contract: LayoutRule stores rule configuration."""
        rule = LayoutRule(
            pattern="firefox",
            layout_name="browser_layout",
            match_field="class",
            priority=5
        )
        
        assert rule.pattern == "firefox"
        assert rule.layout_name == "browser_layout"
        assert rule.match_field == "class"
        assert rule.priority == 5
    
    def test_layout_rule_defaults(self):
        """Design contract: LayoutRule has sensible defaults."""
        rule = LayoutRule(pattern="test", layout_name="test_layout")
        
        assert rule.match_field == 'class'  # Default match field
        assert rule.priority == 0  # Default priority


class TestLayoutManager:
    """Tests for LayoutManager."""
    
    @pytest.fixture
    def manager(self):
        """LayoutManager instance."""
        return LayoutManager(default_layout_name="default")
    
    @pytest.fixture
    def window(self):
        """Sample WindowInfo for testing."""
        return WindowInfo(
            title="Firefox Browser",
            class_="firefox",
            raw="firefox raw"
        )
    
    # ==================== Initialization Tests ====================
    
    def test_initialization(self, manager):
        """Design contract: Manager initializes with default layout."""
        assert manager.get_default_layout() == "default"
        assert manager.get_rule_count() == 0
    
    # ==================== Rule Management Tests ====================
    
    def test_add_rule(self, manager):
        """Design contract: Rules can be added."""
        manager.add_rule("firefox", "browser_layout")
        
        assert manager.get_rule_count() == 1
    
    def test_add_multiple_rules(self, manager):
        """Design contract: Multiple rules can be registered."""
        manager.add_rule("firefox", "browser_layout")
        manager.add_rule("chrome", "browser_layout")
        manager.add_rule("vscode", "ide_layout")
        
        assert manager.get_rule_count() == 3
    
    def test_remove_rule(self, manager):
        """Design contract: Rules can be removed."""
        manager.add_rule("firefox", "browser_layout")
        result = manager.remove_rule("firefox", "browser_layout")
        
        assert result is True
        assert manager.get_rule_count() == 0
    
    def test_remove_nonexistent_rule(self, manager):
        """Design contract: Removing nonexistent rule is safe."""
        result = manager.remove_rule("nonexistent", "layout")
        
        assert result is False
    
    def test_clear_rules(self, manager):
        """Design contract: All rules can be cleared."""
        manager.add_rule("firefox", "browser_layout")
        manager.add_rule("chrome", "browser_layout")
        
        manager.clear_rules()
        
        assert manager.get_rule_count() == 0
    
    # ==================== String Pattern Matching Tests ====================
    
    def test_string_pattern_matches_substring(self, manager, window):
        """CRITICAL: String patterns match as case-insensitive substrings."""
        manager.add_rule("fire", "browser_layout")  # Substring of "firefox"
        
        result = manager.select_layout(window)
        
        assert result == "browser_layout"
    
    def test_string_pattern_case_insensitive(self, manager):
        """Design contract: String matching is case-insensitive."""
        manager.add_rule("FIREFOX", "browser_layout")
        window = WindowInfo(title="", class_="firefox", raw="")
        
        result = manager.select_layout(window)
        
        assert result == "browser_layout"
    
    def test_string_pattern_no_match(self, manager, window):
        """Design contract: Non-matching pattern returns default."""
        manager.add_rule("chrome", "browser_layout")
        
        result = manager.select_layout(window)
        
        assert result == "default"
    
    # ==================== Regex Pattern Matching Tests ====================
    
    def test_regex_pattern_matches(self, manager, window):
        """CRITICAL: Regex patterns work correctly."""
        pattern = re.compile(r"fire.*")
        manager.add_rule(pattern, "browser_layout")
        
        result = manager.select_layout(window)
        
        assert result == "browser_layout"
    
    def test_regex_pattern_no_match(self, manager, window):
        """Design contract: Non-matching regex returns default."""
        pattern = re.compile(r"^chrome$")
        manager.add_rule(pattern, "browser_layout")
        
        result = manager.select_layout(window)
        
        assert result == "default"
    
    # ==================== List Pattern Matching Tests ====================
    
    def test_list_of_patterns_or_logic(self, manager, window):
        """CRITICAL: List of patterns uses OR logic."""
        manager.add_rule(["chrome", "firefox", "safari"], "browser_layout")
        
        result = manager.select_layout(window)
        
        assert result == "browser_layout"
    
    def test_list_with_regex(self, manager, window):
        """Design contract: List can contain regex patterns."""
        pattern1 = re.compile(r"chrome")
        pattern2 = re.compile(r"fire.*")
        manager.add_rule([pattern1, pattern2], "browser_layout")
        
        result = manager.select_layout(window)
        
        assert result == "browser_layout"
    
    def test_list_mixed_types(self, manager, window):
        """Design contract: List can mix strings and regex."""
        pattern = re.compile(r"^chrome$")
        manager.add_rule([pattern, "firefox"], "browser_layout")
        
        result = manager.select_layout(window)
        
        assert result == "browser_layout"
    
    # ==================== Match Field Tests ====================
    
    def test_match_on_title(self, manager):
        """Design contract: Can match on window title."""
        manager.add_rule("Firefox Browser", "browser_layout", match_field="title")
        window = WindowInfo(title="Firefox Browser", class_="org.mozilla.firefox", raw="")
        
        result = manager.select_layout(window)
        
        assert result == "browser_layout"
    
    def test_match_on_class(self, manager, window):
        """Design contract: Can match on window class (default)."""
        manager.add_rule("firefox", "browser_layout", match_field="class")
        
        result = manager.select_layout(window)
        
        assert result == "browser_layout"
    
    def test_match_on_raw(self, manager):
        """Design contract: Can match on raw field."""
        manager.add_rule("raw", "test_layout", match_field="raw")
        window = WindowInfo(title="", class_="", raw="firefox raw")
        
        result = manager.select_layout(window)
        
        assert result == "test_layout"
    
    def test_invalid_match_field_no_match(self, manager, window):
        """Error handling: Invalid match field doesn't match."""
        manager.add_rule("firefox", "browser_layout", match_field="invalid")
        
        result = manager.select_layout(window)
        
        assert result == "default"
    
    # ==================== Priority Tests ====================
    
    def test_higher_priority_checked_first(self, manager, window):
        """CRITICAL: Higher priority rules checked before lower."""
        # Add low priority rule
        manager.add_rule("firefox", "low_priority_layout", priority=1)
        
        # Add high priority rule (more specific)
        manager.add_rule("fire", "high_priority_layout", priority=10)
        
        # High priority should win (checked first)
        result = manager.select_layout(window)
        
        assert result == "high_priority_layout"
    
    def test_first_matching_rule_wins(self, manager, window):
        """Design contract: First matching rule (by priority) wins."""
        # Both match, but first by priority should win
        manager.add_rule("firefox", "layout1", priority=5)
        manager.add_rule("fire", "layout2", priority=10)  # Higher priority
        
        result = manager.select_layout(window)
        
        assert result == "layout2"  # Higher priority wins
    
    def test_rules_sorted_by_priority(self, manager):
        """Design contract: Rules are sorted by priority after adding."""
        manager.add_rule("a", "layout_a", priority=1)
        manager.add_rule("b", "layout_b", priority=10)
        manager.add_rule("c", "layout_c", priority=5)
        
        # Check internal rule order
        assert manager._rules[0].priority == 10
        assert manager._rules[1].priority == 5
        assert manager._rules[2].priority == 1
    
    # ==================== Default Layout Tests ====================
    
    def test_default_layout_when_no_match(self, manager, window):
        """Design contract: Default layout used when no rules match."""
        manager.add_rule("chrome", "browser_layout")
        
        result = manager.select_layout(window)
        
        assert result == "default"
    
    def test_empty_rules_returns_default(self, manager, window):
        """Design contract: No rules always returns default."""
        result = manager.select_layout(window)
        
        assert result == "default"
    
    def test_set_default_layout(self, manager):
        """Design contract: Default layout can be changed."""
        manager.set_default_layout("new_default")
        
        assert manager.get_default_layout() == "new_default"
    
    def test_changed_default_used(self, manager, window):
        """Design contract: Changed default is used."""
        manager.set_default_layout("custom_default")
        manager.add_rule("chrome", "browser_layout")  # Won't match
        
        result = manager.select_layout(window)
        
        assert result == "custom_default"
    
    # ==================== Integration-Style Tests ====================
    
    def test_complex_rule_set(self, manager):
        """Logical test: Complex rule set with priorities."""
        # Add various rules
        manager.add_rule("firefox", "firefox_layout", priority=10)
        manager.add_rule(["chrome", "chromium"], "chrome_layout", priority=9)
        manager.add_rule(re.compile(r".*code.*"), "ide_layout", priority=5)
        manager.add_rule("terminal", "terminal_layout", priority=3)
        
        # Test Firefox
        firefox = WindowInfo(title="", class_="firefox", raw="")
        assert manager.select_layout(firefox) == "firefox_layout"
        
        # Test Chrome
        chrome = WindowInfo(title="", class_="chrome", raw="")
        assert manager.select_layout(chrome) == "chrome_layout"
        
        # Test VSCode
        vscode = WindowInfo(title="", class_="vscode", raw="")
        assert manager.select_layout(vscode) == "ide_layout"
        
        # Test unknown
        unknown = WindowInfo(title="", class_="unknown", raw="")
        assert manager.select_layout(unknown) == "default"
