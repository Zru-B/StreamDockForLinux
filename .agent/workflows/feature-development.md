---
description: Systematic workflow for developing new features with design-based testing
---

# Feature Development Workflow

This workflow outlines a systematic approach to designing, implementing, and testing new features with emphasis on requirements clarity, architectural integrity, and design-based testing.

## 🔑 Core Philosophy: Design First, Test the Design, Not the Implementation

**Key Principles:**
1. **Understand before coding** - Clarify all requirements upfront
2. **Validate architecture alignment** - Ensure new features fit existing design
3. **Test design contracts, not implementation details** - Tests should survive refactoring
4. **Code reuse first** - Adapt existing patterns before creating new ones
5. **Hybrid testing approach** - Write tests after code, but before merge

---

## Phase 0: Workspace Preparation

### 0. Ensure Clean State
- [ ] **Check git status**
  ```bash
  git status
  ```
  - Ensure you are on the correct branch (e.g., feature branch)
  - Verify working directory is clean
  - **Goal:** Start with a known good state

## Phase 1: Requirements & Design Validation

### 1. Gather & Clarify Requirements

**🚨 MANDATORY: You MUST ask clarifying questions before proceeding**

- [ ] **Document the feature request**
  - What problem does this feature solve?
  - Who is the user and what is their use case?
  - What is the expected behavior?

- [ ] **Ask clarifying questions** (Required - do not skip)
  - **Scope Questions:**
    - What is the minimum viable version of this feature?
    - Are there any constraints (performance, compatibility)?
    - Should this work with existing configurations?
  
  - **Behavior Questions:**
    - What should happen in edge cases? (e.g., device disconnected, invalid config)
    - How should this interact with existing features?
    - What are the expected inputs and outputs?
  
  - **Design Questions:**
    - Should this follow existing patterns (e.g., similar to CHANGE_LAYOUT action)?
    - Are there any breaking changes to existing functionality?
    - Does this require configuration changes?

- [ ] **Use `notify_user` to request clarification**
  - List all ambiguities and questions
  - Set `BlockedOnUser: true`
  - Wait for answers before design

### 2. Analyze Architecture Impact

- [ ] **Use Codebase Investigator (Recommended)**
  - Use `codebase_investigator` to map existing architecture
  - Identify dependencies and potential impact areas
  - Understand how similar features are implemented

- [ ] **Identify affected components**
  - Which modules/classes will be modified?
  - Which modules will be newly created?
  - Example: `ConfigLoader`, `DeviceManager`, `Layout`, `actions/`
  
- [ ] **Check for design conflicts**
  - Does this conflict with existing patterns?
  - Search codebase for similar functionality (avoid duplication)
  - Example: If adding a new action type, check how `CHANGE_LAYOUT` is implemented
  
- [ ] **Identify reusable code**
  - What existing code can be adapted?
  - Which helper functions/utilities already exist?
  - What design patterns are already established?

### 3. Design the Solution

- [ ] **Create implementation plan artifact**
  - Use `write_to_file` to create `implementation_plan.md`
  - Document high-level design approach
  - Explain how it fits with existing architecture
  
- [ ] **Define component changes**
  - New files to create
  - Existing files to modify
  - Configuration schema changes (if any)
  
- [ ] **Consider edge cases**
  - Error conditions
  - Device state changes
  - Configuration variations

- [ ] **Document architectural decisions**
  - Create a new record in `docs/architecture/adr/` for any significant design choices.

### 4. Identify Design Contracts to Test

**🔑 CRITICAL: Define WHAT to test based on design requirements, not implementation**

- [ ] **Document design contracts**
  
  **Ask: "What must remain true regardless of how we implement this?"**
  
  Types of design contracts:
  
  - **API Contracts**: Function signatures and return values
    - Example: `set_brightness(value: int) -> None` must clamp to [0, 100]
  
  - **Component Contracts**: How components interact
    - Example: "WindowMonitor MUST notify DeviceManager when focus changes"
  
  - **Configuration Contracts**: Config schema requirements
    - Example: "Each layout MUST have a unique name"
  
  - **Hardware Contracts**: Device behavior guarantees
    - Example: "Brightness changes MUST update device within 100ms"
  
  - **State Contracts**: System state invariants
    - Example: "Only one layout can be active at a time"

- [ ] **Write test scenarios (not test code yet)**
  
  For each design contract, document:
  - **Given**: Initial state/setup
  - **When**: Action/trigger
  - **Then**: Expected observable outcome
  
  **Example:**
  ```markdown
  ## Design Contract: Window Focus Triggers Layout Switch
  
  **Given**: Device has "default" and "firefox" layouts configured
  **When**: User switches window focus to Firefox
  **Then**: 
    - Device displays "firefox" layout
    - Key bindings match firefox layout configuration
    - Layout change completes within 500ms
  ```

