"""Move a solid, carrying and pushing whatever it touches.

`CharacterMover` is how a character moves under its own control. This is
the other half of Celeste's model: how the *world* moves a character that
isn't driving -- riding a platform, or being shoved by one closing in from
the side or above.

A rider or a pushed actor is placed directly at the position the solid's
own motion dictates, not swept there: the solid has already decided exactly
where the actor is going, so there is nothing to search for. What has to be
checked afterwards is whether that position is actually clear of everything
*except* the solid that moved it -- if not, the actor has been squished
between it and something else, which is reported rather than silently
resolved, since what a squish should do (damage, death, nothing) is a game
decision, not a physics one.

This mirrors Celeste's `Solid.MoveHExact`/`MoveVExact`: riders are found by
their position *before* the solid moves (an actor resting flush on top),
carried by the exact same delta, then checked; anything not riding that the
solid's *new* footprint now overlaps is pushed clear along whichever axis
the solid is actually moving, then checked the same way.
"""

from __future__ import annotations

import time

from pyguara.common.components import Transform
from pyguara.common.types import Vector2
from pyguara.ecs.entity import Entity
from pyguara.ecs.manager import EntityManager
from pyguara.events.dispatcher import EventDispatcher
from pyguara.physics.character_mover import SKIN
from pyguara.physics.components import CharacterBody, Collider
from pyguara.physics.events import OnActorSquished
from pyguara.physics.protocols import IPhysicsEngine

# How close a resting gap can be and still count as riding. Matches the
# mover's own SKIN allowance: a swept actor settles within this of a
# surface, not necessarily at an exact zero gap.
RIDE_TOLERANCE = 1.0

_DEFAULT_HALF_EXTENTS = Vector2(12.0, 20.0)


def _half_extents(collider: Collider | None) -> Vector2:
    """Half width/height from a Collider, or a sane default without one."""
    if collider is None:
        return _DEFAULT_HALF_EXTENTS
    return Vector2(collider.dimensions[0] / 2, collider.dimensions[1] / 2)


def _shrink(half: Vector2) -> Vector2:
    """Apply the same skin allowance CharacterMover queries with."""
    return Vector2(max(half.x - SKIN, 0.01), max(half.y - SKIN, 0.01))


def _is_riding(
    actor_pos: Vector2, actor_half: Vector2, solid_pos: Vector2, solid_half: Vector2
) -> bool:
    """Report whether an actor rests on top of a solid, before it moves."""
    within_x = abs(actor_pos.x - solid_pos.x) < actor_half.x + solid_half.x
    actor_bottom = actor_pos.y + actor_half.y
    solid_top = solid_pos.y - solid_half.y
    return within_x and abs(actor_bottom - solid_top) <= RIDE_TOLERANCE


def _push_delta(
    actor_pos: Vector2,
    actor_half: Vector2,
    solid_pos: Vector2,
    solid_half: Vector2,
    solid_delta: Vector2,
) -> Vector2:
    """How far to shove an actor clear of a solid's new footprint.

    Along whichever axis the solid is actually moving -- the one it would
    feel like being pushed by -- resolving the smaller of the two overlaps
    first when it moves on both.
    """
    overlap_x = (actor_half.x + solid_half.x) - abs(actor_pos.x - solid_pos.x)
    overlap_y = (actor_half.y + solid_half.y) - abs(actor_pos.y - solid_pos.y)
    if overlap_x <= 0 or overlap_y <= 0:
        return Vector2(0, 0)

    if solid_delta.x != 0 and (solid_delta.y == 0 or overlap_x <= overlap_y):
        return Vector2(overlap_x if solid_delta.x > 0 else -overlap_x, 0)
    if solid_delta.y != 0:
        return Vector2(0, overlap_y if solid_delta.y > 0 else -overlap_y)
    return Vector2(0, 0)


