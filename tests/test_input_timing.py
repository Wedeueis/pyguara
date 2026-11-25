"""Input buffering, held time and gestures, driven through `InputManager`.

Input time moves only on `advance`, so every test steps it by hand, as
`Application` does once a frame.
"""

from __future__ import annotations

import math

import pytest

from pyguara.events.dispatcher import EventDispatcher
from pyguara.events.input import KeyDownEvent, KeyUpEvent
from pyguara.input import (
    ActionSequence,
    Chord,
    DoubleTap,
    Hold,
    InputContext,
    PlayerRouter,
    Tap,
)
from pyguara.input.backends.null_backend import NullInputBackend
from pyguara.input.events import (
    GamepadButtonEvent,
    GamepadDisconnectedEvent,
    OnActionEvent,
)
from pyguara.input.manager import InputManager
from pyguara.input.types import ActionType, GamepadButton, InputDevice

JUMP, ATTACK, DOWN, LEFT = 32, 97, 115, 100


@pytest.fixture
def dispatcher() -> EventDispatcher:
    return EventDispatcher()


@pytest.fixture
def manager(dispatcher: EventDispatcher) -> InputManager:
    manager = InputManager(dispatcher, NullInputBackend())
    for name, key in (("jump", JUMP), ("attack", ATTACK), ("down", DOWN)):
        manager.register_action(name, ActionType.PRESS)
        manager.bind_input(InputDevice.KEYBOARD, key, name)
    manager.register_action("left", ActionType.HOLD)
    manager.bind_input(InputDevice.KEYBOARD, LEFT, "left")
    return manager


@pytest.fixture
def heard(dispatcher: EventDispatcher) -> list[tuple[str, int]]:
    events: list[tuple[str, int]] = []
    dispatcher.subscribe(
        OnActionEvent, lambda e: events.append((e.action_name, e.player))
    )
    return events


def _press(manager: InputManager, key: int) -> None:
    manager.process_event(KeyDownEvent(key_code=key))


def _release(manager: InputManager, key: int) -> None:
    manager.process_event(KeyUpEvent(key_code=key))


def _tap(manager: InputManager, key: int) -> None:
    _press(manager, key)
    _release(manager, key)


# --------------------------------------------------------------------------- #
# Buffering                                                                    #
# --------------------------------------------------------------------------- #


def test_a_press_is_buffered_for_the_window_and_no_longer(
    manager: InputManager,
) -> None:
    _tap(manager, JUMP)
    manager.advance(0.08)
    assert manager.was_pressed_within("jump", 0.1)
    manager.advance(0.03)
    assert not manager.was_pressed_within("jump", 0.1)


def test_a_consumed_press_fires_once(manager: InputManager) -> None:
    _tap(manager, JUMP)
    manager.advance(0.05)
    assert manager.consume_press("jump", 0.1)
    assert not manager.consume_press("jump", 0.1)
    assert not manager.was_pressed_within("jump", 0.1)


def test_nothing_pressed_is_not_buffered(manager: InputManager) -> None:
    assert not manager.was_pressed_within("jump", 10.0)


def test_a_bad_window_is_refused(manager: InputManager) -> None:
    for seconds in (-0.1, math.nan, math.inf):
        with pytest.raises(ValueError, match="0 or more"):
            manager.was_pressed_within("jump", seconds)


def test_time_only_moves_forward(manager: InputManager) -> None:
    for seconds in (-0.01, math.nan):
        with pytest.raises(ValueError, match="0 or more"):
            manager.advance(seconds)


def test_buffered_presses_are_per_player(dispatcher: EventDispatcher) -> None:
    router = PlayerRouter(dispatcher)
    manager = InputManager(dispatcher, NullInputBackend(), player_router=router)
    manager.register_action("jump", ActionType.PRESS)
    manager.bind_input(InputDevice.GAMEPAD, GamepadButton.A.value, "jump")
    router.assign(InputDevice.GAMEPAD, 0, 0)
    router.assign(InputDevice.GAMEPAD, 1, 1)

    dispatcher.dispatch(GamepadButtonEvent(1, GamepadButton.A, is_pressed=True))
    assert manager.was_pressed_within("jump", 0.1, player=1)
    assert not manager.was_pressed_within("jump", 0.1, player=0)


def test_an_unassigned_pad_buffers_nothing(dispatcher: EventDispatcher) -> None:
    manager = InputManager(
        dispatcher, NullInputBackend(), player_router=PlayerRouter(dispatcher)
    )
    manager.register_action("jump", ActionType.PRESS)
    manager.bind_input(InputDevice.GAMEPAD, GamepadButton.A.value, "jump")
    dispatcher.dispatch(GamepadButtonEvent(0, GamepadButton.A, is_pressed=True))
    assert not manager.was_pressed_within("jump", 0.1)
    assert not manager.is_held("jump")


