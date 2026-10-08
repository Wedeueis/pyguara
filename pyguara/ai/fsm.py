"""Finite State Machine (FSM) implementation."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass

from pyguara.ai.blackboard import Blackboard
from pyguara.ecs.entity import Entity
from pyguara.log import get_logger

logger = get_logger(__name__)


class State(ABC):
    """Abstract base class for FSM states."""

    def __init__(self, entity: Entity, blackboard: Blackboard):
        """Initialize the state of an entity and a Blackboard."""
        self.entity = entity
        self.blackboard = blackboard

    @abstractmethod
    def on_enter(self) -> None:
        """Call when entering this state."""
        pass

    @abstractmethod
    def on_exit(self) -> None:
        """Call when exiting this state."""
        pass

    @abstractmethod
    def update(self, dt: float) -> str | None:
        """
        Update the state logic.

        Returns:
            Name of the next state to transition to, or None to stay.
        """
        pass


_ANY_STATE = "*"
"""Key under which "from any state" transitions are stored."""


@dataclass(frozen=True)
class _Transition:
    """One declared transition.

    Attributes:
        to_state: Where it goes.
        predicate: Condition on the machine, or None for "no condition".
        event: Event that must have been posted, or None for "any update".
    """

    to_state: str
    predicate: Callable[[StateMachine], bool] | None
    event: str | None


class StateMachine:
    """Manages states and transitions for an entity."""

    def __init__(self, entity: Entity, blackboard: Blackboard):
        """Initialize the State Machine of an entity and a Blackboard."""
        self.entity = entity
        self.blackboard = blackboard
        self._states: dict[str, State] = {}
        self._current_state: State | None = None
        self._current_state_name: str = ""
        # Transitions declared outside the states, so a state does not have
        # to know what comes after it. Keyed by source state; `_ANY_STATE`
        # holds the ones that apply everywhere.
        self._transitions: dict[str, list[_Transition]] = {}
        # Events fired since the last update, drained each tick.
        self._pending_events: list[str] = []

    def add_state(self, name: str, state: State) -> None:
        """Register a state instance."""
        self._states[name] = state

    def set_initial_state(self, name: str) -> None:
        """Set the starting state."""
        if name not in self._states:
            logger.warning(
                "set_initial_state(%r): no such state registered; "
                "the machine stays inert. Known states: %s",
                name,
                sorted(self._states),
            )
            return

        if self._current_state is not None:
            self._current_state.on_exit()

        self._current_state = self._states[name]
        self._current_state_name = name
        self._current_state.on_enter()

    def add_transition(
        self,
        from_state: str | None,
        to_state: str,
        predicate: Callable[[StateMachine], bool] | None = None,
        *,
        on_event: str | None = None,
    ) -> None:
        """Declare a transition outside the states themselves.

        Transitions used to exist *only* as a `State.update()` return value,
        which meant every state had to know which states follow it. A table
        keeps that knowledge in one place, so a state can be written once
        and reused in several machines, and so an FSM can be authored from
        data (#46).

        Args:
            from_state: The state this applies to, or None for "any state"
                -- the usual home for `on_damaged` style interrupts.
            to_state: Where to go.
            predicate: Called with this machine each update; the transition
                fires when it returns True. None means "always", which only
                makes sense together with `on_event`.
            on_event: Fire only when this event has been posted since the
                last update. Combined with `predicate`, both must hold.

        Raises:
            ValueError: If neither a predicate nor an event is given, which
                would be a transition that fires unconditionally every tick
                and so a state that can never be stayed in.
        """
        if predicate is None and on_event is None:
            raise ValueError(
                "add_transition needs a predicate, an on_event, or both -- "
                "otherwise it fires every tick and the source state can "
                "never be held."
            )
        key = _ANY_STATE if from_state is None else from_state
        self._transitions.setdefault(key, []).append(
            _Transition(to_state=to_state, predicate=predicate, event=on_event)
        )

    def post_event(self, event: str) -> None:
        """Queue an event for the next update.

        Queued rather than applied immediately so a transition never runs
        half-way through whatever code posted it -- a state's `on_exit`
        firing inside a collision callback is the kind of surprise that is
        very hard to trace back.

        Args:
            event: The event name, matched against `on_event`.
        """
        self._pending_events.append(event)

    def update(self, dt: float) -> None:
        """Update current state and handle transitions."""
        if not self._current_state:
            self._pending_events.clear()
            return

        events = self._pending_events
        self._pending_events = []

        # The table is checked first. A declared interrupt -- "on_damaged,
        # go to stagger, from anywhere" -- should win over whatever the
        # current state would otherwise have asked for.
        target = self._first_matching_transition(events)
        if target is not None:
            self._transition_to(target)
            return

        # Update returns potential transition
        next_state_name = self._current_state.update(dt)

        if next_state_name and next_state_name != self._current_state_name:
            self._transition_to(next_state_name)

    def _first_matching_transition(self, events: list[str]) -> str | None:
        """Return the first declared transition that fires now, if any.

        State-specific transitions are considered before any-state ones, so
        a state can override a global interrupt by declaring its own.

        Args:
            events: Events posted since the last update.

        Returns:
            The target state name, or None.
        """
        for key in (self._current_state_name, _ANY_STATE):
            for transition in self._transitions.get(key, ()):
                if transition.event is not None and transition.event not in events:
                    continue
                if transition.predicate is not None and not transition.predicate(self):
                    continue
                if transition.to_state == self._current_state_name:
                    continue
                return transition.to_state
        return None

    def _transition_to(self, name: str) -> None:
        """Execute transition logic."""
        if name not in self._states:
            logger.warning(
                "State %r asked to transition to %r, which is not registered; "
                "staying in %r. Known states: %s",
                self._current_state_name,
                name,
                self._current_state_name,
                sorted(self._states),
            )
            return

        if self._current_state:
            self._current_state.on_exit()

        self._current_state = self._states[name]
        self._current_state_name = name
        self._current_state.on_enter()
