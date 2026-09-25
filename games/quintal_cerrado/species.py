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

Each crop also names the season it belongs to (`seasons.py`), following
roughly when it actually fruits in the Cerrado: baru and cagaita in the
dry months, pequi and guandu with the rains. Harvesting in season pays
more, which is what makes the calendar worth planting around.
"""

from __future__ import annotations

from dataclasses import dataclass

from games.quintal_cerrado.seasons import DRY, WET
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
        stage_days: Days `systems/plant_growth_system.py` needs, at a
            growth multiplier of 1.0, to fill one stage's growth budget.
            Demo-paced, not realistic -- a canopy tree taking real years
            to mature would leave a twelve-day session with nothing to show
            for it. Guandu takes a day a stage and baru two, so a crop is
            three to six nights of commitment.
        seed_cost: Sementes (the game's currency) one seed costs. Meaningless
            for a weed, which is never bought.
        base_price: Sementes a harvested plant sells for at the normal
            market rate, before `economy.py`'s organic premium or chemical
            discount is applied. Meaningless for a weed, which pulling
            pays out in generic seed stock instead of Sementes (see
            `economy.harvest_cell`).
        fixes_nitrogen: Whether this plant puts nitrogen back into its own
            cell and its neighbours as it grows -- what makes a legume
            worth interplanting rather than just growing on its own.
        lifts_potassium: Whether its roots bring potassium up to the
            surface, which is what a deep canopy tree does for everything
            under it.
        leaves_calcium: Whether a grown one leaves calcium in the soil.
        appetite: How heavily it feeds on nitrogen and phosphorus while it
            grows, relative to a ground-cover plant.
        season: The `seasons.Season` key this crop belongs to, or None for
            one that does not care. Harvesting it in its own season pays
            `seasons.IN_SEASON_PREMIUM` -- the reason to plan what goes in
            the ground around the calendar rather than around what is
            cheapest today.
        repels_pests: Whether a grown plant of this species suppresses
            pest pressure on and around its own cell -- the PRD's "pest
            resistance via flora".
        spread_chance: Chance, each night `systems/weed_spread_system.py`
            rolls, that a mature-or-later plant of this species seeds a free
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
    stage_days: float = 1.5
    seed_cost: int = 5
    base_price: int = 8
    repels_pests: bool = False
    spread_chance: float = 0.0
    is_weed: bool = False
    fixes_nitrogen: bool = False
    lifts_potassium: bool = False
    leaves_calcium: bool = False
    appetite: float = 1.0
    season: str | None = None


SPECIES_TABLE: dict[str, Species] = {
    "guandu": Species(
        species_id="guandu",
        display_name="Guandu",
        canopy_layer="ground_cover",
        color=Verdant.SAGE_500,
        stage_days=1.0,
        seed_cost=5,
        base_price=10,
        spread_chance=0.03,
        fixes_nitrogen=True,
        season=WET,
    ),
    "cagaita": Species(
        species_id="cagaita",
        display_name="Cagaita",
        canopy_layer="understory",
        color=Sand.C400,
        stage_days=1.5,
        seed_cost=10,
        base_price=20,
        spread_chance=0.02,
        appetite=1.3,
        season=DRY,
    ),
    "baru": Species(
        species_id="baru",
        display_name="Baru",
        canopy_layer="canopy",
        color=Verdant.COLONIAL_500,
        stage_days=2.0,
        seed_cost=15,
        base_price=30,
        spread_chance=0.008,
        lifts_potassium=True,
        appetite=1.6,
        season=DRY,
    ),
    "pequi": Species(
        species_id="pequi",
        display_name="Pequi",
        canopy_layer="canopy",
        color=Guara.C500,
        stage_days=1.7,
        seed_cost=12,
        base_price=26,
        repels_pests=True,
        spread_chance=0.008,
        leaves_calcium=True,
        appetite=1.4,
        season=WET,
    ),
    WEED_SPECIES_ID: Species(
        species_id=WEED_SPECIES_ID,
        display_name="Weed",
        canopy_layer="ground_cover",
        color=Verdant.COLONIAL_700,
        stage_days=0.7,
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
