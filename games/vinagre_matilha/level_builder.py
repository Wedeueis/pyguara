"""Vinagre: Matilha - Level Builder.

Builds one stage's entities (pack, jaguar, vanguard, water zones, pressure
plate/log) plus the `GridGraph`/`FlowFieldService` the pack navigates with,
from a `StageConfig`. Wall/log rects and the `GridGraph`'s wall cells are
derived from one shared source of truth so they can never drift apart.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from games.vinagre_matilha.components import (
    CurrentZone,
    DogState,
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
from pyguara.kits.action_combat import Health
from pyguara.kits.pack import PackMember, PackRole
from pyguara.physics.components import Collider, RigidBody
from pyguara.physics.trigger_volume import TriggerVolume
from pyguara.physics.types import BodyType, ShapeType

CELL_SIZE = 32.0
_GOLDEN_ANGLE = 2.399963229728653  # radians; pi * (3 - sqrt(5))
DOG_COLLIDER_RADIUS = 8.0
VANGUARD_COLLIDER_RADIUS = 10.0
JAGUAR_COLLIDER_RADIUS = 14.0
WATER_WEIGHT = 2.5


@dataclass
class StageConfig:
    """Everything about one stage's layout, cast, and win/lose thresholds."""

    name: str
    briefing: str
    grid_width: int
    grid_height: int
    pack_size: int  # includes the vanguard
    dog_spawn: Vector2
    jaguar_spawn: Vector2
    corner_zone: Rect
    required_capture_dogs: int
    jaguar_health: float
    pack_break_threshold: int
    corridor_top: int
    corridor_height: int
    water_zones: list[Rect] = field(default_factory=list)
    wall_rects: list[Rect] = field(default_factory=list)
    plate_rect: Rect | None = None
    plate_required: int = 0
    log_rect: Rect | None = None

    @property
    def world_width(self) -> int:
        """Playfield width in pixels."""
        return int(self.grid_width * CELL_SIZE)

    @property
    def world_height(self) -> int:
        """Playfield height in pixels."""
        return int(self.grid_height * CELL_SIZE)


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

    jaguar_id = _create_jaguar(
        entity_manager, config.jaguar_spawn, config.jaguar_health
    )

    vanguard_id = _create_dog(
        entity_manager, config.dog_spawn, PackRole.VANGUARD, "vanguard"
    )

    dog_ids = [vanguard_id]
    for i in range(config.pack_size - 1):
        # Phyllotaxis (golden-angle) spread: an evenly distributed cluster
        # for *any* pack size. A previous row-major grid put every dog of
        # a four-strong pack on the same row, so the flankers spawned --
        # and stayed -- in a single overlapping line.
        angle = i * _GOLDEN_ANGLE
        radius = 20.0 + 10.0 * math.sqrt(i)
        offset = Vector2(math.cos(angle) * radius, math.sin(angle) * radius)
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
    entity.add_component(DogState())
    entity.add_component(WebbedFeet())
    entity.add_component(RigidBody(body_type=BodyType.KINEMATIC, fixed_rotation=True))
    entity.add_component(
        Collider(shape_type=ShapeType.CIRCLE, dimensions=[DOG_COLLIDER_RADIUS])
    )

    if role is PackRole.FLANKER:
        assert blackboard is not None
        entity.add_component(
            FlockingAgent(
                max_speed=158.0,
                neighbor_radius=110.0,
                # Wide enough that a pack converging on one target spreads
                # into a ring instead of queueing into a single-file line
                # behind it, which is what a tighter radius produced.
                separation_radius=46.0,
                separation_weight=2.1,
            )
        )
        entity.add_component(
            AIComponent(blackboard=blackboard, behavior_tree=build_pack_tree())
        )

    return entity.id


def _create_jaguar(
    entity_manager: EntityManager, position: Vector2, health: float
) -> str:
    entity = entity_manager.create_entity()
    entity.add_component(Transform(position=position))
    entity.add_component(JaguarState())
    entity.add_component(Health(current=health, max_health=health))
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