# --------------------------------------------------------------------------- #
# Held time                                                                    #
# --------------------------------------------------------------------------- #


def test_held_time_counts_from_the_press(manager: InputManager) -> None:
    _press(manager, LEFT)
    manager.advance(0.25)
    assert manager.is_held("left")
    assert manager.held_for("left") == pytest.approx(0.25)
    _release(manager, LEFT)
    assert not manager.is_held("left")
    assert manager.held_for("left") == 0.0


def test_a_repeating_key_does_not_restart_the_hold(manager: InputManager) -> None:
    _press(manager, LEFT)
    manager.advance(0.2)
    _press(manager, LEFT)
    assert manager.held_for("left") == pytest.approx(0.2)


def test_two_keys_on_one_action_hold_it_until_both_let_go(
    manager: InputManager,
) -> None:
    manager.bind_input(InputDevice.KEYBOARD, 1073741904, "left")
    _press(manager, LEFT)
    _press(manager, 1073741904)
    _release(manager, LEFT)
    assert manager.is_held("left")
    _release(manager, 1073741904)
    assert not manager.is_held("left")


def test_a_release_after_a_context_change_still_lets_go(
    manager: InputManager,
) -> None:
    _press(manager, LEFT)
    manager.context = InputContext.MENU
    _release(manager, LEFT)
    assert not manager.is_held("left")


def test_an_unplugged_pad_lets_go_of_what_it_held(
    dispatcher: EventDispatcher, manager: InputManager
) -> None:
    manager.bind_input(InputDevice.GAMEPAD, GamepadButton.X.value, "left")
    dispatcher.dispatch(GamepadButtonEvent(0, GamepadButton.X, is_pressed=True))
    assert manager.is_held("left")
    dispatcher.dispatch(GamepadDisconnectedEvent(controller_id=0))
    assert not manager.is_held("left")


def test_reset_forgets_held_and_buffered(manager: InputManager) -> None:
    _press(manager, LEFT)
    _tap(manager, JUMP)
    manager.reset_timing()
    assert not manager.is_held("left")
    assert not manager.was_pressed_within("jump", 1.0)


# --------------------------------------------------------------------------- #
# Gestures                                                                     #
# --------------------------------------------------------------------------- #


def test_a_hold_fires_once_when_its_time_is_reached(
    manager: InputManager, heard: list[tuple[str, int]]
) -> None:
    manager.add_gesture(Hold("charge", "attack", seconds=0.5))
    _press(manager, ATTACK)
    manager.advance(0.4)
    assert ("charge", 0) not in heard
    manager.advance(0.1)
    manager.advance(0.5)
    assert heard.count(("charge", 0)) == 1
    _release(manager, ATTACK)
    _press(manager, ATTACK)
    manager.advance(0.5)
    assert heard.count(("charge", 0)) == 2


def test_a_tap_fires_on_a_short_press_only(
    manager: InputManager, heard: list[tuple[str, int]]
) -> None:
    manager.add_gesture(Tap("jab", "attack", max_seconds=0.2))
    _press(manager, ATTACK)
    manager.advance(0.1)
    _release(manager, ATTACK)
    assert heard.count(("jab", 0)) == 1
    _press(manager, ATTACK)
    manager.advance(0.3)
    _release(manager, ATTACK)
    assert heard.count(("jab", 0)) == 1


def test_a_double_tap_fires_on_the_second_press_in_the_window(
    manager: InputManager, heard: list[tuple[str, int]]
) -> None:
    manager.add_gesture(DoubleTap("dash", "left", window=0.3))
    _tap(manager, LEFT)
    manager.advance(0.2)
    _tap(manager, LEFT)
    assert heard.count(("dash", 0)) == 1
    manager.advance(0.1)
    _tap(manager, LEFT)
    assert heard.count(("dash", 0)) == 1, "a third press starts a new pair"


def test_a_double_tap_too_slow_does_not_fire(
    manager: InputManager, heard: list[tuple[str, int]]
) -> None:
    manager.add_gesture(DoubleTap("dash", "left", window=0.3))
    _tap(manager, LEFT)
    manager.advance(0.4)
    _tap(manager, LEFT)
    assert ("dash", 0) not in heard


def test_a_chord_fires_when_all_are_down_in_any_order(
    manager: InputManager, heard: list[tuple[str, int]]
) -> None:
    manager.add_gesture(Chord("special", ("attack", "jump"), window=0.1))
    _press(manager, JUMP)
    manager.advance(0.05)
    _press(manager, ATTACK)
    assert heard.count(("special", 0)) == 1
    _release(manager, JUMP)
    _press(manager, JUMP)
    assert heard.count(("special", 0)) == 2


