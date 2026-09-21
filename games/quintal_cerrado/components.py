"""Quintal do Cerrado - ECS Components and Soil State.

Two kinds of state, deliberately not the same kind. `SoilCell` is plain
data outside the ECS: a cell's five chemistry values have no individual
behaviour of their own and are read and mutated in bulk by grid-wide
systems every tick, the same idiom `guara_falcao`'s raw `tiles` grid
uses -- 96 per-cell `Entity`s would be the wrong shape for this. A planted
crop, by contrast, has individual identity, a position and (from Phase 2
on) FSM-driven behaviour, so it is a real entity carrying `PlantComponent`.
"""

from dataclasses import dataclass

from pyguara.ecs.component import BaseComponent


@dataclass
class SoilCell:
    """One tile's soil chemistry.

    Not an ECS component -- see the module docstring. `GardenGrid` owns a
    plain `list[list[SoilCell]]` parallel to its `Tilemap`.
    """

    soil_type: str = "raw_dirt"
    moisture: float = 0.3
    nitrogen: float = 0.2
    organic_matter: float = 0.2
    shade_level: float = 0.0
    pest_pressure: float = 0.0
    is_chemically_degraded: bool = False


@dataclass
class PlantComponent(BaseComponent):
    """A planted crop's species and lifecycle state.

    `growth_stage` mirrors the plant's `StateMachine`'s current state name
    (Phase 2 on) rather than being written directly by game code -- it is
    read-only bookkeeping for anything that wants the stage without
    reaching into the FSM (the save schema, the HUD's cell inspector).
    """

    species_id: str = "guandu"
    growth_stage: str = "seedling"
    growth_progress: float = 0.0
    health: float = 1.0
    is_chemical_boosted: bool = False
    growth_multiplier: float = 1.0

    def __post_init__(self) -> None:
        """Initialize the component."""
        super().__init__()


def till_cell(soil: SoilCell) -> bool:
    """Turn raw dirt into tilled dirt.

    A free function because it mutates, the same shape
    `guara_falcao.components.take_damage`/`heal` use.

    Args:
        soil: The cell to till.

    Returns:
        Whether tilling changed anything. Already-tilled ground is a
        no-op, not an error -- a click can land on ground already worked.
    """
    if soil.soil_type != "raw_dirt":
        return False
    soil.soil_type = "tilled_dirt"
    return True
