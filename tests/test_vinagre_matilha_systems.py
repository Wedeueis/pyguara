"""Tests for Vinagre: Matilha's game-specific systems (games/vinagre_matilha/systems.py).

No test file existed for any of these five systems before this tuning pass;
each is exercised directly against a bare `EntityManager` the way
`tests/test_steering.py` tests `SteeringSystem`, rather than only through
whole-demo headless capture.
"""

from __future__ import annotations

from games.vinagre_matilha.components import (
    CurrentZone,
    DogState,
    JaguarState,
    LogGate,
    PressurePlate,
    WebbedFeet,
)
from games.vinagre_matilha.events import GateOpenedEvent, JaguarCorneredEvent
from games.vinagre_matilha.pack_behaviors import PLATE_ASSIGNEES_KEY, PLATE_POSITION_KEY
from games.vinagre_matilha.systems import (
    CurrentZoneSystem,
    FlankerAssignmentSystem,
    JaguarAISystem,
    PackContainmentSystem,
    PressurePlateSystem,
    VanguardControlSystem,
)
from pyguara.ai.blackboard import Blackboard
from pyguara.ai.flocking_system import FlockingAgent
from pyguara.ai.pathfinding.flow_field_service import FlowFieldService
from pyguara.ai.pathfinding.grid import GridGraph
from pyguara.common.components import Transform
from pyguara.common.types import Rect, Vector2
from pyguara.ecs.entity import Entity
from pyguara.ecs.manager import EntityManager
from pyguara.events.dispatcher import EventDispatcher
from pyguara.kits.pack import (
    PackMember,
    PackRole,
    flanker_vector_for,
    reinforcements_requested,
    request_reinforcements,
    threat_position,
)
from pyguara.physics.trigger_volume import TriggerVolume

CELL_SIZE = 32.0


def _flanker(em: EntityManager, pos: Vector2, **agent_kwargs) -> Entity:
    entity = em.create_entity()
    entity.add_component(Transform(position=pos))
    entity.add_component(PackMember(role=PackRole.FLANKER, dog_id=entity.id))
    entity.add_component(DogState())
    entity.add_component(FlockingAgent(**agent_kwargs))
    return entity


def _vanguard(em: EntityManager, pos: Vector2) -> Entity:
    entity = em.create_entity()
    entity.add_component(Transform(position=pos))
    entity.add_component(PackMember(role=PackRole.VANGUARD, dog_id=entity.id))
    entity.add_component(DogState())
    return entity


def _jaguar(em: EntityManager, pos: Vector2, **state_kwargs) -> Entity:
    entity = em.create_entity()
    entity.add_component(Transform(position=pos))
    entity.add_component(JaguarState(**state_kwargs))
    return entity


# ========== FlankerAssignmentSystem ==========


