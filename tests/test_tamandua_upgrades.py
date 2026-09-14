"""Tests for the 1-of-3 pick: the table, the layout, and the ring.

The demo runs on ModernGL and cannot boot headlessly, and its cards draw
on the finished frame rather than through `UIRenderer` -- so neither half
can be looked at by an automated check. These test the rules instead: what
the table contains, where the cards land, and that the focus ring drives
the selection.
"""

from __future__ import annotations

import pytest

from games.tamandua_murundus.components import Murundu, Tamandua
from games.tamandua_murundus.upgrade_ui import (
    CARD_HEIGHT,
    CARD_WIDTH,
    CardElement,
    card_views,
    layout_cards,
)
from games.tamandua_murundus.upgrades import build_pool
from pyguara.common.components import Transform
from pyguara.common.random import RandomStream
from pyguara.common.types import Vector2
from pyguara.ecs.manager import EntityManager
from pyguara.events.dispatcher import EventDispatcher
from pyguara.kits.progression import Magnet, UpgradeRecord, offer, take
from pyguara.ui.manager import UIManager

WIDTH, HEIGHT = 960, 720


def world() -> tuple[EntityManager, str]:
    """A world holding one anteater and five mounds."""
    entity_manager = EntityManager()
    hero = entity_manager.create_entity()
    hero.add_component(Transform(position=Vector2(480, 380)))
    hero.add_component(Tamandua())
    hero.add_component(Magnet())
    for index in range(5):
        mound = entity_manager.create_entity()
        mound.add_component(Transform(position=Vector2(100 + index * 150, 200)))
        mound.add_component(Murundu())
    return entity_manager, hero.id


class TestTheTable:
    def test_the_table_is_six_to_eight_cards(self) -> None:
        """The size the level curve was tuned against: a run reaches about
        eight levels, and should offer about as many distinct picks."""
        entity_manager, _ = world()

        assert 6 <= len(build_pool(entity_manager)) <= 8

    def test_every_key_is_unique(self) -> None:
        """`UpgradeRecord` counts by key -- a duplicate would make two
        cards share a take count and a max."""
        entity_manager, _ = world()
        keys = [card.upgrade.key for card in build_pool(entity_manager)]

        assert len(set(keys)) == len(keys)

    def test_every_card_has_words(self) -> None:
        entity_manager, _ = world()

        for card in build_pool(entity_manager):
            assert card.title.strip()
            assert card.blurb.strip()

    def test_every_card_is_bounded(self) -> None:
        """An unlimited upgrade in a seven-card table would crowd out the
        rest of the offers for the whole back half of a run."""
        entity_manager, _ = world()

        for card in build_pool(entity_manager):
            assert card.upgrade.max_taken is not None
            assert card.upgrade.max_taken >= 1


class TestApplying:
    def test_a_tongue_upgrade_changes_the_tongue(self) -> None:
        entity_manager, hero_id = world()
        card = next(
            c for c in build_pool(entity_manager) if c.upgrade.key == "lingua_longa"
        )
        hunter = entity_manager.get_entity(hero_id).get_component(Tamandua)
        before = hunter.tongue_range

        take(UpgradeRecord(), card.upgrade, hero_id)

        assert hunter.tongue_range > before

    def test_a_magnet_upgrade_changes_the_magnet(self) -> None:
        entity_manager, hero_id = world()
        card = next(
            c for c in build_pool(entity_manager) if c.upgrade.key == "ima_forte"
        )
        magnet = entity_manager.get_entity(hero_id).get_component(Magnet)
        before = magnet.radius

        take(UpgradeRecord(), card.upgrade, hero_id)

        assert magnet.radius > before

    def test_the_mound_upgrade_reaches_past_the_player(self) -> None:
        """The one card that changes the night rather than the anteater,
        so not every pick is the same shape."""
        entity_manager, hero_id = world()
        card = next(
            c for c in build_pool(entity_manager) if c.upgrade.key == "murundu_manso"
        )
        intervals = [
            entity.get_component(Murundu).feed_interval
            for entity in entity_manager.get_entities_with(Murundu)
        ]

        take(UpgradeRecord(), card.upgrade, hero_id)

        after = [
            entity.get_component(Murundu).feed_interval
            for entity in entity_manager.get_entities_with(Murundu)
        ]
        assert all(
            later > before for before, later in zip(intervals, after, strict=True)
        )

    def test_stacking_compounds(self) -> None:
        entity_manager, hero_id = world()
        card = next(
            c for c in build_pool(entity_manager) if c.upgrade.key == "lingua_rapida"
        )
        hunter = entity_manager.get_entity(hero_id).get_component(Tamandua)
        record = UpgradeRecord()

        take(record, card.upgrade, hero_id)
        once = hunter.tongue_interval
        take(record, card.upgrade, hero_id)

        assert hunter.tongue_interval < once

    def test_applying_to_a_missing_entity_is_ignored(self) -> None:
        """`apply` takes an id, not an entity, so a player rebuilt between
        the offer and the take must not raise here."""
        entity_manager, _ = world()
        card = build_pool(entity_manager)[0]

        take(UpgradeRecord(), card.upgrade, "no-such-entity")


