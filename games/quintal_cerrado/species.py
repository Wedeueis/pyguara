"""The plantable species catalogue.

Filled in incrementally. Phase 1 shipped only Guandu, since there was no
growth or companion-planting yet for a canopy layer or growth rate to
matter to. Phase 2 adds Baru (canopy) and Cagaita (understory) -- the
PRD's own stratification example, "planting Cagaita under the shade of
Baru with Guandu at the base" -- since `systems/shade_system.py` and
`systems/syntropic_system.py` now give those fields real weight. Pequi (the
pest-recovery species) is Phase 3's, alongside the pest mechanic it exists
to answer.
"""

from __future__ import annotations

from dataclasses import dataclass

from pyguara.common.types import Color
from pyguara.ui.design_system.tokens import Sand, Verdant


@dataclass(frozen=True)
class Species:
    """One plantable species' static data.

    Attributes:
        species_id: Stable id, matching `PlantComponent.species_id`.
        display_name: Label the store and cell inspector show.
        canopy_layer: `"ground_cover"`, `"understory"` or `"canopy"` --
            what `systems/syntropic_system.py`'s stratification bonus and
            `systems/shade_system.py`'s shade-casting key off.
        color: The plant's fill colour (this demo ships no textures).
        stage_seconds: Seconds `systems/plant_growth_system.py` needs, at a
            growth multiplier of 1.0, to fill one stage's growth budget.
            Demo-paced, not realistic -- a canopy tree taking real years to
            mature would leave a 15-minute playable loop with nothing to
            show for it.
    """

    species_id: str
    display_name: str
    canopy_layer: str
    color: Color
    stage_seconds: float = 4.0


SPECIES_TABLE: dict[str, Species] = {
    "guandu": Species(
        species_id="guandu",
        display_name="Guandu",
        canopy_layer="ground_cover",
        color=Verdant.SAGE_500,
        stage_seconds=3.0,
    ),
    "cagaita": Species(
        species_id="cagaita",
        display_name="Cagaita",
        canopy_layer="understory",
        color=Sand.C400,
        stage_seconds=4.5,
    ),
    "baru": Species(
        species_id="baru",
        display_name="Baru",
        canopy_layer="canopy",
        color=Verdant.COLONIAL_500,
        stage_seconds=6.0,
    ),
}
