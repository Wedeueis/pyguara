"""The automation tech tree: the store, placing structures, and what they do.

Reuses `tests/test_quintal_cerrado_growth.py`'s container and scene fixtures
rather than a third copy -- same mocked container, no real window.
"""
# ruff: noqa: F811  (fixtures imported from the growth tests are used by name)

from __future__ import annotations

import pytest

from games.quintal_cerrado import structures
from games.quintal_cerrado.components import AutomationComponent, PlantComponent
from games.quintal_cerrado.events import PlantHarvestedEvent, SolarIncomeEvent
from games.quintal_cerrado.scenes import GardenScene
from games.quintal_cerrado.store import StoreOverlayScene
from games.quintal_cerrado.systems import automation_system as auto
from games.quintal_cerrado.systems.automation_system import (
    DRIP_TARGET,
    DRONE_HARVESTS_PER_NIGHT,
    SOLAR_YIELD,
)
from games.quintal_cerrado.systems.day_resolver import SUB_STEP
from pyguara.events.dispatcher import EventDispatcher
from pyguara.events.input import KeyDownEvent
from pyguara.input.keys import ESCAPE, KEY_O
from pyguara.input.manager import InputManager
from pyguara.scene.manager import SceneManager
from pyguara.ui.manager import UIManager
from pyguara.ui.types import UILayer
from tests.test_quintal_cerrado_growth import (  # noqa: F401
    FIXED_DT,
    _force_stage,
    _nights,
    _plant_at,
    _resolve,
    game_container,
    scene,
)


def _machines(scene: GardenScene) -> None:
    """Run one night of the machines: power, solar, drip and the drone.

    They act once a night now, not on interval timers, so a test asks for
    a night's worth rather than a number of seconds.
    """
    assert scene._resolver is not None
    scene._resolver.automation.resolve_night()
    scene.entity_manager.flush_pending_removals()


def _place(scene: GardenScene, kind: str, cell: tuple[int, int]) -> AutomationComponent:
    """Buy and place `kind`, bypassing the tech-tree lock (tested apart)."""
    scene.economy.inventory[kind] = scene.economy.inventory.get(kind, 0) + 1
    assert (
        structures.place_structure(
            scene.grid, scene.entity_manager, scene.economy, kind, cell
        )
        == structures.OK
    )
    entity = scene.entity_manager.get_entity(scene.grid.automation_at[cell])
    return entity.get_component(AutomationComponent)


class TestTheTechTree:
    def test_only_the_root_is_available_at_the_start(self, scene: GardenScene) -> None:
        unlocked = [
            kind
            for kind in structures.STRUCTURE_TABLE
            if structures.is_unlocked(scene.economy, kind)
        ]

        assert unlocked == ["solar_panel"]

    def test_buying_a_locked_structure_is_refused_and_free(
        self, scene: GardenScene
    ) -> None:
        credits = scene.economy.credits

        result = structures.buy_structure(scene.economy, "drip_irrigation")

        assert result == structures.LOCKED
        assert scene.economy.credits == credits
        assert scene.economy.inventory == {}

    def test_buying_charges_and_stocks_the_inventory(self, scene: GardenScene) -> None:
        credits = scene.economy.credits

        result = structures.buy_structure(scene.economy, "solar_panel")

        assert result == structures.OK
        assert (
            scene.economy.credits
            == credits - structures.STRUCTURE_TABLE["solar_panel"].cost
        )
        assert scene.economy.inventory["solar_panel"] == 1

    def test_buying_needs_the_money(self, scene: GardenScene) -> None:
        scene.economy.credits = 1

        assert (
            structures.buy_structure(scene.economy, "solar_panel") == structures.BROKE
        )
        assert scene.economy.inventory == {}

    def test_placing_a_kind_unlocks_the_next_one(self, scene: GardenScene) -> None:
        _place(scene, "solar_panel", (0, 0))

        assert structures.is_unlocked(scene.economy, "drip_irrigation")
        assert not structures.is_unlocked(scene.economy, "soil_sensor")

    def test_the_whole_chain_can_be_climbed(self, scene: GardenScene) -> None:
        scene.economy.credits = 10_000
        for index, kind in enumerate(structures.STRUCTURE_TABLE):
            assert structures.buy_structure(scene.economy, kind) == structures.OK
            structures.place_structure(
                scene.grid, scene.entity_manager, scene.economy, kind, (index, 0)
            )

        assert scene.economy.unlocked_tech == set(structures.STRUCTURE_TABLE)