class TestFlankerAssignmentSystem:
    def test_writes_jaguar_position_as_the_shared_threat(self) -> None:
        em = EntityManager()
        jaguar = _jaguar(em, Vector2(200, 200))
        blackboard = Blackboard()
        graph = GridGraph(20, 20)
        system = FlankerAssignmentSystem(
            em, blackboard, FlowFieldService(graph), jaguar.id
        )

        system.update(1 / 60)

        assert threat_position(blackboard) == Vector2(200, 200)

    def test_recomputes_the_flow_field_toward_the_jaguar(self) -> None:
        em = EntityManager()
        jaguar = _jaguar(em, Vector2(200, 200))
        blackboard = Blackboard()
        flow_field = FlowFieldService(GridGraph(20, 20))
        system = FlankerAssignmentSystem(em, blackboard, flow_field, jaguar.id)

        assert not flow_field.is_computed
        system.update(1 / 60)
        assert flow_field.is_computed

    def test_assigns_each_flanker_a_distinct_encirclement_vector(self) -> None:
        em = EntityManager()
        jaguar = _jaguar(em, Vector2(300, 300))
        dogs = [_flanker(em, Vector2(100 + i * 20, 100)) for i in range(3)]
        blackboard = Blackboard()
        system = FlankerAssignmentSystem(
            em, blackboard, FlowFieldService(GridGraph(30, 30)), jaguar.id
        )

        system.update(1 / 60)

        vectors = [flanker_vector_for(blackboard, dog.id) for dog in dogs]
        assert all(v is not None for v in vectors)
        assert len({v.to_tuple() for v in vectors if v is not None}) == 3  # distinct

    def test_reinforcements_request_tightens_flocking_and_clears_the_flag(
        self,
    ) -> None:
        em = EntityManager()
        jaguar = _jaguar(em, Vector2(300, 300))
        dog = _flanker(
            em, Vector2(100, 100), cohesion_weight=1.0, separation_weight=1.0
        )
        blackboard = Blackboard()
        system = FlankerAssignmentSystem(
            em, blackboard, FlowFieldService(GridGraph(30, 30)), jaguar.id
        )

        request_reinforcements(blackboard)
        system.update(1 / 60)

        agent = dog.get_component(FlockingAgent)
        assert agent.cohesion_weight > 1.0
        assert agent.separation_weight > 1.0
        assert reinforcements_requested(blackboard) is False

    def test_routes_the_nearest_flankers_to_an_unopened_plate(self) -> None:
        """Regression: without this, nothing ever assigns a dog to a plate
        at all, so a stage with a plate puzzle can never be solved no
        matter how the pack chases the jaguar -- caught by headless
        playtesting on Stage 3, not by a numbers-only tuning pass.
        """
        em = EntityManager()
        jaguar = _jaguar(em, Vector2(900, 900))  # far away, irrelevant here
        near = _flanker(em, Vector2(10, 0))
        far = _flanker(em, Vector2(1000, 0))
        plate = em.create_entity()
        plate.add_component(Transform(position=Vector2(0, 0)))
        plate.add_component(TriggerVolume())
        plate.add_component(PressurePlate(required_count=1, log_entity_id="log"))
        blackboard = Blackboard()
        system = FlankerAssignmentSystem(
            em, blackboard, FlowFieldService(GridGraph(50, 50)), jaguar.id
        )

        system.update(1 / 60)

        assignees = blackboard.get(PLATE_ASSIGNEES_KEY)
        assert assignees == {near.id}
        assert far.id not in assignees
        assert blackboard.get(PLATE_POSITION_KEY) == Vector2(0, 0)

    def test_does_not_assign_anyone_once_the_plate_is_opened(self) -> None:
        em = EntityManager()
        jaguar = _jaguar(em, Vector2(900, 900))
        _flanker(em, Vector2(10, 0))
        plate = em.create_entity()
        plate.add_component(Transform(position=Vector2(0, 0)))
        plate.add_component(TriggerVolume())
        plate.add_component(
            PressurePlate(required_count=1, log_entity_id="log", opened=True)
        )
        blackboard = Blackboard()
        system = FlankerAssignmentSystem(
            em, blackboard, FlowFieldService(GridGraph(50, 50)), jaguar.id
        )

        system.update(1 / 60)

        assert blackboard.get(PLATE_ASSIGNEES_KEY) == frozenset()


# ========== VanguardControlSystem ==========


class TestVanguardControlSystem:
    def test_moves_in_the_set_direction(self) -> None:
        em = EntityManager()
        vanguard = _vanguard(em, Vector2(100, 100))
        graph = GridGraph(20, 20)
        system = VanguardControlSystem(em, graph, vanguard.id, speed=100.0)

        system.move_direction = Vector2(1, 0)
        system.update(1.0)

        assert vanguard.get_component(Transform).position.x > 100

    def test_is_blocked_by_a_wall_cell(self) -> None:
        em = EntityManager()
        vanguard = _vanguard(em, Vector2(100, 100))
        graph = GridGraph(20, 20)
        # Wall off everything east of the vanguard's starting cell.
        for x in range(4, 20):
            for y in range(20):
                graph.walls.add((x, y))
        system = VanguardControlSystem(em, graph, vanguard.id, speed=500.0)

        system.move_direction = Vector2(1, 0)
        system.update(1.0)

        assert vanguard.get_component(Transform).position.x < 128  # cell 4's edge

    def test_a_stranded_vanguard_can_still_walk_out_of_a_wall(self) -> None:
        """Regression: knocked into a bank, the player could not move at all.

        From inside a wall cell every candidate step is *also* inside a
        wall, so the ordinary "only step onto walkable ground" rule refused
        the very move that would escape -- the run became unplayable.
        """
        em = EntityManager()
        vanguard = _vanguard(em, Vector2(100, 100))
        graph = GridGraph(20, 20)
        for x in range(20):  # the whole top band is bank, vanguard inside it
            for y in range(0, 5):
                graph.walls.add((x, y))
        system = VanguardControlSystem(em, graph, vanguard.id, speed=100.0)

        system.move_direction = Vector2(0, 1)  # walk south, out of the bank
        system.update(1.0)

        assert vanguard.get_component(Transform).position.y > 100

    def test_does_nothing_for_a_missing_entity(self) -> None:
        em = EntityManager()
        graph = GridGraph(20, 20)
        system = VanguardControlSystem(em, graph, "nonexistent")
        system.move_direction = Vector2(1, 0)
        system.update(1.0)  # must not raise


