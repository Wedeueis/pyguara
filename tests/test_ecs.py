from dataclasses import dataclass
from pyguara.ecs.manager import EntityManager
from pyguara.ecs.component import BaseComponent
from pyguara.ecs.entity import Entity


# -- Mocks --
@dataclass
class Position(BaseComponent):
    x: float = 0
    y: float = 0


@dataclass
class Health(BaseComponent):
    hp: int = 100


@dataclass
class Velocity(BaseComponent):
    vx: float = 0


def test_create_entity():
    manager = EntityManager()
    entity = manager.create_entity()
    assert entity.id is not None
    assert manager.get_entity(entity.id) == entity


def test_add_component():
    manager = EntityManager()
    entity = manager.create_entity()

    pos = Position(10, 20)
    entity.add_component(pos)

    assert entity.has_component(Position)
    assert entity.get_component(Position) == pos
    # Check attribute cache
    assert entity.position == pos


def test_ecs_query():
    manager = EntityManager()

    # Ent 1: Pos + Health
    e1 = manager.create_entity()
    e1.add_component(Position())
    e1.add_component(Health())

    # Ent 2: Pos only
    e2 = manager.create_entity()
    e2.add_component(Position())

    # Ent 3: Health only
    e3 = manager.create_entity()
    e3.add_component(Health())

    # Query: Position + Health
    results = list(manager.get_entities_with(Position, Health))

    assert len(results) == 1
    assert results[0] == e1

    # Query: Position
    results_pos = list(manager.get_entities_with(Position))
    assert len(results_pos) == 2
    assert set(results_pos) == {e1, e2}


def test_remove_entity():
    manager = EntityManager()
    e1 = manager.create_entity()
    e1.add_component(Position())

    eid = e1.id
    manager.remove_entity(eid)

    assert manager.get_entity(eid) is None
    # Index should be clear
    assert len(list(manager.get_entities_with(Position))) == 0


def test_component_added_after_registration():
    """Ensure adding a component *after* entity creation updates the manager's index."""
    manager = EntityManager()
    e1 = manager.create_entity()

    # Initially has no Position
    assert len(list(manager.get_entities_with(Position))) == 0

    # Add component dynamically
    e1.add_component(Position())

    # Manager should know about it now (via Observer hook)
    assert len(list(manager.get_entities_with(Position))) == 1


def test_snake_case_conversion():
    """Verify the naming optimization logic."""

    class RigidBody(BaseComponent):
        pass

    class AIController(BaseComponent):
        pass

    assert Entity._get_snake_name(Position) == "position"
    assert Entity._get_snake_name(RigidBody) == "rigid_body"
    # Note: Regex logic for AIController might depend on implementation details
    # standard regex: AIController -> ai_controller (usually) or a_i_controller
    # Let's verify what the actual impl does:
    # s1 = re.sub("(.)([A-Z][a-z]+)", r"\1_\2", type_name)
    # s2 = re.sub("([a-z0-9])([A-Z])", r"\1_\2", s1).lower()
    # AIController -> AI_Controller -> ai_controller
    assert Entity._get_snake_name(AIController) == "ai_controller"