- [ ] **Avoid testing implementation details**
  
  ❌ **Don't test:**
  - Private methods/attributes (`_internal_cache`)
  - Internal data structures
  - How something is implemented
  
  ✅ **Do test:**
  - Public APIs and observable behavior
  - Design requirements and contracts
  - What the feature accomplishes

### 5. Plan Test Types

- [ ] **Select test types based on feature category**
  
  **Configuration Feature** (new YAML fields, validation):
  - ✅ **Configuration Tests** - Required
  - ✅ **Unit Tests** - Required (validation logic)
  - Add sample configs to `tests/configs/`
  
  **New Action Type** (e.g., RUN_SCRIPT, BRIGHTNESS_CONTROL):
  - ✅ **Unit Tests** - Required (action logic)
  - ✅ **Integration Tests** - Required (action → device interaction)
  - ✅ **Hardware Tests** - Manual validation
  
  **Device Communication Feature** (HID, LED updates):
  - ✅ **Unit Tests** (mocked) - Required
  - ✅ **Hardware Integration Tests** - Required (manual)
  - Mock tests verify logic, hardware tests verify real device
  
  **System Integration Feature** (D-Bus, window monitoring):
  - ✅ **Integration Tests** (mocked) - Required
  - ✅ **End-to-End Tests** - Recommended (manual)
  
  **UI/Display Feature**:
  - ✅ **Unit Tests** - Required (layout logic)
  - ✅ **Hardware Tests** - Required (visual validation)

### 6. Get User Approval on Design

- [ ] **Request design review via `notify_user`**
  - Present implementation plan
  - Highlight architectural decisions
  - List design contracts to be tested
  - Include any concerns or trade-offs
  - Set `BlockedOnUser: true`
  - Wait for approval before implementation

---

## Phase 2: Implementation

### 7. Set Up Task Tracking

- [ ] **Create task breakdown**
  - Use `write_to_file` to create/update `task.md`
  - Break implementation into concrete steps
  - Example:
    ```markdown
    - [ ] Add new config fields to ConfigLoader schema
    - [ ] Implement brightness control action
    - [ ] Integrate with DeviceManager
    - [ ] Add design-based tests
    - [ ] Hardware validation
    - [ ] Update documentation
    ```

- [ ] **Set task boundary**
  - Use `task_boundary` tool in EXECUTION mode
  - Provide clear TaskName: e.g., "Implementing Brightness Control Feature"

### 8. Implement Core Functionality

- [ ] **🔑 PRIORITY: Search for existing code to reuse**
  - Check for similar features already implemented
  - Identify helper functions and utilities
  - Copy and adapt working patterns
  - Don't reinvent existing solutions

- [ ] **Create new files** (if needed)
  - Follow existing project structure
  - Use established naming conventions
  - Add module-level docstrings

- [ ] **Modify existing files**
  - **⚠️ SAFETY: Always `read_file` before `replace` or `write_file` to verify content**
  - Follow existing code patterns
  - Maintain consistency with surrounding code
  - Add type hints for all new functions
  - Use Google-style docstrings

- [ ] **Apply coding standards**
  - Follow PEP 8 and project style guide
  - Use proper error handling
  - Add logging at appropriate levels
  - Validate inputs defensively

### 9. Prototype & Refine

- [ ] **Test manually during development**
  - Quick validation that code works
  - Use real hardware if feature requires it
  - Iterate on implementation

- [ ] **Refactor as needed**
  - Extract common logic into helpers
  - Ensure functions have single responsibility
  - Keep functions under 50 lines

- [ ] **Update task.md as you progress**
  - Mark completed steps
  - Note any discoveries or changes

---

## Phase 3: Testing (Design-Based)

### 10. Write Design Contract Tests

**🎯 Goal: Test the WHAT (design requirements), not the HOW (implementation)**

- [ ] **Create test files**
  - Follow existing test structure
  - Use `test_*.py` naming convention
  - Organize by component: `test_config_loader.py`, `test_brightness_control.py`

