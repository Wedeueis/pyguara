"""The plantable species catalogue.

Filled in incrementally. Phase 1 plants only Guandu, the legume seed the
PRD's onboarding beat starts the player with -- there is no growth or
companion-planting yet for a canopy layer or growth rate to matter to.
Later phases add Baru, Cagaita and Pequi alongside the mechanics that give
those fields real weight.
"""

from __future__ import annotations

from dataclasses import dataclass

from pyguara.common.types import Color
from pyguara.ui.design_system.tokens import Verdant


@dataclass(frozen=True)
class Species:
    """One plantable species' static data.

    Attributes:
        species_id: Stable id, matching `PlantComponent.species_id`.
        display_name: Label the store and cell inspector show.
        canopy_layer: `"ground_cover"`, `"understory"` or `"canopy"` --
            what the Phase 2 stratification bonus keys off.
        color: The seedling's fill colour (this demo ships no textures).
    """

    species_id: str
    display_name: str
    canopy_layer: str
    color: Color


SPECIES_TABLE: dict[str, Species] = {
    "guandu": Species(
        species_id="guandu",
        display_name="Guandu",
        canopy_layer="ground_cover",
        color=Verdant.SAGE_500,
    ),
}
