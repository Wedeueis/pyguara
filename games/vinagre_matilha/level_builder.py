"""Vinagre: Matilha - Level Builder.

Builds one stage's entities (pack, jaguar, vanguard, water zones, pressure
plate/log) plus the `GridGraph`/`FlowFieldService` the pack navigates with,
from a `StageConfig`. Wall/log rects and the `GridGraph`'s wall cells are
derived from one shared source of truth so they can never drift apart.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from games.vinagre_matilha.components import (
    CurrentZone,
    JaguarState,
    LogGate,
    PressurePlate,
    WebbedFeet,
)
from games.vinagre_matilha.pack_behaviors import build_pack_tree
from pyguara.ai.blackboard import Blackboard
from pyguara.ai.components import AIComponent
from pyguara.ai.flocking_system import FlockingAgent
from pyguara.ai.pathfinding.flow_field_service import FlowFieldService
from pyguara.ai.pathfinding.grid import GridGraph
from pyguara.common.components import Transform
from pyguara.common.grid import Cell, world_to_cell
from pyguara.common.types import Rect, Vector2
from pyguara.ecs.manager import EntityManager
from pyguara.kits.pack import PackMember, PackRole
from pyguara.physics.components import Collider, RigidBody
from pyguara.physics.trigger_volume import TriggerVolume
from pyguara.physics.types import BodyType, ShapeType

CELL_SIZE = 32.0
DOG_COLLIDER_RADIUS = 8.0
VANGUARD_COLLIDER_RADIUS = 10.0
JAGUAR_COLLIDER_RADIUS = 14.0
WATER_WEIGHT = 2.5


@dataclass
class StageConfig:
    """Everything about one stage's layout and win condition."""

    name: str
    grid_width: int
    grid_height: int
    pack_size: int  # includes the vanguard
    dog_spawn: Vector2
    jaguar_spawn: Vector2
    corner_zone: Rect
    required_capture_dogs: int
    water_zones: list[Rect] = field(default_factory=list)
    wall_rects: list[Rect] = field(default_factory=list)
    plate_rect: Rect | None = None
    plate_required: int = 0
    log_rect: Rect | None = None


@dataclass
class LevelHandles:
    """Everything `GameScene` needs to wire systems up after building a stage."""

    graph: GridGraph
    flow_field: FlowFieldService
    blackboard: Blackboard
    vanguard_id: str
    dog_ids: list[str]
    jaguar_id: str
    plate_id: str | None
    log_id: str | None
    corner_zone: Rect
    required_capture_dogs: int


def _rect_to_cells(rect: Rect, cell_size: float) -> list[Cell]:
    """Every grid cell `rect` overlaps, in world space."""
    min_cell = world_to_cell(Vector2(rect.left, rect.top), cell_size)
    max_cell = world_to_cell(Vector2(rect.right - 1, rect.bottom - 1), cell_size)
    return [
        (x, y)
        for x in range(min_cell[0], max_cell[0] + 1)
        for y in range(min_cell[1], max_cell[1] + 1)
    ]


def build_graph(config: StageConfig) -> tuple[GridGraph, list[Cell]]:
    """Build `config`'s `GridGraph` (walls, water weights, the log's cells).

    Split out of `build_stage()` so a level's connectivity -- can the pack
    actually reach the jaguar and the corner zone, is the log's corridor
    genuinely sealed until the plate opens it -- can be asserted directly in
    tests, without spinning up an `EntityManager` and every entity.

    Returns:
        The graph, and the log's cells separately (also duplicated onto
        `LogGate.cells` for the entity `build_stage()` creates, but a test
        checking pre/post-open connectivity needs them before any entity
        exists).
    """
    graph = GridGraph(config.grid_width, config.grid_height, allow_diagonal=True)

    for rect in config.wall_rects:
        graph.walls.update(_rect_to_cells(rect, CELL_SIZE))
    for rect in config.water_zones:
        for cell in _rect_to_cells(rect, CELL_SIZE):
            graph.weights[cell] = WATER_WEIGHT

    log_cells: list[Cell] = []
    if config.log_rect is not None:
        log_cells = _rect_to_cells(config.log_rect, CELL_SIZE)
        graph.walls.update(log_cells)

    return graph, log_cells