# ========== JaguarAISystem ==========


class TestJaguarAISystem:
    def test_flees_the_nearest_pack_member(self) -> None:
        em = EntityManager()
        jaguar = _jaguar(em, Vector2(200, 200))
        _flanker(em, Vector2(180, 200))  # threat approaches from the west
        graph = GridGraph(20, 20)
        dispatcher = EventDispatcher()
        system = JaguarAISystem(em, graph, jaguar.id, Rect(0, 0, 10, 10), 1, dispatcher)

        for _ in range(30):
            system.update(1 / 60)

        # Fled east, away from the threat.
        assert jaguar.get_component(Transform).position.x > 200

    def test_reverts_a_move_into_a_wall(self) -> None:
        em = EntityManager()
        jaguar = _jaguar(em, Vector2(64, 64), max_speed=1000.0, max_force=5000.0)
        _flanker(em, Vector2(0, 64))  # pushes the jaguar east, into a wall
        graph = GridGraph(20, 20)
        for y in range(20):
            graph.walls.add((3, y))  # wall directly east of the jaguar's cell
        dispatcher = EventDispatcher()
        system = JaguarAISystem(em, graph, jaguar.id, Rect(0, 0, 10, 10), 1, dispatcher)

        for _ in range(30):
            system.update(1 / 60)

        # Never crossed into the walled cell (world x >= 96).
        assert jaguar.get_component(Transform).position.x < 96

    def test_dispatches_cornered_event_once_sustained_in_the_corner_zone(
        self,
    ) -> None:
        em = EntityManager()
        corner = Rect(190, 190, 20, 20)
        jaguar = _jaguar(em, Vector2(200, 200))
        _flanker(em, Vector2(195, 200))
        _flanker(em, Vector2(205, 200))
        graph = GridGraph(20, 20)
        dispatcher = EventDispatcher()
        events: list[JaguarCorneredEvent] = []
        dispatcher.subscribe(JaguarCorneredEvent, events.append)
        system = JaguarAISystem(
            em,
            graph,
            jaguar.id,
            corner,
            required_capture_dogs=2,
            event_dispatcher=dispatcher,
        )

        for _ in range(90):  # 1.5s @ 60fps, past the 1.0s sustain threshold
            system.update(1 / 60)

        assert len(events) == 1
        assert jaguar.get_component(JaguarState).cornered is True

    def test_does_not_corner_below_the_required_dog_count(self) -> None:
        em = EntityManager()
        corner = Rect(190, 190, 20, 20)
        jaguar = _jaguar(em, Vector2(200, 200))
        _flanker(em, Vector2(195, 200))  # only 1, below the requirement
        graph = GridGraph(20, 20)
        dispatcher = EventDispatcher()
        events: list[JaguarCorneredEvent] = []
        dispatcher.subscribe(JaguarCorneredEvent, events.append)
        system = JaguarAISystem(
            em,
            graph,
            jaguar.id,
            corner,
            required_capture_dogs=2,
            event_dispatcher=dispatcher,
        )

        for _ in range(90):
            system.update(1 / 60)

        assert events == []


# ========== CurrentZoneSystem ==========


