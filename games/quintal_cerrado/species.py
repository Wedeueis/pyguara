"""The plantable species catalogue.

Filled in incrementally. Phase 1 shipped only Guandu, since there was no
growth or companion-planting yet for a canopy layer or growth rate to
matter to. Phase 2 adds Baru (canopy) and Cagaita (understory) -- the
PRD's own stratification example, "planting Cagaita under the shade of
Baru with Guandu at the base" -- since `systems/shade_system.py` and
`systems/syntropic_system.py` now give those fields real weight. Phase 3
adds Pequi, the pest-recovery species the PRD's organic path names
("Plant Pequi and add organic compost"): it is the one species that
repels pests, which is what `systems/pest_system.py` reads `repels_pests`
for.
"""

from __future__ import annotations

from dataclasses import dataclass

from pyguara.common.types import Color
from pyguara.ui.design_system.tokens import Guara, Sand, Verdant


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
        seed_cost: Sementes (the game's currency) one seed costs.
        base_price: Sementes a harvested plant sells for at the normal
            market rate, before `economy.py`'s organic premium or chemical
            discount is applied.
        repels_pests: Whether a grown plant of this species suppresses
            pest pressure on and around its own cell -- the PRD's "pest
            resistance via flora".
    """

    species_id: str
    display_name: str
    canopy_layer: str
    color: Color
    stage_seconds: float = 4.0
    seed_cost: int = 5
    base_price: int = 8
    repels_pests: bool = False


SPECIES_TABLE: dict[str, Species] = {
    "guandu": Species(
        species_id="guandu",
        display_name="Guandu",
        canopy_layer="ground_cover",
        color=Verdant.SAGE_500,
        stage_seconds=3.0,
        seed_cost=5,
        base_price=8,
    ),
    "cagaita": Species(
        species_id="cagaita",
        display_name="Cagaita",
        canopy_layer="understory",
        color=Sand.C400,
        stage_seconds=4.5,
        seed_cost=10,
        base_price=16,
    ),
    "baru": Species(
        species_id="baru",
        display_name="Baru",
        canopy_layer="canopy",
        color=Verdant.COLONIAL_500,
        stage_seconds=6.0,
        seed_cost=15,
        base_price=24,
    ),
    "pequi": Species(
        species_id="pequi",
        display_name="Pequi",
        canopy_layer="canopy",
        color=Guara.C500,
        stage_seconds=5.0,
        seed_cost=12,
        base_price=20,
        repels_pests=True,
    ),
}
