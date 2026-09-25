"""Vinagre: Matilha - Game Systems.

Everything genre-generic (flocking, behavior trees, steering) already ticks
via core systems (`FlockingSystem`, `pyguara.ai.ai_system.AISystem`,
`SteeringSystem`) constructed directly by `GameScene`. What's here is
specific to this demo: feeding the shared pack blackboard, the
grid-aware Vanguard/jaguar movement, and the two trigger-volume mechanics.
"""

from __future__ import annotations

import math
from typing import cast

from games.vinagre_matilha.components import (
    CurrentZone,
    DogState,
    JaguarPhase,
    JaguarState,
    LogGate,
    PressurePlate,
    WebbedFeet,
)
from games.vinagre_matilha.events import GateOpenedEvent, JaguarCorneredEvent
from games.vinagre_matilha.level_builder import CELL_SIZE, FLANKER_SPATIAL_MASK
from games.vinagre_matilha.pack_behaviors import (
    NEIGHBOR_COUNT_KEY,
    PLATE_ASSIGNEES_KEY,
    PLATE_POSITION_KEY,
)
from pyguara.ai.blackboard import Blackboard
from pyguara.ai.flocking_system import FlockingAgent
from pyguara.ai.pathfinding.flow_field_service import FlowFieldService
from pyguara.ai.pathfinding.grid import GridGraph
from pyguara.ai.steering import SteeringBehavior
from pyguara.common.components import Transform
from pyguara.common.grid import Cell, world_to_cell
from pyguara.common.spatial import SpatialHash
from pyguara.common.types import Rect, Vector2
from pyguara.ecs.entity import Entity
from pyguara.ecs.manager import EntityManager
from pyguara.events.dispatcher import EventDispatcher
from pyguara.kits.pack import (
    PackMember,
    PackRole,
    assign_flanker_vector,
    clear_reinforcements,
    reinforcements_requested,
    set_threat,
)
from pyguara.physics.trigger_volume import TriggerVolume

# Must sit inside `combat.BITE_RANGE`, or Pincer becomes strictly worse
# than issuing no order at all: an earlier build ringed the pack at 90px
# around a jaguar they could only bite at 34px, so the "attack" command
# politely held formation just out of reach and dealt no damage for the
# entire fight. Dog-to-dog spacing comes from `separation_radius`, not
# from this, so a tight ring still spreads around the target's perimeter.
_ENCIRCLE_RADIUS = 30.0
_CAPTURE_RADIUS = 80.0
_CORNERED_SUSTAIN_SECONDS = 1.0


def _walkable(graph: GridGraph, cell: Cell) -> bool:
    return graph.in_bounds(cell) and graph.is_passable(cell)


