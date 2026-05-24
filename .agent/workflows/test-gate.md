---
description: Test-Gate Enforcement for All Development
---

# Development Test-Gate Requirement

**MANDATORY FOR ALL DEVELOPMENT WORK**

All code changes MUST pass the test-gate before committing.

## Test-Gate Rule

Before ANY `git commit` or `git push`:

// turbo
```bash
# Run full test suite
pytest tests/ -v
```

**Required Output:**
```
===== XXX passed, YY skipped ======
```

**Zero failures. Zero errors.**

## When to Run Tests

- Before every commit
- After changing any implementation code
- After adding new tests
- After updating dependencies
- After merging branches

## Test Suite Overview

- **320+ tests** across all layers
- **Unit tests:** Test individual components
- **Integration tests:** Test component interactions  
- **Application tests:** Test full lifecycle

##  Exemptions

**Allowed:**
- Skipped tests (`@pytest.mark.skip`) for incomplete features
- Known external dependency issues (documented)

**Not Allowed:**
- Failures
- Errors
- Hanging tests

## Quick Troubleshooting

**Mock Issues:**
```python
# ❌ Wrong
mock_obj = Mock()

# ✅ Right
mock_obj = Mock()
mock_obj.method = Mock(return_value=[])
```

**Fixture Issues:**
- Move shared fixtures to `conftest.py`
- Check fixture scope (function/class/module)

## Full Documentation

See [`.agent/TEST_GATE.md`](TEST_GATE.md) for:
- Detailed troubleshooting
- Common test issues
- Fix procedures
- Test categories
- CI/CD integration

## Enforcement

**Manual (Current):**
- Developer responsibility to run tests
- Code review verification

**Automated (Future):**
- Pre-commit hooks
- CI pipeline gates
- Required PR status checks

---

**Remember: Passing tests = Working code. No exceptions.**
