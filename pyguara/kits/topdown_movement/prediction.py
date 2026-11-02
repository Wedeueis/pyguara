"""Letting a networked client predict a top-down character.

`pyguara.net` knows nothing about movement, so this is what connects the two. It only
matches `pyguara.net.prediction.PredictedBody`'s shape, and imports nothing from the
network package.

`velocity_of` runs on both machines, on a command that came over the network on one of
them. Velocity must be a pure function of the command, or a replay has nothing to re-run,
and it must limit what it returns, because the command is untrusted on the host.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from pyguara.common.components import Transform
from pyguara.common.types import Vector2
from pyguara.ecs.entity import Entity
from pyguara.kits.topdown_movement.body import TopDownBody
from pyguara.kits.topdown_movement.system import step_body
from pyguara.physics.character_mover import CharacterMover
from pyguara.physics.components import Collider


class TopDownPrediction:
    """One top-down character's state and step, for prediction to capture and replay."""

    def __init__(
        self,
        entity: Entity,
        mover: CharacterMover,
        velocity_of: Callable[[Any], Vector2],
    ) -> None:
        """Bind to a character.

        Args:
            entity: Has a `TopDownBody` and a `Transform`, and may have a `Collider`.
            mover: Does the movement, against this machine's solids.
            velocity_of: Turns a command into a velocity. See the module docstring.
        """
        self._id = entity.id
        self._mover = mover
        self._velocity_of = velocity_of
        self._body = entity.get_component(TopDownBody)
        self._transform = entity.get_component(Transform)
        self._collider = (
            entity.get_component(Collider) if entity.has_component(Collider) else None
        )

    def capture(self) -> tuple[float, ...]:
        """Return everything the next step depends on."""
        position = self._transform.position
        remainder = self._body._remainder
        return (position.x, position.y, remainder.x, remainder.y)

    def restore(self, state: tuple[float, ...]) -> None:
        """Go back to a captured state."""
        self._transform.position = Vector2(state[0], state[1])
        self._body._remainder = Vector2(state[2], state[3])

    def advance(self, command: Any, dt: float) -> None:
        """Run one step of this character alone."""
        self._body.velocity = self._velocity_of(command)
        step_body(
            self._mover, self._id, self._body, self._transform, self._collider, dt
        )

    def position(self) -> tuple[float, float]:
        """Return where it is, to measure a correction."""
        position = self._transform.position
        return (position.x, position.y)

    def show_offset(self, x: float, y: float) -> None:
        """Draw it this far from where it is, until the next `restore`."""
        self._transform.position = self._transform.position + Vector2(x, y)
