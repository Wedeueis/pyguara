"""Gestures built from actions: hold, tap, double-tap, chords and sequences.

A gesture watches actions being pressed and released, not keys, so it
follows rebinding and every device bound to the action. When one
completes, `InputManager` dispatches an `OnActionEvent` under the
gesture's name for the player who made it. A gesture never watches
another gesture.
"""

from __future__ import annotations

import math
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass
from itertools import pairwise


def _check_name(name: str, sources: tuple[str, ...]) -> None:
    """Refuse an empty gesture name, or one that is also its own source.

    Raises:
        ValueError: If `name` is empty or among `sources`.
    """
    if not name:
        raise ValueError("a gesture needs a name")
    if name in sources:
        raise ValueError(f"gesture {name!r} cannot watch an action of its own name")


def _check_seconds(label: str, seconds: float) -> None:
    """Refuse a time that is not a finite number above 0.

    Raises:
        ValueError: If `seconds` is not finite and above 0.
    """
    if not (math.isfinite(seconds) and seconds > 0.0):
        raise ValueError(f"{label} must be a finite number above 0, got {seconds}")


def _check_actions(name: str, actions: tuple[str, ...]) -> None:
    """Refuse fewer than two actions, or a list that is not a tuple.

    Raises:
        ValueError: If `actions` is not a tuple of at least two names.
    """
    value: object = actions
    if not isinstance(value, tuple) or len(actions) < 2:
        raise ValueError(f"gesture {name!r} needs a tuple of at least two actions")


@dataclass(frozen=True, slots=True)
class Hold:
    """Fires once when `action` has been held down for `seconds`.

    It fires again only after the action is released and held again.
    """

    name: str
    action: str
    seconds: float

    def __post_init__(self) -> None:
        """Check the name and time.

        Raises:
            ValueError: If the name is empty or the action's own, or
                `seconds` is not a finite number above 0.
        """
        _check_name(self.name, (self.action,))
        _check_seconds("seconds", self.seconds)

    @property
    def watches(self) -> tuple[str, ...]:
        """The actions this gesture is made from."""
        return (self.action,)


@dataclass(frozen=True, slots=True)
class Tap:
    """Fires when `action` is released within `max_seconds` of its press."""

    name: str
    action: str
    max_seconds: float = 0.2

    def __post_init__(self) -> None:
        """Check the name and time.

        Raises:
            ValueError: If the name is empty or the action's own, or
                `max_seconds` is not a finite number above 0.
        """
        _check_name(self.name, (self.action,))
        _check_seconds("max_seconds", self.max_seconds)

    @property
    def watches(self) -> tuple[str, ...]:
        """The actions this gesture is made from."""
        return (self.action,)


@dataclass(frozen=True, slots=True)
class DoubleTap:
    """Fires on a press of `action` within `window` seconds of the last one.

    A third press starts a new pair, so a triple press fires once.
    """

    name: str
    action: str
    window: float = 0.3

    def __post_init__(self) -> None:
        """Check the name and time.

        Raises:
            ValueError: If the name is empty or the action's own, or
                `window` is not a finite number above 0.
        """
        _check_name(self.name, (self.action,))
        _check_seconds("window", self.window)

    @property
    def watches(self) -> tuple[str, ...]:
        """The actions this gesture is made from."""
        return (self.action,)


@dataclass(frozen=True, slots=True)
class Chord:
    """Fires when every one of `actions` is down, all pressed within `window`.

    The order does not matter. It fires once, and again only after one of
    the actions is released and the chord is made again.
    """

    name: str
    actions: tuple[str, ...]
    window: float = 0.1

    def __post_init__(self) -> None:
        """Check the name, actions and time.

        Raises:
            ValueError: If the name is empty or one of the actions, there
                are fewer than two distinct actions, or `window` is not a
                finite number above 0.
        """
        _check_actions(self.name, self.actions)
        if len(set(self.actions)) != len(self.actions):
            raise ValueError(f"chord {self.name!r} names an action twice")
        _check_name(self.name, self.actions)
        _check_seconds("window", self.window)

    @property
    def watches(self) -> tuple[str, ...]:
        """The actions this gesture is made from."""
        return self.actions