class FlankerAssignmentSystem:
    """Feeds the shared blackboard every tick.

    Writes the jaguar's position as the pack's threat, each flanker's
    neighbor count (for `CallReinforcements`' isolation check), and --
    under Pincer orders -- one encirclement point per flanker, assigned by
    current angle around the jaguar so a dog isn't reshuffled to the
    opposite side every frame. Also owns recomputing the shared flow field
    toward the jaguar's current cell.

    The neighbour counts come from the shared `SpatialHash`, the way
    `kits/projectiles` and `kits/progression`'s magnet find their
    candidates. Flankers are tracked in it the usual way
    (`pyguara.spatial.SpatialTracked` + `SpatialIndexSystem`, registered by
    `GameScene`); this system never inserts into it itself.
    """

    def __init__(
        self,
        entity_manager: EntityManager,
        blackboard: Blackboard,
        flow_field: FlowFieldService,
        jaguar_id: str,
        spatial_index: SpatialHash[str],
    ) -> None:
        self._em = entity_manager
        self._blackboard = blackboard
        self._flow_field = flow_field
        self._jaguar_id = jaguar_id
        self._spatial_index = spatial_index
        blackboard.set("pack_flow_field", flow_field)
        blackboard.set("pack_cell_size", CELL_SIZE)

    def update(self, dt: float) -> None:
        jaguar = self._em.get_entity(self._jaguar_id)
        if jaguar is None:
            return
        threat_pos = jaguar.get_component(Transform).position
        set_threat(self._blackboard, threat_pos)

        flankers = [
            entity
            for entity in self._em.get_entities_with(
                PackMember, FlockingAgent, Transform
            )
            if entity.get_component(PackMember).role is PackRole.FLANKER
        ]

        # Per dog, the cells its neighbour radius spans -- not every other
        # dog. A pack is small enough that the old pairwise scan was never
        # the bottleneck here, but this is a capstone demo, and the next
        # person who needs neighbour counts is likely to start from it.
        counts: dict[str, int] = {}
        for dog in flankers:
            position = dog.get_component(Transform).position
            radius = dog.get_component(FlockingAgent).neighbor_radius
            nearby = self._spatial_index.query_radius(
                position, radius, FLANKER_SPATIAL_MASK
            )
            # The dog finds itself, at distance zero. Excluding it by id
            # rather than subtracting one keeps the count right on a tick
            # where `SpatialIndexSystem` has not run yet and the dog is not
            # in the index at all.
            counts[dog.id] = sum(1 for other_id in nearby if other_id != dog.id)
        self._blackboard.set(NEIGHBOR_COUNT_KEY, counts)

        self._assign_plate_runners(flankers)

        # CallReinforcements' observable effect: an isolated, threatened dog
        # calls the pack to tighten formation for a moment (higher cohesion
        # and separation), rather than spawning anything new.
        if reinforcements_requested(self._blackboard):
            for dog in flankers:
                agent = dog.get_component(FlockingAgent)
                agent.cohesion_weight = 1.6
                agent.separation_weight = 1.8
            clear_reinforcements(self._blackboard)

        goal_cell = world_to_cell(threat_pos, CELL_SIZE)
        self._flow_field.recompute(goals=[goal_cell])

        if not flankers:
            return

        def _angle_around_threat(dog: Entity) -> float:
            diff = dog.get_component(Transform).position - threat_pos
            return math.atan2(diff.y, diff.x)

        flankers_by_angle = sorted(flankers, key=_angle_around_threat)
        count = len(flankers_by_angle)
        for i, dog in enumerate(flankers_by_angle):
            angle = 2 * math.pi * i / count
            point = threat_pos + Vector2(
                math.cos(angle) * _ENCIRCLE_RADIUS, math.sin(angle) * _ENCIRCLE_RADIUS
            )
            assign_flanker_vector(self._blackboard, dog.id, point)

    def _assign_plate_runners(self, flankers: list[Entity]) -> None:
        """Route the nearest `required_count` flankers to any unopened
        pressure plate, ahead of whatever command the player has issued.

        Without this, nothing ever routes a dog to a plate at all: the
        Pincer/Scatter/Distract leaves only ever steer relative to the
        jaguar, so a stage with a plate puzzle would sit unsolved forever
        no matter how long the pack chased the jaguar around it -- caught
        by headless playtesting on Stage 3, not by a numbers-only pass.
        """
        for plate_entity in self._em.get_entities_with(TriggerVolume, PressurePlate):
            plate = plate_entity.get_component(PressurePlate)
            if plate.opened:
                continue
            plate_pos = plate_entity.get_component(Transform).position
            self._blackboard.set(PLATE_POSITION_KEY, plate_pos)

            nearest = sorted(
                flankers,
                key=lambda dog: (
                    dog.get_component(Transform).position - plate_pos
                ).length,
            )[: plate.required_count]
            self._blackboard.set(
                PLATE_ASSIGNEES_KEY, frozenset(dog.id for dog in nearest)
            )
            return  # only one plate per stage in practice; first one wins

        # No unopened plate this tick (none exists, or it's already open):
        # nobody is assigned, so every flanker's PlateSequence leaf fails
        # and falls through to the normal command behavior.
        self._blackboard.set(PLATE_ASSIGNEES_KEY, frozenset())


class VanguardControlSystem:
    """Moves the player-controlled Vanguard, respecting the pathfinding grid.

    Level geometry (walls, the closed log) blocks movement via the same
    `GridGraph` the pack's flow field routes around -- one shared source of
    truth for "what's solid here" rather than a second physics-collider
    representation.
    """

    def __init__(
        self,
        entity_manager: EntityManager,
        graph: GridGraph,
        vanguard_id: str,
        speed: float = 180.0,
    ) -> None:
        self._em = entity_manager
        self._graph = graph
        self._vanguard_id = vanguard_id
        self._speed = speed
        self.move_direction = Vector2(0, 0)

    def update(self, dt: float) -> None:
        entity = self._em.get_entity(self._vanguard_id)
        if entity is None:
            return
        state = entity.get_component(DogState)
        if state.is_downed:
            return

        transform = entity.get_component(Transform)
        direction = self.move_direction
        if direction.length > 0.001:
            direction = cast(Vector2, direction.normalized())
            state.facing = direction
        delta = direction * self._speed * dt

        # From *inside* a wall cell, every candidate step is also inside a
        # wall, so the usual "only step onto walkable ground" rule refuses
        # the very move that would escape -- the player is sealed in for
        # good. `PackContainmentSystem` should stop that happening at all,
        # but if something does strand the alpha in a bank, let it walk
        # out rather than leaving the run unplayable.
        stranded = not _walkable(
            self._graph, world_to_cell(transform.position, CELL_SIZE)
        )

        candidate = Vector2(transform.position.x + delta.x, transform.position.y)
        if stranded or _walkable(self._graph, world_to_cell(candidate, CELL_SIZE)):
            transform.position = candidate

        candidate = Vector2(transform.position.x, transform.position.y + delta.y)
        if stranded or _walkable(self._graph, world_to_cell(candidate, CELL_SIZE)):
            transform.position = candidate