class TestCurrentZoneSystem:
    """`damping` is a per-*second* retention rate (see `CurrentZone`'s
    docstring for the bug applying it as a flat per-tick multiplier caused:
    velocity crushed to near zero within a couple of frames regardless of
    the configured value). These tests call `update(dt=1.0)` -- exactly one
    second -- so `damping ** dt == damping` and the assertions read as
    plainly as the old, buggy per-tick version did.
    """

    def _zone(self, em: EntityManager, damping: float = 0.5) -> Entity:
        zone = em.create_entity()
        zone.add_component(TriggerVolume())
        zone.add_component(CurrentZone(damping=damping))
        return zone

    def test_damps_a_flocking_agent_without_webbed_feet(self) -> None:
        em = EntityManager()
        zone = self._zone(em, damping=0.5)
        dog = em.create_entity()
        dog.add_component(Transform(position=Vector2(0, 0)))
        dog.add_component(FlockingAgent(velocity=Vector2(100, 0)))
        zone.get_component(TriggerVolume).entities_inside.add(dog.id)
        system = CurrentZoneSystem(em)

        system.update(1.0)

        assert dog.get_component(FlockingAgent).velocity.x == 50.0

    def test_does_not_damp_an_entity_with_webbed_feet(self) -> None:
        em = EntityManager()
        zone = self._zone(em, damping=0.5)
        dog = em.create_entity()
        dog.add_component(Transform(position=Vector2(0, 0)))
        dog.add_component(FlockingAgent(velocity=Vector2(100, 0)))
        dog.add_component(WebbedFeet())
        zone.get_component(TriggerVolume).entities_inside.add(dog.id)
        system = CurrentZoneSystem(em)

        system.update(1.0)

        assert dog.get_component(FlockingAgent).velocity.x == 100.0

    def test_damps_the_jaguar_too(self) -> None:
        em = EntityManager()
        zone = self._zone(em, damping=0.5)
        jaguar = _jaguar(em, Vector2(0, 0))
        jaguar.get_component(JaguarState).velocity = Vector2(100, 0)
        zone.get_component(TriggerVolume).entities_inside.add(jaguar.id)
        system = CurrentZoneSystem(em)

        system.update(1.0)

        assert jaguar.get_component(JaguarState).velocity.x == 50.0

    def test_ignores_an_entity_not_inside_the_zone(self) -> None:
        em = EntityManager()
        self._zone(em, damping=0.5)
        dog = em.create_entity()
        dog.add_component(Transform(position=Vector2(0, 0)))
        dog.add_component(FlockingAgent(velocity=Vector2(100, 0)))
        system = CurrentZoneSystem(em)

        system.update(1.0)

        assert dog.get_component(FlockingAgent).velocity.x == 100.0

    def test_a_brief_tick_barely_damps_at_all(self) -> None:
        """The regression case: one 1/60s physics tick must not crush
        velocity the way a flat per-tick multiplier did."""
        em = EntityManager()
        zone = self._zone(em, damping=0.35)
        dog = em.create_entity()
        dog.add_component(Transform(position=Vector2(0, 0)))
        dog.add_component(FlockingAgent(velocity=Vector2(100, 0)))
        zone.get_component(TriggerVolume).entities_inside.add(dog.id)
        system = CurrentZoneSystem(em)

        system.update(1 / 60)

        assert dog.get_component(FlockingAgent).velocity.x > 95.0


# ========== PressurePlateSystem ==========


