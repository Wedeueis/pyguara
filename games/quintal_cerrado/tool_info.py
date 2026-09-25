"""What each tool and seed actually does, for the HUD to explain.

The dock says what something costs; it cannot say what it is for. A player
who has never met syntropic agriculture has no way to guess that compost
sheds pest pressure, that a spray halves what the crop sells for, or that
Cagaita wants a canopy over it -- and the PRD's whole dilemma depends on
knowing the trade.

Species lines are generated from `SPECIES_TABLE` rather than written out,
so a new species cannot ship with a description that quietly contradicts
its own numbers.
"""

from __future__ import annotations

from dataclasses import dataclass

from games.quintal_cerrado.economy import COMPOST_COST, ORGANIC_PREMIUM, SPRAY_COST
from games.quintal_cerrado.species import SPECIES_TABLE
from games.quintal_cerrado.structures import STRUCTURE_TABLE
from games.quintal_cerrado.turn import SESSION_DAYS, action_cost

LAYER_NAMES = {
    "canopy": "Alto (canopy)",
    "understory": "Médio (understory)",
    "ground_cover": "Baixo (ground cover)",
}
"""The syntropic ladder's rungs as the cell inspector labels them, each
with what it means -- the ladder word alone tells a new player nothing."""


@dataclass(frozen=True)
class ToolInfo:
    """One dock slot explained.

    Attributes:
        name: What the dock calls it.
        icon_id: The `icons.ICONS` key, so the card can lead with it.
        lines: The description, already split into sentences. The card
            wraps them to its own width.
        stamina: What one use costs.
        price: Sementes it costs, or "" when it is free.
    """

    name: str
    icon_id: str
    lines: tuple[str, ...]
    stamina: int
    price: str = ""


_TOOL_LINES = {
    "till": ("Breaks raw ground into a bed.", "Only raw dirt can be tilled."),
    "water": (
        "Raises a cell's moisture.",
        "Growth stalls on dry ground, and a watering lasts about two days.",
    ),
    "harvest": (
        "Collects a ready crop, or clears a plant the pests killed.",
        "The cell stays tilled either way.",
    ),
    "compost": (
        "Feeds the soil on a tilled cell.",
        "Organic matter sheds pest pressure overnight and is most of the "
        "soil-health score.",
    ),
    "spray": (
        "Clears pests at once and grows the crop faster.",
        "It degrades the soil and marks every plant it touches: those sell "
        "at half price for good.",
    ),
    "store": (
        "Buys the automation tree -- panel, drip, sensor, drone.",
        "Each rung unlocks the next by being placed.",
    ),
    "menu": ("Pause, save, see the score, or quit to the title.",),
}


def describe(tool: str) -> ToolInfo | None:
    """Explain `tool`, or None if there is nothing to say about it.

    Args:
        tool: A tool id as `scenes.GardenScene` knows it.

    Returns:
        The card's contents, or None for an unknown tool.
    """
    if tool == "sleep":
        return ToolInfo(
            name="Dormir",
            icon_id="sleep",
            lines=(
                "Ends the day. Everything happens at once while you sleep: "
                "plants grow, soil dries, pests spread and the sky turns.",
                f"The garden is scored after day {SESSION_DAYS}.",
            ),
            stamina=0,
        )
    if tool.startswith("plant_"):
        return _describe_seed(tool)
    if tool.startswith("build_"):
        return _describe_structure(tool)
    lines = _TOOL_LINES.get(tool)
    if lines is None:
        return None
    return ToolInfo(
        name=_NAMES[tool],
        icon_id=tool,
        lines=lines,
        stamina=action_cost(tool),
        price=_tool_price(tool),
    )


_NAMES = {
    "till": "Enxada",
    "water": "Regador",
    "harvest": "Colher",
    "compost": "Adubo",
    "spray": "Calda",
    "store": "Loja",
    "menu": "Menu",
}


def _tool_price(tool: str) -> str:
    if tool == "compost":
        return str(COMPOST_COST)
    if tool == "spray":
        return str(SPRAY_COST)
    return ""


def _describe_seed(tool: str) -> ToolInfo | None:
    """A species, described from its own row of `SPECIES_TABLE`."""
    if tool == "plant_generic":
        return ToolInfo(
            name="Genérica",
            icon_id=tool,
            lines=(
                "A seed saved from a pulled weed or an overripe crop.",
                "It sows a common species, picked when it goes in the ground.",
            ),
            stamina=action_cost(tool),
        )
    species = SPECIES_TABLE.get(tool.removeprefix("plant_"))
    if species is None:
        return None
    nights = species.stage_days * 3
    lines = [
        f"{LAYER_NAMES.get(species.canopy_layer, '?')}. "
        f"About {nights:.0f} nights to a harvest.",
        f"Sells for {species.base_price}, or "
        f"{round(species.base_price * ORGANIC_PREMIUM)} if it was never sprayed.",
    ]
    if species.canopy_layer == "understory":
        lines.append("Grows 40% faster in the shade of a grown canopy tree.")
    elif species.canopy_layer == "ground_cover":
        lines.append("Grows 40% faster beside a plant of any other layer.")
    if species.repels_pests:
        lines.append("A grown one suppresses pests on and around its cell.")
    return ToolInfo(
        name=species.display_name,
        icon_id=tool,
        lines=tuple(lines),
        stamina=action_cost(tool),
        price=str(species.seed_cost),
    )


def _describe_structure(tool: str) -> ToolInfo | None:
    """A structure waiting to be placed."""
    structure = STRUCTURE_TABLE.get(tool.removeprefix("build_"))
    if structure is None:
        return None
    return ToolInfo(
        name=structure.display_name,
        icon_id="store",
        lines=(
            "Bought and waiting. Click a free cell to place it.",
            "It does its work overnight, like everything else.",
        ),
        stamina=action_cost(tool),
    )