class JaguarAISystem:
    """Flees the nearest pack member, enforces the grid's walls, and detects
    when the jaguar has been cornered.

    Calls `SteeringBehavior.flee()` directly and integrates the result by
    hand -- the same F=ma clamp `SteeringSystem` uses internally -- rather
    than going through a `SteeringAgent`/`SteeringSystem`: that generic
    dispatch has no way to pass a custom `panic_distance` per agent, only
    its own hardcoded default, which would leave `JaguarState.
    panic_distance` declared and silently ignored.
    """

    def __init__(
        self,
        entity_manager: EntityManager,
        graph: GridGraph,
        jaguar_id: str,
        corner_zone: Rect,
        required_capture_dogs: int,
        event_dispatcher: EventDispatcher,
    ) -> None:
        self._em = entity_manager
        self._graph = graph
        self._jaguar_id = jaguar_id
        self._corner_zone = corner_zone
        self._required_capture_dogs = required_capture_dogs
        self._dispatcher = event_dispatcher
        self._cornered_time = 0.0

    def update(self, dt: float) -> None:
        jaguar = self._em.get_entity(self._jaguar_id)
        if jaguar is None:
            return
        transform = jaguar.get_component(Transform)
        state = jaguar.get_component(JaguarState)
        state.previous_position = transform.position

        # It plants its feet to swing: a swipe you could simply outrun
        # would make the wind-up tell pointless. Cornered, it stops running
        # altogether and makes a stand -- which is what finally lets the
        # pack land sustained damage, so the pocket has a gameplay purpose
        # beyond being a marked rectangle.
        planted = state.phase in (JaguarPhase.WINDUP, JaguarPhase.SWIPE)
        # Inside the pocket it is trapped and must make a stand, whether or
        # not enough dogs have closed yet. Gating this on the sustained
        # capture count instead meant the pocket rarely slowed it at all --
        # it simply ran back out past the pack, and the fight never got a
        # climax. The capture count still drives the `cornered` flag below,
        # which is what the HUD and the win-adjacent feedback read.
        in_pocket = self._corner_zone.contains_point(transform.position)
        speed_scale = 0.0 if planted else (0.3 if in_pocket else 1.0)

        dogs = [
            dog
            for dog in self._em.get_entities_with(PackMember, DogState, Transform)
            if not dog.get_component(DogState).is_downed
        ]
        if dogs and speed_scale > 0.0:
            nearest = min(
                dogs,
                key=lambda dog: (
                    dog.get_component(Transform).position - transform.position
                ).length,
            )
            force = SteeringBehavior.flee(
                transform,
                nearest.get_component(Transform).position,
                state.max_speed * speed_scale,
                state.velocity,
                panic_distance=state.panic_distance,
            )
            if force.length > state.max_force:
                force = cast(Vector2, force.normalized() * state.max_force)
            new_velocity = state.velocity + force * dt
            max_speed = state.max_speed * speed_scale
            if new_velocity.length > max_speed:
                new_velocity = cast(Vector2, new_velocity.normalized() * max_speed)
            state.velocity = new_velocity
            transform.position = transform.position + state.velocity * dt
            if state.velocity.length > 8.0:
                state.facing = cast(Vector2, state.velocity.normalized())
        elif planted:
            state.velocity = Vector2(0, 0)
            state.facing = state.swipe_direction

        cell = world_to_cell(transform.position, CELL_SIZE)
        if not _walkable(self._graph, cell):
            transform.position = state.previous_position
            state.velocity = Vector2(0, 0)

        if state.cornered:
            return

        nearby_dogs = sum(
            1
            for dog in self._em.get_entities_with(PackMember, Transform)
            if (dog.get_component(Transform).position - transform.position).length
            < _CAPTURE_RADIUS
        )
        in_corner = self._corner_zone.contains_point(transform.position)
        if in_corner and nearby_dogs >= self._required_capture_dogs:
            self._cornered_time += dt
        else:
            self._cornered_time = 0.0

        if self._cornered_time >= _CORNERED_SUSTAIN_SECONDS:
            state.cornered = True
            self._dispatcher.dispatch(JaguarCorneredEvent())


