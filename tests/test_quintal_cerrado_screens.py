"""Quintal do Cerrado's screens, built headlessly.

Pixel checks live in `tools/agent_view.py quintal_cerrado`; this pins down
what a screenshot cannot: which layer each screen builds onto, and that a
click on the grid actually reaches `GardenGrid` through the real
`GardenGridCanvas._process_input` path rather than the demo's own
`_on_cell_clicked` short-circuit.

No GPU needed: the UI system is backend-agnostic, so a real `UIManager`
plus a mocked `UIRenderer`/`IRenderer` is the whole harness, the same
pattern `tests/test_guara_falcao_screens.py` uses.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

from games.quintal_cerrado.components import PlantComponent
from games.quintal_cerrado.garden_grid import GardenGrid
from games.quintal_cerrado.garden_widget import GardenGridCanvas
from games.quintal_cerrado.persistence_schema import SCHEMA_VERSION
from games.quintal_cerrado.scenes import GardenScene, TitleScene
from games.quintal_cerrado.soil_health_effect import SoilHealthEffect
from games.quintal_cerrado.store import StoreOverlayScene
from pyguara.ai.components import AIComponent
from pyguara.audio.audio_system import IAudioSystem
from pyguara.audio.manager import AudioManager
from pyguara.common.types import Color, Vector2
from pyguara.di.container import DIContainer
from pyguara.ecs.manager import EntityManager
from pyguara.events.dispatcher import EventDispatcher
from pyguara.events.input import MouseButtonEvent
from pyguara.graphics.protocols import IRenderer, UIRenderer
from pyguara.graphics.vfx.effects.storm import StormEffect
from pyguara.graphics.vfx.effects.vignette import VignetteEffect
from pyguara.input.events import OnActionEvent
from pyguara.input.manager import InputManager
from pyguara.input.protocols import IInputBackend
from pyguara.persistence.manager import PersistenceManager
from pyguara.persistence.migration import MigrationManager
from pyguara.persistence.storage import FileStorageBackend
from pyguara.prefabs.loader import PrefabCache
from pyguara.prefabs.registry import ComponentRegistry, get_component_registry
from pyguara.resources.manager import ResourceManager
from pyguara.scene.manager import SceneManager
from pyguara.ui.manager import UIManager
from pyguara.ui.types import UILayer

SCREEN = (960, 640)


@pytest.fixture
def dispatcher() -> EventDispatcher:
    return EventDispatcher()


@pytest.fixture
def ui(dispatcher: EventDispatcher) -> UIManager:
    # Shares `dispatcher` with `game_container`'s `InputManager` -- a real
    # mouse click has to reach the same `UIManager` that subscribed to it,
    # which is what `test_a_real_mouse_click_tills_the_cell_under_it` checks.
    manager = UIManager(dispatcher)
    manager.set_screen_size(*SCREEN)
    return manager


@pytest.fixture
def renderer() -> Any:
    """A world renderer -- `render_world()` (Phase 5) is what this feeds."""
    return MagicMock(spec=IRenderer)


@pytest.fixture
def game_container(
    ui: UIManager, dispatcher: EventDispatcher, tmp_path: Path
) -> DIContainer:
    """Enough of the game's container for a scene to build itself."""
    container = DIContainer()
    container.register_instance(DIContainer, container)
    container.register_instance(EventDispatcher, dispatcher)
    container.register_instance(UIManager, ui)
    scene_manager = SceneManager()
    container.register_instance(SceneManager, scene_manager)
    container.register_instance(ResourceManager, ResourceManager())
    container.register_instance(ComponentRegistry, get_component_registry())
    container.register_instance(PrefabCache, PrefabCache())
    container.register_instance(IRenderer, MagicMock(spec=IRenderer))  # type: ignore[type-abstract]
    container.register_instance(UIRenderer, MagicMock(spec=UIRenderer))  # type: ignore[type-abstract]
    container.register_instance(IAudioSystem, MagicMock(spec=IAudioSystem))  # type: ignore[type-abstract]
    container.register_singleton(AudioManager, AudioManager)
    # GPU-owning effects: real ones need a live moderngl context this
    # headless suite never has (see `bootstrap.py`), so every scene test
    # gets a mock instead -- `scenes.py` only ever sets plain attributes
    # on these (`.rain`, `.intensity`, `.health`, `.strength`) and calls
    # `.update(dt)`, none of which needs a real shader program behind it.
    container.register_instance(StormEffect, MagicMock(spec=StormEffect))
    container.register_instance(VignetteEffect, MagicMock(spec=VignetteEffect))
    container.register_instance(SoilHealthEffect, MagicMock(spec=SoilHealthEffect))
    input_manager = InputManager(dispatcher, MagicMock(spec=IInputBackend))
    container.register_instance(InputManager, input_manager)
    # `TitleScene._on_play` registers `GardenScene` and pushes it, which
    # only wires the new scene's `container` if the manager already knows
    # one -- `Application.__init__` does this via `set_container()` too.
    # A real store in a temp directory: the garden saves on exit, and a test
    # must never write into the repository's own `saves/`.
    container.register_instance(
        PersistenceManager,
        PersistenceManager(
            FileStorageBackend(base_path=str(tmp_path / "saves")),
            MigrationManager(current_version=SCHEMA_VERSION),
        ),
    )
    scene_manager.set_container(container)
    return container