class TestPressurePlateSystem:
    def _log(self, em: EntityManager, cells: list[tuple[int, int]]) -> Entity:
        log = em.create_entity()
        log.add_component(Transform(position=Vector2(0, 0)))
        log.add_component(LogGate(cells=list(cells)))
        return log

    def _plate(self, em: EntityManager, required: int, log_id: str) -> Entity:
        plate = em.create_entity()
        plate.add_component(TriggerVolume())
        plate.add_component(
            PressurePlate(required_count=required, log_entity_id=log_id)
        )
        return plate

    def test_opens_once_the_required_count_is_met(self) -> None:
        em = EntityManager()
        graph = GridGraph(10, 10)
        log_cells = [(5, 5), (5, 6)]
        graph.walls.update(log_cells)
        log = self._log(em, log_cells)
        plate = self._plate(em, required=2, log_id=log.id)
        plate.get_component(TriggerVolume).entities_inside.update({"d1", "d2"})
        dispatcher = EventDispatcher()
        events: list[GateOpenedEvent] = []
        dispatcher.subscribe(GateOpenedEvent, events.append)
        system = PressurePlateSystem(em, graph, dispatcher)

        system.update(1 / 60)

        assert plate.get_component(PressurePlate).opened is True
        assert graph.walls.isdisjoint(log_cells)
        assert em.get_entity(log.id) is None
        assert len(events) == 1

    def test_stays_closed_below_the_required_count(self) -> None:
        em = EntityManager()
        graph = GridGraph(10, 10)
        log_cells = [(5, 5)]
        graph.walls.update(log_cells)
        log = self._log(em, log_cells)
        plate = self._plate(em, required=2, log_id=log.id)
        plate.get_component(TriggerVolume).entities_inside.add("d1")
        dispatcher = EventDispatcher()
        system = PressurePlateSystem(em, graph, dispatcher)

        system.update(1 / 60)

        assert plate.get_component(PressurePlate).opened is False
        assert graph.walls == {(5, 5)}
        assert em.get_entity(log.id) is not None

    def test_does_not_reopen_or_refire_once_opened(self) -> None:
        em = EntityManager()
        graph = GridGraph(10, 10)
        log_cells = [(5, 5)]
        graph.walls.update(log_cells)
        log = self._log(em, log_cells)
        plate = self._plate(em, required=1, log_id=log.id)
        plate.get_component(TriggerVolume).entities_inside.add("d1")
        dispatcher = EventDispatcher()
        events: list[GateOpenedEvent] = []
        dispatcher.subscribe(GateOpenedEvent, events.append)
        system = PressurePlateSystem(em, graph, dispatcher)

        system.update(1 / 60)
        plate.get_component(TriggerVolume).entities_inside.clear()
        system.update(1 / 60)
        system.update(1 / 60)

        assert len(events) == 1


# ========== PackContainmentSystem ==========


class TestPackContainmentSystem:
    """Nothing may leave the walkable corridor and get stuck there.

    `FlockingSystem` and swipe knockback both move dogs without consulting
    the grid, and a dog inside a wall cell cannot move at all afterwards --
    every candidate step from in there is also a wall.
    """

    def _graph_with_bank(self) -> GridGraph:
        graph = GridGraph(20, 20)
        for x in range(20):
            for y in range(0, 5):  # north bank
                graph.walls.add((x, y))
        return graph

    def test_records_a_walkable_position_as_safe(self) -> None:
        em = EntityManager()
        dog = _vanguard(em, Vector2(200, 300))
        system = PackContainmentSystem(em, self._graph_with_bank())

        system.update(1 / 60)

        assert dog.get_component(DogState).last_safe_position == Vector2(200, 300)

    def test_puts_a_dog_knocked_into_the_bank_back_on_safe_ground(self) -> None:
        em = EntityManager()
        dog = _vanguard(em, Vector2(200, 300))
        system = PackContainmentSystem(em, self._graph_with_bank())
        system.update(1 / 60)  # records (200, 300) as safe

        dog.get_component(Transform).position = Vector2(200, 40)  # into the bank
        dog.get_component(DogState).knockback = Vector2(0, -400)
        system.update(1 / 60)

        assert dog.get_component(Transform).position == Vector2(200, 300)
        assert dog.get_component(DogState).knockback == Vector2(0, 0)

    def test_zeroes_a_flocking_agents_velocity_on_recovery(self) -> None:
        em = EntityManager()
        dog = _flanker(em, Vector2(200, 300), velocity=Vector2(0, -200))
        system = PackContainmentSystem(em, self._graph_with_bank())
        system.update(1 / 60)

        dog.get_component(Transform).position = Vector2(200, 40)
        system.update(1 / 60)

        assert dog.get_component(FlockingAgent).velocity == Vector2(0, 0)

    def test_leaves_a_dog_alone_while_it_stays_in_the_corridor(self) -> None:
        em = EntityManager()
        dog = _vanguard(em, Vector2(200, 300))
        system = PackContainmentSystem(em, self._graph_with_bank())

        system.update(1 / 60)
        dog.get_component(Transform).position = Vector2(260, 340)
        system.update(1 / 60)

        assert dog.get_component(Transform).position == Vector2(260, 340)
