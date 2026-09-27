"""
Layout management and rule matching - Pure business logic.

This module provides layout selection logic extracted from WindowMonitor,
focusing purely on rule matching and layout selection.
No device dependencies - pure business logic.
"""

import logging
import re
from dataclasses import dataclass
from typing import List, Pattern, Union

from StreamDock.domain.Models import WindowInfo

logger = logging.getLogger(__name__)

# Titles come from any window, so any program can set them. Every rule's
# pattern runs against the value on each poll; capping its length bounds that
# work (a user regex prone to backtracking included).
MAX_MATCH_LENGTH = 512


@dataclass
class LayoutRule:
    """
    Rule for matching windows to layouts.

    A layout rule defines a pattern to match against window information
    and specifies which layout should be selected when the pattern matches.

    Attributes:
        pattern: String, regex Pattern, or list thereof for matching
        layout_name: Name of layout to select when matched
        match_field: Field to match against ('title', 'class', 'raw')
        priority: Priority for rule ordering (higher = checked first)
    """
    pattern: Union[str, Pattern, List[Union[str, Pattern]]]
    layout_name: str
    match_field: str = 'class'
    priority: int = 0


def rule_patterns(window_name, is_regex: bool = False):
    """
    A rule's ``window_name`` as the matcher takes it.

    With ``is_regex`` every pattern becomes a case-insensitive regex; a plain
    word still matches anywhere, as ``search()`` does. Raises ``re.error``
    for a pattern that does not compile.
    """
    if not is_regex:
        return window_name
    if isinstance(window_name, list):
        return [re.compile(pattern, re.IGNORECASE) for pattern in window_name]
    return re.compile(window_name, re.IGNORECASE)


def window_matches(window_info: WindowInfo, pattern, match_field: str = 'class') -> bool:
    """
    Whether a window satisfies a rule's pattern.

    Shared with the rule editor's live preview, so what the editor says
    matches is what the runtime will switch on.

    Supports:
    - String: case-insensitive substring match
    - Pattern (regex): ``search()``
    - List: any of the above (OR)
    """
    if match_field not in ('title', 'class', 'raw'):
        logger.warning("Invalid match_field: %s", match_field)
        return False
    field_value = getattr(window_info, 'class_' if match_field == 'class' else match_field, None)
    if field_value is None:
        logger.debug("Window missing field: %s", match_field)
        return False
    if isinstance(field_value, str):
        field_value = field_value[:MAX_MATCH_LENGTH]

    for candidate in pattern if isinstance(pattern, list) else [pattern]:
        if isinstance(candidate, Pattern):
            if candidate.search(field_value):
                return True
        elif isinstance(candidate, str):
            if candidate.lower() in field_value.lower():
                return True
    return False