@dataclass(frozen=True, slots=True)
class ActionSequence:
    """Fires when `actions` are pressed in order, each within `window` of the last.

    Presses of actions the sequence does not name are ignored, so moving
    while entering it does not break it.
    """

    name: str
    actions: tuple[str, ...]
    window: float = 0.4

    def __post_init__(self) -> None:
        """Check the name, actions and time.

        Raises:
            ValueError: If the name is empty or one of the actions, there
                are fewer than two actions, or `window` is not a finite
                number above 0.
        """
        _check_actions(self.name, self.actions)
        _check_name(self.name, self.actions)
        _check_seconds("window", self.window)

    @property
    def watches(self) -> tuple[str, ...]:
        """The actions this gesture is made from."""
        return self.actions


Gesture = Hold | Tap | DoubleTap | Chord | ActionSequence
"""Any one of the gestures `InputManager.add_gesture` takes."""

Fired = list[tuple[int, str]]
"""Gestures that completed, as (player, gesture name), in the order made."""


class ActionTracker:
    """What each player is holding, when each action was last pressed, and gestures.

    It is fed the press and release of each input source (a key, button or
    mouse button) with the actions it drives, and the time. Times are
    seconds on the clock `InputManager.advance` moves.
    """

    def __init__(self) -> None:
        """Start with nothing held, pressed or in progress."""
        self._gestures: dict[str, Gesture] = {}
        # Which (player, action) pairs each held source pressed, so its
        # release lets go of them whatever the input context is by then.
        self._sources: dict[object, list[tuple[int, str]]] = {}
        self._holders: dict[tuple[int, str], set[object]] = {}
        self._down_since: dict[tuple[int, str], float] = {}
        self._last_press: dict[tuple[int, str], float] = {}
        self._fired: set[tuple[int, str]] = set()
        self._last_tap: dict[tuple[int, str], float] = {}
        self._history: dict[tuple[int, str], deque[tuple[str, float]]] = {}

    @property
    def gestures(self) -> tuple[Gesture, ...]:
        """The gestures being recognised, in the order they were added."""
        return tuple(self._gestures.values())

    def add(self, gesture: Gesture) -> None:
        """Start recognising `gesture`.

        Raises:
            ValueError: If a gesture of that name is already recognised.
        """
        if gesture.name in self._gestures:
            raise ValueError(f"there is already a gesture named {gesture.name!r}")
        self._gestures[gesture.name] = gesture

    def remove(self, name: str) -> None:
        """Stop recognising the gesture `name`, dropping its progress.

        Raises:
            KeyError: If no gesture has that name.
        """
        if name not in self._gestures:
            raise KeyError(f"no gesture named {name!r}")
        del self._gestures[name]
        self._fired = {key for key in self._fired if key[1] != name}
        self._last_tap = {k: v for k, v in self._last_tap.items() if k[1] != name}
        self._history = {k: v for k, v in self._history.items() if k[1] != name}

    def reset(self) -> None:
        """Forget everything held, pressed and in progress; keep the gestures."""
        self._sources.clear()
        self._holders.clear()
        self._down_since.clear()
        self._last_press.clear()
        self._fired.clear()
        self._last_tap.clear()
        self._history.clear()

    def is_held(self, action: str, player: int) -> bool:
        """Whether any source is holding `action` down for `player`."""
        return (player, action) in self._down_since

    def held_for(self, action: str, player: int, now: float) -> float:
        """Seconds `player` has held `action` down, or 0 when it is up."""
        since = self._down_since.get((player, action))
        return 0.0 if since is None else now - since

    def is_source_down(self, source: object) -> bool:
        """Whether `source` is down, so a press of it is a repeat."""
        return source in self._sources

    def last_press(self, action: str, player: int) -> float | None:
        """When `player` last pressed `action` or made that gesture, if ever."""
        return self._last_press.get((player, action))

    def forget_press(self, action: str, player: int) -> None:
        """Drop `player`'s last press of `action`, so it is not buffered again."""
        self._last_press.pop((player, action), None)

    def press(
        self, source: object, player: int, actions: list[str], now: float
    ) -> Fired:
        """Record `source` going down, driving `actions` for `player`.

        A source already down (a key repeating) changes nothing.
        """
        if source in self._sources:
            return []
        pairs = [(player, action) for action in actions]
        self._sources[source] = pairs
        fired: Fired = []
        for key in pairs:
            holders = self._holders.setdefault(key, set())
            holders.add(source)
            if len(holders) == 1:
                self._down_since[key] = now
                self._last_press[key] = now
                self._pressed(key[0], key[1], now, fired)
        return fired

    def release(self, source: object, now: float) -> Fired:
        """Record `source` going up, letting go of whatever it pressed."""
        fired: Fired = []
        for key in self._sources.pop(source, []):
            holders = self._holders.get(key)
            if holders is None:
                continue
            holders.discard(source)
            if not holders:
                del self._holders[key]
                since = self._down_since.pop(key)
                self._released(key[0], key[1], now, now - since, fired)
        return fired

    def release_matching(self, matches: Callable[[object], bool], now: float) -> Fired:
        """Release every held source for which `matches(source)` is true."""
        fired: Fired = []
        for source in [s for s in self._sources if matches(s)]:
            fired.extend(self.release(source, now))
        return fired

    def advance(self, now: float) -> Fired:
        """Fire every hold that has reached its time by `now`."""
        fired: Fired = []
        for gesture in self._gestures.values():
            if not isinstance(gesture, Hold):
                continue
            for (player, action), since in self._down_since.items():
                key = (player, gesture.name)
                if (
                    action == gesture.action
                    and key not in self._fired
                    and now - since >= gesture.seconds
                ):
                    self._fire(key, now, fired, latch=True)
        return fired

    def _fire(
        self, key: tuple[int, str], now: float, fired: Fired, *, latch: bool = False
    ) -> None:
        """Record a gesture made and buffer it; a latched one waits for a release."""
        if latch:
            self._fired.add(key)
        self._last_press[key] = now
        fired.append(key)

    def _pressed(self, player: int, action: str, now: float, fired: Fired) -> None:
        """Advance every press-driven gesture watching `action`."""
        for gesture in self._gestures.values():
            key = (player, gesture.name)
            if isinstance(gesture, DoubleTap) and gesture.action == action:
                previous = self._last_tap.pop(key, None)
                if previous is not None and now - previous <= gesture.window:
                    self._fire(key, now, fired)
                else:
                    self._last_tap[key] = now
            elif isinstance(gesture, Chord) and action in gesture.actions:
                times = [self._down_since.get((player, a)) for a in gesture.actions]
                if key not in self._fired and all(t is not None for t in times):
                    held = [t for t in times if t is not None]
                    if max(held) - min(held) <= gesture.window:
                        self._fire(key, now, fired, latch=True)
            elif isinstance(gesture, ActionSequence) and action in gesture.actions:
                history = self._history.setdefault(
                    key, deque(maxlen=len(gesture.actions))
                )
                history.append((action, now))
                if self._completes(gesture, history):
                    history.clear()
                    self._fire(key, now, fired)

    def _released(
        self, player: int, action: str, now: float, held: float, fired: Fired
    ) -> None:
        """Fire taps, and let holds and chords on `action` be made again."""
        for gesture in self._gestures.values():
            key = (player, gesture.name)
            if (isinstance(gesture, Hold) and gesture.action == action) or (
                isinstance(gesture, Chord) and action in gesture.actions
            ):
                self._fired.discard(key)
            elif (
                isinstance(gesture, Tap)
                and gesture.action == action
                and held <= gesture.max_seconds
            ):
                self._fire(key, now, fired)

    @staticmethod
    def _completes(gesture: ActionSequence, history: deque[tuple[str, float]]) -> bool:
        """Whether the last presses are the sequence, each in time."""
        if len(history) < len(gesture.actions):
            return False
        if tuple(action for action, _ in history) != gesture.actions:
            return False
        times = [t for _, t in history]
        return all(b - a <= gesture.window for a, b in pairwise(times))