class TestPlacing:
    def test_placing_consumes_the_stock_and_occupies_the_cell(
        self, scene: GardenScene
    ) -> None:
        structures.buy_structure(scene.economy, "solar_panel")

        result = structures.place_structure(
            scene.grid, scene.entity_manager, scene.economy, "solar_panel", (3, 3)
        )

        assert result == structures.OK
        assert scene.economy.inventory["solar_panel"] == 0
        assert (3, 3) in scene.grid.automation_at
        assert scene.grid.tilemap.layers["automation"].get_tile((3, 3)) != 0

    def test_placing_with_nothing_in_stock_does_nothing(
        self, scene: GardenScene
    ) -> None:
        result = structures.place_structure(
            scene.grid, scene.entity_manager, scene.economy, "solar_panel", (3, 3)
        )

        assert result == structures.NOTHING
        assert (3, 3) not in scene.grid.automation_at

    def test_a_structure_cannot_go_on_a_plant_or_another_structure(
        self, scene: GardenScene
    ) -> None:
        _plant_at(scene, (2, 2), "guandu")
        _place(scene, "solar_panel", (5, 5))
        scene.economy.inventory["solar_panel"] = 2

        for cell in ((2, 2), (5, 5), (-1, 0)):
            assert (
                structures.place_structure(
                    scene.grid, scene.entity_manager, scene.economy, "solar_panel", cell
                )
                == structures.NOTHING
            )
        assert scene.economy.inventory["solar_panel"] == 2

    def test_a_structure_needs_no_tilled_soil(self, scene: GardenScene) -> None:
        assert scene.grid.soil_at((7, 7)).soil_type == "raw_dirt"

        _place(scene, "solar_panel", (7, 7))

        assert (7, 7) in scene.grid.automation_at

    def test_nothing_can_be_planted_under_a_structure(self, scene: GardenScene) -> None:
        scene.grid.till((4, 4))
        _place(scene, "solar_panel", (4, 4))

        assert not scene.grid.can_plant((4, 4))

    def test_the_build_tool_drops_itself_when_the_stock_runs_out(
        self, scene: GardenScene
    ) -> None:
        structures.buy_structure(scene.economy, "solar_panel")
        scene._on_structure_bought("solar_panel")
        assert scene._active_tool == "build_solar_panel"

        scene._on_cell_clicked((1, 1))

        assert (1, 1) in scene.grid.automation_at
        assert scene._active_tool == "till"


class TestPower:
    def test_a_panel_runs_three_devices_and_the_fourth_goes_dark(
        self, scene: GardenScene
    ) -> None:
        _place(scene, "solar_panel", (0, 0))
        devices = [
            _place(scene, "drip_irrigation", (2, 0)),
            _place(scene, "drip_irrigation", (4, 0)),
            _place(scene, "drip_irrigation", (6, 0)),
            _place(scene, "drip_irrigation", (8, 0)),
        ]

        _machines(scene)

        assert [d.powered for d in devices] == [True, True, True, False]

    def test_a_second_panel_powers_the_rest(self, scene: GardenScene) -> None:
        _place(scene, "solar_panel", (0, 0))
        devices = [_place(scene, "drip_irrigation", (2 + i * 2, 0)) for i in range(4)]
        _place(scene, "solar_panel", (0, 2))

        _machines(scene)

        assert all(d.powered for d in devices)

    def test_a_device_with_no_panel_is_unpowered(self, scene: GardenScene) -> None:
        drip = _place(scene, "drip_irrigation", (2, 2))

        _machines(scene)

        assert not drip.powered

    def test_a_sensor_needs_no_power(self, scene: GardenScene) -> None:
        sensor = _place(scene, "soil_sensor", (2, 2))

        _machines(scene)

        assert sensor.powered