def build_stage(entity_manager: EntityManager, config: StageConfig) -> LevelHandles:
    """Create every entity for `config` and return the handles to wire up."""
    graph, log_cells = build_graph(config)

    log_id: str | None = None
    if config.log_rect is not None:
        log_id = _create_log(entity_manager, config.log_rect, log_cells)

    flow_field = FlowFieldService(graph)
    blackboard = Blackboard()

    jaguar_id = _create_jaguar(entity_manager, config.jaguar_spawn)

    vanguard_id = _create_dog(
        entity_manager, config.dog_spawn, PackRole.VANGUARD, "vanguard"
    )

    dog_ids = [vanguard_id]
    for i in range(config.pack_size - 1):
        offset = Vector2((i % 4) * 24.0 - 36.0, (i // 4) * 24.0 + 24.0)
        dog_id = _create_dog(
            entity_manager,
            config.dog_spawn + offset,
            PackRole.FLANKER,
            f"flanker-{i}",
            blackboard=blackboard,
        )
        dog_ids.append(dog_id)

    plate_id: str | None = None
    if config.plate_rect is not None and log_id is not None:
        plate_id = _create_plate(
            entity_manager, config.plate_rect, config.plate_required, log_id
        )

    for rect in config.water_zones:
        _create_current_zone(entity_manager, rect)

    return LevelHandles(
        graph=graph,
        flow_field=flow_field,
        blackboard=blackboard,
        vanguard_id=vanguard_id,
        dog_ids=dog_ids,
        jaguar_id=jaguar_id,
        plate_id=plate_id,
        log_id=log_id,
        corner_zone=config.corner_zone,
        required_capture_dogs=config.required_capture_dogs,
    )


def _create_dog(
    entity_manager: EntityManager,
    position: Vector2,
    role: PackRole,
    dog_id: str,
    blackboard: Blackboard | None = None,
) -> str:
    entity = entity_manager.create_entity()
    entity.add_component(Transform(position=position))
    entity.add_component(PackMember(role=role, dog_id=entity.id))
    entity.add_component(WebbedFeet())
    entity.add_component(RigidBody(body_type=BodyType.KINEMATIC, fixed_rotation=True))
    entity.add_component(
        Collider(shape_type=ShapeType.CIRCLE, dimensions=[DOG_COLLIDER_RADIUS])
    )

    if role is PackRole.FLANKER:
        assert blackboard is not None
        entity.add_component(
            FlockingAgent(
                max_speed=150.0,
                neighbor_radius=90.0,
                separation_radius=28.0,
            )
        )
        entity.add_component(
            AIComponent(blackboard=blackboard, behavior_tree=build_pack_tree())
        )

    return entity.id


def _create_jaguar(entity_manager: EntityManager, position: Vector2) -> str:
    entity = entity_manager.create_entity()
    entity.add_component(Transform(position=position))
    entity.add_component(JaguarState())
    entity.add_component(RigidBody(body_type=BodyType.KINEMATIC, fixed_rotation=True))
    entity.add_component(
        Collider(shape_type=ShapeType.CIRCLE, dimensions=[JAGUAR_COLLIDER_RADIUS])
    )
    return entity.id


def _create_current_zone(entity_manager: EntityManager, rect: Rect) -> str:
    entity = entity_manager.create_entity()
    entity.add_component(Transform(position=rect.center_vec))
    entity.add_component(
        TriggerVolume(
            shape_type=ShapeType.BOX,
            dimensions=[float(rect.width), float(rect.height)],
        )
    )
    entity.add_component(CurrentZone())
    return entity.id


def _create_plate(
    entity_manager: EntityManager, rect: Rect, required: int, log_id: str
) -> str:
    entity = entity_manager.create_entity()
    entity.add_component(Transform(position=rect.center_vec))
    entity.add_component(
        TriggerVolume(
            shape_type=ShapeType.BOX,
            dimensions=[float(rect.width), float(rect.height)],
        )
    )
    entity.add_component(PressurePlate(required_count=required, log_entity_id=log_id))
    return entity.id


def _create_log(entity_manager: EntityManager, rect: Rect, cells: list[Cell]) -> str:
    entity = entity_manager.create_entity()
    entity.add_component(Transform(position=rect.center_vec))
    entity.add_component(LogGate(cells=cells))
    entity.add_component(RigidBody(body_type=BodyType.STATIC))
    entity.add_component(
        Collider(
            shape_type=ShapeType.BOX,
            dimensions=[float(rect.width), float(rect.height)],
        )
    )
    return entity.id


# ========== Stage configs ==========
#
# Every stage is a single east-west riverbed corridor, walled off top and
# bottom -- not an open field. An early build left stages wall-less, and
# headless playtesting caught the failure mode directly: with nowhere it
# *couldn't* go, a fleeing jaguar would dodge north/south around flanking
# dogs and wander back past its own spawn instead of ever reaching the
# corner zone. Confining vertical movement to one corridor band means the
# only way left to flee, once the pack blocks the west, is east -- straight
# into the dead end the grid's own boundary already forms at the corridor's
# far end. No separate "trap" geometry is needed; the corner zone is just
# the corridor's last few columns.

# Shared corridor band, in cells: rows 6-13 (8 cells tall) for the two
# 30-wide stages, rows 6-9 (4 cells tall) for the narrower tutorial.

STAGE_1 = StageConfig(
    name="Sandbar Drill",
    grid_width=24,
    grid_height=16,
    pack_size=4,
    dog_spawn=Vector2(120, 256),
    jaguar_spawn=Vector2(450, 256),
    corner_zone=Rect(672, 192, 96, 128),  # corridor's last 3 columns
    required_capture_dogs=2,
    wall_rects=[
        Rect(0, 0, 768, 192),  # north bank
        Rect(0, 320, 768, 192),  # south bank
    ],
)

STAGE_2 = StageConfig(
    name="Braided Channel",
    grid_width=30,
    grid_height=20,
    pack_size=7,
    dog_spawn=Vector2(80, 320),
    jaguar_spawn=Vector2(520, 320),  # between the two crossings
    corner_zone=Rect(832, 192, 128, 256),  # corridor's last 4 columns
    required_capture_dogs=3,
    wall_rects=[
        Rect(0, 0, 960, 192),  # north bank
        Rect(0, 448, 960, 192),  # south bank
    ],
    water_zones=[
        Rect(320, 192, 96, 256),  # first braid, west of the jaguar's spawn
        Rect(576, 192, 64, 256),  # second braid, between it and the pocket
    ],
)

STAGE_3 = StageConfig(
    name="Jaguar's Bend",
    grid_width=30,
    grid_height=20,
    pack_size=12,
    dog_spawn=Vector2(80, 320),
    jaguar_spawn=Vector2(500, 320),  # before the alcove and the log
    corner_zone=Rect(832, 192, 128, 256),  # corridor's last 4 columns
    required_capture_dogs=5,
    wall_rects=[
        Rect(0, 0, 960, 192),  # north bank, unbroken
        Rect(0, 448, 512, 192),  # south bank, west of the plate alcove
        Rect(640, 448, 320, 192),  # south bank, east of the plate alcove
    ],
    water_zones=[Rect(320, 192, 96, 256)],
    # The alcove is simply the gap the two south-bank segments leave open
    # (x512-640) -- no separate room wall needed, it's bounded by them on
    # both sides and by the grid's own edge below.
    plate_rect=Rect(512, 480, 128, 128),
    plate_required=4,
    # A full-height column sealing the corridor outright until the plate
    # opens it -- not a bypassable obstacle at the corridor's edge.
    log_rect=Rect(672, 192, 32, 256),
)

STAGES = [STAGE_1, STAGE_2, STAGE_3]
