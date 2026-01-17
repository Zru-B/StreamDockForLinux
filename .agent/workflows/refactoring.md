---
description: Systematic workflow for refactoring code while preserving behavior and design
---

# Refactoring Workflow

This workflow outlines a systematic approach to refactoring code safely, ensuring behavior preservation, test integrity, and improved maintainability without breaking existing functionality.

## 🔑 Core Philosophy: Tests First, Refactor Safely, Maintain Design Contracts

**Key Principles:**
1. **Green before refactoring** - All tests must pass before you start
2. **Test behavior, not implementation** - Tests should survive refactoring
3. **Small, incremental changes** - Refactor in tiny steps with test validation
4. **Preserve design contracts** - Don't accidentally change requirements
5. **Document design decisions** - Explain why, not just what

---

## When to Refactor

### Good Reasons to Refactor:
✅ Code duplication (DRY violation)  
✅ Functions longer than 50 lines  
✅ Deep nesting (> 3 levels)  
✅ Poor naming or unclear intent  
✅ Tight coupling between components  
✅ Difficult to test code  
✅ Performance bottlenecks  
✅ Preparing for new feature implementation  

### Bad Reasons to Refactor:
❌ "I don't like this style" (personal preference)  
❌ "This is old code" (if it works and is tested)  
❌ "Let me rewrite this from scratch" (without justification)  
❌ During active bug investigation  
❌ Right before a release deadline  

---

## Phase 0: Workspace Preparation

### 0. Ensure Clean State
- [ ] **Check git status**
  ```bash
  git status
  ```
  - Ensure working directory is clean
  - **Refactoring requires a clean slate to easily rollback if tests fail**

## Phase 1: Preparation & Safety Checks

### 1. Identify Refactoring Opportunity

- [ ] **Use Codebase Investigator (Recommended)**
  - Use `codebase_investigator` to map dependencies
  - Identify all usages of the code to be refactored
  - Assess impact on other modules

- [ ] **Document what needs refactoring**
  - Which code is problematic?
  - What specific issues exist?
  - How will refactoring improve it?

- [ ] **Define success criteria**
  - What will the refactored code achieve?
  - What design improvements are expected?
  - Example: "Extract duplicate layout parsing into single helper function"

- [ ] **Assess scope and risk**
  - **Low Risk**: Local variable renaming, extract method in single file
  - **Medium Risk**: Restructuring class methods, changing internal data structures
  - **High Risk**: Changing public APIs, refactoring cross-component interactions
  
  **For high-risk refactoring**: Consider creating an implementation plan and getting user approval

### 2. Ensure Comprehensive Test Coverage

**🚨 CRITICAL: You MUST have tests before refactoring**

- [ ] **Check existing test coverage**
  ```bash
  pytest --cov=src/ModuleToRefactor tests/ --cov-report=term-missing
  ```
  - Identify untested code paths
  - Note coverage percentage

- [ ] **If coverage is insufficient (< 80%):**
  - ⚠️ **STOP: Add tests FIRST before refactoring**
  - Write tests for current behavior (even if code is ugly)
  - Focus on **design contracts** and **observable behavior**
  - Tests should validate WHAT the code does, not HOW
  
  Example:
  ```python
  def test_layout_parser_extracts_all_keys():
      """Design contract: Parser must extract all key definitions"""
      config = load_test_config("complex_layout.yml")
      layout = parse_layout(config)  # Current implementation (even if ugly)
      
      # Test the WHAT (design requirement)
      assert len(layout.keys) == 15
      assert layout.keys[0].action_type == "CHANGE_LAYOUT"
      # These tests will pass before AND after refactoring
  ```

- [ ] **Run all tests and verify they PASS**
  ```bash
  pytest tests/ -v
  ```
  - ✅ All tests green = Safe to refactor
  - ❌ Any failures = Fix tests first, don't refactor yet

### 3. Create Refactoring Plan

- [ ] **Document refactoring approach**
  - Create `implementation_plan.md` (for major refactoring)
  - Or add notes to `task.md` (for minor refactoring)
  
- [ ] **Break down into small steps**
  - Each step should be independently testable
  - Example for extracting duplicate code:
    ```markdown
    1. Extract helper function with current duplicated code
    2. Replace first usage with helper call
    3. Run tests (should pass)
    4. Replace second usage with helper call
    5. Run tests (should pass)
    6. Remove duplicate code
    7. Run tests (should pass)
    ```

