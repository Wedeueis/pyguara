"""The icon dock: every icon exists and draws, slots price honestly, and the
screen's regions do not overlap."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest

from games.quintal_cerrado import layout
from games.quintal_cerrado.bootstrap import WINDOW_HEIGHT, WINDOW_WIDTH
from games.quintal_cerrado.components import (
    GENERIC_SEED_KEY,
    PlayerEconomy,
    specific_seed_key,
)
from games.quintal_cerrado.economy import COMPOST_COST, SPRAY_COST
from games.quintal_cerrado.hud import CellInspector
from games.quintal_cerrado.hud_widgets import GLOW, ToolDock, ToolSlot
from games.quintal_cerrado.icons import DIM_TARGET, ICONS, draw_icon
from games.quintal_cerrado.scenes import (
    _TOOL_KEYS,
    MENU_SLOT,
    STORE_SLOT,
    _dock_groups,
    slot_status,
)
from games.quintal_cerrado.species import SPECIES_TABLE
from games.quintal_cerrado.weather import WEATHER_TABLE
from pyguara.common.types import Color, Rect
from pyguara.graphics.protocols import UIRenderer

EXPECTED_ICONS = (
    set(_TOOL_KEYS)
    | {STORE_SLOT, MENU_SLOT}
    | set(WEATHER_TABLE)
    | {icon_id for _name, _key, icon_id, _color in CellInspector.METRICS}
    | {"seed", "seed_pouch", "leaf", "sun", "moon"}
)


def _renderer() -> Any:
    renderer = MagicMock(spec=UIRenderer)
    renderer.get_text_size.return_value = (20, 12)
    return renderer


def _colors_drawn(renderer: Any) -> list[Color]:
    colors = []
    for name in ("draw_rect", "draw_circle", "draw_line", "draw_polygon"):
        for call in getattr(renderer, name).call_args_list:
            colors.extend(arg for arg in call.args if isinstance(arg, Color))
    return colors


class TestIcons:
    """Every id the HUD asks for is in the registry, and draws something."""

    def test_every_id_the_hud_uses_has_an_icon(self) -> None:
        """A new tool or weather condition must not ship icon-less."""
        assert set(ICONS) >= EXPECTED_ICONS

    @pytest.mark.parametrize("icon_id", sorted(ICONS))
    def test_each_icon_draws_at_least_one_primitive(self, icon_id: str) -> None:
        renderer = _renderer()

        draw_icon(renderer, icon_id, Rect(0, 0, 40, 40))

        assert _colors_drawn(renderer)

    @pytest.mark.parametrize("icon_id", sorted(ICONS))
    def test_full_dim_fades_every_colour_into_the_card(self, icon_id: str) -> None:
        renderer = _renderer()

        draw_icon(renderer, icon_id, Rect(0, 0, 40, 40), dim=1.0)

        assert all(color == DIM_TARGET for color in _colors_drawn(renderer))

    def test_an_icon_stays_inside_its_rect(self) -> None:
        renderer = _renderer()
        rect = Rect(100, 200, 40, 40)

        draw_icon(renderer, "till", rect)

        for call in renderer.draw_polygon.call_args_list:
            for x, y in call.args[0]:
                assert rect.x - 2 <= x <= rect.right + 2
                assert rect.y - 2 <= y <= rect.bottom + 2

    def test_an_unknown_id_draws_nothing(self) -> None:
        renderer = _renderer()

        draw_icon(renderer, "no_such_icon", Rect(0, 0, 40, 40))

        assert not _colors_drawn(renderer)


class TestSlotStatus:
    """What a slot's badge promises matches what the click will charge."""

    def test_a_species_shows_its_price_and_is_affordable_with_enough(self) -> None:
        cost = SPECIES_TABLE["baru"].seed_cost

        assert slot_status("plant_baru", PlayerEconomy(credits=cost)) == (
            str(cost),
            True,
        )
        assert slot_status("plant_baru", PlayerEconomy(credits=cost - 1)) == (
            str(cost),
            False,
        )

    def test_stocked_seed_shows_the_stock_and_is_free(self) -> None:
        economy = PlayerEconomy(credits=0)
        economy.inventory[specific_seed_key("pequi")] = 2

        assert slot_status("plant_pequi", economy) == ("x2", True)

    def test_generic_depends_only_on_generic_stock(self) -> None:
        assert slot_status("plant_generic", PlayerEconomy(credits=999)) == (
            "x0",
            False,
        )
        economy = PlayerEconomy(credits=0)
        economy.inventory[GENERIC_SEED_KEY] = 3
        assert slot_status("plant_generic", economy) == ("x3", True)

    @pytest.mark.parametrize(
        ("tool", "cost"), [("compost", COMPOST_COST), ("spray", SPRAY_COST)]
    )
    def test_treatments_show_their_flat_cost(self, tool: str, cost: int) -> None:
        assert slot_status(tool, PlayerEconomy(credits=cost)) == (str(cost), True)
        assert slot_status(tool, PlayerEconomy(credits=cost - 1))[1] is False

    @pytest.mark.parametrize("tool", ["till", "water", "harvest"])
    def test_free_tools_have_no_badge(self, tool: str) -> None:
        assert slot_status(tool, PlayerEconomy(credits=0)) == ("", True)


