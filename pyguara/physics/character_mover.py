"""Move a character by sweeping it and stopping flush against what it hits.

The engine's platformer characters are dynamic rigid bodies whose velocity is
assigned each tick. That works until the character is pressed into geometry:
the solver is left to push it back out, and while it does, the character is
*inside* the world. Measured in guara_falcao, a character that jumped while
running landed 8px inside the floor and climbed out at 0.04px a tick -- it
reads as sinking into the ground.

This is the other approach, and the one platformers generally use (Godot's
`move_and_slide`, Unity's `CharacterController`, and -- the model this
follows -- Celeste's `Actor`/`Solid`): move the character yourself, and stop
it flush the moment the next step would overlap something. Penetration is
not resolved after the fact because it never happens.

Position is kept to whole pixels. A float `remainder` accumulates whatever
motion didn't add up to a whole pixel yet -- gravity at 900px/s^2 is 15px a
tick at 60Hz but rarely a whole number of pixels -- so nothing is lost to
rounding and nothing drifts: the same input produces the same motion
regardless of how the sub-pixel amounts happened to fall. Only whole pixels
are ever stepped, and every one of them is tested, which is what makes
tunnelling impossible without a bisection to settle where the character
actually stops -- the last free whole pixel *is* the answer.

What this deliberately does not do: rotate, or handle slopes. It is an
axis-aligned mover for characters, not a physics solver. Pushing other
boxes and being carried by moving ones is `SolidMover`, built on top of this.
"""

from __future__ import annotations

from dataclasses import dataclass

from pyguara.common.types import Vector2
from pyguara.physics.protocols import IPhysicsEngine

# The probe box is shrunk by this much on each side before every overlap
# query. Without it, a character resting exactly flush against a surface
# would read as overlapping it -- Chipmunk's `shape_query` counts an exact
# touch as an overlap -- and the very next whole-pixel step in the same
# direction would report blocked a pixel early. SKIN is applied only to the
# query box, never to the position a character actually occupies, so it
# does not change where anything ends up settling; it only keeps a resting
# contact from poisoning the next step's query. Unity calls the same
# allowance skin width. It is well under a pixel.
SKIN = 0.05


@dataclass(frozen=True)
class MoveResult:
    """What a move ran into.

    Attributes:
        position: Where the character ended up. Always whole pixels.
        remainder: Sub-pixel motion not yet spent, to be passed back into
            the next call so it accumulates rather than being discarded.
        hit_x: True if horizontal motion was stopped by something.
        hit_y: True if vertical motion was stopped by something.
        blocking_x: Entity that stopped horizontal motion, or None.
        blocking_y: Entity that stopped vertical motion, or None.
        grounded: True if this call's downward motion was stopped -- the
            character landed or is resting against something below it.
            False on a tick where nothing moved it downward at all (e.g.
            already resting, with velocity clamped to zero), even though
            it may still be on the ground; continuous "is grounded" state
            is `probe()`'s job, not this field's.
    """

    position: Vector2
    remainder: Vector2
    hit_x: bool
    hit_y: bool
    blocking_x: int | str | None
    blocking_y: int | str | None
    grounded: bool


