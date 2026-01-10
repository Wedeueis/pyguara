# Implementation Plan: P0-004 Resource Memory Leak

**Issue ID:** P0-004
**Priority:** Critical (P0)
**Assignee:** TBD
**Status:** Ready
**Branch:** `feature/P0-004-resource-memory-leak`

## Summary

Implement resource reference counting and unloading mechanism to prevent memory leaks in long-running games.

## Files to Modify

- `pyguara/resources/manager.py`
- `pyguara/resources/types.py`
- `tests/test_resources.py`

## Implementation Checklist

### Step 1: Add Reference Counting
- [ ] Add `_reference_counts: Dict[str, int]` to ResourceManager
- [ ] Implement `acquire(path)` method to increment ref count
- [ ] Implement `release(path)` method to decrement ref count
- [ ] Auto-increment on `load()`, auto-decrement on `unload()`

### Step 2: Implement Unload Mechanism
- [ ] Add `unload(path_or_name: str)` method
- [ ] Only unload when reference count reaches 0
- [ ] Add `unload_unused()` to batch-unload all zero-ref resources
- [ ] Add `clear_cache()` for scene transitions

### Step 3: Resource Lifecycle Tracking
- [ ] Add `last_accessed: float` timestamp to track usage
- [ ] Implement LRU (Least Recently Used) eviction strategy
- [ ] Add `max_cache_size_mb` configuration option
- [ ] Implement automatic cleanup when cache size exceeded

### Step 4: Add Memory Profiling
- [ ] Add `get_cache_stats()` method returning size, count, memory usage
- [ ] Track total memory usage of cached resources
- [ ] Add debug logging for load/unload operations

### Step 5: Update Tests
- [ ] Test: Load and unload resource
- [ ] Test: Reference counting works correctly
- [ ] Test: Resource not unloaded while references exist
- [ ] Test: Unload_unused clears only zero-ref resources
- [ ] Test: Memory usage decreases after unload (integration test)

### Step 6: Documentation
- [ ] Update ResourceManager docstrings
- [ ] Add resource lifecycle guide to docs
- [ ] Include best practices (when to unload)

## Acceptance Criteria

- [ ] Resources can be explicitly unloaded
- [ ] Reference counting prevents premature unloading
- [ ] Memory usage measurable via stats API
- [ ] Tests verify memory is freed (use tracemalloc)
- [ ] Tests pass (pytest tests/test_resources.py)
- [ ] No regression in load performance

## Testing Commands

```bash
pytest tests/test_resources.py -v
pytest tests/test_resources.py::test_resource_unloading -v

# Memory leak test (integration)
pytest tests/integration/test_resource_lifecycle.py -v
```

## Implementation Reference

See: `docs/dev/backlog/2026-01-09-product-enhancement-proposal.md` Section 8.1 (P0-004)

## Code Example

```python
# Usage pattern
# In scene on_enter
self.player_texture = resource_mgr.load("player.png", Texture)
resource_mgr.acquire("player.png")  # Optional: explicit ref count

# In scene on_exit
resource_mgr.release("player.png")

# Between scenes
resource_mgr.unload_unused()  # Cleanup all zero-ref resources
```

## Performance Considerations

- `load()` must remain fast (no performance regression)
- Reference counting is O(1)
- `unload_unused()` is O(N) where N is cache size (acceptable for scene transitions)

## Estimated Effort

- Implementation: 4 hours
- Testing: 2 hours
- Documentation: 1 hour
- **Total: 7 hours**