class TestSolar:
    def test_a_panel_pays_once_a_night(self, scene: GardenScene) -> None:
        _place(scene, "solar_panel", (0, 0))
        credits = scene.economy.credits

        _machines(scene)

        assert scene.economy.credits == credits + SOLAR_YIELD

    def test_nothing_is_paid_for_time_passing(self, scene: GardenScene) -> None:
        """A panel earns a night's work, not a frame's."""
        _place(scene, "solar_panel", (0, 0))
        credits = scene.economy.credits

        for _ in range(600):
            scene.update(1 / 60)

        assert scene.economy.credits == credits

    def test_a_payout_is_announced(self, scene: GardenScene) -> None:
        paid: list[SolarIncomeEvent] = []
        scene.event_dispatcher.subscribe(SolarIncomeEvent, paid.append)
        _place(scene, "solar_panel", (3, 4))

        _machines(scene)

        assert len(paid) == 1
        assert paid[0].cell == (3, 4)
        assert paid[0].amount == SOLAR_YIELD

    def test_two_panels_earn_twice_as_much(self, scene: GardenScene) -> None:
        _place(scene, "solar_panel", (0, 0))
        _place(scene, "solar_panel", (2, 0))
        credits = scene.economy.credits

        _machines(scene)

        assert scene.economy.credits == credits + 2 * SOLAR_YIELD


class TestDrip:
    def test_a_powered_nozzle_waters_its_three_by_three(
        self, scene: GardenScene
    ) -> None:
        _place(scene, "solar_panel", (0, 0))
        _place(scene, "drip_irrigation", (5, 5))
        for cell in ((5, 5), (6, 6), (8, 5)):
            scene.grid.soil_at(cell).moisture = 0.0

        _machines(scene)

        assert scene.grid.soil_at((5, 5)).moisture == pytest.approx(DRIP_TARGET)
        assert scene.grid.soil_at((6, 6)).moisture == pytest.approx(DRIP_TARGET)
        assert scene.grid.soil_at((8, 5)).moisture < DRIP_TARGET

    def test_it_does_not_flood_a_wetter_cell(self, scene: GardenScene) -> None:
        _place(scene, "solar_panel", (0, 0))
        _place(scene, "drip_irrigation", (5, 5))
        scene.grid.soil_at((5, 6)).moisture = 0.9

        _machines(scene)

        assert scene.grid.soil_at((5, 6)).moisture == pytest.approx(0.9)

    def test_an_unpowered_nozzle_waters_nothing(self, scene: GardenScene) -> None:
        _place(scene, "drip_irrigation", (5, 5))
        scene.grid.soil_at((5, 5)).moisture = 0.0

        _machines(scene)

        assert scene.grid.soil_at((5, 5)).moisture == 0.0

    def test_drip_keeps_a_plant_growing_with_no_hand_watering(
        self, scene: GardenScene
    ) -> None:
        """The point of the second rung: a drip cell is never dry in the
        morning, so it grows without the watering can."""
        _place(scene, "solar_panel", (0, 0))
        _place(scene, "drip_irrigation", (5, 5))
        scene.grid.till((5, 6))
        scene._plant((5, 6), "guandu")
        scene.grid.soil_at((5, 6)).moisture = 0.0

        _nights(scene, 3)

        # Which stage exactly depends on the nights' weather (a cloudy or
        # cold night grows less); what this pins is that it kept growing
        # with no watering can, which is the second rung's whole point.
        plant = scene.entity_manager.get_entity(scene.grid.plant_at[(5, 6)])
        assert plant.get_component(PlantComponent).growth_stage in (
            "mature",
            "harvestable",
        )
        assert scene.grid.soil_at((5, 6)).moisture > 0.0


