---
description: Systematic workflow for investigating and fixing bugs
---

# Bug Squash Workflow

This workflow outlines a systematic approach to investigating, fixing, and verifying bugs in the codebase, based on successful bug resolution patterns.

## 🔑 Core Philosophy: Code Reuse First

**ALWAYS prioritize reusing existing code over writing new solutions.**

When fixing bugs:
1. **Search for existing solutions** - Look for similar fixes already in the codebase
2. **Adapt, don't recreate** - Copy and modify working patterns rather than starting from scratch
3. **Maintain consistency** - Follow established code style, naming conventions, and architectural patterns
4. **DRY (Don't Repeat Yourself)** - If the functionality exists elsewhere, reuse or extend it

This approach:
- ✅ Reduces bugs by using proven code
- ✅ Maintains codebase consistency
- ✅ Saves development time
- ✅ Makes the codebase easier to maintain

---

## Phase 0: Workspace Preparation

### 0. Ensure Clean State
- [ ] **Check git status**
  ```bash
  git status
  ```
  - Ensure you are on the correct branch
  - Verify working directory is clean (or changes are unrelated/staged)
  - **Goal:** Start with a known good state to avoid confusion

## Phase 1: Investigation & Root Cause Analysis

### 1. Gather Information
- [ ] **Read the error message carefully**
  - Note the exception type (AttributeError, TypeError, etc.)
  - Identify the failing line from the stack trace
  - Record the error context (what operation was being performed)
  - If information is missing - specifically ask the user to provide it

- [ ] **Collect reproduction details**
  - Get the user's configuration or input that triggers the bug
  - Note any error logs with timestamps
  - Understand what the user expected vs. what actually happened

### 2. Analyze the Stack Trace
- [ ] **Identify the failure point**
  - Find the exact line in the code where the exception occurs
  - Use `view_file` to examine that code section
  
- [ ] **Use Codebase Investigator (Recommended)**
  - Use `codebase_investigator` to understand the surrounding context and dependencies
  - Identify where the failing component fits in the architecture
  - Trace how data flows into the failing component

- [ ] **Trace backward through the call stack**
  - Understand how the code reached the failure point
  - Identify where data is transformed or passed between functions
  - Look for type mismatches or missing conversions

### 3. Root Cause Identification
- [ ] **Compare with working code patterns**
  - **⚠️ CRITICAL: Search the codebase for similar functionality that already works correctly**
  - Look for resolution/conversion patterns (e.g., how does `CHANGE_LAYOUT` resolve references?)
  - Identify existing helper methods or utilities that can be reused
  - Check if other actions use similar parameter transformations
  
- [ ] **Document findings**
  - Write a clear explanation of why the bug occurs
  - Explain to the user what you discovered
  - **Note any existing code patterns that can be adapted for the fix**

## Phase 2: Planning the Fix

### 4. Design the Solution
- [ ] **Create an initial implementation plan artifact**
  - Use `write_to_file` to create `implementation_plan.md`
  - Document the proposed changes by component/file
  - Identify which files need modification
  
- [ ] **🔑 PRIORITY: Look for existing patterns to reuse**
  - **Search for similar fixes already implemented in the codebase**
  - **Identify existing methods/functions that can be adapted rather than rewritten**
  - Look for established patterns (e.g., reference resolution, parameter parsing)
  - Check if there are utility functions or helper classes that can be reused
  - **Prefer adapting existing code over writing new code from scratch**
  
- [ ] **Document architectural decisions**
  - If the fix requires a significant architectural change, create a new record in `docs/architecture/adr/`.
  
- [ ] **Consider edge cases**
  - What if the referenced item doesn't exist?
  - What if the item is in an unexpected state?
  - What if the user's config uses a variation of the format?

- [ ] **Review the initial implementation plan**
  - Identify additional uncovered edge cases
  - Iterate on the initial plan, improve it's robustness and make sure the fix won't impact other code areas

### 5. Write a Failing Test FIRST (Test-Driven Bug Fixing)

**🔑 RECOMMENDED APPROACH: Write the test before writing the fix**

- [ ] **Identify which test should have caught this bug**
  - Search existing tests for coverage of the affected code path
  - Ask: "Why didn't existing tests catch this?"
  - Reasons may include:
    - No test exists for this code path (coverage gap)
    - Existing test doesn't cover this edge case
    - Test assertion was too loose/permissive
    - Test used wrong mocking that hid the bug

- [ ] **Write or modify test to reproduce the bug**
  - If no test exists: Create new test in appropriate test file
  - If test exists but inadequate: Strengthen the existing test
  - Name test descriptively: `test_<component>_<bug_scenario>_issue<NUMBER>`
  - Mark with `@pytest.mark.regression` and `@pytest.mark.issue<NUMBER>`
  - Example:
    ```python
    @pytest.mark.regression
    @pytest.mark.issue42
    def test_config_loader_handles_missing_layout_reference_issue42():
        """Regression test for issue #42: crash on undefined layout reference"""
        config = {'layout_ref': 'NonExistentLayout'}
        with pytest.raises(ConfigValidationError, match="Layout.*not found"):
            loader.resolve_layout(config)
    ```

- [ ] **Run the test and verify it FAILS**
  ```bash
  pytest tests/path/to/test.py::test_name -v
  ```
  - ✅ Test should fail with the same error as the bug report
  - ✅ Failure proves you've reproduced the bug in a test
  - ❌ If test passes: Your test doesn't reproduce the bug (revise it)
  - ❌ If test fails differently: Check your understanding of root cause

- [ ] **Benefits of this approach**
  - Confirms you understand the bug (test reproduces it)
  - Provides clear success criterion (test will pass when fixed)
  - Prevents regressions (test stays in suite forever)
  - Improves test coverage (fills gaps)

**Skip test-first only if:**
- ❌ Bug requires real hardware and can't be mocked reliably
- ❌ Bug is intermittent/timing-based and can't be reproduced consistently
- ❌ Root cause is still unclear (finish investigation first)
- ❌ Bug is purely performance-related (use performance tests instead)

**If you skip test-first**, document why in implementation plan and commit to adding test after fix validation.

### 6. Determine Required Test Types

- [ ] **Select test types based on bug category** (in addition to regression test above)

  **Logic/Algorithm Bugs** (incorrect calculations, wrong conditions):
  - ✅ **Unit Tests** (mocked) - Required
  
  **Component Interaction Bugs** (data flow, state management):
  - ✅ **Integration Tests** (mocked) - Required
  - ✅ **Unit Tests** (mocked) - Recommended
  
  **Configuration/YAML Bugs** (parsing errors, validation):
  - ✅ **Configuration Tests** - Required
  - Add sample YAML to `tests/configs/` that reproduces the issue
  
  **Hardware Communication Bugs** (HID, device state, LED updates):
  - ✅ **Hardware Integration Tests** - Required (manual, pre-release)
  - ✅ **Unit Tests** (mocked) - Required
  - Mark hardware tests with `@pytest.mark.hardware`
  
  **System Integration Bugs** (D-Bus, window monitoring, udev):
  - ✅ **Integration Tests** (mocked) - Required
  - ✅ **End-to-End Tests** - Recommended (manual, pre-release)
  
  **Device Reconnection/Stability Bugs**:
  - ✅ **Reconnection Tests** - Required (manual)
  - ✅ **Unit Tests** (mocked) - Required
  
  **Performance/Memory Bugs**:
  - ✅ **Performance Tests** - Required (manual)
  - ✅ **Unit Tests** (mocked) - Recommended

- [ ] **Document test plan in implementation_plan.md**
  - Note that failing regression test exists (if test-first was used)
  - List any additional required test types
  - Explain why each test type is needed
  - Note which tests are automated vs manual
  - Example:
    ```markdown
    ## Test Plan
    1. ✅ Regression test (written, currently FAILING): `test_config_loader_handles_missing_layout_reference_issue42`
    2. Unit test (automated): Verify new validation logic in `resolve_layout()`
    3. Configuration test (automated): Add `tests/configs/issue42_missing_ref.yml`
    4. Hardware test (manual): Validate fix doesn't break device initialization
    ```

### 7. Get User Approval
- [ ] **Request plan review via `notify_user`**
  - Mention that failing test exists (if test-first approach used)
  - Provide clear confidence score and justification
  - Set `BlockedOnUser: true`
  - Wait for approval before implementation

## Phase 3: Implementation

### 8. Implement the Fix
- [ ] **Create task breakdown**
  - Use `write_to_file` to create/update `task.md`
  - Break down implementation into concrete steps
  - Note: The goal is to make the failing test pass
  
- [ ] **Set task boundary**
  - Use `task_boundary` tool in EXECUTION mode
  - Provide clear TaskName and TaskStatus
  
- [ ] **Make code changes to fix the bug**
  - **⚠️ SAFETY: Always `read_file` before `replace` or `write_file` to verify content**
  - Follow the implementation plan
  - **🎯 Goal: Make the failing test pass**
  - **⚠️ REUSE BEFORE REWRITE: Always check if existing code can be adapted**
  - Copy and adapt patterns from similar working code
  - Maintain consistency with existing code style and patterns
  - Make one logical change at a time
  - Update task.md as you complete steps

### 9. Add Additional Test Coverage (if needed)
- [ ] **Regression test already exists** (from step 5)
  - This test should now PASS after the fix
  
- [ ] **Check for existing test coverage FIRST**
  - Search for tests covering the same code path/function
  - Review existing tests to see if they already validate the fixed behavior
  - Run `pytest --cov=src/module tests/ --cov-report=term-missing` to see coverage
  
- [ ] **Only add tests if needed**
  - ✅ Add a test if: The bug occurred in an untested code path
  - ✅ Add a test if: Existing tests don't cover the specific edge case
  - ❌ Don't add if: The bug was caused by incorrect logic in well-tested code (fix the existing test instead)
  - ❌ Don't add if: Similar tests already exist (update existing test if it needs adjustment)

- [ ] **Add regression test for the specific bug** (if new test is needed)
  - Mark with `@pytest.mark.regression` decorator
  - Mark with issue number: `@pytest.mark.issue<NUMBER>` (e.g., `@pytest.mark.issue42`)
  - Name test to describe the bug: `test_<component>_<bug_scenario>_issue<NUMBER>`
  - Example:
    ```python
    @pytest.mark.regression
    @pytest.mark.issue42
    def test_device_manager_handles_reconnect_without_crash_issue42():
        """Regression test for issue #42: device reconnect caused crash"""
        # Test implementation
    ```
  
- [ ] **Add test configuration files** (if needed)
  - Create minimal configs that reproduce the scenario
  - **Reuse existing configs if possible** - check `tests/configs/` first
  - Only create new configs for truly unique scenarios
  - Store in `tests/configs/` with descriptive names
  
- [ ] **Update existing tests if behavior changed**
  - If the fix changes expected behavior, update existing tests to match
  - Document why the assertion changed in a comment
  - Don't leave old tests failing

- [ ] **Follow existing test patterns**
  - Use the same fixtures and structure
  - Match naming conventions
  - Reuse test helpers and utilities

## Phase 4: Verification

### 10. Verify Code Quality
- [ ] **Run Linting & Formatting**
  - Run project linters (e.g., `pylint`, `flake8`) on modified files
  - Run formatters (e.g., `black`, `isort`) if applicable
  - Ensure no new linting errors were introduced
  - Fix any style violations immediately

### 11. Verify Regression Test Now Passes
- [ ] **Run the regression test that was failing**
  ```bash
  pytest tests/path/to/test_file.py::test_name_issue<NUMBER> -v
  ```
  - ✅ Test should now PASS (proving the bug is fixed)
  - ❌ If still failing: Bug fix is incomplete or incorrect
  
- [ ] **This is your primary success criterion**
  - Red → Green transition proves the fix works
  - Provides confidence the bug is truly resolved

### 12. Run Full Test Suite
- [ ] **Test any additional new functionality** (if applicable)
  ```bash
  pytest tests/path/to/test_file.py::TestClass::test_new_feature -v
  ```
  
- [ ] **Run all tests in the affected module**
  ```bash
  pytest tests/path/to/test_file.py -v
  ```
  
- [ ] **Verify all tests pass**
  - No new failures
  - All new tests passing

### 13. Test with Real Configuration
- [ ] **Load user's actual config**
  - Use Python one-liner to test config loading
  - Verify no exceptions are raised
  
- [ ] **Manual testing** (if applicable)
  - Run the application
  - Reproduce the original scenario
  - Verify the bug is fixed

## Phase 5: Iteration (if issues found)

### 14. Handle Discovery of Additional Issues
- [ ] **Stay in same TaskName if related**
  - Switch to PLANNING mode if design needs rethinking
  - Update TaskSummary to explain the pivot
  
- [ ] **Create new task if fundamentally different**
  - Only if the new issue requires a different approach
  
- [ ] **Apply same workflow**
  - Re-investigate the new issue
  - Update implementation plan
  - Add more tests

### 15. Refine Until Verified
- [ ] **Iterate on the fix**
  - Adjust implementation based on new findings
  - Add tests for newly discovered edge cases
  
- [ ] **Re-run verification**
  - All tests must pass
  - User's config must load successfully

## Phase 6: Documentation & Completion

### 16. Update Documentation
- [ ] **Update relevant docs**
  - API documentation
  - Configuration guides
  - User-facing markdown files
  
- [ ] **Synchronize agent documentation**
  - Ensure `docs/architecture/AGENT_KNOWLEDGE_BASE.md` is updated if internal logic changed.
  - Verify that code comments and docstrings match the new implementation.
  
- [ ] **Include practical examples**
  - Show the exact scenario that was fixed
  - Provide variations users might need

### 17. Final Summary
- [ ] **Provide clear completion message**
  - Explain what was fixed
  - Show test results (✅ all passing)
  - Confirm user's scenario works
  - Point out any documentation updates

### 18. Final Cleanup
- [ ] **Check git status**
  ```bash
  git status
  ```
  - Verify all changes are staged or ready to be staged
  - Ensure no unintended files are modified
  - **Remind user to commit changes** if automatic commits aren't enabled

## Best Practices

### Investigation
✅ **Always read error messages carefully** - The stack trace tells you exactly where to look  
✅ **Search for similar code patterns** - Don't reinvent solutions  
✅ **Ask for user's config/input** - Essential for reproduction  

### Planning  
✅ **Write a failing test FIRST** - Proves you understand the bug and provides success criterion  
✅ **Search for existing solutions FIRST** - Don't reinvent the wheel  
✅ **Reuse working patterns over creating new ones** - Adapt, don't recreate  
✅ **Select appropriate test types for the bug category** - Match test strategy to bug type  
✅ **Create implementation plans for non-trivial fixes** - Think before coding  
✅ **Get user approval on plans** - Avoid wasted effort on wrong approaches  

### Implementation
✅ **Goal: Make the failing test pass** - Clear success criterion from test-first approach  
✅ **Reuse existing helpers and utilities** - Don't duplicate functionality  
✅ **Follow established code patterns** - Maintain consistency across codebase  
✅ **Use task boundaries for structured work** - Keep user informed of progress  
✅ **Make incremental changes** - Easier to debug if something goes wrong  
✅ **Test early and often** - Catch issues before they compound  

### Testing
✅ **Write failing test before fixing the bug** - Test-driven bug fixing is the gold standard  
✅ **Verify test FAILS before writing fix** - Proves you reproduced the bug  
✅ **Verify test PASSES after fix** - Proves the fix works  
✅ **Check existing test coverage FIRST** - Don't duplicate tests for already-covered code  
✅ **Mark regression tests with issue numbers** - Use `@pytest.mark.regression` and `@pytest.mark.issue<N>`  
✅ **Reuse existing test fixtures and helpers** - Don't duplicate test infrastructure  
✅ **Update existing tests if behavior changed** - Keep tests synchronized with code  
✅ **Run full test suite** - Ensure no regressions  

### Iteration
✅ **Don't panic when new issues appear** - It's normal to discover edge cases  
✅ **Document what you learn** - Update plans and summaries as you go  
✅ **Stay systematic** - Apply the same methodology to new discoveries  

## Common Pitfalls to Avoid

❌ **Rewriting code that already exists elsewhere** - Search for existing solutions FIRST  
❌ **Ignoring established patterns in the codebase** - Follow existing conventions  
❌ **Creating new utilities when similar ones exist** - Reuse or extend existing code  
❌ **Jumping to implementation without understanding root cause** - Always investigate first  
❌ **Fixing only the immediate symptom** - Address the underlying issue  
❌ **Skipping test creation** - Future you (or someone else) will regret it  
❌ **Not testing with user's actual config** - Lab tests != real-world usage  
❌ **Forgetting to update documentation** - Code changes should be documented  
❌ **Making too many changes at once** - Hard to isolate what fixed (or broke) things  

## Tools & Commands Reference

### Investigation
```bash
# Search for patterns in code
grep -r "pattern" src/

# Find files by name
find . -name "pattern*"

# Check git history for related changes
git log --all -- path/to/file

# Inspect changes without pager (recommended for agents)
git --no-pager diff
```

### Testing
```bash
# Run specific test
pytest path/to/test.py::TestClass::test_method -v

# Run all tests in file
pytest path/to/test.py -v

# Run with coverage
pytest --cov=src/module tests/

# Quick config validation
python -c "from module import Loader; Loader('config.yml').load()"
```

### Verification
```bash
# Check for syntax errors
python -m py_compile path/to/file.py

# Run linter
pylint path/to/file.py

# Type checking (if using mypy)
mypy path/to/file.py
```