- [ ] **Identify potential breaking points**
  - Public API changes
  - Configuration schema changes
  - Cross-component dependencies

- [ ] **Document architectural changes**
  - If refactoring involves a significant shift in design patterns, document it in `docs/architecture/adr/`.

### 4. Get Approval (for significant refactoring)

- [ ] **For high-risk or large-scale refactoring**
  - Use `notify_user` to request approval
  - Explain the rationale and expected benefits
  - Highlight any risks or breaking changes
  - Set `BlockedOnUser: true`
  - Wait for approval before proceeding

---

## Phase 2: Incremental Refactoring

### 5. Set Up Task Tracking

- [ ] **Create or update `task.md`**
  - List all refactoring steps
  - Track progress as you go
  
- [ ] **Set task boundary**
  - Use `task_boundary` tool in EXECUTION mode
  - TaskName: e.g., "Refactoring Layout Parser"

### 6. Refactor in Small Steps

**🔑 RULE: Make ONE change at a time, test after EACH change**
**⚠️ SAFETY: Always `read_file` before `replace` or `write_file` to verify content**

#### Common Refactoring Patterns:

##### **Extract Method/Function**
- [ ] Identify duplicated or complex code block
- [ ] Extract into new function with descriptive name
- [ ] Add type hints and docstring
- [ ] Replace original code with function call
- [ ] Run tests → Should pass

##### **Rename for Clarity**
- [ ] Identify poorly named variable/function/class
- [ ] Rename to descriptive, self-documenting name
- [ ] Update all references
- [ ] Run tests → Should pass

##### **Simplify Conditionals**
- [ ] Identify complex conditional logic
- [ ] Extract into well-named predicate functions
- [ ] Example:
  ```python
  # Before
  if device.is_connected and device.brightness > 0 and device.layout is not None:
  
  # After
  def is_device_ready(device: Device) -> bool:
      return device.is_connected and device.brightness > 0 and device.layout is not None
  
  if is_device_ready(device):
  ```
- [ ] Run tests → Should pass

##### **Reduce Nesting**
- [ ] Identify deeply nested code (> 3 levels)
- [ ] Use early returns or guard clauses
- [ ] Example:
  ```python
  # Before
  def process(data):
      if data:
          if data.is_valid():
              if data.has_layout():
                  return process_layout(data)
  
  # After
  def process(data):
      if not data:
          return None
      if not data.is_valid():
          return None
      if not data.has_layout():
          return None
      return process_layout(data)
  ```
- [ ] Run tests → Should pass

##### **Extract Class**
- [ ] Identify group of related methods/data
- [ ] Create new class with single responsibility
- [ ] Move related methods and data
- [ ] Update references
- [ ] Run tests → Should pass

##### **Replace Magic Numbers/Strings**
- [ ] Identify hardcoded values
- [ ] Extract to named constants or config
- [ ] Example:
  ```python
  # Before
  if brightness > 100:
  
  # After
  MAX_BRIGHTNESS = 100
  if brightness > MAX_BRIGHTNESS:
  ```
- [ ] Run tests → Should pass

### 7. Maintain Design Contracts

**🚨 CRITICAL: Don't accidentally change behavior**

- [ ] **Preserve public APIs**
  - If changing function signatures, ensure backward compatibility
  - Or explicitly mark as breaking change

- [ ] **Preserve design contracts**
  - The WHAT (observable behavior) must remain the same
  - Only the HOW (implementation) changes

- [ ] **Update tests only if needed**
  - ✅ Update if testing implementation details (those tests were wrong)
  - ❌ Don't update if testing design contracts (behavior changed = bug in refactor)

### 8. Test After Every Change

- [ ] **Run affected tests after each small change**
  ```bash
  pytest tests/test_refactored_module.py -v
  ```

- [ ] **If tests fail:**
  - ⚠️ STOP: Refactoring broke something
  - Revert the change
  - Understand why it failed
  - Fix the refactoring approach
  
- [ ] **If tests pass:**
  - ✅ Change is safe
  - Commit or move to next step
  - Update `task.md`

### 9. Update Related Tests (if needed)

- [ ] **If you removed implementation-coupled tests:**
  - Document why they were removed
  - Ensure design contracts are still tested
  