class TestDrone:
    def _ready_plant(self, scene: GardenScene, cell: tuple[int, int]) -> None:
        _plant_at(scene, cell, "baru", stage="harvestable")

    def test_a_drone_sells_a_ready_plant_in_reach(self, scene: GardenScene) -> None:
        sold: list[PlantHarvestedEvent] = []
        scene.event_dispatcher.subscribe(PlantHarvestedEvent, sold.append)
        _place(scene, "solar_panel", (0, 0))
        _place(scene, "auto_harvester", (5, 5))
        self._ready_plant(scene, (5, 6))
        credits = scene.economy.credits

        _machines(scene)

        assert (5, 6) not in scene.grid.plant_at
        # The same night also pays the panel that powers the drone.
        assert scene.economy.credits == credits + sold[0].value + SOLAR_YIELD
        assert sold[0].species_id == "baru"
        assert scene.economy.organic_sales == 1

    def test_a_drone_ignores_plants_out_of_reach(self, scene: GardenScene) -> None:
        _place(scene, "solar_panel", (0, 0))
        _place(scene, "auto_harvester", (5, 5))
        self._ready_plant(scene, (5, 7))  # two cells away

        _machines(scene)

        assert (5, 7) in scene.grid.plant_at

    def test_a_drone_leaves_plants_that_are_not_ready(self, scene: GardenScene) -> None:
        _place(scene, "solar_panel", (0, 0))
        _place(scene, "auto_harvester", (5, 5))
        _plant_at(scene, (5, 6), "baru", stage="mature")

        _machines(scene)

        assert (5, 6) in scene.grid.plant_at

    def test_a_drone_will_not_harvest_an_infested_plant(
        self, scene: GardenScene
    ) -> None:
        _place(scene, "solar_panel", (0, 0))
        _place(scene, "auto_harvester", (5, 5))
        self._ready_plant(scene, (5, 6))
        _force_stage(scene, (5, 6), "infested")

        _machines(scene)

        assert (5, 6) in scene.grid.plant_at

    def test_a_drone_collects_only_so_many_a_night(self, scene: GardenScene) -> None:
        """A pair of extra hands, not a replacement for tending the plot."""
        _place(scene, "solar_panel", (0, 0))
        _place(scene, "auto_harvester", (5, 5))
        ready = [(4, 5), (6, 5), (5, 4), (5, 6)]
        for cell in ready:
            self._ready_plant(scene, cell)

        _machines(scene)

        left = [cell for cell in ready if cell in scene.grid.plant_at]
        assert len(left) == len(ready) - DRONE_HARVESTS_PER_NIGHT

        _machines(scene)

        assert not [cell for cell in ready if cell in scene.grid.plant_at]

    def test_an_unpowered_drone_does_nothing(self, scene: GardenScene) -> None:
        _place(scene, "auto_harvester", (5, 5))
        self._ready_plant(scene, (5, 6))

        _machines(scene)

        assert (5, 6) in scene.grid.plant_at

    def test_a_drone_sells_a_chemical_plant_at_the_discount(
        self, scene: GardenScene
    ) -> None:
        _place(scene, "solar_panel", (0, 0))
        _place(scene, "auto_harvester", (5, 5))
        self._ready_plant(scene, (5, 6))
        scene.entity_manager.get_entity(scene.grid.plant_at[(5, 6)]).get_component(
            PlantComponent
        ).is_chemical_boosted = True

        _machines(scene)

        assert scene.economy.chemical_sales == 1
        assert scene.economy.organic_sales == 0


