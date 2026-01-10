# Implementation Plan: P0-006 Gamepad Support

**Issue ID:** P0-006
**Priority:** Critical (P0)
**Assignee:** TBD
**Status:** Ready
**Branch:** `feature/P0-006-gamepad-support`

## Summary

Implement comprehensive gamepad/controller support with action mapping, deadzone configuration, and multi-controller support.

## Files to Create/Modify

**New Files:**
- `pyguara/input/gamepad.py` (GamepadManager class)
- `pyguara/input/events.py` (GamepadButtonEvent, GamepadAxisEvent) - may exist

**Modified Files:**
- `pyguara/input/types.py` (add GamepadButton, GamepadAxis enums)
- `pyguara/input/manager.py` (integrate GamepadManager)
- `tests/test_input.py` (gamepad tests)
- `pyguara/application/bootstrap.py` (register gamepad in DI)

## Implementation Checklist

### Step 1: Define Gamepad Types (2 hours)
- [ ] Create `GamepadButton` enum (A, B, X, Y, bumpers, etc.)
- [ ] Create `GamepadAxis` enum (sticks, triggers)
- [ ] Create `GamepadState` dataclass
- [ ] Create `GamepadConfig` dataclass (deadzone, etc.)
- [ ] Create `GamepadButtonEvent` and `GamepadAxisEvent`

### Step 2: Implement GamepadManager (4 hours)
- [ ] Initialize pygame.joystick module
- [ ] Implement device scanning (`_scan_devices()`)
- [ ] Implement hot-plug detection
- [ ] Implement button state tracking with events
- [ ] Implement axis state tracking with deadzone
- [ ] Add `get_button()` and `get_axis()` query methods
- [ ] Implement rumble/vibration support (if available)

### Step 3: Integrate with InputManager (1 hour)
- [ ] Add `GamepadManager` as property
- [ ] Call `gamepad_manager.update()` in InputManager.update()
- [ ] Ensure events fire through EventDispatcher

### Step 4: Action Mapping System (3 hours)
- [ ] Design InputAction abstraction
- [ ] Map logical actions (Jump, Attack) to physical inputs
- [ ] Support keyboard OR gamepad for same action
- [ ] Configuration file format (JSON/TOML)
- [ ] Runtime rebinding support

### Step 5: Comprehensive Testing (3 hours)
- [ ] Test: Gamepad detection and initialization
- [ ] Test: Button press events fire correctly
- [ ] Test: Axis values with deadzone application
- [ ] Test: Multiple controllers distinguished
- [ ] Test: Hot-plug/unplug handling
- [ ] Mock joystick for testing (pytest-mock)
- [ ] Integration test with actual controller (manual)

### Step 6: Documentation (2 hours)
- [ ] API documentation for GamepadManager
- [ ] Tutorial: Setting up gamepad controls
- [ ] Example: 2-player local multiplayer
- [ ] Controller compatibility notes

## Acceptance Criteria

- [ ] Detects connected gamepads on startup
- [ ] Hot-plug support works
- [ ] All standard buttons accessible
- [ ] Analog sticks work with configurable deadzone
- [ ] Triggers work correctly
- [ ] Multiple controllers can be used simultaneously
- [ ] Events fire through EventDispatcher
- [ ] Tests pass (pytest tests/test_input.py)
- [ ] Type checking passes (mypy pyguara/input/)
- [ ] Example game uses gamepad controls

## Testing Commands

```bash
# Unit tests
pytest tests/test_input.py::test_gamepad_* -v

# All input tests
pytest tests/test_input.py -v

# Type check
mypy pyguara/input/

# Manual test (requires physical controller)
python examples/gamepad_test.py
```

## Implementation Reference

See: `docs/dev/backlog/2026-01-09-product-enhancement-proposal.md` Section 8.4
(Complete implementation provided in PEP)

## Dependencies

- pygame-ce ≥ 2.5.6 (joystick API)
- pytest-mock for testing

## Performance Targets

- < 1ms per frame for gamepad polling
- Support 4+ simultaneous controllers
- Zero input lag (same-frame event dispatch)

## Future Enhancements (Post-P0)

- Input recording/playback
- Gamepad profiles per game
- Steam Input integration
- Custom controller mapping UI

## Estimated Effort

- Implementation: 10 hours
- Testing: 3 hours
- Documentation: 2 hours
- **Total: 15 hours (~2 days)**

## Implementation Priority

**Week 2 of Phase 1** - After core system fixes (P0-001, P0-002, P0-003)
This is a prerequisite for shipping any game that requires controller support.
