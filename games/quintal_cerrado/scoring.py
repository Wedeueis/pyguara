"""The Agroecological Score: soil health, biodiversity and revenue.

The PRD's own three ingredients ("Soil Health + Biodiversity Index + Total
Revenue"), plus how much of what was sold was sold organically -- the one
number that says *how* the money was made, which is the whole point of the
game's dilemma. Each ingredient is a 0-1 fraction; the total is out of 1000.

Everything is read from the garden as it stands: nothing is tracked for the
score alone, so it cannot drift from what the player can see on the plot.
"""

from __future__ import annotations

from dataclasses import dataclass

from games.quintal_cerrado.components import PlantComponent, PlayerEconomy
from games.quintal_cerrado.garden_grid import GardenGrid
from games.quintal_cerrado.species import SPECIES_TABLE
from pyguara.ecs.manager import EntityManager

REVENUE_GOAL = 600.0
"""Sementes earned that count as a full revenue score."""

DEGRADED_SOIL_PENALTY = 0.5
"""Multiplier on a chemically degraded cell's contribution to soil health."""

_WEIGHTS = {"soil": 0.30, "biodiversity": 0.30, "revenue": 0.30, "organic": 0.10}

_GRADES = (
    (800, "Guardian of the Cerrado"),
    (550, "Syntropic Farmer"),
    (300, "Sprout"),
    (0, "Seed"),
)


@dataclass(frozen=True)
class Score:
    """A garden's score, as four 0-1 fractions and a total.

    Attributes:
        soil_health: Mean organic matter of the tilled soil, halved where
            chemically degraded.
        biodiversity: Distinct species living on the plot, out of all of them.
        revenue: Total Sementes earned, as a fraction of `REVENUE_GOAL`.
        organic: Fraction of harvests sold at the organic premium.
        total: Out of 1000.
        grade: A title for the total.
    """

    soil_health: float
    biodiversity: float
    revenue: float
    organic: float
    total: int
    grade: str


def compute_score(
    grid: GardenGrid, entity_manager: EntityManager, economy: PlayerEconomy
) -> Score:
    """Score the garden as it stands.

    Args:
        grid: The plot.
        entity_manager: Where the plants live.
        economy: The player's economy.

    Returns:
        The `Score`.
    """
    tilled = [
        soil for row in grid.soil for soil in row if soil.soil_type == "tilled_dirt"
    ]
    soil_health = 0.0
    if tilled:
        soil_health = sum(
            min(1.0, soil.organic_matter)
            * (DEGRADED_SOIL_PENALTY if soil.is_chemically_degraded else 1.0)
            for soil in tilled
        ) / len(tilled)

    living: set[str] = set()
    for entity_id in grid.plant_at.values():
        entity = entity_manager.get_entity(entity_id)
        if entity is None or not entity.has_component(PlantComponent):
            continue
        plant = entity.get_component(PlantComponent)
        if plant.growth_stage != "dying":
            living.add(plant.species_id)
    biodiversity = len(living) / len(SPECIES_TABLE)

    revenue = min(1.0, economy.revenue / REVENUE_GOAL)

    sales = economy.organic_sales + economy.chemical_sales
    organic = economy.organic_sales / sales if sales else 0.0

    total = round(
        1000
        * (
            _WEIGHTS["soil"] * soil_health
            + _WEIGHTS["biodiversity"] * biodiversity
            + _WEIGHTS["revenue"] * revenue
            + _WEIGHTS["organic"] * organic
        )
    )
    grade = next(name for floor, name in _GRADES if total >= floor)
    return Score(soil_health, biodiversity, revenue, organic, total, grade)
