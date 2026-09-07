"""Move a character by sweeping it and stopping flush against what it hits.

The engine's platformer characters are dynamic rigid bodies whose velocity is
assigned each tick. That works until the character is pressed into geometry:
the solver is left to push it back out, and while it does, the character is
*inside* the world. Measured in guara_falcao, a character that jumped while
running landed 8px inside the floor and climbed out at 0.04px a tick -- it
reads as sinking into the ground.

This is the other approach, and the one platformers generally use (Godot's
`move_and_slide`, Unity's `CharacterController`, Celeste's actors): move the
character yourself, in steps small enough to never skip a surface, and stop
it flush the moment the next step would overlap something. Penetration is
not resolved after the fact because it never happens.

What this deliberately does not do: rotate, push dynamic bodies, or handle
slopes. It is an axis-aligned mover for characters, not a physics solver.
"""

from __future__ import annotations

from dataclasses import dataclass

from pyguara.common.types import Vector2
from pyguara.physics.protocols import IPhysicsEngine

# A step no larger than this is taken before testing for overlap. It bounds
# how far the character can move without being checked, so it is also what
# stops a fast character from stepping over a thin wall entirely.
MAX_STEP = 4.0

# Halvings used to settle against a surface. Eight brings a 4px step within
# ~0.016px, far below anything a 2D game can show.
BISECTIONS = 8

# The probe box is shrunk by this much on each side. Without it a character
# resting exactly flush on the floor reads as overlapping it -- a touching
# contact counts -- and then every candidate position looks blocked and the
# character cannot move at all. Unity calls the same allowance skin width.
# It is well under a pixel, and under Chipmunk's own 0.1px collision slop.
SKIN = 0.05


@dataclass(frozen=True)
class MoveResult:
    """What a move ran into.

    Attributes:
        position: Where the character ended up.
        hit_x: True if horizontal motion was stopped by something.
        hit_y: True if vertical motion was stopped by something.
        grounded: True if downward motion was stopped -- the character is
            resting on a surface rather than merely touching one.
    """

    position: Vector2
    hit_x: bool
    hit_y: bool
    grounded: bool


class CharacterMover:
    """Sweeps a character's box through the world one axis at a time.

    Axes are resolved separately, which is what produces sliding: a character
    walking into a wall keeps its vertical motion, and one landing while
    running keeps its horizontal motion.
    """

    def __init__(self, engine: IPhysicsEngine) -> None:
        """Store the engine used for overlap queries.

        Args:
            engine: Physics engine providing `overlap_box`.
        """
        self._engine = engine

    def move(
        self,
        position: Vector2,
        half_extents: Vector2,
        delta: Vector2,
        entity_id: int | str | None = None,
    ) -> MoveResult:
        """Move as far along `delta` as the world allows.

        Args:
            position: Current centre of the character's box.
            half_extents: Half width and half height of that box.
            delta: Desired movement this tick, in pixels.
            entity_id: The character, excluded from overlap tests so it does
                not detect its own collider.

        Returns:
            The final position and what stopped it.
        """
        x, hit_x = self._sweep_axis(
            position, half_extents, delta.x, horizontal=True, entity_id=entity_id
        )
        position = Vector2(x, position.y)

        y, hit_y = self._sweep_axis(
            position, half_extents, delta.y, horizontal=False, entity_id=entity_id
        )

        return MoveResult(
            position=Vector2(x, y),
            hit_x=hit_x,
            hit_y=hit_y,
            grounded=hit_y and delta.y > 0,
        )

    def _sweep_axis(
        self,
        position: Vector2,
        half_extents: Vector2,
        distance: float,
        horizontal: bool,
        entity_id: int | str | None,
    ) -> tuple[float, bool]:
        """Advance along one axis until blocked, then settle flush.

        Args:
            position: Starting centre.
            half_extents: Half size of the character's box.
            distance: Signed distance to travel on this axis.
            horizontal: True for x, False for y.
            entity_id: Body to ignore.

        Returns:
            The coordinate reached on this axis, and whether something
            stopped it short.
        """
        current = position.x if horizontal else position.y
        if distance == 0.0:
            return current, False

        direction = 1.0 if distance > 0 else -1.0
        remaining = abs(distance)

        while remaining > 0.0:
            step = direction * min(MAX_STEP, remaining)
            if not self._overlaps(
                position, half_extents, current + step, horizontal, entity_id
            ):
                current += step
                remaining -= abs(step)
                continue

            # Blocked within this step: bisect for the last free position, so
            # the character finishes touching the surface rather than inside
            # it or short of it by a visible gap.
            free, blocked = 0.0, step
            for _ in range(BISECTIONS):
                midpoint = (free + blocked) / 2
                if self._overlaps(
                    position, half_extents, current + midpoint, horizontal, entity_id
                ):
                    blocked = midpoint
                else:
                    free = midpoint
            return current + free, True

        return current, False

    def _overlaps(
        self,
        position: Vector2,
        half_extents: Vector2,
        coordinate: float,
        horizontal: bool,
        entity_id: int | str | None,
    ) -> bool:
        """Test the character's box at one candidate coordinate."""
        centre = (
            Vector2(coordinate, position.y)
            if horizontal
            else Vector2(position.x, coordinate)
        )
        probe = Vector2(
            max(half_extents.x - SKIN, 0.01), max(half_extents.y - SKIN, 0.01)
        )
        return self._engine.overlap_box(centre, probe, entity_id)