class TestToolSlot:
    """The slot draws its states."""

    def test_an_active_slot_draws_the_glow_ring(self) -> None:
        slot = ToolSlot("till", "Enxada", "T")
        renderer = _renderer()

        slot.render(renderer)
        assert not any(
            call.args[1] == GLOW and call.kwargs.get("width") == 2
            for call in renderer.draw_rect.call_args_list
        )

        slot.active = True
        slot.render(renderer)
        assert any(
            call.args[1] == GLOW and call.kwargs.get("width") == 2
            for call in renderer.draw_rect.call_args_list
        )

    def test_an_unaffordable_slot_draws_its_label_dimmed(self) -> None:
        slot = ToolSlot("compost", "Adubo", "M")
        slot.affordable = False
        renderer = _renderer()

        slot.render(renderer)

        label_calls = [
            call
            for call in renderer.draw_text.call_args_list
            if call.args[0] == "Adubo"
        ]
        assert label_calls
        assert label_calls[0].args[2] != Color(253, 236, 190)


class TestLayout:
    """The screen's regions stay apart and on screen."""

    def _dock(self) -> ToolDock:
        return ToolDock(_dock_groups(), WINDOW_WIDTH)

    def test_the_dock_has_every_tool_plus_the_store_and_menu(self) -> None:
        assert set(self._dock().slots) == set(_TOOL_KEYS) | {STORE_SLOT, MENU_SLOT}

    def test_dock_groups_fit_on_screen_below_the_grid_without_overlap(self) -> None:
        groups = [group.rect for group in self._dock().groups]

        for rect in groups:
            assert rect.x >= 0 and rect.right <= WINDOW_WIDTH
            assert rect.y > layout.GRID_RECT.bottom
            assert rect.bottom <= WINDOW_HEIGHT
        for left, right in zip(groups, groups[1:], strict=False):
            assert left.right < right.x

    def test_every_slot_sits_inside_its_group(self) -> None:
        for group in self._dock().groups:
            for slot in group.children:
                assert group.rect.x <= slot.rect.x
                assert slot.rect.right <= group.rect.right
                assert group.rect.y <= slot.rect.y
                assert slot.rect.bottom <= group.rect.bottom

    def test_ribbon_cards_grid_and_column_do_not_overlap(self) -> None:
        cards = [layout.RESOURCE_CARD, layout.WEATHER_CARD, layout.RESILIENCE_CARD]
        for left, right in zip(cards, cards[1:], strict=False):
            assert left.right < right.x
        for card in cards:
            assert card.bottom < layout.GRID_RECT.y
            assert card.right <= WINDOW_WIDTH
        assert layout.GRID_RECT.right < layout.COLUMN_X