class LayoutManager:
    """
    Pure business logic for layout selection based on window matching.

    This class manages a set of layout selection rules and determines which
    layout should be active based on the current window information.

    Responsibilities:
    - Register layout rules (window pattern → layout name)
    - Match window info against rules
    - Select appropriate layout based on match
    - Maintain default layout

    Design Principles:
    - PURE business logic - no device control, no window detection
    - Returns layout names (strings), not layout objects
    - String-based interface decouples from Layout class
    - Easily testable with mock WindowInfo

    Extracted from: WindowMonitor's rule matching logic
    Dependencies: WindowInfo model only (no infrastructure)
    """

    def __init__(self, default_layout_name: str = "default"):
        """
        Initialize layout manager.

        Args:
            default_layout_name: Name of default layout when no rules match

        Design Contract:
            - Rules registered via add_rule()
            - Matching happens via select_layout()
            - Rules sorted by priority (highest first)
        """
        self._rules: List[LayoutRule] = []
        self._default_layout_name = default_layout_name
        logger.debug("LayoutManager initialized with default layout: %s", default_layout_name)

    def add_rule(self,
                 pattern: Union[str, Pattern, List[Union[str, Pattern]]],
                 layout_name: str,
                 match_field: str = 'class',
                 priority: int = 0) -> None:
        """
        Add a layout selection rule.

        Rules with higher priority are checked first. If multiple rules match,
        the first one (by priority order) wins.

        Args:
            pattern: Pattern(s) to match against window field
                    - str: Case-insensitive substring match
                    - Pattern: Regex match
                    - List: Match any pattern (OR logic)
            layout_name: Layout to select when matched
            match_field: Field to match ('title', 'class', 'raw')
            priority: Rule priority (higher = checked first, default: 0)

        Design Contract:
            - Rules with higher priority checked first
            - First matching rule wins
            - Supports string (substring), regex, or list of patterns
        """
        rule = LayoutRule(
            pattern=pattern,
            layout_name=layout_name,
            match_field=match_field,
            priority=priority
        )
        self._rules.append(rule)
        self._sort_rules()
        logger.debug("Added rule: %s~%s -> %s (priority=%d)", match_field, pattern, layout_name, priority)

    def remove_rule(self, pattern: Union[str, Pattern, List], layout_name: str) -> bool:
        """
        Remove a previously added rule.

        Args:
            pattern: Pattern to match (must match exactly)
            layout_name: Layout name (must match exactly)

        Returns:
            True if rule was found and removed, False otherwise

        Design Contract:
            - Safe to call even if rule doesn't exist
            - Both pattern and layout_name must match
        """
        for rule in self._rules:
            if rule.pattern == pattern and rule.layout_name == layout_name:
                self._rules.remove(rule)
                logger.debug("Removed rule: %s -> %s", pattern, layout_name)
                return True

        logger.debug("Rule not found: %s -> %s", pattern, layout_name)
        return False

    def clear_rules(self) -> None:
        """
        Remove all rules.

        Design Contract:
            - After clearing, select_layout() always returns default
            - Idempotent - safe to call multiple times
        """
        count = len(self._rules)
        self._rules.clear()
        logger.debug("Cleared %d rules", count)

    def select_layout(self, window_info: WindowInfo) -> str:
        """
        PURE BUSINESS LOGIC: Select layout based on window info.

        Matches window against rules in priority order (highest first).
        Returns first matching layout name, or default if no match.

        Args:
            window_info: Window information to match

        Returns:
            Layout name to use (guaranteed non-empty)

        Design Contract:
            - Returns layout name (string), not layout object
            - Caller responsible for looking up actual layout
            - Always returns a layout name (default if no match)
            - First matching rule wins (by priority order)
        """
        for rule in self._rules:
            if self._matches_rule(window_info, rule):
                logger.debug(
                    "Window '%s' matched rule '%s' -> layout '%s'",
                    window_info.class_, rule.pattern, rule.layout_name
                )
                return rule.layout_name

        logger.debug("No rules matched for '%s', using default '%s'",
                     window_info.class_, self._default_layout_name)
        return self._default_layout_name

    def _matches_rule(self, window_info: WindowInfo, rule: LayoutRule) -> bool:
        return window_matches(window_info, rule.pattern, rule.match_field)

    def _sort_rules(self) -> None:
        """
        Sort rules by priority (highest first).

        Called after adding rules to maintain priority ordering.
        """
        self._rules.sort(key=lambda r: r.priority, reverse=True)

    def get_rule_count(self) -> int:
        """
        Get number of registered rules.

        Returns:
            Number of rules currently registered
        """
        return len(self._rules)

    def set_default_layout(self, layout_name: str) -> None:
        """
        Change default layout.

        Args:
            layout_name: New default layout name

        Design Contract:
            - Used when no rules match
            - Can be changed at any time
        """
        old_default = self._default_layout_name
        self._default_layout_name = layout_name
        logger.debug("Default layout changed: %s -> %s", old_default, layout_name)

    def get_default_layout(self) -> str:
        """
        Get current default layout name.

        Returns:
            Default layout name
        """
        return self._default_layout_name
