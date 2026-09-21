"""Prices, and the organic-versus-chemical fork in what a harvest sells for.

The PRD's dilemma in one place: a plant that was ever chemically treated
sells at half the market rate, and one that never was sells at double it.
That is the whole reason the natural path is worth its slower recovery --
`treatments.py`'s spray fixes a pest outbreak instantly and costs the
premium for good, since `PlantComponent.is_chemical_boosted` never clears.

A set of free functions rather than a ticking `economy_system.py`: unlike
soil or shade, nothing about money changes on its own between player
actions, so there is nothing for a system to tick.
"""

from __future__ import annotations

from games.quintal_cerrado.components import PlantComponent
from games.quintal_cerrado.species import SPECIES_TABLE

COMPOST_COST = 5
SPRAY_COST = 25

ORGANIC_PREMIUM = 2.0
"""Sale multiplier for a plant never touched by chemicals (PRD: 2.0x)."""

CHEMICAL_DISCOUNT = 0.5
"""Sale multiplier for a chemically treated plant (PRD: 0.5x)."""


def sale_multiplier(plant: PlantComponent) -> float:
    """How much of the market rate `plant` fetches.

    Args:
        plant: The plant being sold.

    Returns:
        `CHEMICAL_DISCOUNT` if it was ever sprayed, else `ORGANIC_PREMIUM`.
    """
    return CHEMICAL_DISCOUNT if plant.is_chemical_boosted else ORGANIC_PREMIUM


def sale_value(plant: PlantComponent) -> int:
    """Whole Sementes `plant` sells for.

    Args:
        plant: The plant being sold.

    Returns:
        Its species' base price times `sale_multiplier`, rounded to a whole
        number and never less than 1 -- an unknown species sells for 0.
    """
    species = SPECIES_TABLE.get(plant.species_id)
    if species is None:
        return 0
    return max(1, round(species.base_price * sale_multiplier(plant)))
