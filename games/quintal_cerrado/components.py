"""Quintal do Cerrado - ECS Components and Soil State.

Two kinds of state, deliberately not the same kind. `SoilCell` is plain
data outside the ECS: a cell's five chemistry values have no individual
behaviour of their own and are read and mutated in bulk by grid-wide
systems every tick, the same idiom `guara_falcao`'s raw `tiles` grid
uses -- 96 per-cell `Entity`s would be the wrong shape for this. A planted
crop, by contrast, has individual identity, a position and (from Phase 2
on) FSM-driven behaviour, so it is a real entity carrying `PlantComponent`.
"""

from dataclasses import dataclass, field

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
    pest_pressure: float = 0.0
    """Mirror of the plant's own cell's `SoilCell.pest_pressure`, written by
    `systems/pest_system.py` each tick. It exists so `plant_states.py`'s
    states can decide `infested` transitions from the plant's own component
    without holding a reference to the grid."""

    def __post_init__(self) -> None:
        """Initialize the component."""
        super().__init__()


STARTING_CREDITS = 150.0
"""The PRD's own figure for a new game's Sementes."""


@dataclass
class PlayerEconomy(BaseComponent):
    """The player's Sementes, and what they have earned by which method.

    A component on a lightweight `"player"` entity rather than a loose
    attribute on the scene, following `guara_falcao`'s `Score`/`Health`
    precedent, so it composes with the same `get_entities_with(...)`
    query idiom the rest of the engine uses.

    Attributes:
        credits: Sementes on hand.
        organic_sales: Harvests sold at the organic premium.
        chemical_sales: Harvests sold at the chemical discount. Both counts
            are what a later evaluation screen scores the player's
            agroecology on.
        revenue: Sementes earned from harvests and solar since the start --
            the money-in half of the evaluation score, kept apart from
            `credits` because spending must not lower it.
        inventory: Structures bought from the store and not yet placed,
            by kind.
        unlocked_tech: Structure kinds the player has placed at least once
            -- what `structures.py`'s tech tree gates each next structure
            on, and what the save schema records.
    """

    credits: float = STARTING_CREDITS
    revenue: float = 0.0
    organic_sales: int = 0
    chemical_sales: int = 0
    inventory: dict[str, int] = field(default_factory=dict)
    unlocked_tech: set[str] = field(default_factory=set)

    def __post_init__(self) -> None:
        """Initialize the component."""
        super().__init__()


@dataclass
class GardenConditions(BaseComponent):
    """The garden-wide pest situation, driven by `garden_states.py`'s FSM.

    Attributes:
        phase: Mirrors the conditions FSM's current state name, the same
            way `PlantComponent.growth_stage` mirrors a plant's.
        last_treatment: `"organic"` or `"chemical"` -- how the player last
            answered an outbreak. The FSM reads it to decide which
            `resolved_*` state an outbreak ends in.
        organic_resolutions: Outbreaks that ended after an organic answer
            (or none at all).
        chemical_resolutions: Outbreaks that ended after a chemical answer.
    """

    phase: str = "stable"
    last_treatment: str = ""
    organic_resolutions: int = 0
    chemical_resolutions: int = 0

    def __post_init__(self) -> None:
        """Initialize the component."""
        super().__init__()


@dataclass
class AutomationComponent(BaseComponent):
    """A placed structure: what it is and what it is currently doing.

    Attributes:
        kind: A key of `structures.STRUCTURE_TABLE`.
        powered: Whether the structure has power this tick. Written by
            `systems/automation_system.py`, which shares each solar panel's
            output out in placement order; a structure that needs power and
            does not get it does nothing, and the art draws a warning.
        timer: Seconds of accumulated work -- a solar panel's progress
            towards its next payout, or a drone's cooldown to its next
            harvest.
    """

    kind: str = "solar_panel"
    powered: bool = True
    timer: float = 0.0

    def __post_init__(self) -> None:
        """Initialize the component."""
        super().__init__()


def add_credits(economy: PlayerEconomy, amount: float) -> None:
    """Credit `amount` Sementes to `economy`, counting it as revenue.

    Every way of *earning* goes through here -- a harvest, a drone's sale,
    a solar payout -- so `revenue` can be trusted as total income.

    Args:
        economy: The economy to credit.
        amount: How many Sementes to add.
    """
    economy.credits += amount
    economy.revenue += amount


def spend_credits(economy: PlayerEconomy, amount: float) -> bool:
    """Debit `amount` Sementes, if the player can afford it.

    Args:
        economy: The economy to debit.
        amount: How many Sementes to spend.

    Returns:
        Whether the purchase went through. Nothing is debited on False.
    """
    if economy.credits < amount:
        return False
    economy.credits -= amount
    return True


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


WATER_AMOUNT = 0.4
"""Moisture a single watering adds, capped at 1.0. `systems/soil_system.py`
decays it back down over time, so this is a top-up, not a permanent fix."""


def water_cell(soil: SoilCell) -> bool:
    """Raise a cell's moisture, capped at 1.0.

    Args:
        soil: The cell to water.

    Returns:
        Whether watering changed anything. Already-saturated soil is a
        no-op, not an error.
    """
    if soil.moisture >= 1.0:
        return False
    soil.moisture = min(1.0, soil.moisture + WATER_AMOUNT)
    return True


COMPOST_AMOUNT = 0.5
"""Organic matter a single compost application adds, capped at 1.0."""

COMPOST_HEALS_DEGRADATION_AT = 0.7
"""Organic matter at which compost also clears `is_chemically_degraded` --
a spray drops organic matter, so a degraded cell needs more than one
application before the soil counts as recovered."""

SPRAY_ORGANIC_MATTER_LOSS = 0.15
"""Organic matter a chemical spray strips from every cell it reaches."""


def compost_cell(soil: SoilCell) -> bool:
    """Add organic matter to a cell, healing chemical damage once rich enough.

    Args:
        soil: The cell to compost.

    Returns:
        Whether composting changed anything. Already-saturated soil is a
        no-op, not an error.
    """
    if soil.organic_matter >= 1.0:
        return False
    soil.organic_matter = min(1.0, soil.organic_matter + COMPOST_AMOUNT)
    if (
        soil.is_chemically_degraded
        and soil.organic_matter >= COMPOST_HEALS_DEGRADATION_AT
    ):
        soil.is_chemically_degraded = False
    return True


def spray_cell(soil: SoilCell) -> None:
    """Clear a cell's pests the fast way, at the soil's expense.

    Args:
        soil: The cell to spray.
    """
    soil.pest_pressure = 0.0
    soil.is_chemically_degraded = True
    soil.organic_matter = max(0.0, soil.organic_matter - SPRAY_ORGANIC_MATTER_LOSS)
