# Implementation Plan: P0-002 DIScope Public API

**Issue ID:** P0-002
**Priority:** Critical (P0)
**Assignee:** TBD
**Status:** Ready
**Branch:** `feature/P0-002-discope-public-api`

## Summary

Add public `get()` method to DIScope class to resolve scoped services without using internal APIs.

## Files to Modify

- `pyguara/di/container.py`
- `tests/test_di.py`
- `docs/core/architecture.md` (or dependency-injection.md)

## Implementation Checklist

### Step 1: Add Public get() Method
- [ ] Add `get(service_type: Type[T]) -> T` method to DIScope
- [ ] Delegate to `container._resolve_service(service_type, scope=self)`
- [ ] Add comprehensive docstring with examples
- [ ] Preserve generic type information with TypeVar

### Step 2: Update Tests
- [ ] Replace all `container._resolve_service(Type, scope)` with `scope.get(Type)`
- [ ] Add test for scoped service resolution via public API
- [ ] Add integration test for scene lifecycle pattern

### Step 3: Add Documentation
- [ ] Add usage example to docstring
- [ ] Create "Using Scoped Services" section in docs
- [ ] Include scene lifecycle example

### Step 4: Validate Edge Cases
- [ ] Test: Scoped service without active scope raises clear error
- [ ] Test: Singleton resolved via scope returns correct instance
- [ ] Test: Transient resolved via scope creates new instance

## Acceptance Criteria

- [ ] All checklist items completed
- [ ] Public API method added and documented
- [ ] All tests use public API (no internal `_resolve_service` calls)
- [ ] Tests pass (pytest tests/test_di.py)
- [ ] Type checking passes (mypy pyguara/di/)
- [ ] Example code in documentation works

## Testing Commands

```bash
pytest tests/test_di.py::test_scoped_resolution -v
pytest tests/test_di.py -v
mypy pyguara/di/
```

## Implementation Reference

See: `docs/dev/backlog/2026-01-09-product-enhancement-proposal.md` Section 8.2

## Estimated Effort

- Implementation: 1 hour
- Testing: 1 hour
- Documentation: 30 minutes
- **Total: 2.5 hours**
