# Test-Gate Requirement

**CRITICAL:** ALL tests must pass before committing any code.

## Mandatory Test Verification

Before ANY commit to the repository, you MUST run the full test suite and verify 100% pass rate:

// turbo
```bash
pytest tests/ -v
```

**Required Result:**
```
===== XXX passed, YY skipped ======
```

**NO failures allowed. NO errors allowed.**

## Handling Test Failures

If tests fail:

1. **STOP** - Do not commit
2. **Investigate** - Determine root cause
   - Are test mocks stale? → Update mocks
   - Is implementation wrong? → Fix implementation
   - Are assertions incorrect? → Fix assertions
3. **Fix** - Resolve the issue
4. **Re-run** - Verify 100% pass rate
5. **Only then commit**

## Common Test Issues

### Stale Mocks
- **Symptom:** `TypeError: object of type 'Mock' has no len()`
- **Fix:** Update mock return values (e.g., `Mock(return_value=[])`)

### Fixture Scope Issues
- **Symptom:** `fixture 'X' not found`
- **Fix:** Move shared fixtures to `tests/<module>/conftest.py`

### API Changes
- **Symptom:** `TypeError: missing required positional argument`
- **Fix:** Update test calls to match new API signature

## Test Categories

- **Unit Tests:** Test individual components in isolation
- **Integration Tests:** Test component interactions
- **Application Tests:** Test full application lifecycle

**ALL categories must pass.**

## Exception: Skipped Tests

Tests marked with `@pytest.mark.skip` are allowed and expected for:
- Features not yet implemented (Phase 6+ work)
- Known external dependencies (xdotool fragility)
- Incomplete integration wiring

**Skipped tests do NOT count as failures.**

## CI/CD Integration

When CI/CD is set up, this test-gate will be enforced automatically:
- Pre-commit hooks will run tests
- CI pipelines will block merges on test failures
- Status checks will be required for PR approval

Until then, **manual enforcement is MANDATORY.**
