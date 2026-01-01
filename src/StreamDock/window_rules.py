"""
Window matching rules and rule engine.

This module provides a type-safe rule engine for matching windows and
executing callbacks based on window properties.
"""
import logging
import re
from dataclasses import dataclass
from enum import Enum
from typing import Callable, List, Optional, Pattern

from .window_detection import WindowInfo


class MatchField(Enum):
    """Fields that can be used for window matching."""
    TITLE = "title"
    CLASS = "class"
    RAW = "raw"  # Backward compatibility
    

@dataclass
class WindowRule:
    """
    A rule that matches windows and executes a callback.
    
    Attributes:
        pattern: String or regex pattern to match
        callback: Function to call when pattern matches
        match_field: Which field to match against
        is_regex: Whether pattern is a regex
        priority: Rule priority (higher = checked first)
    """
    pattern: str | Pattern
    callback: Callable[[dict], None]
    match_field: MatchField = MatchField.CLASS
    is_regex: bool = False
    priority: int = 0
    
    def __post_init__(self):
        """Validate and normalize the rule."""
        if isinstance(self.pattern, re.Pattern):
            self.is_regex = True
        
        # Convert string match_field to enum if needed
        if isinstance(self.match_field, str):
            try:
                self.match_field = MatchField(self.match_field)
            except ValueError:
                # Default to CLASS for unknown fields
                self.match_field = MatchField.CLASS
    
    def matches(self, window_info: WindowInfo) -> bool:
        """
        Check if this rule matches the given window.
        
        Args:
            window_info: Window information to match against
            
        Returns:
            True if the rule matches, False otherwise
        """
        # Get the appropriate field value
        if self.match_field == MatchField.TITLE:
            field_value = window_info.title
        elif self.match_field == MatchField.CLASS:
            field_value = window_info.window_class
        elif self.match_field == MatchField.RAW:
            field_value = window_info.title  # Raw is just title for backward compat
        else:
            field_value = ""
        
        if not field_value:
            return False
        
        # Perform the match
        if self.is_regex:
            return self.pattern.search(field_value) is not None
        else:
            return self.pattern.lower() in field_value.lower()
    
    def execute(self, window_info: WindowInfo) -> None:
        """
        Execute the callback with window info.
        
        Args:
            window_info: Window information to pass to callback
        """
        try:
            # Convert to dict for backward compatibility
            self.callback(window_info.to_dict())
        except Exception as e:
            logger = logging.getLogger(__name__)
            logger.exception(f"Error executing rule callback: {e}")


class RuleEngine:
    """
    Manages window rules and executes matching logic.
    
    Rules are checked in priority order (highest first), then in
    the order they were added. Only the first matching rule is executed.
    """
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.rules: List[WindowRule] = []
        self.default_callback: Optional[Callable[[dict], None]] = None
    
    def add_rule(
        self,
        pattern: str | Pattern,
        callback: Callable[[dict], None],
        match_field: str | MatchField = MatchField.CLASS,
        priority: int = 0
    ) -> None:
        """
        Add a new window rule.
        
        Args:
            pattern: String or regex pattern to match
            callback: Function to call when matched
            match_field: Field to match against ('title', 'class', or 'raw')
            priority: Rule priority (higher = checked first)
        """
        rule = WindowRule(
            pattern=pattern,
            callback=callback,
            match_field=match_field if isinstance(match_field, MatchField) else MatchField(match_field),
            priority=priority
        )
        self.rules.append(rule)
        
        # Sort by priority (highest first), then maintain insertion order
        self.rules.sort(key=lambda r: (-r.priority, self.rules.index(r) if r in self.rules else 0))
    
    def remove_rule(self, pattern: str | Pattern) -> bool:
        """
        Remove a rule by its pattern.
        
        Args:
            pattern: Pattern of the rule to remove
            
        Returns:
            True if a rule was removed, False otherwise
        """
        original_len = len(self.rules)
        self.rules = [r for r in self.rules if r.pattern != pattern]
        return len(self.rules) < original_len
    
    def clear_rules(self) -> None:
        """Clear all window rules."""
        self.rules.clear()
    
    def set_default_callback(self, callback: Callable[[dict], None]) -> None:
        """
        Set a callback to execute when no rules match.
        
        Args:
            callback: Function to call when no rules match
        """
        self.default_callback = callback
    
    def find_matching_rule(self, window_info: WindowInfo) -> Optional[WindowRule]:
        """
        Find the first rule that matches the given window.
        
        Args:
            window_info: Window information to match
            
        Returns:
            First matching WindowRule, or None if no match
        """
        for rule in self.rules:
            if rule.matches(window_info):
                return rule
        return None
    
    def execute_rules(self, window_info: WindowInfo) -> bool:
        """
        Execute matching rule or default callback for the given window.
        
        Args:
            window_info: Window information to match and execute
            
        Returns:
            True if any rule matched, False otherwise
        """
        if not window_info or not window_info.is_valid():
            return False
        
        # Find and execute first matching rule
        matching_rule = self.find_matching_rule(window_info)
        if matching_rule:
            self.logger.debug(
                f"Rule matched for window '{window_info.title}' "
                f"(class: {window_info.window_class})"
            )
            matching_rule.execute(window_info)
            return True
        
        # No rules matched, execute default callback if set
        if self.default_callback:
            try:
                self.default_callback(window_info.to_dict())
            except Exception as e:
                self.logger.exception(f"Error executing default callback: {e}")
        
        return False
