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

from typing import Any
from unittest.mock import MagicMock

import pytest

from games.quintal_cerrado.components import PlantComponent
from games.quintal_cerrado.garden_widget import GardenGridCanvas
from games.quintal_cerrado.scenes import GardenScene, TitleScene
from pyguara.ai.components import AIComponent
from pyguara.audio.audio_system import IAudioSystem
from pyguara.di.container import DIContainer
from pyguara.events.dispatcher import EventDispatcher
from pyguara.events.input import MouseButtonEvent
from pyguara.graphics.protocols import IRenderer, UIRenderer
from pyguara.input.events import OnActionEvent
from pyguara.input.manager import InputManager
from pyguara.input.protocols import IInputBackend
from pyguara.prefabs.loader import PrefabCache
from pyguara.prefabs.registry import ComponentRegistry, get_component_registry
from pyguara.resources.manager import ResourceManager
from pyguara.scene.manager import SceneManager
from pyguara.ui.design_system import Skins
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
    mock = MagicMock(spec=UIRenderer)
    mock.get_text_size.return_value = (40, 16)
    return mock


@pytest.fixture
def game_container(ui: UIManager, dispatcher: EventDispatcher) -> DIContainer:
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
    input_manager = InputManager(dispatcher, MagicMock(spec=IInputBackend))
    container.register_instance(InputManager, input_manager)
    # `TitleScene._on_play` registers `GardenScene` and pushes it, which
    # only wires the new scene's `container` if the manager already knows
    # one -- `Application.__init__` does this via `set_container()` too.
    scene_manager.set_container(container)
    return container


class TestTheTitleScreen:
    """The title screen's Play button leads to the garden."""

    def test_play_button_is_on_the_content_layer(
        self, game_container: DIContainer
    ) -> None:
        scene = TitleScene(game_container.get(EventDispatcher))
        scene.resolve_dependencies(game_container)
        scene.on_enter()

        ui_manager = game_container.get(UIManager)
        roots = ui_manager.elements(UILayer.CONTENT)
        buttons = [
            child
            for root in roots
            for child in ([root, *root.children])
            if getattr(child, "text", None) == "Play"
        ]
        assert len(buttons) == 1

    def test_play_button_registers_and_pushes_the_garden_scene(
        self, game_container: DIContainer
    ) -> None:
        scene = TitleScene(game_container.get(EventDispatcher))
        scene.resolve_dependencies(game_container)
        scene.on_enter()

        scene._on_play(None)

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
        assert scene._tool_buttons["till"].skin is Skins.SAGE
        assert scene._tool_buttons["water"].skin is Skins.GHOST

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
            "water",
            "harvest",
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
        assert scene._tool_buttons["plant_cagaita"].skin is Skins.SAGE
        assert scene._tool_buttons["till"].skin is Skins.GHOST

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
