"""The Cerrado upgrade table: what a level buys, and what it says.

`kits/progression` deliberately knows nothing about what an upgrade
*does* -- `Upgrade.apply` is an opaque callable -- and nothing about what
it is called, because names and blurbs are content. Both live here.

**Flat, not a synergy graph.** Seven upgrades, each a single stat step,
two of them thematic enough that the clearing's flavour survives. A
synergy table would be a second data structure proving nothing the first
does not, and it doubles the balance surface for a four-minute run.
Weapon evolution needs no new type either -- `Upgrade.requires` plus
`UpgradeRecord.taken` already expresses it -- but this demo has one
weapon, so nothing here uses it.

Every `apply` is a closure over the scene's own components. That is the
whole point of the kit's opaque callable: this module imports no kit
except `progression` itself, and the kit imports nothing of this.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from games.tamandua_murundus.components import Murundu, Tamandua
from pyguara.ecs.manager import EntityManager
from pyguara.kits.progression import Magnet, Upgrade


@dataclass(frozen=True)
class Card:
    """One upgrade, plus the words the player reads.

    The split is deliberate: `upgrade` is what `kits/progression` offers
    and records, `title` and `blurb` are content the kit never sees.

    Attributes:
        upgrade: The kit's upgrade, carrying the key and the closure.
        title: Short name, shown large.
        blurb: One line saying what it does, in plain terms.
    """

    upgrade: Upgrade
    title: str
    blurb: str


def _each_tamandua(
    entity_manager: EntityManager, change: Callable[[Tamandua], None]
) -> Callable[[str], None]:
    """Build an `apply` that mutates the taking entity's `Tamandua`.

    Takes the entity id the kit passes, rather than capturing an entity,
    so an upgrade applied to a rebuilt player still lands on the live one.
    """

    def apply(entity_id: str) -> None:
        entity = entity_manager.get_entity(entity_id)
        if entity is not None and entity.has_component(Tamandua):
            change(entity.get_component(Tamandua))

    return apply


def _each_magnet(
    entity_manager: EntityManager, change: Callable[[Magnet], None]
) -> Callable[[str], None]:
    """Build an `apply` that mutates the taking entity's `Magnet`."""

    def apply(entity_id: str) -> None:
        entity = entity_manager.get_entity(entity_id)
        if entity is not None and entity.has_component(Magnet):
            change(entity.get_component(Magnet))

    return apply


def _slow_the_mounds(entity_manager: EntityManager) -> Callable[[str], None]:
    """Build an `apply` that lengthens every mound's feed interval.

    The one upgrade that reaches past the player: it does not make the
    anteater better, it makes the night quieter. Worth having in the table
    so not every pick is the same shape.
    """

    def apply(entity_id: str) -> None:
        for entity in entity_manager.get_entities_with(Murundu):
            entity.get_component(Murundu).feed_interval *= 1.18

    return apply


def build_pool(entity_manager: EntityManager) -> list[Card]:
    """The run's whole upgrade table.

    Built against a live `EntityManager` rather than declared as module
    data, because every `apply` is a closure over the world it changes.

    Args:
        entity_manager: The scene's world.

    Returns:
        Seven cards, in no particular order -- `offer()` weights the draw.
    """
    return [
        Card(
            Upgrade(
                key="lingua_longa",
                apply=_each_tamandua(
                    entity_manager,
                    lambda hunter: setattr(
                        hunter, "tongue_range", hunter.tongue_range * 1.22
                    ),
                ),
                max_taken=3,
                weight=1.2,
            ),
            "LÍNGUA LONGA",
            "a língua alcança mais longe",
        ),
        Card(
            Upgrade(
                key="lingua_rapida",
                apply=_each_tamandua(
                    entity_manager,
                    lambda hunter: setattr(
                        hunter, "tongue_interval", hunter.tongue_interval * 0.86
                    ),
                ),
                max_taken=3,
                weight=1.2,
            ),
            "LÍNGUA RÁPIDA",
            "a língua ataca com mais frequência",
        ),
        Card(
            Upgrade(
                key="arco_amplo",
                apply=_each_tamandua(
                    entity_manager,
                    lambda hunter: setattr(
                        hunter, "tongue_arc", min(hunter.tongue_arc * 1.2, 3.0)
                    ),
                ),
                max_taken=2,
            ),
            "ARCO AMPLO",
            "a língua varre um arco mais largo",
        ),
        Card(
            Upgrade(
                key="patas_ligeiras",
                apply=_each_tamandua(
                    entity_manager,
                    lambda hunter: setattr(hunter, "speed", hunter.speed * 1.14),
                ),
                max_taken=3,
            ),
            "PATAS LIGEIRAS",
            "o guardião anda mais rápido",
        ),
        Card(
            Upgrade(
                key="ima_forte",
                apply=_each_magnet(
                    entity_manager,
                    lambda magnet: setattr(magnet, "radius", magnet.radius * 1.3),
                ),
                max_taken=3,
            ),
            "ÍMÃ FORTE",
            "as centelhas vêm de mais longe",
        ),
        Card(
            Upgrade(
                key="cupim_doce",
                apply=_each_magnet(
                    entity_manager,
                    lambda magnet: setattr(magnet, "speed", magnet.speed * 1.5),
                ),
                max_taken=2,
            ),
            "CUPIM DOCE",
            "as centelhas correm para você",
        ),
        Card(
            Upgrade(
                key="murundu_manso",
                apply=_slow_the_mounds(entity_manager),
                max_taken=2,
                weight=0.7,
            ),
            "MURUNDU MANSO",
            "os murundus soltam mais devagar",
        ),
    ]