class TestOfferingFromTheTable:
    def test_an_offer_draws_three_distinct_cards(self) -> None:
        entity_manager, _ = world()
        pool = [card.upgrade for card in build_pool(entity_manager)]

        drawn = offer(RandomStream(seed=4), pool, UpgradeRecord(), count=3)

        assert len(drawn) == 3
        assert len({upgrade.key for upgrade in drawn}) == 3

    def test_an_exhausted_card_stops_being_offered(self) -> None:
        entity_manager, _ = world()
        pool = [card.upgrade for card in build_pool(entity_manager)]
        record = UpgradeRecord(taken={"arco_amplo": 2})

        for seed in range(12):
            drawn = offer(RandomStream(seed=seed), pool, record, count=3)
            assert "arco_amplo" not in {upgrade.key for upgrade in drawn}


class TestCardLayout:
    def test_three_cards_are_centred_as_a_row(self) -> None:
        entity_manager, _ = world()
        cards = build_pool(entity_manager)[:3]

        positions = layout_cards(cards, WIDTH, HEIGHT)

        span = positions[-1].x + CARD_WIDTH - positions[0].x
        assert positions[0].x == pytest.approx((WIDTH - span) / 2)
        assert len({position.y for position in positions}) == 1

    def test_cards_do_not_overlap(self) -> None:
        entity_manager, _ = world()
        cards = build_pool(entity_manager)[:3]

        positions = layout_cards(cards, WIDTH, HEIGHT)

        for left, right in zip(positions, positions[1:], strict=False):
            assert right.x >= left.x + CARD_WIDTH

    def test_a_short_offer_still_centres(self) -> None:
        """Late in a run the pool runs down and two cards are offered."""
        entity_manager, _ = world()
        cards = build_pool(entity_manager)[:2]

        positions = layout_cards(cards, WIDTH, HEIGHT)

        span = positions[-1].x + CARD_WIDTH - positions[0].x
        assert positions[0].x == pytest.approx((WIDTH - span) / 2)

    def test_no_cards_lays_out_nothing(self) -> None:
        assert layout_cards([], WIDTH, HEIGHT) == []

    def test_the_row_fits_on_screen(self) -> None:
        entity_manager, _ = world()
        cards = build_pool(entity_manager)[:3]

        positions = layout_cards(cards, WIDTH, HEIGHT)

        assert positions[0].x >= 0
        assert positions[-1].x + CARD_WIDTH <= WIDTH
        assert positions[0].y + CARD_HEIGHT <= HEIGHT


class TestTheFocusRing:
    """E8's focus ring driving a real menu, which is what it was for."""

    def elements(self) -> tuple[UIManager, list[CardElement]]:
        """A manager holding three cards, the first focused."""
        entity_manager, _ = world()
        cards = build_pool(entity_manager)[:3]
        manager = UIManager(EventDispatcher())
        elements = [
            CardElement(card, position)
            for card, position in zip(
                cards, layout_cards(cards, WIDTH, HEIGHT), strict=True
            )
        ]
        for element in elements:
            manager.add_element(element)
        manager.set_focus(elements[0])
        return manager, elements

    def test_every_card_is_in_the_ring(self) -> None:
        manager, elements = self.elements()

        assert manager.focus_ring() == elements

    def test_the_ring_traverses_in_layout_order(self) -> None:
        """Left to right, which is how the row reads."""
        manager, elements = self.elements()

        assert manager.focus_next() is elements[1]
        assert manager.focus_next() is elements[2]

    def test_the_ring_wraps(self) -> None:
        manager, elements = self.elements()
        manager.set_focus(elements[2])

        assert manager.focus_next() is elements[0]

    def test_focus_moves_backwards_too(self) -> None:
        manager, elements = self.elements()

        assert manager.focus_previous() is elements[2]

    def test_a_card_knows_which_upgrade_it_offers(self) -> None:
        """What `_take_card()` reads off the focused element."""
        manager, elements = self.elements()

        focused = manager.focused_element

        assert isinstance(focused, CardElement)
        assert focused.card.upgrade.key


class TestCardViews:
    def test_only_the_focused_card_is_marked(self) -> None:
        entity_manager, _ = world()
        cards = build_pool(entity_manager)[:3]
        elements = [
            CardElement(card, position)
            for card, position in zip(
                cards, layout_cards(cards, WIDTH, HEIGHT), strict=True
            )
        ]

        views = card_views(elements, elements[1])

        assert [view.focused for view in views] == [False, True, False]

    def test_a_view_carries_what_the_scene_draws(self) -> None:
        """Plain values, so the drawing takes no `UIElement` and no
        `UIManager` -- which is what lets the layout be tested at all."""
        entity_manager, _ = world()
        cards = build_pool(entity_manager)[:1]
        element = CardElement(cards[0], layout_cards(cards, WIDTH, HEIGHT)[0])

        view = card_views([element], None)[0]

        assert view.title == cards[0].title
        assert view.blurb == cards[0].blurb
        assert view.card_key == cards[0].upgrade.key
        assert view.bounds.width == CARD_WIDTH