class TestTheTitleScreen:
    """The title screen's buttons lead to the garden."""

    def test_the_title_buttons_are_on_the_content_layer(
        self, game_container: DIContainer
    ) -> None:
        scene = TitleScene(game_container.get(EventDispatcher))
        scene.resolve_dependencies(game_container)
        scene.on_enter()

        ui_manager = game_container.get(UIManager)
        roots = ui_manager.elements(UILayer.CONTENT)
        labels = {
            getattr(child, "text", None)
            for root in roots
            for child in ([root, *root.children])
        }
        assert {"Continue", "New Garden"} <= labels

    def test_new_garden_registers_and_pushes_the_garden_scene(
        self, game_container: DIContainer
    ) -> None:
        scene = TitleScene(game_container.get(EventDispatcher))
        scene.resolve_dependencies(game_container)
        scene.on_enter()

        scene._on_new(None)

        scene_manager = game_container.get(SceneManager)
        assert scene_manager.current_scene is not None
        assert scene_manager.current_scene.name == "GardenScene"


class TestTheGardenScreen:
    """The grid widget, the tool selector, and a click reaching the grid."""

    def _entered_scene(self, game_container: DIContainer) -> GardenScene:
        # Through `SceneManager.switch_to()`, not a direct `on_enter()` call
        # -- `GardenScene._on_action`'s reentrancy guard checks
        # `scene_manager.current_scene`, so a test of it needs the manager
        # to actually agree this scene is current.
        scene = GardenScene(game_container.get(EventDispatcher))
        scene_manager = game_container.get(SceneManager)
        scene_manager.register(scene)
        scene_manager.switch_to("GardenScene")
        return scene

    def test_grid_canvas_is_on_the_content_layer(
        self, game_container: DIContainer
    ) -> None:
        self._entered_scene(game_container)

        ui_manager = game_container.get(UIManager)
        roots = ui_manager.elements(UILayer.CONTENT)
        assert any(isinstance(root, GardenGridCanvas) for root in roots)

    def test_default_tool_is_till(self, game_container: DIContainer) -> None:
        scene = self._entered_scene(game_container)

        assert scene._active_tool == "till"
        assert scene._tool_buttons["till"].active
        assert not scene._tool_buttons["water"].active

    def test_tool_bar_has_a_clickable_button_per_tool(
        self, game_container: DIContainer
    ) -> None:
        """The bar itself is the fix for a tool being invisible in the HUD.

        `water`/`harvest` have keyboard shortcuts but nothing on screen
        named them before this bar existed -- a click is what makes them
        discoverable.
        """
        scene = self._entered_scene(game_container)

        assert set(scene._tool_buttons) == {
            "till",
            "plant_guandu",
            "plant_cagaita",
            "plant_baru",
            "plant_pequi",
            "plant_generic",
            "water",
            "harvest",
            "compost",
            "spray",
        }

        scene._tool_buttons["water"].on_click(scene._tool_buttons["water"])
        assert scene._active_tool == "water"

    def test_a_real_mouse_click_tills_the_cell_under_it(
        self, game_container: DIContainer
    ) -> None:
        """Exercises the actual input path, not the scene's own callback.

        `MouseButtonEvent` -> `InputManager.process_event` -> `OnMouseEvent`
        -> `UIManager` -> `GardenGridCanvas._process_input` -> the scene's
        `on_cell_clicked` callback -- the same chain a real player's click
        travels, proving `GardenGridCanvas` is wired into the live UI tree
        rather than only reachable by calling its methods directly.
        """
        scene = self._entered_scene(game_container)
        assert scene._canvas is not None
        canvas = scene._canvas
        cell = (0, 0)

        input_manager = game_container.get(InputManager)
        click_x = canvas.rect.x + 5
        click_y = canvas.rect.y + 5
        input_manager.process_event(
            MouseButtonEvent(button=1, x=click_x, y=click_y, is_down=True)
        )

        assert scene.grid.soil_at(cell).soil_type == "tilled_dirt"

    def test_switching_tool_updates_active_tool_and_button_highlight(
        self, game_container: DIContainer
    ) -> None:
        scene = self._entered_scene(game_container)

        scene._on_action(
            OnActionEvent(action_name="plant_cagaita", context="gameplay", value=1.0)
        )

        assert scene._active_tool == "plant_cagaita"
        assert scene._tool_buttons["plant_cagaita"].active
        assert not scene._tool_buttons["till"].active

    def test_the_dock_reprices_its_slots_from_the_live_economy(
        self, game_container: DIContainer
    ) -> None:
        """Badges and dimming follow Sementes every frame, not once at build."""
        scene = self._entered_scene(game_container)
        scene.economy.credits = 1000
        scene.update(1 / 60)
        assert scene._tool_buttons["spray"].affordable

        scene.economy.credits = 0
        scene.update(1 / 60)

        assert not scene._tool_buttons["spray"].affordable
        assert not scene._tool_buttons["plant_baru"].affordable
        assert scene._tool_buttons["till"].affordable
        assert scene._tool_buttons["plant_generic"].badge == "x0"

    def test_the_store_slot_opens_the_store(self, game_container: DIContainer) -> None:
        scene = self._entered_scene(game_container)
        assert scene._store_button is not None

        scene._store_button.on_click(scene._store_button)

        current = game_container.get(SceneManager).current_scene
        assert isinstance(current, StoreOverlayScene)

    def test_planting_requires_tilled_unoccupied_ground(
        self, game_container: DIContainer
    ) -> None:
        scene = self._entered_scene(game_container)
        scene._set_active_tool("plant_guandu")
        cell = (3, 3)

        scene._on_cell_clicked(cell)
        assert cell not in scene.grid.plant_at

        scene.grid.till(cell)
        scene._on_cell_clicked(cell)
        assert cell in scene.grid.plant_at

    def test_each_species_tool_plants_its_own_species(
        self, game_container: DIContainer
    ) -> None:
        scene = self._entered_scene(game_container)

        for tool, cell in (
            ("plant_guandu", (0, 0)),
            ("plant_cagaita", (1, 0)),
            ("plant_baru", (2, 0)),
        ):
            scene.grid.till(cell)
            scene._set_active_tool(tool)
            scene._on_cell_clicked(cell)

            entity_id = scene.grid.plant_at[cell]
            entity = scene.entity_manager.get_entity(entity_id)
            assert entity.get_component(PlantComponent).species_id == tool.removeprefix(
                "plant_"
            )

    def test_a_newly_planted_entity_carries_a_seedling_fsm(
        self, game_container: DIContainer
    ) -> None:
        scene = self._entered_scene(game_container)
        cell = (4, 4)
        scene.grid.till(cell)
        scene._set_active_tool("plant_guandu")

        scene._on_cell_clicked(cell)

        entity = scene.entity_manager.get_entity(scene.grid.plant_at[cell])
        assert entity.has_component(AIComponent)
        assert entity.get_component(AIComponent).fsm is not None
        assert entity.get_component(PlantComponent).growth_stage == "seedling"

    def test_watering_raises_moisture_and_celebrates(
        self, game_container: DIContainer
    ) -> None:
        scene = self._entered_scene(game_container)
        scene._set_active_tool("water")
        cell = (2, 2)
        before = scene.grid.soil_at(cell).moisture

        scene._on_cell_clicked(cell)

        assert scene.grid.soil_at(cell).moisture > before

    def test_harvest_tool_only_removes_a_harvestable_plant(
        self, game_container: DIContainer
    ) -> None:
        scene = self._entered_scene(game_container)
        cell = (5, 5)
        scene.grid.till(cell)
        scene._plant(cell, "guandu")
        entity_id = scene.grid.plant_at[cell]

        # Still a seedling -- harvest is a no-op.
        scene._set_active_tool("harvest")
        scene._on_cell_clicked(cell)
        assert cell in scene.grid.plant_at

        # Force it ready and try again.
        plant = scene.entity_manager.get_entity(entity_id).get_component(PlantComponent)
        plant.growth_stage = "harvestable"
        scene._on_cell_clicked(cell)

        assert cell not in scene.grid.plant_at
        assert scene.entity_manager.get_entity(entity_id) is None
        # The cell stays tilled, ready to replant immediately.
        assert scene.grid.soil_at(cell).soil_type == "tilled_dirt"
        assert scene.grid.can_plant(cell)

    def test_hud_shows_the_players_sementes(self, game_container: DIContainer) -> None:
        scene = self._entered_scene(game_container)
        scene.economy.credits = 42

        scene.update(1 / 60)

        assert scene._hud is not None
        assert scene._hud.credits_label.text == "Sementes: 42"

    def test_hud_shows_an_outbreak(self, game_container: DIContainer) -> None:
        scene = self._entered_scene(game_container)
        scene.conditions.phase = "outbreak"

        scene.update(1 / 60)

        assert scene._hud is not None
        assert "OUTBREAK" in scene._hud.status_label.text

    def test_an_unaffordable_seed_says_so_and_plants_nothing(
        self, game_container: DIContainer
    ) -> None:
        scene = self._entered_scene(game_container)
        cell = (2, 2)
        scene.grid.till(cell)
        scene.economy.credits = 0
        scene._set_active_tool("plant_baru")

        scene._on_cell_clicked(cell)
        scene.update(1 / 60)

        assert cell not in scene.grid.plant_at
        assert scene._hud is not None
        assert "Not enough" in scene._hud.message_label.text

    def test_a_stage_change_pop_grows_past_target_then_settles(
        self, game_container: DIContainer
    ) -> None:
        """The pop tween overshoots 1.0 before landing on it exactly.

        `EASE_OUT_BACK` is what turns a stage change into a "grew bigger
        than its target, then returned" beat rather than a flat pop-in --
        this pins that the overshoot, and the settle afterwards, both
        actually happen.
        """
        scene = self._entered_scene(game_container)
        assert scene._canvas is not None
        cell = (6, 6)
        scene.grid.till(cell)
        scene._plant(cell, "guandu")
        entity_id = scene.grid.plant_at[cell]

        # The first update discovers the freshly planted entity and starts
        # its pop tween.
        scene._canvas.update(1 / 60)
        visual = scene._canvas._visuals[entity_id]
        assert visual.pop_tween is not None

        scales: list[float] = []
        for _ in range(30):  # well past POP_DURATION at 60fps
            scene._canvas.update(1 / 60)
            current = visual.pop_tween.current_value
            assert isinstance(current, float)
            scales.append(current)

        assert max(scales) > 1.0  # it grew past its resting size...
        assert scales[-1] == pytest.approx(1.0)  # ...and settled back on it

    def test_a_canvas_with_no_audio_manager_still_celebrates(self) -> None:
        """`audio` is optional -- every `celebrate_*` must tolerate `None`.

        Every existing caller either passes a real `AudioManager` or (like
        this test) nothing at all -- neither should ever raise.
        """
        canvas = GardenGridCanvas(Vector2(0, 0), GardenGrid(), EntityManager())
        cell = (0, 0)

        canvas.celebrate_till(cell)
        canvas.celebrate_water(cell)
        canvas.celebrate_harvest(cell, "guandu")
        canvas.celebrate_compost(cell)
        canvas.celebrate_spray(cell)
        canvas.celebrate_build(cell, "solar_panel")

    def test_the_plot_renders_every_state_without_error(
        self, game_container: DIContainer, renderer: Any
    ) -> None:
        """A smoke test for draw paths the frame-capture only sees by luck.

        Infested and dying plants, pest marks, degraded soil, floating
        labels and the outbreak alert are each drawn only in a state a
        short scripted playthrough may never reach, and a mocked renderer
        is enough to catch a bad argument or a missing key in any of them.
        """
        scene = self._entered_scene(game_container)
        assert scene._canvas is not None
        for cell, stage in (
            ((0, 0), "seedling"),
            ((1, 0), "growing"),
            ((2, 0), "mature"),
            ((3, 0), "harvestable"),
            ((4, 0), "infested"),
            ((5, 0), "dying"),
        ):
            scene.grid.till(cell)
            scene._plant(cell, "baru")
            entity = scene.entity_manager.get_entity(scene.grid.plant_at[cell])
            entity.get_component(AIComponent).fsm._transition_to(stage)
        scene.grid.soil_at((6, 0)).is_chemically_degraded = True
        scene.grid.soil_at((7, 0)).pest_pressure = 0.9
        scene._canvas.spawn_label((0, 0), "+16", Color(255, 226, 140))
        scene._canvas.flash_alert()
        scene._canvas.celebrate_spray((3, 3))
        scene._canvas.celebrate_compost((3, 3))

        scene._canvas.update(1 / 60)
        scene._canvas.render_world(renderer)

        assert renderer.draw_rect.called
        assert renderer.draw_text.called