class CharacterMover:
    """Sweeps a character's box through the world one whole pixel at a time.

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
        remainder: Vector2 = Vector2(0.0, 0.0),
        entity_id: int | str | None = None,
    ) -> MoveResult:
        """Move as far along `delta` as the world allows.

        Args:
            position: Current centre of the character's box, whole pixels.
            half_extents: Half width and half height of that box.
            delta: Desired movement this tick, in pixels -- typically
                `velocity * dt`, and rarely a whole number.
            remainder: Sub-pixel motion carried over from the previous call.
                Pass `MoveResult.remainder` back in every tick; the zero
                default is only for a character's first move.
            entity_id: The character, excluded from overlap tests so it does
                not detect its own collider.

        Returns:
            The final position, the leftover remainder, and what stopped it.
        """
        x, rem_x, hit_x, block_x = self._move_axis(
            position.x,
            half_extents,
            delta.x,
            remainder.x,
            position,
            horizontal=True,
            entity_id=entity_id,
        )
        position = Vector2(x, position.y)

        y, rem_y, hit_y, block_y = self._move_axis(
            position.y,
            half_extents,
            delta.y,
            remainder.y,
            position,
            horizontal=False,
            entity_id=entity_id,
        )

        return MoveResult(
            position=Vector2(x, y),
            remainder=Vector2(rem_x, rem_y),
            hit_x=hit_x,
            hit_y=hit_y,
            blocking_x=block_x,
            blocking_y=block_y,
            grounded=hit_y and delta.y > 0,
        )

    def probe(
        self,
        position: Vector2,
        half_extents: Vector2,
        direction: Vector2,
        entity_id: int | str | None = None,
    ) -> int | str | None:
        """Report what, if anything, is one pixel away in `direction`.

        A contact check that does not move or depend on velocity -- Celeste's
        `OnGround()` is exactly `CollideCheck(Position + Vector2.UnitY)`, an
        overlap test one pixel below, not a raycast. Ground/wall detection
        built on a raycast has to work around the query's own geometry (a
        swept circle can reach back into the caster); a probe built from the
        same overlap primitive as `move()` can't have that problem, because
        it is the same test a step would make.

        Args:
            position: The character's current centre.
            half_extents: Half width and half height of its box.
            direction: Which side to probe; only each axis's sign matters,
                so `Vector2(0, 1)` probes one pixel below and
                `Vector2(-1, 0)` probes one pixel to the left.
            entity_id: The character, excluded from the test.

        Returns:
            The entity id found there, or None if that pixel is clear.
        """
        offset = Vector2(
            1.0 if direction.x > 0 else -1.0 if direction.x < 0 else 0.0,
            1.0 if direction.y > 0 else -1.0 if direction.y < 0 else 0.0,
        )
        centre = Vector2(position.x + offset.x, position.y + offset.y)
        probe_half = Vector2(
            max(half_extents.x - SKIN, 0.01), max(half_extents.y - SKIN, 0.01)
        )
        return self._engine.overlap_box(centre, probe_half, entity_id)

    def _move_axis(
        self,
        current: float,
        half_extents: Vector2,
        distance: float,
        remainder: float,
        position: Vector2,
        horizontal: bool,
        entity_id: int | str | None,
    ) -> tuple[float, float, bool, int | str | None]:
        """Advance along one axis by whole pixels, banking the remainder.

        Args:
            current: Starting coordinate on this axis.
            half_extents: Half size of the character's box.
            distance: Signed distance requested on this axis this tick.
            remainder: Unspent sub-pixel motion from previous ticks.
            position: The character's full position, for the axis held
                fixed while this one is swept.
            horizontal: True for x, False for y.
            entity_id: Body to ignore.

        Returns:
            The coordinate reached, the new remainder, whether something
            stopped it short, and what that was.
        """
        remainder += distance
        amount = round(remainder)
        remainder -= amount

        if amount == 0:
            return current, remainder, False, None

        step = 1 if amount > 0 else -1
        blocking: int | str | None = None
        while amount != 0:
            candidate = current + step
            blocker = self._overlaps(
                position, half_extents, candidate, horizontal, entity_id
            )
            if blocker is not None:
                blocking = blocker
                # Discard the banked remainder for the distance that
                # couldn't be travelled -- otherwise the moment the
                # obstruction clears, the character lurches forward by
                # everything gravity or input piled up while it was stuck.
                remainder = 0.0
                break
            current = candidate
            amount -= step

        return current, remainder, blocking is not None, blocking

    def _overlaps(
        self,
        position: Vector2,
        half_extents: Vector2,
        coordinate: float,
        horizontal: bool,
        entity_id: int | str | None,
    ) -> int | str | None:
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