class CurrentZoneSystem:
    """Damps the velocity of anything without `WebbedFeet` inside a `CurrentZone`.

    `CurrentZone.damping` is a per-*second* retention rate (see its
    docstring for the bug this avoids); applying it directly as a per-tick
    multiplier would crush velocity almost to zero within a couple of
    frames regardless of the configured value, since it compounds every
    physics tick. `damping ** dt` converts the per-second rate to whatever
    this tick's fraction of a second actually is.
    """

    def __init__(self, entity_manager: EntityManager) -> None:
        self._em = entity_manager

    def update(self, dt: float) -> None:
        for zone in self._em.get_entities_with(TriggerVolume, CurrentZone):
            trigger = zone.get_component(TriggerVolume)
            current = zone.get_component(CurrentZone)
            factor = current.damping**dt
            for entity_id in trigger.entities_inside:
                entity = self._em.get_entity(entity_id)
                if entity is None or entity.has_component(WebbedFeet):
                    continue
                if entity.has_component(JaguarState):
                    jaguar_state = entity.get_component(JaguarState)
                    jaguar_state.velocity = jaguar_state.velocity * factor
                    # Pushed downstream as well as slowed: a current the
                    # webbed-footed pack shrugs off should visibly cost the
                    # jaguar ground, not merely speed.
                    transform = entity.get_component(Transform)
                    transform.position = transform.position + current.flow * dt
                elif entity.has_component(FlockingAgent):
                    flocking_agent = entity.get_component(FlockingAgent)
                    flocking_agent.velocity = flocking_agent.velocity * factor


class PackMotionSystem:
    """Keeps each dog's steering enablement and facing in sync with its state.

    A downed dog has its `FlockingAgent` switched off outright rather than
    merely ignored: leaving it enabled would keep it contributing cohesion
    and separation forces to its packmates while lying unconscious, so the
    flock would still clump around a dog that is, as far as the fight is
    concerned, not there.
    """

    def __init__(self, entity_manager: EntityManager) -> None:
        self._em = entity_manager

    def update(self, dt: float) -> None:
        for entity in self._em.get_entities_with(DogState, FlockingAgent):
            state = entity.get_component(DogState)
            agent = entity.get_component(FlockingAgent)
            agent.enabled = not state.is_downed
            if not state.is_downed and agent.velocity.length > 8.0:
                state.facing = cast(Vector2, agent.velocity.normalized())


class PackContainmentSystem:
    """Keeps every dog inside the walkable corridor.

    Two things move a dog without consulting the grid at all: `FlockingSystem`
    (core, and rightly grid-agnostic) and a jaguar swipe's knockback. Either
    can park a dog inside a bank -- and being inside a wall cell is
    *unrecoverable* on its own, because from in there every candidate step
    is also inside a wall, so movement systems refuse all of them and the
    dog is sealed in permanently. That stranded the player's own alpha on
    any swipe that threw it into the bank.

    So: record the last legitimately walkable position each tick, and put
    a dog that has ended up in a bank back on it, killing the momentum that
    carried it there. Registered after combat so it catches knockback in
    the same tick that applies it, rather than a frame later.
    """

    def __init__(self, entity_manager: EntityManager, graph: GridGraph) -> None:
        self._em = entity_manager
        self._graph = graph

    def update(self, dt: float) -> None:
        for entity in self._em.get_entities_with(DogState, Transform):
            state = entity.get_component(DogState)
            transform = entity.get_component(Transform)

            if _walkable(self._graph, world_to_cell(transform.position, CELL_SIZE)):
                state.last_safe_position = transform.position
                continue

            if state.last_safe_position is not None:
                transform.position = state.last_safe_position
            state.knockback = Vector2(0, 0)
            if entity.has_component(FlockingAgent):
                entity.get_component(FlockingAgent).velocity = Vector2(0, 0)


class PressurePlateSystem:
    """Opens a paired `LogGate` once enough pack members stand on the plate.

    Opening means removing the log's cells from the pack's `GridGraph.walls`
    (recomputed into the flow field next `FlankerAssignmentSystem` tick) and
    destroying the log entity outright -- no live sensor toggling, and no
    stale collider left behind for the Vanguard to still bump into.
    """

    def __init__(
        self,
        entity_manager: EntityManager,
        graph: GridGraph,
        event_dispatcher: EventDispatcher,
    ) -> None:
        self._em = entity_manager
        self._graph = graph
        self._dispatcher = event_dispatcher

    def update(self, dt: float) -> None:
        for plate_entity in self._em.get_entities_with(TriggerVolume, PressurePlate):
            plate = plate_entity.get_component(PressurePlate)
            if plate.opened:
                continue
            trigger = plate_entity.get_component(TriggerVolume)
            if trigger.get_entity_count() < plate.required_count:
                continue

            plate.opened = True
            log_entity = self._em.get_entity(plate.log_entity_id)
            if log_entity is not None:
                self._graph.walls.difference_update(
                    log_entity.get_component(LogGate).cells
                )
                self._em.remove_entity(log_entity.id)

            self._dispatcher.dispatch(
                GateOpenedEvent(log_entity_id=plate.log_entity_id)
            )
