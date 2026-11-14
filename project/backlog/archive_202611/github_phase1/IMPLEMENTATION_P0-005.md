# Implementation Plan: P0-005 Event Error Handling Strategy

**Issue ID:** P0-005
**Priority:** Critical (P0)
**Assignee:** Claude Code
**Status:** Completed - Ready for Review
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

## Implementation Results

**Completed:** 2026-01-10
**Branch:** `feature/P0-005-error-handling-strategy`

### Changes Made

#### `pyguara/events/types.py` (lines 13-40)

**Added ErrorHandlingStrategy Enum:**
- Three strategies: LOG, RAISE, IGNORE
- Comprehensive documentation with usage examples
- LOG: Log error and continue (graceful degradation)
- RAISE: Log error and re-raise (fail-fast, default)
- IGNORE: Silently ignore errors (not recommended)

#### `pyguara/events/dispatcher.py` (lines 27-51, 101-131)

**Updated EventDispatcher:**
- Added `error_strategy` parameter to __init__ (default: RAISE)
- Updated `_process_handlers()` to use configured strategy
- Enhanced error messages with handler name and event type
- Includes stack trace via `exc_info=True` when logging
- RAISE strategy re-raises after logging
- LOG strategy logs and continues to next handler
- IGNORE strategy silently continues (no logging)

**Error Message Format:**
```
Error in event handler 'handler_name' for event type 'EventType': <exception>
```

#### `pyguara/di/types.py` (lines 16-43)

**Added ErrorHandlingStrategy Enum:**
- Same three strategies as events module
- Tailored documentation for DI context
- Usage examples for container initialization

#### `pyguara/di/container.py` (lines 37-51, 251-271)

**Updated DIContainer:**
- Added `error_strategy` parameter to __init__ (default: RAISE)
- Updated `_extract_dependencies()` to use configured strategy
- Enhanced error messages with service name and context
- RAISE strategy throws DIException with full context
- LOG strategy prints warning and returns empty dict
- IGNORE strategy silently returns empty dict

**Error Message Format:**
```
[DI] Dependency extraction failed for 'ServiceName': <exception>.
This may cause injection failures if the service is requested.
```

### Test Results

```
============================= test session starts ==============================
collected 20 items

tests/test_events.py::test_subscribe_and_dispatch PASSED                 [  5%]
tests/test_events.py::test_unsubscribe PASSED                            [ 10%]
tests/test_events.py::test_priority PASSED                               [ 15%]
tests/test_events.py::test_event_queue PASSED                            [ 20%]
tests/test_events.py::test_event_filtering PASSED                        [ 25%]
tests/test_events.py::test_error_handling_strategy_raise PASSED          [ 30%]
tests/test_events.py::test_error_handling_strategy_log PASSED            [ 35%]
tests/test_events.py::test_error_handling_strategy_ignore PASSED         [ 40%]
tests/test_events.py::test_error_message_includes_context PASSED         [ 45%]
tests/test_di.py::test_singleton_registration PASSED                     [ 50%]
tests/test_di.py::test_transient_registration PASSED                     [ 55%]
tests/test_di.py::test_dependency_resolution PASSED                      [ 60%]
tests/test_di.py::test_scoped_resolution PASSED                          [ 65%]
tests/test_di.py::test_circular_dependency PASSED                        [ 70%]
tests/test_di.py::test_service_not_found PASSED                          [ 75%]
tests/test_di.py::test_scope_disposal PASSED                             [ 80%]
tests/test_di.py::test_error_handling_strategy_raise_on_dependency_extraction PASSED [ 85%]
tests/test_di.py::test_error_handling_strategy_log_on_dependency_extraction PASSED [ 90%]
tests/test_di.py::test_error_handling_strategy_ignore_on_dependency_extraction PASSED [ 95%]
tests/test_di.py::test_default_error_strategy_is_raise PASSED            [100%]

============================== 20 passed in 0.06s ==============================
```

### Type Checking

```
Success: no issues found in 12 source files
```

### Code Quality

```
ruff check pyguara/events/ pyguara/di/ tests/test_events.py tests/test_di.py
All checks passed!
```

### Impact

This implementation solves the P0-005 error swallowing issue by:

1. **Configurable Error Handling**: Applications can choose between fail-fast (RAISE) and graceful degradation (LOG) based on environment
2. **Better Error Messages**: All errors now include full context (handler/service name, event/service type, stack trace)
3. **No More Silent Failures**: Default strategy is RAISE, ensuring errors are never silently swallowed in development
4. **Production Flexibility**: LOG strategy allows production systems to continue operating despite handler failures
5. **Backward Compatible**: Existing code continues to work (just with better error handling via new default)

**Key Benefits:**
- Eliminates silent failures that made debugging extremely difficult
- Fail-fast by default for rapid development iteration
- Configurable graceful degradation for production stability
- Rich error context speeds up debugging
- Type-safe enum prevents configuration errors

### Usage Examples

**Development Mode (Default):**
```python
# Fail-fast for rapid debugging
dispatcher = EventDispatcher()  # Uses RAISE by default
container = DIContainer()  # Uses RAISE by default

# Errors immediately surface during development
dispatcher.dispatch(event)  # Raises if handler fails
```

**Production Mode:**
```python
# Graceful degradation
dispatcher = EventDispatcher(
    logger=logger,
    error_strategy=ErrorHandlingStrategy.LOG
)
container = DIContainer(error_strategy=ErrorHandlingStrategy.LOG)

# System continues operating, errors logged for monitoring
dispatcher.dispatch(event)  # Logs error, continues to next handler
```

**Testing Mode:**
```python
# Silent errors for specific test scenarios
dispatcher = EventDispatcher(error_strategy=ErrorHandlingStrategy.IGNORE)

# Useful for testing error recovery paths
```

### Breaking Changes

**Behavior Change (Backward Compatible API):**
- **Old Behavior**: Errors were logged but swallowed (silent failures)
- **New Behavior**: Errors are re-raised by default (fail-fast)

**Migration:**
- Existing code that relied on silent error swallowing should explicitly use `ErrorHandlingStrategy.LOG`
- Most applications will benefit from the new fail-fast default
- No API changes - purely behavioral improvement

### Tests Added

**Event System (4 new tests):**
- test_error_handling_strategy_raise - Verifies RAISE re-raises exceptions
- test_error_handling_strategy_log - Verifies LOG continues after error
- test_error_handling_strategy_ignore - Verifies IGNORE silently continues
- test_error_message_includes_context - Verifies error messages have full context

**DI System (4 new tests):**
- test_error_handling_strategy_raise_on_dependency_extraction - Verifies RAISE throws DIException
- test_error_handling_strategy_log_on_dependency_extraction - Verifies LOG continues with empty deps
- test_error_handling_strategy_ignore_on_dependency_extraction - Verifies IGNORE silent operation
- test_default_error_strategy_is_raise - Verifies default is fail-fast

### Next Steps

1. **Code Review**: Ready for peer review
2. **Merge**: After approval, merge to `develop` branch
3. **Documentation**: Update user docs with error handling best practices
4. **Monitoring**: Production systems using LOG strategy should monitor error logs