- [ ] **Write tests for each design contract**
  
  For each contract identified in Phase 1:
  
  - [ ] **Test observable behavior**
    ```python
    def test_brightness_control_clamps_to_valid_range():
        """Design contract: Brightness must be clamped to [0, 100]"""
        # Test the WHAT, not the HOW
        device.set_brightness(150)
        assert device.get_brightness() == 100  # Observable outcome
        
        device.set_brightness(-10)
        assert device.get_brightness() == 0  # Observable outcome
    ```
  
  - [ ] **Test API contracts**
    ```python
    def test_layout_change_updates_device_keys():
        """Design contract: Layout changes must update all device key bindings"""
        manager.change_layout("media_layout")
        
        # Test public API behavior
        assert device.get_current_layout().name == "media_layout"
        assert len(device.key_bindings) == 15  # Expected key count
        assert device.key_bindings[0].action_type == "VOLUME_UP"
    ```
  
  - [ ] **Test component interactions**
    ```python
    def test_window_focus_triggers_layout_change():
        """Design contract: Window focus changes trigger layout switches"""
        # Arrange
        device.set_layout("default")
        
        # Act
        window_monitor.notify_focus_change("Firefox")
        
        # Assert - Test the design requirement
        assert device.get_current_layout().name == "firefox"
    ```

- [ ] **Add configuration tests** (if config changes)
  - Create sample configs in `tests/configs/`
  - Test valid configurations load successfully
  - Test invalid configurations raise validation errors
  - Example: `tests/configs/brightness_control_feature.yml`

- [ ] **Follow existing test patterns**
  - Reuse test fixtures
  - Match naming conventions
  - Use same mocking strategies

### 11. Add Additional Coverage

- [ ] **Test edge cases**
  - Device disconnected during operation
  - Invalid user input
  - Race conditions (if applicable)
  - Configuration edge cases

- [ ] **Test error handling**
  - Verify specific exceptions are raised
  - Check error messages are helpful
  - Ensure graceful degradation

- [ ] **Add integration tests** (if needed)
  - Test multiple components working together
  - Use mocks for hardware/system dependencies
  - Verify data flows correctly through components

---

## Phase 4: Verification

### 12. Verify Code Quality
- [ ] **Run Linting & Formatting**
  - Run project linters (e.g., `pylint`, `flake8`)
  - Run formatters (e.g., `black`, `isort`) if applicable
  - Ensure code adheres to project standards
  - Fix style issues before running tests

### 13. Run Automated Tests

- [ ] **Run new tests**
  ```bash
  pytest tests/test_new_feature.py -v
  ```
  - All new tests should pass
  
- [ ] **Run full test suite**
  ```bash
  pytest tests/ -v
  ```
  - Ensure no regressions
  - All existing tests still pass

- [ ] **Check test coverage**
  ```bash
  pytest --cov=src/NewModule tests/ --cov-report=term-missing
  ```
  - Aim for 80%+ coverage on new code
  - 100% on critical paths

### 14. Hardware Validation (if applicable)

- [ ] **Test with real StreamDock device**
  - Mark hardware tests with `@pytest.mark.hardware`
  - Run manually: `pytest -m hardware tests/`
  
- [ ] **Validate observable behavior**
  - LEDs update correctly
  - Key presses trigger correct actions
  - Brightness changes are visible
  - Timing requirements met

- [ ] **Test device reconnection** (if relevant)
  - Unplug/replug device
  - Verify feature still works
  - Check for resource leaks

### 15. Manual Testing

- [ ] **Test with user's actual use case**
  - Create a config matching the original request
  - Verify feature works as expected
  - Check edge cases manually

- [ ] **Performance validation**
  - Measure response times (if performance-sensitive)
  - Check memory usage during extended operation
  - Verify no obvious performance regressions

---

## Phase 5: Documentation

### 16. Update Documentation

- [ ] **Update README.md** (if user-facing)
  - Add feature description
  - Provide configuration examples
  - Show usage examples

- [ ] **Update API documentation**
  - Add docstrings to new functions/classes
  - Document parameters and return values
  - Provide code examples

- [ ] **Add configuration examples**
  - Show minimal working config
  - Show advanced usage
  - Document all new config fields

- [ ] **Update relevant guides**
  - Installation guide (if dependencies changed)
  - Configuration guide (if schema changed)
  - Troubleshooting guide (if new errors possible)

- [ ] **Synchronize agent documentation**
  - Ensure `docs/architecture/AGENT_KNOWLEDGE_BASE.md` and `docs/architecture/DEPENDENCY_MAP.md` are updated.
  - **Update `docs/architecture/GLOSSARY.md`** if new classes, modules, or domain terminology were introduced.
  - Verify that code comments and docstrings match the new implementation.

### 17. Create Walkthrough

- [ ] **Document what was built**
  - Use `write_to_file` to create/update `walkthrough.md`
  - Explain the feature and its implementation
  - Show test results
  - Include examples and screenshots (if applicable)

---

## Phase 6: Completion

### 18. Final Checklist

- [ ] **Code quality**
  - ✅ All code follows style guide
  - ✅ Type hints on all functions
  - ✅ Proper error handling
  - ✅ Logging at appropriate levels