# Every stage is 30x20 cells, exactly filling the 960x640 window, with a
# corridor band of rows 5-14 (y 160-480). That band is deliberately tall:
# dodging a telegraphed swipe needs somewhere to dodge *to*, and a pack of
# twelve needs room to actually flank rather than queue up single file.

_CORRIDOR_TOP = 160
_CORRIDOR_HEIGHT = 320
_NORTH_BANK = Rect(0, 0, 960, _CORRIDOR_TOP)
_SOUTH_BANK = Rect(0, 480, 960, 160)
# Rock wall capping the bend, so the jaguar is stopped a body-length short
# of the window edge instead of ending the fight half off-screen.
_EAST_WALL = Rect(896, _CORRIDOR_TOP, 64, _CORRIDOR_HEIGHT)
_POCKET = Rect(768, _CORRIDOR_TOP, 128, _CORRIDOR_HEIGHT)

STAGE_1 = StageConfig(
    name="Sandbar Drill",
    briefing="Drive the jaguar east. Bite when close -- Scatter when it winds up.",
    grid_width=30,
    grid_height=20,
    pack_size=4,
    dog_spawn=Vector2(96, 320),
    jaguar_spawn=Vector2(560, 320),
    corner_zone=_POCKET,
    required_capture_dogs=2,
    jaguar_health=120.0,
    # The tutorial only breaks if the *whole* pack is down at once: a
    # first-time player is still learning to read the wind-up, and losing
    # three seconds in teaches nothing.
    pack_break_threshold=4,
    corridor_top=_CORRIDOR_TOP,
    corridor_height=_CORRIDOR_HEIGHT,
    wall_rects=[_NORTH_BANK, _SOUTH_BANK, _EAST_WALL],
)

STAGE_2 = StageConfig(
    name="Braided Channel",
    briefing="Currents slow the jaguar, not your webbed pack. Use them.",
    grid_width=30,
    grid_height=20,
    pack_size=7,
    dog_spawn=Vector2(96, 320),
    jaguar_spawn=Vector2(520, 320),  # between the two crossings
    corner_zone=_POCKET,
    required_capture_dogs=3,
    jaguar_health=170.0,
    pack_break_threshold=4,
    corridor_top=_CORRIDOR_TOP,
    corridor_height=_CORRIDOR_HEIGHT,
    wall_rects=[_NORTH_BANK, _SOUTH_BANK, _EAST_WALL],
    water_zones=[
        Rect(320, _CORRIDOR_TOP, 96, _CORRIDOR_HEIGHT),  # first braid
        Rect(608, _CORRIDOR_TOP, 64, _CORRIDOR_HEIGHT),  # second braid
    ],
)

STAGE_3 = StageConfig(
    name="Jaguar's Bend",
    briefing="Four of the pack must hold the plate to drop the log. Split them.",
    grid_width=30,
    grid_height=20,
    pack_size=12,
    dog_spawn=Vector2(96, 320),
    jaguar_spawn=Vector2(460, 320),  # before the alcove and the log
    corner_zone=_POCKET,
    required_capture_dogs=5,
    jaguar_health=260.0,
    pack_break_threshold=6,
    corridor_top=_CORRIDOR_TOP,
    corridor_height=_CORRIDOR_HEIGHT,
    wall_rects=[
        _NORTH_BANK,
        Rect(0, 480, 512, 160),  # south bank, west of the plate alcove
        Rect(640, 480, 320, 160),  # south bank, east of the plate alcove
        _EAST_WALL,
    ],
    water_zones=[Rect(320, _CORRIDOR_TOP, 96, _CORRIDOR_HEIGHT)],
    # The alcove is simply the gap the two south-bank segments leave open
    # (x512-640) -- no separate room wall needed, it's bounded by them on
    # both sides and by the grid's own edge below.
    plate_rect=Rect(516, 500, 120, 120),
    plate_required=4,
    # A full-height column sealing the corridor outright until the plate
    # opens it -- not a bypassable obstacle at the corridor's edge.
    log_rect=Rect(736, _CORRIDOR_TOP, 32, _CORRIDOR_HEIGHT),
)

STAGES = [STAGE_1, STAGE_2, STAGE_3]
