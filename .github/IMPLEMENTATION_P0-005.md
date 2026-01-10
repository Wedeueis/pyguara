# Implementation Plan: P0-005 Event Error Handling Strategy

**Issue ID:** P0-005
**Priority:** Critical (P0)
**Assignee:** TBD
**Status:** Ready
**Branch:** `feature/P0-005-error-handling-strategy`

## Summary

Implement configurable error handling strategy for event dispatchers and DI container to prevent silent failures while allowing graceful degradation when needed.

## Files to Modify

- `pyguara/events/dispatcher.py`
- `pyguara/events/types.py`
- `pyguara/di/container.py`
- `pyguara/di/types.py`
- `tests/test_events.py`
- `tests/test_di.py`

## Implementation Checklist

### Step 1: Define Error Handling Strategies
- [ ] Create `ErrorHandlingStrategy` enum (LOG, RAISE, IGNORE)
- [ ] Add to `pyguara/events/types.py` and `pyguara/di/types.py`

### Step 2: Update EventDispatcher
- [ ] Add `error_strategy` parameter to `__init__`
- [ ] Modify `_process_handlers()` to use strategy
- [ ] LOG: Log error and continue
- [ ] RAISE: Re-raise exception after logging
- [ ] IGNORE: Silently continue (not recommended, for testing)
- [ ] Add handler-specific error callbacks (optional)

### Step 3: Update DIContainer
- [ ] Add `error_strategy` to container initialization
- [ ] Update `_extract_dependencies()` to use strategy instead of silent print
- [ ] Improve error messages with full context

### Step 4: Add Error Context
- [ ] Include event type in error logs
- [ ] Include service type in DI errors
- [ ] Add stack trace option for debugging
- [ ] Include handler/factory info in error messages

### Step 5: Comprehensive Testing
- [ ] Test: Error strategy LOG logs and continues
- [ ] Test: Error strategy RAISE re-raises after logging
- [ ] Test: Multiple handler errors handled correctly
- [ ] Test: DI extraction errors properly reported
- [ ] Test: Error messages include full context

### Step 6: Documentation
- [ ] Document error handling strategies
- [ ] Add troubleshooting guide
- [ ] Include examples of error handling configuration

## Acceptance Criteria

- [ ] Configurable error handling strategy implemented
- [ ] Default strategy is RAISE (fail fast in development)
- [ ] Production can configure to LOG (graceful degradation)
- [ ] Error messages include full context
- [ ] Tests pass (pytest tests/test_events.py tests/test_di.py)
- [ ] No silent failures remain

## Testing Commands

```bash
pytest tests/test_events.py::test_error_handling_strategy -v
pytest tests/test_di.py::test_error_handling -v
pytest tests/test_events.py tests/test_di.py -v
```

## Implementation Reference

See: `docs/dev/backlog/2026-01-09-product-enhancement-proposal.md` Section 8.1 (P0-005)

## Code Example

```python
# pyguara/events/types.py
from enum import Enum

class ErrorHandlingStrategy(Enum):
    """How to handle errors in event handlers."""
    LOG = "log"        # Log and continue
    RAISE = "raise"    # Re-raise after logging
    IGNORE = "ignore"  # Silent (not recommended)

# Usage
dispatcher = EventDispatcher(
    logger=logger,
    error_strategy=ErrorHandlingStrategy.RAISE  # Fail fast
)

# Production
dispatcher = EventDispatcher(
    logger=logger,
    error_strategy=ErrorHandlingStrategy.LOG  # Graceful
)
```

## Breaking Changes

None - this is backward compatible. Default behavior changes from "log and continue" to "log and raise" for safety.

## Estimated Effort

- Implementation: 3 hours
- Testing: 1.5 hours
- Documentation: 30 minutes
- **Total: 5 hours**
