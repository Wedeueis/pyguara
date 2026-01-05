"""Finite State Machine (FSM) implementation."""

from abc import ABC, abstractmethod
from typing import Dict, Optional

from pyguara.ai.blackboard import Blackboard
from pyguara.ecs.entity import Entity


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
    def update(self, dt: float) -> Optional[str]:
        """
        Update the state logic.

        Returns:
            Name of the next state to transition to, or None to stay.
        """
        pass


class StateMachine:
    """Manages states and transitions for an entity."""

    def __init__(self, entity: Entity, blackboard: Blackboard):
        """Initialize the State Machine of an entity and a Blackboard."""
        self.entity = entity
        self.blackboard = blackboard
        self._states: Dict[str, State] = {}
        self._current_state: Optional[State] = None
        self._current_state_name: str = ""

    def add_state(self, name: str, state: State) -> None:
        """Register a state instance."""
        self._states[name] = state

    def set_initial_state(self, name: str) -> None:
        """Set the starting state."""
        if name in self._states:
            self._current_state = self._states[name]
            self._current_state_name = name
            self._current_state.on_enter()

    def update(self, dt: float) -> None:
        """Update current state and handle transitions."""
        if not self._current_state:
            return

        # Update returns potential transition
        next_state_name = self._current_state.update(dt)

        if next_state_name and next_state_name != self._current_state_name:
            self._transition_to(next_state_name)

    def _transition_to(self, name: str) -> None:
        """Execute transition logic."""
        if name not in self._states:
            return

        if self._current_state:
            self._current_state.on_exit()

        self._current_state = self._states[name]
        self._current_state_name = name
        self._current_state.on_enter()