class TestTheStore:
    def _open(self, scene: GardenScene) -> StoreOverlayScene:
        scene._open_store()
        current = scene.container.get(SceneManager).current_scene
        assert isinstance(current, StoreOverlayScene)
        return current

    def test_opening_pushes_the_store_over_a_frozen_garden(
        self, scene: GardenScene
    ) -> None:
        store = self._open(scene)

        assert store.name == "StoreOverlayScene"
        assert not scene.system_manager.enabled

    def test_closing_returns_to_a_running_garden(self, scene: GardenScene) -> None:
        store = self._open(scene)

        store._close()

        assert scene.container.get(SceneManager).current_scene is scene
        assert scene.system_manager.enabled
        assert not scene.container.get(UIManager).elements(UILayer.OVERLAY)

    def test_closing_twice_does_not_close_the_garden(self, scene: GardenScene) -> None:
        store = self._open(scene)

        store._close()
        store._close()

        assert scene.container.get(SceneManager).current_scene is scene

    def test_only_unlocked_structures_have_an_enabled_buy_button(
        self, scene: GardenScene
    ) -> None:
        store = self._open(scene)

        enabled = [kind for kind, b in store.buy_buttons.items() if b.enabled]

        assert enabled == ["solar_panel"]

    def test_placing_a_structure_unlocks_its_button(self, scene: GardenScene) -> None:
        _place(scene, "solar_panel", (0, 0))

        store = self._open(scene)

        assert store.buy_buttons["drip_irrigation"].enabled
        assert not store.buy_buttons["soil_sensor"].enabled

    def test_buying_closes_the_store_and_hands_over_the_build_tool(
        self, scene: GardenScene
    ) -> None:
        store = self._open(scene)
        credits = scene.economy.credits

        store.buy_buttons["solar_panel"].on_click(store.buy_buttons["solar_panel"])

        assert scene.container.get(SceneManager).current_scene is scene
        assert scene.economy.inventory["solar_panel"] == 1
        assert (
            scene.economy.credits
            == credits - structures.STRUCTURE_TABLE["solar_panel"].cost
        )
        assert scene._active_tool == "build_solar_panel"

    def test_a_purchase_you_cannot_afford_keeps_the_store_open(
        self, scene: GardenScene
    ) -> None:
        store = self._open(scene)
        scene.economy.credits = 10

        store.buy_buttons["solar_panel"].on_click(store.buy_buttons["solar_panel"])

        assert scene.container.get(SceneManager).current_scene is store
        assert scene.economy.inventory == {}
        assert store._message is not None
        assert "Not enough" in store._message.text

    def test_the_store_button_and_hotkey_are_on_the_bar(
        self, scene: GardenScene
    ) -> None:
        scene._on_action(
            __import__(
                "pyguara.input.events", fromlist=["OnActionEvent"]
            ).OnActionEvent(action_name="open_store", context="gameplay", value=1.0)
        )

        assert isinstance(
            scene.container.get(SceneManager).current_scene, StoreOverlayScene
        )

    def test_a_real_o_keypress_opens_the_store_and_leaves_it_open(
        self, scene: GardenScene
    ) -> None:
        """`O` opens the store *and* closes it, so it must not do both at once.

        The store binds its own close key in `on_enter()`, mid-way through
        the very key press that opened it. A real bug once: that same press
        closed the store the instant it opened, and only a real keypress --
        not a directly-fed action -- could show it.
        """
        manager = scene.container.get(SceneManager)
        input_manager = scene.container.get(InputManager)

        input_manager.process_event(KeyDownEvent(key_code=KEY_O))

        assert isinstance(manager.current_scene, StoreOverlayScene)

    def test_o_closes_the_store_once_a_frame_has_passed(
        self, scene: GardenScene
    ) -> None:
        manager = scene.container.get(SceneManager)
        input_manager = scene.container.get(InputManager)
        input_manager.process_event(KeyDownEvent(key_code=KEY_O))
        assert manager.current_scene is not scene

        manager.current_scene.update(1 / 60)
        input_manager.process_event(KeyDownEvent(key_code=KEY_O))

        assert manager.current_scene is scene

    def test_escape_closes_the_store_once_a_frame_has_passed(
        self, scene: GardenScene
    ) -> None:
        manager = scene.container.get(SceneManager)
        scene._open_store()

        manager.current_scene.update(1 / 60)
        scene.container.get(InputManager).process_event(KeyDownEvent(key_code=ESCAPE))

        assert manager.current_scene is scene


class TestRendering:
    def test_every_structure_renders_powered_and_unpowered(
        self, scene: GardenScene
    ) -> None:
        from unittest.mock import MagicMock

        from pyguara.graphics.protocols import IRenderer

        renderer = MagicMock(spec=IRenderer)
        _place(scene, "solar_panel", (0, 0))
        _place(scene, "drip_irrigation", (2, 0))
        _place(scene, "soil_sensor", (4, 0))
        _place(scene, "auto_harvester", (6, 0))
        assert scene._canvas is not None
        scene._canvas.celebrate_build((0, 0), "solar_panel")

        _resolve(scene, SUB_STEP)
        scene._canvas.update(1 / 60)
        scene._canvas.render_world(renderer)
        scene.entity_manager.get_entity(scene.grid.automation_at[(2, 0)]).get_component(
            AutomationComponent
        ).powered = False
        scene._canvas.render_world(renderer)

        assert renderer.draw_circle.called
        assert renderer.draw_line.called


def test_the_dispatcher_fixture_is_shared(scene: GardenScene) -> None:
    assert scene.event_dispatcher is scene.container.get(EventDispatcher)
    assert auto.SOLAR_YIELD > 0 and FIXED_DT > 0