- [ ] **Testing**
  - ✅ All automated tests pass
  - ✅ Design contracts are tested
  - ✅ Hardware validated (if applicable)
  - ✅ No test coverage regressions

- [ ] **Documentation**
  - ✅ README updated
  - ✅ Docstrings added
  - ✅ Examples provided
  - ✅ User guide updated

- [ ] **Integration**
  - ✅ No conflicts with existing features
  - ✅ Follows established patterns
  - ✅ Reused existing code where possible

### 19. User Communication

- [ ] **Provide completion summary**
  - Explain what was implemented
  - Show test results (all passing)
  - Provide usage examples
  - Highlight any limitations or known issues
  - Point to documentation updates

### 20. Final Cleanup
- [ ] **Check git status**
  ```bash
  git status
  ```
  - Verify all new files are tracked
  - Ensure changes are staged correctly
  - **Remind user to commit changes**

---

## Best Practices

### Requirements & Design
✅ **Always ask clarifying questions** - Don't assume, ask the user  
✅ **Validate architecture fit** - Ensure new features align with existing design  
✅ **Identify design contracts early** - Know what to test before coding  
✅ **Get user approval on design** - Avoid wasted effort on wrong approaches  

### Implementation
✅ **Search for existing code FIRST** - Reuse before creating  
✅ **Follow established patterns** - Maintain architectural consistency  
✅ **Prototype freely** - Iterate on implementation without rigid tests  
✅ **Refactor as you go** - Keep code clean during development  

### Testing
✅ **Test design contracts, not implementation** - Tests should survive refactoring  
✅ **Write tests after code, before merge** - Hybrid approach for flexibility  
✅ **Focus on observable behavior** - Test what users/systems can observe  
✅ **Avoid testing private methods** - Only test public APIs  
✅ **Use real configs in tests** - Validate real-world usage  

### Documentation
✅ **Document as you go** - Update docs while context is fresh  
✅ **Provide examples** - Show real usage, not just API reference  
✅ **Explain design decisions** - Help future developers understand why  

---

## Common Pitfalls to Avoid

❌ **Skipping requirements clarification** - Always ask questions upfront  
❌ **Ignoring architecture alignment** - Features should fit existing design  
❌ **Testing implementation details** - Test design contracts instead  
❌ **Writing tests that break on refactor** - Test observable behavior, not internals  
❌ **Duplicating existing code** - Search and reuse first  
❌ **Skipping hardware validation** - Manual testing is essential for hardware features  
❌ **Forgetting documentation** - Undocumented features are unusable  
❌ **No user approval on design** - Get buy-in before investing effort  

---

## Design-Based Testing Examples

### ❌ Bad: Implementation-Coupled Test
```python
def test_layout_manager_internal_cache_updated():
    """This breaks if we refactor the caching mechanism"""
    manager.change_layout("media")
    assert manager._layout_cache["current"] == "media"  # ❌ Testing internal detail
    assert isinstance(manager._cache_dict, dict)  # ❌ Testing data structure choice
```

### ✅ Good: Design Contract Test
```python
def test_layout_change_updates_device_state():
    """Design contract: Layout changes must update device within 500ms"""
    # Arrange
    device.set_layout("default")
    start_time = time.time()
    
    # Act
    manager.change_layout("media")
    
    # Assert - Test observable behavior
    assert device.get_current_layout().name == "media"  # ✅ Observable outcome
    assert device.key_bindings[0].action == "VOLUME_UP"  # ✅ Design requirement
    assert time.time() - start_time < 0.5  # ✅ Performance contract
```

---

## Tools & Commands Reference

### Testing
```bash
# Run specific test
pytest tests/test_feature.py::TestClass::test_method -v

# Run all new tests
pytest tests/test_feature.py -v

# Run with coverage
pytest --cov=src/NewModule tests/ --cov-report=term-missing

# Run hardware tests (manual)
pytest -m hardware tests/

# Check coverage for specific module
pytest --cov=src/NewModule --cov-report=html tests/
```

### Configuration Validation
```bash
# Quick config loading test
python -c "from src.StreamDock.ConfigLoader import ConfigLoader; ConfigLoader('config.yml').load()"

# Validate new config fields
python -c "from src.StreamDock.ConfigLoader import ConfigLoader; c = ConfigLoader('tests/configs/new_feature.yml'); c.load(); print(c.config)"
```

### Hardware Testing
```bash
# List connected devices
python -c "from src.StreamDock.DeviceManager import DeviceManager; print(DeviceManager().enumerate())"

# Quick device test
python -c "from src.StreamDock import Device; d = Device(); d.open(); d.set_brightness(50); d.close()"

# Inspect changes without pager (recommended for agents)
git --no-pager diff
```
