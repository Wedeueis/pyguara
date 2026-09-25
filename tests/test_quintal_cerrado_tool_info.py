# ruff: noqa: F811  - pytest fixtures are imported by name from the growth suite
"""The tool card: what a slot is *for*, not just what it costs.

The dock can only say a price. The PRD's dilemma depends on the player
knowing what a spray trades away, and a new player has no way to guess
that Cagaita wants a canopy over it.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest

from games.quintal_cerrado.economy import ORGANIC_PREMIUM, SPRAY_COST
from games.quintal_cerrado.hud import ToolCard
from games.quintal_cerrado.icons import ICONS
from games.quintal_cerrado.scenes import GardenScene, _dock_groups
from games.quintal_cerrado.species import SPECIES_TABLE
from games.quintal_cerrado.tool_info import describe
from games.quintal_cerrado.turn import action_cost
from pyguara.common.types import Vector2
from pyguara.graphics.protocols import UIRenderer
from pyguara.ui.types import UIElementState
from tests.test_quintal_cerrado_growth import (  # noqa: F401
    game_container,
    scene,
)


def _renderer() -> Any:
    renderer = MagicMock(spec=UIRenderer)
    renderer.get_text_size.side_effect = lambda text, size: (
        len(text) * size // 2,
        size,
    )
    return renderer


def _slots() -> list[str]:
    return [spec.tool_id for group in _dock_groups() for spec in group.slots]


class TestEverySlotIsExplained:
    """A slot the card cannot describe is a slot nobody can learn."""

    @pytest.mark.parametrize("tool", _slots())
    def test_it_has_a_name_an_icon_and_something_to_say(self, tool: str) -> None:
        info = describe(tool)

        assert info is not None
        assert info.name
        assert info.icon_id in ICONS
        assert info.lines and all(info.lines)

    @pytest.mark.parametrize("tool", _slots())
    def test_its_stamina_matches_what_the_click_will_spend(self, tool: str) -> None:
        info = describe(tool)

        assert info is not None
        assert info.stamina == action_cost(tool)

    def test_an_unknown_tool_says_nothing_rather_than_raising(self) -> None:
        assert describe("teleport") is None
        assert describe("plant_dragonfruit") is None


class TestWhatItSays:
    """Generated from the tables, so it cannot drift from the numbers."""

    def test_a_species_names_its_layer_nights_and_price(self) -> None:
        info = describe("plant_baru")
        species = SPECIES_TABLE["baru"]

        assert info is not None
        body = " ".join(info.lines)
        assert "Alto" in body and "canopy" in body
        assert f"{species.stage_days * 3:.0f} nights" in body
        assert str(species.base_price) in body
        assert str(round(species.base_price * ORGANIC_PREMIUM)) in body
        assert info.price == str(species.seed_cost)

    def test_the_understory_bonus_is_only_claimed_where_it_applies(self) -> None:
        cagaita = " ".join(describe("plant_cagaita").lines)  # type: ignore[union-attr]
        baru = " ".join(describe("plant_baru").lines)  # type: ignore[union-attr]

        assert "under a grown canopy" in cagaita
        assert "under a grown canopy" not in baru

    def test_only_pequi_claims_to_repel_pests(self) -> None:
        for species_id, species in SPECIES_TABLE.items():
            if species.is_weed:
                continue
            info = describe(f"plant_{species_id}")
            assert info is not None
            claims = "suppresses pests" in " ".join(info.lines)
            assert claims == species.repels_pests

    def test_the_spray_names_what_it_trades_away(self) -> None:
        """The dilemma only works if the cost is stated before the click."""
        info = describe("spray")

        assert info is not None
        body = " ".join(info.lines)
        assert "degrades the soil" in body
        assert "half price" in body
        assert info.price == str(SPRAY_COST)


class TestTheCard:
    """It follows the cursor, and never goes blank."""

    def test_it_explains_the_hovered_slot(self, scene: GardenScene) -> None:
        scene._set_active_tool("till")
        scene._dock_slots["spray"].state = UIElementState.HOVERED

        scene.update(1 / 60)

        assert scene._hud is not None
        assert scene._hud.tools.tool == "spray"

    def test_it_falls_back_to_the_active_tool(self, scene: GardenScene) -> None:
        """Off the dock, the useful thing is what the next click will do."""
        scene._set_active_tool("compost")

        scene.update(1 / 60)

        assert scene._hud is not None
        assert scene._hud.tools.tool == "compost"

    def test_it_wraps_its_body_inside_the_card(self, scene: GardenScene) -> None:
        card = ToolCard(360)
        card.show("spray")
        renderer = _renderer()

        card.render(renderer)

        drawn = [
            call
            for call in renderer.draw_text.call_args_list
            if isinstance(call.args[1], Vector2)
        ]
        assert len(drawn) > 2, "the body wrapped onto several lines"
        for call in drawn:
            assert call.args[1].y < card.rect.bottom

    def test_an_undescribed_tool_draws_only_the_card(self) -> None:
        card = ToolCard(360)
        card.show("teleport")
        renderer = _renderer()

        card.render(renderer)

        assert renderer.draw_rect.called
        assert not renderer.draw_text.called