def test_a_chord_pressed_too_far_apart_does_not_fire(
    manager: InputManager, heard: list[tuple[str, int]]
) -> None:
    manager.add_gesture(Chord("special", ("attack", "jump"), window=0.1))
    _press(manager, JUMP)
    manager.advance(0.2)
    _press(manager, ATTACK)
    assert ("special", 0) not in heard


def test_a_sequence_fires_in_order_and_in_time(
    manager: InputManager, heard: list[tuple[str, int]]
) -> None:
    manager.add_gesture(ActionSequence("slam", ("down", "down", "attack")))
    for key in (DOWN, DOWN, DOWN, LEFT, ATTACK):
        _tap(manager, key)
        manager.advance(0.1)
    assert heard.count(("slam", 0)) == 1


def test_a_sequence_out_of_time_or_order_does_not_fire(
    manager: InputManager, heard: list[tuple[str, int]]
) -> None:
    manager.add_gesture(ActionSequence("slam", ("down", "down", "attack")))
    for key in (DOWN, ATTACK, DOWN):
        _tap(manager, key)
    _tap(manager, DOWN)
    manager.advance(0.5)
    _tap(manager, ATTACK)
    assert ("slam", 0) not in heard


def test_a_gesture_is_buffered_like_a_press(manager: InputManager) -> None:
    manager.add_gesture(DoubleTap("dash", "left"))
    _tap(manager, LEFT)
    _tap(manager, LEFT)
    manager.advance(0.05)
    assert manager.consume_press("dash", 0.1)


def test_gestures_are_per_player(
    dispatcher: EventDispatcher, heard: list[tuple[str, int]]
) -> None:
    router = PlayerRouter(dispatcher)
    manager = InputManager(dispatcher, NullInputBackend(), player_router=router)
    manager.register_action("attack", ActionType.PRESS)
    manager.bind_input(InputDevice.GAMEPAD, GamepadButton.X.value, "attack")
    manager.add_gesture(DoubleTap("flurry", "attack"))
    router.assign(InputDevice.GAMEPAD, 0, 0)
    router.assign(InputDevice.GAMEPAD, 1, 1)

    for pad in (0, 1):
        dispatcher.dispatch(GamepadButtonEvent(pad, GamepadButton.X, True))
        dispatcher.dispatch(GamepadButtonEvent(pad, GamepadButton.X, False))
    assert ("flurry", 0) not in heard and ("flurry", 1) not in heard
    dispatcher.dispatch(GamepadButtonEvent(1, GamepadButton.X, True))
    assert ("flurry", 1) in heard and ("flurry", 0) not in heard


def test_a_removed_gesture_no_longer_fires(
    manager: InputManager, heard: list[tuple[str, int]]
) -> None:
    manager.add_gesture(DoubleTap("dash", "left"))
    _tap(manager, LEFT)
    manager.remove_gesture("dash")
    _tap(manager, LEFT)
    assert ("dash", 0) not in heard
    assert manager.gestures == ()
    with pytest.raises(KeyError, match="dash"):
        manager.remove_gesture("dash")


@pytest.mark.parametrize(
    ("gesture", "match"),
    [
        (Hold("charge", "fly", 0.5), "unregistered"),
        (Hold("jump", "attack", 0.5), "registered action"),
        (Chord("both", ("attack", "nope")), "unregistered"),
    ],
)
def test_a_gesture_on_unknown_actions_or_a_taken_name_is_refused(
    manager: InputManager, gesture: Hold | Chord, match: str
) -> None:
    with pytest.raises(ValueError, match=match):
        manager.add_gesture(gesture)


def test_two_gestures_cannot_share_a_name(manager: InputManager) -> None:
    manager.add_gesture(Tap("jab", "attack"))
    with pytest.raises(ValueError, match="already"):
        manager.add_gesture(DoubleTap("jab", "attack"))


@pytest.mark.parametrize(
    ("make", "match"),
    [
        (lambda: Hold("charge", "attack", 0.0), "above 0"),
        (lambda: Tap("jab", "attack", math.nan), "above 0"),
        (lambda: Hold("", "attack", 1.0), "needs a name"),
        (lambda: Tap("attack", "attack"), "own name"),
        (lambda: Chord("c", ("attack",)), "at least two"),
        (lambda: Chord("c", ("attack", "attack")), "twice"),
        (lambda: ActionSequence("s", ["a", "b"]), "tuple"),  # type: ignore[arg-type]
    ],
)
def test_a_malformed_gesture_is_refused(make: object, match: str) -> None:
    assert callable(make)
    with pytest.raises(ValueError, match=match):
        make()