- [ ] **If tests need updates due to refactoring:**
  - Only update tests that were testing implementation details
  - Design contract tests should NOT need updates
  - Example:
    ```python
    # This test needs update (was testing implementation)
    def test_parser_uses_dict_cache():  # ❌ Implementation detail
        parser.parse(config)
        assert isinstance(parser._cache, dict)  # Remove this test
    
    # This test stays unchanged (tests design contract)
    def test_parser_loads_all_layouts():  # ✅ Design contract
        layouts = parser.parse(config)
        assert len(layouts) == 3  # Still valid after refactoring
    ```

---

## Phase 3: Verification

### 10. Verify Code Quality
- [ ] **Run Linting & Formatting**
  - Run project linters on refactored files
  - Ensure refactoring didn't introduce style regressions
  - **Code should be cleaner than when you started**

### 11. Run Full Test Suite

- [ ] **Run all tests**
  ```bash
  pytest tests/ -v
  ```
  - All tests must pass
  - No new failures
  - No skipped tests that were previously passing

- [ ] **Check test coverage**
  ```bash
  pytest --cov=src tests/ --cov-report=term-missing
  ```
  - Coverage should be same or better
  - No reduction in coverage from refactoring

### 12. Performance Validation (if relevant)

- [ ] **For performance-focused refactoring:**
  - Measure before/after metrics
  - Ensure performance improved or stayed the same
  - Example:
    ```bash
    # Before refactoring
    python -m timeit -s "from module import func" "func(data)"
    
    # After refactoring (should be same or faster)
    python -m timeit -s "from module import func" "func(data)"
    ```

- [ ] **For general refactoring:**
  - Quick smoke test that app still performs well
  - No obvious slowdowns

### 13. Manual Testing (if hardware-related)

- [ ] **Test with real StreamDock device** (if refactoring affects hardware)
  - Verify device behavior unchanged
  - Check LED updates, key presses, etc.
  - Ensure no regressions in user experience

---

## Phase 4: Documentation & Completion

### 14. Update Documentation

- [ ] **Update code comments** (if significant changes)
  - Explain new design patterns
  - Document why refactoring was done
  
- [ ] **Update docstrings** (if function signatures changed)
  - Accurate parameter descriptions
  - Correct return types
  - Updated examples

- [ ] **Update architecture docs** (if structural changes)
  - README.md if high-level design changed
  - API documentation if public interfaces changed
  - Update `docs/architecture/AGENT_KNOWLEDGE_BASE.md` and `docs/architecture/DEPENDENCY_MAP.md`.

### 15. Code Review (self-check)

- [ ] **Review your changes**
  - Does code follow style guide?
  - Are type hints present?
  - Is naming clear and self-documenting?
  - Are functions under 50 lines?
  - Is error handling appropriate?

- [ ] **Check for cleanup opportunities**
  - Remove dead code
  - Remove unused imports (`autoflake`)
  - Sort imports (`isort`)
  - Remove commented-out code
  - Remove debug logging

### 16. Final Summary

- [ ] **Document what was refactored**
  - Use `write_to_file` to create/update `walkthrough.md`
  - Explain what was refactored and why
  - Show before/after code snippets (for clarity)
  - Confirm all tests pass
  - Note any design improvements

### 17. Final Cleanup
- [ ] **Check git status**
  ```bash
  git status
  ```
  - Verify changes are ready for commit
  - Ensure no unintended files were modified

---

## Best Practices

### Before Refactoring
✅ **All tests must pass** - Green before you start  
✅ **Ensure test coverage exists** - Add tests if coverage < 80%  
✅ **Tests should validate design, not implementation** - Tests must survive refactoring  
✅ **Plan small, incremental steps** - Don't try to refactor everything at once  

### During Refactoring
✅ **One change at a time** - Make smallest possible change, then test  
✅ **Test after every change** - Don't accumulate untested changes  
✅ **Preserve design contracts** - Observable behavior must not change  
✅ **Use descriptive names** - Make code self-documenting  
✅ **Commit frequently** - Small, atomic commits make rollback easier  

### After Refactoring
✅ **All tests must still pass** - Green when you're done  
✅ **Coverage must not decrease** - Should improve or stay same  
✅ **Update documentation** - Code comments, docstrings, design docs  
✅ **Review for cleanup** - Remove dead code, unused imports  

---

## Common Pitfalls to Avoid