class SolidMover:
    """Carries and pushes `CharacterBody` actors as a solid moves.

    Attributes:
        _entity_manager: Source of actor entities to check each move.
        _engine: Used only for the post-move squish check.
        _dispatcher: Notified of a squish, if given.
    """

    def __init__(
        self,
        entity_manager: EntityManager,
        engine: IPhysicsEngine,
        dispatcher: EventDispatcher | None = None,
    ) -> None:
        """Store collaborators.

        Args:
            entity_manager: Source of actor entities.
            engine: Physics engine, for the squish overlap check.
            dispatcher: Receives `OnActorSquished`, if given.
        """
        self._entity_manager = entity_manager
        self._engine = engine
        self._dispatcher = dispatcher

    def move_solid(
        self,
        solid_entity: Entity,
        delta: Vector2,
        exclude_entity_id: int | str | None = None,
    ) -> None:
        """Carry/push every actor touched by `solid_entity`'s move.

        Args:
            solid_entity: The solid, already at its destination Transform
                this tick -- this reacts to that displacement, it doesn't
                apply it.
            delta: How far `solid_entity` moved this tick.
            exclude_entity_id: Skip this actor entirely. Set when the solid's
                own motion was itself a character pushing it (`try_move`):
                that character's position is that sweep's to decide, not
                this reactive pass's -- without excluding it, a pushed
                crate would also shove back at whoever just pushed it.
        """
        if delta.x == 0.0 and delta.y == 0.0:
            return

        solid_transform = solid_entity.get_component(Transform)
        solid_half = _half_extents(
            solid_entity.get_component(Collider)
            if solid_entity.has_component(Collider)
            else None
        )
        solid_pos_before = solid_transform.position - delta
        solid_pos_after = solid_transform.position

        for actor in self._entity_manager.get_entities_with(
            CharacterBody, Transform, Collider
        ):
            if actor.id == solid_entity.id or actor.id == exclude_entity_id:
                continue
            body = actor.get_component(CharacterBody)
            transform = actor.get_component(Transform)
            half = _half_extents(actor.get_component(Collider))

            if _is_riding(transform.position, half, solid_pos_before, solid_half):
                self._displace(actor, body, transform, delta, solid_entity.id)
                body.riding = solid_entity.id
                continue

            push = _push_delta(
                transform.position, half, solid_pos_after, solid_half, delta
            )
            if push.x != 0.0 or push.y != 0.0:
                self._displace(actor, body, transform, push, solid_entity.id)

    def try_move(
        self, entity: Entity, delta: Vector2, pusher_id: int | str | None = None
    ) -> bool:
        """Attempt to move a `Pushable` solid by `delta`.

        Used when a character's own movement is blocked by a pushable
        entity: `PlatformerSystem` asks this before deciding whether the
        character itself gets to continue.

        Args:
            entity: The pushable solid.
            delta: The distance a character tried to push it.
            pusher_id: The character doing the pushing, excluded from the
                reactive carry/push pass below -- its own position is that
                character's own sweep to decide, not this one's.

        Returns:
            True if the push succeeded -- its Transform moved, and
            whatever else was riding or in the way of *it* was
            carried/pushed in turn. False if something else blocks it, in
            which case its Transform is left exactly where it started.
        """
        transform = entity.get_component(Transform)
        half = _half_extents(
            entity.get_component(Collider) if entity.has_component(Collider) else None
        )
        origin = transform.position
        transform.position = origin + delta

        blocker = self._engine.overlap_box(
            transform.position, _shrink(half), ignore_entity_id=entity.id
        )
        if blocker is not None:
            transform.position = origin
            return False

        self.move_solid(entity, delta, exclude_entity_id=pusher_id)
        return True

    def _displace(
        self,
        actor: Entity,
        body: CharacterBody,
        transform: Transform,
        delta: Vector2,
        solid_id: int | str,
    ) -> None:
        """Move an actor directly and check what that left it overlapping."""
        transform.position = transform.position + delta
        half = _half_extents(
            actor.get_component(Collider) if actor.has_component(Collider) else None
        )
        blocker = self._engine.overlap_box(
            transform.position, _shrink(half), ignore_entity_id=solid_id
        )
        if blocker is not None:
            body.squished = True
            if self._dispatcher is not None:
                self._dispatcher.dispatch(
                    OnActorSquished(
                        entity_id=str(actor.id),
                        solid_entity_id=str(solid_id),
                        timestamp=time.time(),
                        source=self,
                    )
                )
