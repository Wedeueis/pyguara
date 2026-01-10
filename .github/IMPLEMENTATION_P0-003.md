# Implementation Plan: P0-003 UI Event Type Enum

**Issue ID:** P0-003
**Priority:** Critical (P0)
**Assignee:** TBD
**Status:** Ready
**Branch:** `feature/P0-003-ui-event-enum`

## Summary

Replace string-based UI event types ("MOUSE_DOWN", "MOUSE_UP", etc.) with type-safe enums to prevent typos and enable IDE autocomplete.

## Files to Modify

- `pyguara/ui/types.py` (create if needed)
- `pyguara/ui/manager.py`
- `pyguara/ui/base.py`
- `pyguara/ui/components/*.py`
- `tests/test_ui.py`

## Implementation Checklist

### Step 1: Create UIEventType Enum
- [ ] Create/update `pyguara/ui/types.py`
- [ ] Define `UIEventType` enum with all event types
- [ ] Add docstrings for each event type

### Step 2: Update UIManager
- [ ] Replace string literals in `_on_mouse_event()` with enum values
- [ ] Update type hints to use UIEventType
- [ ] Ensure backward compatibility if needed

### Step 3: Update UIElement Base Class
- [ ] Update `handle_event()` signature to accept UIEventType
- [ ] Update all UI component classes (Button, Panel, etc.)

### Step 4: Update Tests
- [ ] Replace all string event types with enum in tests
- [ ] Add test for invalid event type (should fail at type check)
- [ ] Verify IDE autocomplete works (manual check)

### Step 5: Documentation
- [ ] Update UI system documentation
- [ ] Add example showing enum usage
- [ ] Update CHANGELOG.md with breaking change note

## Acceptance Criteria

- [ ] All string-based event types replaced with UIEventType enum
- [ ] Tests pass (pytest tests/test_ui*.py)
- [ ] Type checking passes (mypy pyguara/ui/)
- [ ] No string literals for event types remain in codebase
- [ ] IDE provides autocomplete for event types

## Testing Commands

```bash
pytest tests/test_ui.py -v
pytest tests/test_ui_components.py -v
mypy pyguara/ui/
ruff check pyguara/ui/
```

## Implementation Reference

See: `docs/dev/backlog/2026-01-09-product-enhancement-proposal.md` Section 8.1 (P0-003)

## Code Example

```python
# pyguara/ui/types.py
from enum import Enum

class UIEventType(Enum):
    """UI interaction event types."""
    MOUSE_DOWN = "mouse_down"
    MOUSE_UP = "mouse_up"
    MOUSE_MOVE = "mouse_move"
    MOUSE_ENTER = "mouse_enter"
    MOUSE_LEAVE = "mouse_leave"
    FOCUS_GAINED = "focus_gained"
    FOCUS_LOST = "focus_lost"

# Usage in manager.py
event_type = UIEventType.MOUSE_DOWN if event.is_down else UIEventType.MOUSE_UP
```

## Breaking Changes

This changes the signature of `UIElement.handle_event()`:
- **Old:** `handle_event(self, event_type: str, ...)`
- **New:** `handle_event(self, event_type: UIEventType, ...)`

Migration: Replace string literals with enum values.

## Estimated Effort

- Implementation: 1.5 hours
- Testing: 1 hour
- Documentation: 30 minutes
- **Total: 3 hours**
