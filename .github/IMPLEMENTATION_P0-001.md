# Implementation Plan: P0-001 Component Removal Tracking

**Issue ID:** P0-001
**Priority:** Critical (P0)
**Assignee:** TBD
**Status:** In Progress
**Branch:** `feature/P0-001-component-removal-tracking`

## Summary

Implement component removal tracking in EntityManager to ensure inverted indexes stay synchronized when components are removed from entities.

## Files to Modify

- `pyguara/ecs/entity.py`
- `pyguara/ecs/manager.py`
- `tests/test_ecs.py`

## Implementation Checklist

### Step 1: Add Callback Hook to Entity
- [ ] Add `_on_component_removed` field to `Entity.__init__()`
- [ ] Update type hints to include Optional callback

### Step 2: Modify remove_component Method
- [ ] Call `_on_component_removed` callback after component removal
- [ ] Ensure callback is called AFTER property cache cleanup
- [ ] Add debug logging (optional)

### Step 3: Implement Handler in EntityManager
- [ ] Add `_on_entity_component_removed` method to EntityManager
- [ ] Hook up callback in `add_entity()` method
- [ ] Use `set.discard()` to safely remove entity ID from index

### Step 4: Write Comprehensive Tests
- [ ] Test: Component removal updates index
- [ ] Test: Partial removal from multiple entities
- [ ] Test: Removing non-existent component (edge case)
- [ ] Test: Multiple components removed from same entity
- [ ] Performance test: Removal remains O(1)

### Step 5: Update Documentation
- [ ] Update `remove_component()` docstring
- [ ] Add note in `docs/core/architecture.md`
- [ ] Update ECS tutorial example

## Acceptance Criteria

- [x] All checklist items completed
- [ ] All tests pass (pytest tests/test_ecs.py)
- [ ] Type checking passes (mypy pyguara/ecs/)
- [ ] Code coverage ≥ 90% for modified files
- [ ] Manual testing: Create entity, add component, remove it, query returns empty
- [ ] Code review approved

## Testing Commands

```bash
# Run specific tests
pytest tests/test_ecs.py::test_component_removal_updates_index -v

# Run all ECS tests
pytest tests/test_ecs.py -v

# Check coverage
pytest tests/test_ecs.py --cov=pyguara.ecs --cov-report=term-missing

# Type check
mypy pyguara/ecs/
```

## Implementation Reference

See: `docs/dev/backlog/2026-01-09-product-enhancement-proposal.md` Section 8.1

## Notes

- Original issue acknowledged in `entity.py:104-106`
- This fix is prerequisite for any advanced query features
- Performance must remain O(1) amortized for remove operations

## Estimated Effort

- Implementation: 2 hours
- Testing: 1 hour
- Documentation: 30 minutes
- **Total: 3.5 hours**
