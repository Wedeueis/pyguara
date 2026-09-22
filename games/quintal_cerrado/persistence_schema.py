"""What a save file holds, and how the garden goes to and from it.

The first real use of `pyguara.persistence` by any demo. Two engine facts
shape everything here, both found by reading `persistence/serializer.py`
rather than assuming:

**Dataclasses do not round-trip.** `Serializer` tags a dataclass with
`"__type__": "ClassName"` on the way out, but its `game_object_hook` only
rebuilds `Vector2`, `Color` and `Rect` on the way in -- a saved
`PlayerEconomy` would come back as a plain dict with a stray `__type__` key.
So the payload built here is *only* dicts, lists, strings and numbers,
assembled by hand, and `apply_save_payload()` rebuilds the real components
from it. That boundary is deliberate and is not indirection to simplify
away: pass a component straight to `save_data()` and it silently degrades.

**Cells are lists, not dict keys.** JSON keys must be strings, so the grid
is a flat list of per-cell records carrying their own `x`/`y`.

Loading is **parse, then apply**. `_parse()` turns the whole payload into
validated plain values first and raises `SaveFormatError` on anything
wrong -- a missing field, a wrong type, an unknown stage, a newer schema.
Only a payload that parsed cleanly touches the garden, so a corrupt or
hand-edited save can be refused without leaving a half-loaded plot behind.

`SCHEMA_VERSION` is the engine's own `save_version`, checked by the
`MigrationManager` `bootstrap.py` builds. There is nothing to migrate *from*
yet, so no migration is registered; a version newer than this build knows is
refused rather than guessed at.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from games.quintal_cerrado.components import (
    AutomationComponent,
    GardenConditions,
    PlantComponent,
    PlayerEconomy,
)
from games.quintal_cerrado.garden_grid import GRID_HEIGHT, GRID_WIDTH, GardenGrid
from games.quintal_cerrado.plant_states import build_plant_ai
from games.quintal_cerrado.structures import STRUCTURE_TABLE
from pyguara.ai.components import AIComponent
from pyguara.ecs.manager import EntityManager

SCHEMA_VERSION = 1
SAVE_KEY = "garden_save"
"""Alphanumerics, `_` and `-` only: `FileStorageBackend` rejects any other key
rather than mangling it."""

_PLANT_STAGES = frozenset(
    {"seedling", "growing", "mature", "harvestable", "infested", "dying"}
)
_PHASES = frozenset({"stable", "outbreak", "resolved_organic", "resolved_chemical"})


class SaveFormatError(ValueError):
    """A save could not be understood, and nothing was changed."""


def to_save_payload(
    grid: GardenGrid,
    entity_manager: EntityManager,
    economy: PlayerEconomy,
    conditions: GardenConditions,
    elapsed: float,
) -> dict[str, Any]:
    """Describe the whole garden as plain data.

    Args:
        grid: The plot.
        entity_manager: Where the plants and structures live.
        economy: The player's economy.
        conditions: The garden's pest situation.
        elapsed: Seconds of play so far.

    Returns:
        A dict of dicts, lists, strings and numbers only -- see the module
        docstring for why it must stay that way.
    """
    cells = []
    for y in range(GRID_HEIGHT):
        for x in range(GRID_WIDTH):
            soil = grid.soil_at((x, y))
            cells.append(
                {
                    "x": x,
                    "y": y,
                    "soil_type": soil.soil_type,
                    "moisture": soil.moisture,
                    "nitrogen": soil.nitrogen,
                    "organic_matter": soil.organic_matter,
                    "shade_level": soil.shade_level,
                    "pest_pressure": soil.pest_pressure,
                    "is_chemically_degraded": soil.is_chemically_degraded,
                    "plant": _plant_record(grid, entity_manager, (x, y)),
                    "automation": _automation_record(grid, entity_manager, (x, y)),
                }
            )

    phase_timer = 0.0
    conditions_ai = _conditions_ai(conditions)
    if conditions_ai is not None:
        phase_timer = float(conditions_ai.blackboard.get("elapsed", 0.0))

    return {
        "version": SCHEMA_VERSION,
        "elapsed": elapsed,
        "player": {
            "credits": economy.credits,
            "revenue": economy.revenue,
            "organic_sales": economy.organic_sales,
            "chemical_sales": economy.chemical_sales,
            "inventory": dict(economy.inventory),
            "unlocked_tech": sorted(economy.unlocked_tech),
        },
        "conditions": {
            "phase": conditions.phase,
            "last_treatment": conditions.last_treatment,
            "organic_resolutions": conditions.organic_resolutions,
            "chemical_resolutions": conditions.chemical_resolutions,
            "phase_elapsed": phase_timer,
        },
        "grid": cells,
    }


def _conditions_ai(conditions: GardenConditions) -> AIComponent | None:
    owner = conditions.entity
    if owner is None or not owner.has_component(AIComponent):
        return None
    return owner.get_component(AIComponent)


def _plant_record(
    grid: GardenGrid, entity_manager: EntityManager, cell: tuple[int, int]
) -> dict[str, Any] | None:
    entity_id = grid.plant_at.get(cell)
    entity = entity_manager.get_entity(entity_id) if entity_id else None
    if entity is None or not entity.has_component(PlantComponent):
        return None
    plant = entity.get_component(PlantComponent)
    blackboard = entity.get_component(AIComponent).blackboard
    return {
        "species_id": plant.species_id,
        "growth_stage": plant.growth_stage,
        "growth_progress": plant.growth_progress,
        "health": plant.health,
        "is_chemical_boosted": plant.is_chemical_boosted,
        "growth_multiplier": plant.growth_multiplier,
        "pest_pressure": plant.pest_pressure,
        # What an infested plant needs to return to exactly where it was.
        "resume_stage": blackboard.get("resume_stage"),
        "resume_progress": blackboard.get("resume_progress"),
    }


def _automation_record(
    grid: GardenGrid, entity_manager: EntityManager, cell: tuple[int, int]
) -> dict[str, Any] | None:
    entity_id = grid.automation_at.get(cell)
    entity = entity_manager.get_entity(entity_id) if entity_id else None
    if entity is None or not entity.has_component(AutomationComponent):
        return None
    structure = entity.get_component(AutomationComponent)
    return {
        "kind": structure.kind,
        "powered": structure.powered,
        "timer": structure.timer,
    }


@dataclass
class _Parsed:
    """A payload that has been fully validated, as plain values."""

    elapsed: float
    player: dict[str, Any]
    conditions: dict[str, Any]
    cells: list[dict[str, Any]]


def _parse(payload: Any) -> _Parsed:
    """Validate a payload completely, without touching the garden.

    Raises:
        SaveFormatError: On anything that is not a well-formed save this
            build understands.
    """
    try:
        if not isinstance(payload, dict):
            raise SaveFormatError("save is not a JSON object")
        version = payload["version"]
        if version != SCHEMA_VERSION:
            raise SaveFormatError(
                f"save is schema v{version}; this build reads v{SCHEMA_VERSION}"
            )

        player = payload["player"]
        parsed_player = {
            "credits": float(player["credits"]),
            "revenue": float(player["revenue"]),
            "organic_sales": int(player["organic_sales"]),
            "chemical_sales": int(player["chemical_sales"]),
            "inventory": {str(k): int(v) for k, v in player["inventory"].items()},
            "unlocked_tech": {str(t) for t in player["unlocked_tech"]},
        }
        for kind in [*parsed_player["inventory"], *parsed_player["unlocked_tech"]]:
            if kind not in STRUCTURE_TABLE:
                raise SaveFormatError(f"unknown structure {kind!r}")

        cond = payload["conditions"]
        if cond["phase"] not in _PHASES:
            raise SaveFormatError(f"unknown garden phase {cond['phase']!r}")
        parsed_cond = {
            "phase": str(cond["phase"]),
            "last_treatment": str(cond["last_treatment"]),
            "organic_resolutions": int(cond["organic_resolutions"]),
            "chemical_resolutions": int(cond["chemical_resolutions"]),
            "phase_elapsed": float(cond["phase_elapsed"]),
        }

        cells = [_parse_cell(record) for record in payload["grid"]]
        if len(cells) != GRID_WIDTH * GRID_HEIGHT:
            raise SaveFormatError(f"expected {GRID_WIDTH * GRID_HEIGHT} cells")

        return _Parsed(float(payload["elapsed"]), parsed_player, parsed_cond, cells)
    except (KeyError, TypeError, ValueError, AttributeError) as error:
        if isinstance(error, SaveFormatError):
            raise
        raise SaveFormatError(f"malformed save: {error!r}") from error


def _parse_cell(record: dict[str, Any]) -> dict[str, Any]:
    x, y = int(record["x"]), int(record["y"])
    if not (0 <= x < GRID_WIDTH and 0 <= y < GRID_HEIGHT):
        raise SaveFormatError(f"cell ({x}, {y}) is outside the plot")
    cell: dict[str, Any] = {
        "cell": (x, y),
        "soil_type": str(record["soil_type"]),
        "moisture": float(record["moisture"]),
        "nitrogen": float(record["nitrogen"]),
        "organic_matter": float(record["organic_matter"]),
        "shade_level": float(record["shade_level"]),
        "pest_pressure": float(record["pest_pressure"]),
        "is_chemically_degraded": bool(record["is_chemically_degraded"]),
        "plant": None,
        "automation": None,
    }

    plant = record["plant"]
    if plant is not None:
        if plant["growth_stage"] not in _PLANT_STAGES:
            raise SaveFormatError(f"unknown plant stage {plant['growth_stage']!r}")
        resume_progress = plant["resume_progress"]
        cell["plant"] = {
            "species_id": str(plant["species_id"]),
            "growth_stage": str(plant["growth_stage"]),
            "growth_progress": float(plant["growth_progress"]),
            "health": float(plant["health"]),
            "is_chemical_boosted": bool(plant["is_chemical_boosted"]),
            "growth_multiplier": float(plant["growth_multiplier"]),
            "pest_pressure": float(plant["pest_pressure"]),
            "resume_stage": plant["resume_stage"],
            "resume_progress": None
            if resume_progress is None
            else float(resume_progress),
        }

    automation = record["automation"]
    if automation is not None:
        if automation["kind"] not in STRUCTURE_TABLE:
            raise SaveFormatError(f"unknown structure {automation['kind']!r}")
        cell["automation"] = {
            "kind": str(automation["kind"]),
            "powered": bool(automation["powered"]),
            "timer": float(automation["timer"]),
        }
    return cell


def apply_save_payload(
    payload: Any,
    grid: GardenGrid,
    entity_manager: EntityManager,
    economy: PlayerEconomy,
    conditions: GardenConditions,
) -> float:
    """Rebuild the garden from a saved payload.

    Expects a freshly built, empty garden: it overwrites soil, adds plants
    and structures, and does not clear anything first.

    Args:
        payload: What `load_data()` returned. Anything, including None.
        grid: The empty plot to fill.
        entity_manager: Where the plants and structures are created.
        economy: The economy to overwrite in place.
        conditions: The conditions to overwrite in place. Must already carry
            its `AIComponent`.

    Returns:
        Seconds of play the save recorded.

    Raises:
        SaveFormatError: If the payload is not a valid save. Nothing has
            been changed when this is raised.
    """
    parsed = _parse(payload)

    for key, value in parsed.player.items():
        setattr(economy, key, value)

    for record in parsed.cells:
        cell = record["cell"]
        if record["soil_type"] == "tilled_dirt":
            grid.till(cell)
        soil = grid.soil_at(cell)
        soil.moisture = record["moisture"]
        soil.nitrogen = record["nitrogen"]
        soil.organic_matter = record["organic_matter"]
        soil.shade_level = record["shade_level"]
        soil.pest_pressure = record["pest_pressure"]
        soil.is_chemically_degraded = record["is_chemically_degraded"]
        if record["plant"] is not None:
            _restore_plant(grid, entity_manager, cell, record["plant"])
        if record["automation"] is not None:
            _restore_structure(grid, entity_manager, cell, record["automation"])

    _restore_conditions(conditions, parsed.conditions)
    return parsed.elapsed


def _restore_plant(
    grid: GardenGrid,
    entity_manager: EntityManager,
    cell: tuple[int, int],
    saved: dict[str, Any],
) -> None:
    entity = entity_manager.create_entity()
    plant = entity.add_component(PlantComponent(species_id=saved["species_id"]))
    ai = build_plant_ai(entity)
    assert ai.fsm is not None
    # Through the FSM, so the machine and the component agree on the stage.
    # Entering a state resets progress, so the saved numbers go on afterwards.
    ai.fsm.set_initial_state(saved["growth_stage"])
    plant.growth_progress = saved["growth_progress"]
    plant.health = saved["health"]
    plant.is_chemical_boosted = saved["is_chemical_boosted"]
    plant.growth_multiplier = saved["growth_multiplier"]
    plant.pest_pressure = saved["pest_pressure"]
    ai.blackboard.set("resume_stage", saved["resume_stage"])
    ai.blackboard.set("resume_progress", saved["resume_progress"])
    entity.add_component(ai)
    grid.mark_planted(cell, entity.id)


def _restore_structure(
    grid: GardenGrid,
    entity_manager: EntityManager,
    cell: tuple[int, int],
    saved: dict[str, Any],
) -> None:
    entity = entity_manager.create_entity()
    entity.add_component(
        AutomationComponent(
            kind=saved["kind"], powered=saved["powered"], timer=saved["timer"]
        )
    )
    grid.mark_built(cell, entity.id)


def _restore_conditions(conditions: GardenConditions, saved: dict[str, Any]) -> None:
    ai = _conditions_ai(conditions)
    if ai is not None and ai.fsm is not None:
        # `restoring` stops entering a phase from replaying its side effects:
        # seeding pests, counting a resolution, announcing either.
        ai.blackboard.set("restoring", True)
        ai.fsm.set_initial_state(saved["phase"])
        ai.blackboard.set("restoring", False)
        ai.blackboard.set("elapsed", saved["phase_elapsed"])
    conditions.phase = saved["phase"]
    conditions.last_treatment = saved["last_treatment"]
    conditions.organic_resolutions = saved["organic_resolutions"]
    conditions.chemical_resolutions = saved["chemical_resolutions"]