❌ **Refactoring without tests** - Recipe for disaster  
❌ **Making multiple changes at once** - Can't isolate failures  
❌ **Not running tests after each change** - Small breaks become big problems  
❌ **Changing behavior accidentally** - Design contracts must be preserved  
❌ **Rewriting from scratch without justification** - High risk, low value  
❌ **Refactoring during bug investigation** - Do one or the other, not both  
❌ **Updating tests to match new implementation** - If design contract tests break, you changed behavior  
❌ **Forgetting to update documentation** - Code changes must be documented  

---

## Refactoring Examples

### Example 1: Extract Duplicate Code

**Before:**
```python
def load_default_layout(device):
    config = yaml.safe_load(open('config.yml'))
    layout_data = config['layouts']['default']
    keys = [Key(k['id'], k['action']) for k in layout_data['keys']]
    layout = Layout('default', keys, layout_data.get('brightness', 50))
    device.apply_layout(layout)

def load_media_layout(device):
    config = yaml.safe_load(open('config.yml'))
    layout_data = config['layouts']['media']
    keys = [Key(k['id'], k['action']) for k in layout_data['keys']]
    layout = Layout('media', keys, layout_data.get('brightness', 50))
    device.apply_layout(layout)
```

**After:**
```python
def _load_layout_from_config(layout_name: str) -> Layout:
    """Helper to load and parse a layout from config file."""
    config = yaml.safe_load(open('config.yml'))
    layout_data = config['layouts'][layout_name]
    keys = [Key(k['id'], k['action']) for k in layout_data['keys']]
    return Layout(layout_name, keys, layout_data.get('brightness', 50))

def load_default_layout(device: Device) -> None:
    layout = _load_layout_from_config('default')
    device.apply_layout(layout)

def load_media_layout(device: Device) -> None:
    layout = _load_layout_from_config('media')
    device.apply_layout(layout)

# Better yet: generalize further
def load_layout(device: Device, layout_name: str) -> None:
    """Load and apply a layout by name."""
    layout = _load_layout_from_config(layout_name)
    device.apply_layout(layout)
```

**Tests remain unchanged** (if they tested design contracts):
```python
def test_default_layout_has_15_keys():
    """Design contract: Default layout has 15 keys"""
    load_default_layout(device)
    assert len(device.current_layout.keys) == 15  # Still passes!
```

---

### Example 2: Simplify Complex Conditional

**Before:**
```python
def should_switch_layout(device, window_info):
    if device.is_connected:
        if device.current_layout is not None:
            if window_info is not None:
                if window_info.title and window_info.class_name:
                    if window_info.is_focused:
                        return True
    return False
```

**After:**
```python
def should_switch_layout(device: Device, window_info: WindowInfo) -> bool:
    """Determine if layout switching should occur based on device and window state."""
    if not device.is_connected:
        return False
    if device.current_layout is None:
        return False
    if window_info is None:
        return False
    if not (window_info.title and window_info.class_name):
        return False
    return window_info.is_focused
```

**Tests remain unchanged**:
```python
def test_layout_switches_on_focused_window():
    """Design contract: Layout switches when window gains focus"""
    window_info = WindowInfo(title="Firefox", class_name="firefox", is_focused=True)
    assert should_switch_layout(device, window_info) is True
```

---

## Tools & Commands Reference

### Testing
```bash
# Check coverage before refactoring
pytest --cov=src/ModuleToRefactor tests/ --cov-report=term-missing

# Run tests after each change
pytest tests/test_module.py -v

# Run full suite
pytest tests/ -v

# Quick syntax check
python -m py_compile src/path/to/file.py
```

### Code Cleanup
```bash
# Remove unused imports and sort imports (requires autoflake and isort)
# Replace 'src tests' with your target directories
autoflake --remove-all-unused-imports --recursive --in-place src tests && isort src tests
```

### Performance Testing
```bash
# Benchmark before refactoring
python -m timeit -s "from module import func" "func()"

# Benchmark after refactoring (compare)
python -m timeit -s "from module import func" "func()"

# Memory profiling (if needed)
python -m memory_profiler script.py
```

### Code Quality
```bash
# Check complexity
radon cc src/module.py -a

# Check for code smells
pylint src/module.py

# Type check
mypy src/module.py

# Inspect changes without pager (recommended for agents)
git --no-pager diff
```
