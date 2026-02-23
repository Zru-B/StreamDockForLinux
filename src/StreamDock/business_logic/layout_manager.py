"""
Layout management and rule matching - Pure business logic.

This module provides layout selection logic extracted from WindowMonitor,
focusing purely on rule matching and layout selection.
No device dependencies - pure business logic.
"""

import logging
import re
from dataclasses import dataclass
from typing import Callable, List, Optional, Pattern, Union

from StreamDock.domain.Models import WindowInfo


logger = logging.getLogger(__name__)


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
        logger.debug(f"LayoutManager initialized with default layout: {default_layout_name}")
    
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
        logger.debug(f"Added rule: {match_field}~{pattern} -> {layout_name} (priority={priority})")
    
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
                logger.debug(f"Removed rule: {pattern} -> {layout_name}")
                return True
        
        logger.debug(f"Rule not found: {pattern} -> {layout_name}")
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
        logger.debug(f"Cleared {count} rules")
    
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
                    f"Window '{window_info.class_}' matched rule '{rule.pattern}' "
                    f"-> layout '{rule.layout_name}'"
                )
                return rule.layout_name
        
        logger.debug(f"No rules matched for '{window_info.class_}', using default '{self._default_layout_name}'")
        return self._default_layout_name
    
    def _matches_rule(self, window_info: WindowInfo, rule: LayoutRule) -> bool:
        """
        PURE BUSINESS LOGIC: Check if window matches rule.
        
        Supports multiple pattern types:
        - String: Case-insensitive substring match
        - Pattern (regex): Regex match with search()
        - List: Match any pattern (OR logic)
        
        Args:
            window_info: Window to match
            rule: Rule to check
            
        Returns:
            True if window matches rule pattern, False otherwise
        """
        # Get field value from WindowInfo
        try:
            if rule.match_field == 'title':
                field_value = window_info.title
            elif rule.match_field == 'class':
                field_value = window_info.class_
            elif rule.match_field == 'raw':
                field_value = window_info.raw
            else:
                logger.warning(f"Invalid match_field: {rule.match_field}")
                return False
        except AttributeError:
            logger.debug(f"Window missing field: {rule.match_field}")
            return False
        
        # Normalize pattern to list for uniform processing
        patterns = rule.pattern if isinstance(rule.pattern, list) else [rule.pattern]
        
        # Match against any pattern (OR logic)
        for pattern in patterns:
            if isinstance(pattern, Pattern):
                # Regex match
                if pattern.search(field_value):
                    return True
            elif isinstance(pattern, str):
                # Substring match (case-insensitive)
                if pattern.lower() in field_value.lower():
                    return True
        
        return False
    
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
        logger.debug(f"Default layout changed: {old_default} -> {layout_name}")
    
    def get_default_layout(self) -> str:
        """
        Get current default layout name.
        
        Returns:
            Default layout name
        """
        return self._default_layout_name
