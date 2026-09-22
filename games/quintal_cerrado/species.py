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

The fun-improvement roadmap's Phase 2 adds `Weed` -- not a species the
player ever buys, but the same `Species`/`PlantComponent`/FSM machinery
everything else uses, singled out only by `is_weed` and a much higher
`spread_chance` (see `systems/weed_spread_system.py`). Keeping it a
`Species` rather than a special-cased second kind of thing means
rendering, growth, pests and stratification all already know how to
handle it for free.
"""

from __future__ import annotations

from dataclasses import dataclass

from pyguara.common.random import RandomStream
from pyguara.common.types import Color
from pyguara.ui.design_system.tokens import Guara, Sand, Verdant

WEED_SPECIES_ID = "weed"


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
        seed_cost: Sementes (the game's currency) one seed costs. Meaningless
            for a weed, which is never bought.
        base_price: Sementes a harvested plant sells for at the normal
            market rate, before `economy.py`'s organic premium or chemical
            discount is applied. Meaningless for a weed, which pulling
            pays out in generic seed stock instead of Sementes (see
            `economy.harvest_cell`).
        repels_pests: Whether a grown plant of this species suppresses
            pest pressure on and around its own cell -- the PRD's "pest
            resistance via flora".
        spread_chance: Chance, each time `systems/weed_spread_system.py`
            checks (every `PROPAGATION_INTERVAL` seconds, not every tick),
            that a mature-or-later plant of this species seeds a free
            neighbouring tilled cell with itself. Weeds are given a high
            one; real crops a very low one -- the same "economically
            valuable plants propagate rarely, weeds propagate fast" split
            the roadmap asked for, expressed as one data field rather than
            an `if species_id == "weed"` branch anywhere.
        is_weed: Excludes this species from anything that should not treat
            a weed as a "species" a player is growing -- the biodiversity
            score (`scoring.py`), the buyable-seed tool bar and price hint,
            and `pick_generic_species`'s odds below.
    """

    species_id: str
    display_name: str
    canopy_layer: str
    color: Color
    stage_seconds: float = 4.0
    seed_cost: int = 5
    base_price: int = 8
    repels_pests: bool = False
    spread_chance: float = 0.0
    is_weed: bool = False


SPECIES_TABLE: dict[str, Species] = {
    "guandu": Species(
        species_id="guandu",
        display_name="Guandu",
        canopy_layer="ground_cover",
        color=Verdant.SAGE_500,
        stage_seconds=3.0,
        seed_cost=5,
        base_price=8,
        spread_chance=0.03,
    ),
    "cagaita": Species(
        species_id="cagaita",
        display_name="Cagaita",
        canopy_layer="understory",
        color=Sand.C400,
        stage_seconds=4.5,
        seed_cost=10,
        base_price=16,
        spread_chance=0.02,
    ),
    "baru": Species(
        species_id="baru",
        display_name="Baru",
        canopy_layer="canopy",
        color=Verdant.COLONIAL_500,
        stage_seconds=6.0,
        seed_cost=15,
        base_price=24,
        spread_chance=0.008,
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
        spread_chance=0.008,
    ),
    WEED_SPECIES_ID: Species(
        species_id=WEED_SPECIES_ID,
        display_name="Weed",
        canopy_layer="ground_cover",
        color=Verdant.COLONIAL_700,
        stage_seconds=2.0,
        seed_cost=0,
        base_price=0,
        spread_chance=0.35,
        is_weed=True,
    ),
}


def sellable_species() -> list[Species]:
    """Every species a player can grow on purpose, in table order.

    Excludes the weed -- it never appears in a seed-buying UI, a price
    hint, or the biodiversity score's denominator.
    """
    return [species for species in SPECIES_TABLE.values() if not species.is_weed]


def pick_generic_species(rng: RandomStream) -> str:
    """Roll the species a generic seed grows into.

    Weighted towards cheap, common species (inversely by `seed_cost`) --
    a generic seed is what pulling a weed pays out, and should not be as
    reliable a way to a valuable canopy tree as paying for one outright.

    Args:
        rng: The stream to roll on.

    Returns:
        A `species_id` from `sellable_species()`.
    """
    candidates = sellable_species()
    weights = [1.0 / species.seed_cost for species in candidates]
    roll = rng.uniform(0.0, sum(weights))
    upto = 0.0
    for species, weight in zip(candidates, weights, strict=True):
        upto += weight
        if roll <= upto:
            return species.species_id
    return candidates[-1].species_id  # pragma: no cover -- float-rounding fallback
