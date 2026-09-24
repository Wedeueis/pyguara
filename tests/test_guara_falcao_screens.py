"""The demo's four screens, built headlessly.

`tools/agent_view.py guara_falcao --gl` is how the screens are *looked* at,
and `tests/integration/test_demos_render.py` will not boot this demo at all
now that it runs on ModernGL. What is left to pin down here is everything
that is not pixels: which layer each screen builds onto, that the HUD reads
the numbers it claims to, and that every options row is wired to something
real rather than to a flag nobody reads.

None of it needs a GPU: the UI system is backend-agnostic, so a real
`UIManager` plus a mock renderer is the whole harness.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest

from games.guara_falcao import art
from games.guara_falcao.components import Collectible, Health, Score
from games.guara_falcao.events import DebugCollidersToggled
from games.guara_falcao.hud import Hud
from games.guara_falcao.menus import OptionsScene, PauseScene
from games.guara_falcao.scenes import GameScene
from pyguara.audio.audio_system import IAudioSystem
from pyguara.common.components import Transform
from pyguara.common.types import Rect, Vector2
from pyguara.di.container import DIContainer
from pyguara.ecs.manager import EntityManager
from pyguara.events.dispatcher import EventDispatcher
from pyguara.graphics.lighting.components import LightSource
from pyguara.graphics.protocols import IRenderer, UIRenderer
from pyguara.kits.effects import EffectContainer
from pyguara.kits.effects.effect import Effect
from pyguara.prefabs.loader import PrefabCache
from pyguara.prefabs.registry import ComponentRegistry, get_component_registry
from pyguara.resources.manager import ResourceManager
from pyguara.scene.manager import SceneManager
from pyguara.scripting.coroutines import CoroutineManager
from pyguara.systems.manager import SystemManager
from pyguara.ui.components.checkbox import Checkbox
from pyguara.ui.components.slider import Slider
from pyguara.ui.manager import UIManager
from pyguara.ui.theme import get_theme, set_theme
from pyguara.ui.types import UIElementState, UILayer

SCREEN = (1280, 720)


@pytest.fixture
def ui() -> UIManager:
    manager = UIManager(EventDispatcher())
    manager.set_screen_size(*SCREEN)
    return manager


@pytest.fixture
def renderer() -> Any:
    mock = MagicMock(spec=UIRenderer)
    mock.get_text_size.return_value = (40, 16)
    return mock


@pytest.fixture
def world() -> Any:
    return MagicMock(spec=IRenderer)


@pytest.fixture
def audio() -> Any:
    mock = MagicMock(spec=IAudioSystem)
    mock.get_master_volume.return_value = 1.0
    mock.get_music_volume.return_value = 1.0
    mock.get_sfx_volume.return_value = 1.0
    return mock


@pytest.fixture
def game_container(ui: UIManager, audio: Any) -> DIContainer:
    """Enough of the game's container for a menu to build itself."""
    container = DIContainer()
    dispatcher = EventDispatcher()
    container.register_instance(DIContainer, container)
    container.register_instance(EventDispatcher, dispatcher)
    container.register_instance(UIManager, ui)
    container.register_instance(IAudioSystem, audio)  # type: ignore[type-abstract]
    container.register_instance(SceneManager, SceneManager())
    # `Scene.resolve_dependencies()` builds a scene-scoped world, which
    # wants these even for a menu that has no entities of its own.
    container.register_instance(ResourceManager, ResourceManager())
    container.register_instance(ComponentRegistry, get_component_registry())
    container.register_instance(PrefabCache, PrefabCache())
    container.register_instance(IRenderer, MagicMock(spec=IRenderer))  # type: ignore[type-abstract]
    container.register_instance(UIRenderer, MagicMock(spec=UIRenderer))  # type: ignore[type-abstract]
    container.register_singleton(SystemManager, SystemManager)
    container.register_singleton(CoroutineManager, CoroutineManager)
    return container


@pytest.fixture
def restore_theme() -> Any:
    """Put the global theme back, whatever a test did to it."""
    previous = get_theme()
    yield
    set_theme(previous)


def _player(health: int = 3, coins: int = 0) -> Any:
    """A player entity carrying just what the HUD reads."""
    entity = EntityManager().create_entity("player")
    entity.add_component(Health(current=health, max_health=3))
    entity.add_component(Score(coins_collected=coins))
    entity.add_component(EffectContainer())
    return entity


class TestTheHud:
    def test_every_cluster_lands_on_the_hud_layer(self, ui: UIManager) -> None:
        """Not CONTENT: the HUD has to stay under a pause menu."""
        Hud(ui, total_collectibles=4)

        assert ui.elements(UILayer.HUD)
        assert ui.elements(UILayer.CONTENT) == []
        assert ui.elements(UILayer.OVERLAY) == []

    def test_the_health_bar_follows_the_health_component(self, ui: UIManager) -> None:
        hud = Hud(ui, total_collectibles=4)

        hud.update(_player(health=1))

        assert hud.health_bar.value == pytest.approx(1 / 3)

    def test_the_counter_counts_against_the_level(self, ui: UIManager) -> None:
        hud = Hud(ui, total_collectibles=4)

        hud.update(_player(coins=2))

        assert hud.counter.text == "02 / 04"

    def test_the_counter_cannot_exceed_the_level(self, ui: UIManager) -> None:
        """Pickups credit more than one coin, and a HUD reading 07 / 04 is
        worse than one that stops counting."""
        hud = Hud(ui, total_collectibles=4)

        hud.update(_player(coins=99))

        assert hud.counter.text == "04 / 04"

    def test_the_boost_meter_drains_with_the_effect(self, ui: UIManager) -> None:
        hud = Hud(ui, total_collectibles=4)
        player = _player()
        effect = Effect(key="speed_boost", duration=5.0)
        effect.elapsed = 2.5
        player.get_component(EffectContainer).effects.append(effect)

        hud.update(player)

        assert hud.boost_bar.value == pytest.approx(0.5)
        assert hud.pips.lit == 2

    def test_no_boost_leaves_the_pips_dark(self, ui: UIManager) -> None:
        hud = Hud(ui, total_collectibles=4)

        hud.update(_player())

        assert hud.pips.lit == 0

    def test_it_survives_a_missing_player(self, ui: UIManager) -> None:
        """The level rebuilds between death and respawn."""
        hud = Hud(ui, total_collectibles=4)

        hud.update(None)

        assert hud.health_bar.value == 1.0


class TestThePauseMenu:
    def test_it_builds_on_the_overlay_layer(
        self, game_container: DIContainer, ui: UIManager
    ) -> None:
        scene = PauseScene(game_container.get(EventDispatcher), *SCREEN)
        scene.resolve_dependencies(game_container)

        scene.on_enter()

        assert ui.elements(UILayer.OVERLAY)
        assert ui.elements(UILayer.HUD) == []

    def test_it_focuses_its_first_button(
        self, game_container: DIContainer, ui: UIManager
    ) -> None:
        """A menu you have to click into is not keyboard-usable."""
        scene = PauseScene(game_container.get(EventDispatcher), *SCREEN)
        scene.resolve_dependencies(game_container)

        scene.on_enter()

        assert ui.focused_element is not None
        assert ui.focused_element.state == UIElementState.FOCUSED

    def test_the_hud_stays_out_of_the_focus_ring(
        self, game_container: DIContainer, ui: UIManager
    ) -> None:
        """What makes the menu modal: the pause button behind it is not
        reachable by Tab while the menu is up."""
        hud = Hud(ui, total_collectibles=4)
        scene = PauseScene(game_container.get(EventDispatcher), *SCREEN)
        scene.resolve_dependencies(game_container)

        scene.on_enter()

        assert hud.pause_button not in ui.focus_ring()


class TestTheOptionsPanel:
    def _open(self, container: DIContainer) -> OptionsScene:
        scene = OptionsScene(container.get(EventDispatcher), *SCREEN)
        scene.resolve_dependencies(container)
        scene.on_enter()
        return scene

    @staticmethod
    def _controls(ui: UIManager, kind: type) -> list[Any]:
        """Every control of `kind` anywhere in the overlay layer."""
        found: list[Any] = []

        def walk(element: Any) -> None:
            if isinstance(element, kind):
                found.append(element)
            for child in element.children:
                walk(child)

        for root in ui.elements(UILayer.OVERLAY):
            walk(root)
        return found

    def test_it_builds_on_the_overlay_layer(
        self, game_container: DIContainer, ui: UIManager
    ) -> None:
        self._open(game_container)

        assert ui.elements(UILayer.OVERLAY)

    def test_the_audio_sliders_move_the_mixer(
        self, game_container: DIContainer, ui: UIManager, audio: Any
    ) -> None:
        """Every row has to change something. A settings screen of inert
        toggles is the easiest thing to mock up and the least worth
        shipping."""
        self._open(game_container)
        sliders = self._controls(ui, Slider)

        assert len(sliders) == 3
        sliders[0].set_value(0.25)

        audio.set_master_volume.assert_called_once_with(0.25)

    def test_the_theme_row_reskins_everything(
        self, game_container: DIContainer, ui: UIManager, restore_theme: None
    ) -> None:
        self._open(game_container)
        theme_box = self._controls(ui, Checkbox)[0]

        theme_box.toggle()

        assert get_theme().name == "cerrado_day"

    def test_the_collider_row_is_dispatched_not_reached_for(
        self, game_container: DIContainer, ui: UIManager
    ) -> None:
        """The panel is pushed over the game and holds no reference to it."""
        seen: list[bool] = []
        game_container.get(EventDispatcher).subscribe(
            DebugCollidersToggled, lambda event: seen.append(event.shown)
        )
        self._open(game_container)

        self._controls(ui, Checkbox)[-1].toggle()

        assert seen == [True]


class TestTheArt:
    """The world is drawn from primitives, so "did it draw" is assertable."""

    def test_a_plank_stays_inside_its_rectangle(self, world: Any) -> None:
        """A platform that drew outside its collider would lie about where
        the player can stand."""
        rect = Rect(100, 200, 160, 24)

        art.draw_plank(world, rect)

        for call in world.draw_rect.call_args_list:
            drawn = call.args[0]
            assert drawn.x >= rect.x
            assert drawn.y >= rect.y
            assert drawn.y + drawn.height <= rect.y + rect.height

    def test_the_sky_never_blooms(self) -> None:
        """The sun disc is meant to be the only thing over the bloom
        threshold; a near-white sky band hazed the whole frame."""
        from games.guara_falcao.bootstrap import BLOOM_THRESHOLD

        for band in art.SKY_BANDS:
            luminance = (0.2126 * band.r + 0.7152 * band.g + 0.0722 * band.b) / 255
            assert luminance < BLOOM_THRESHOLD


class TestPickupMotionAndGlow:
    """A pickup's sprite, its light and its collection radius are one thing.

    The float started life as a sine added at draw time, which moved the
    sprite and nothing else -- so the fruit drifted away from its own glow.
    And nothing removes a collected pickup, it is only flagged, so its
    light burned on over an empty patch of air: what "the fruit did not
    disappear" actually looked like.
    """

    def _scene(self, container: DIContainer) -> Any:
        scene = GameScene(container.get(EventDispatcher))
        scene.resolve_dependencies(container)
        return scene

    @staticmethod
    def _fruit(scene: Any, y: float = 100.0, collected: bool = False) -> Any:
        entity = scene.entity_manager.create_entity()
        entity.add_component(Transform(position=Vector2(200.0, y)))
        entity.add_component(Collectible(collect_type="coin", collected=collected))
        return entity

    def test_preparing_lights_a_pickup_and_records_its_height(
        self, game_container: DIContainer
    ) -> None:
        scene = self._scene(game_container)
        fruit = self._fruit(scene, y=140.0)

        scene._prepare_pickups()

        assert fruit.get_component(LightSource) is not None
        assert scene._pickup_home[fruit.id] == 140.0

    def test_an_uncollected_pickup_floats(self, game_container: DIContainer) -> None:
        scene = self._scene(game_container)
        fruit = self._fruit(scene, y=140.0)
        scene._prepare_pickups()

        heights = set()
        for _ in range(12):
            scene._elapsed += 0.1
            scene._animate_pickups()
            heights.add(round(fruit.get_component(Transform).position.y, 3))

        assert len(heights) > 1

    def test_the_float_is_a_displacement_not_a_drift(
        self, game_container: DIContainer
    ) -> None:
        """Accumulating on the previous position would walk the fruit off
        the screen over a long run."""
        scene = self._scene(game_container)
        fruit = self._fruit(scene, y=140.0)
        scene._prepare_pickups()

        for _ in range(600):
            scene._elapsed += 0.1
            scene._animate_pickups()

        assert abs(fruit.get_component(Transform).position.y - 140.0) <= 3.0

    def test_collecting_one_puts_its_light_out(
        self, game_container: DIContainer
    ) -> None:
        scene = self._scene(game_container)
        fruit = self._fruit(scene)
        scene._prepare_pickups()
        assert fruit.get_component(LightSource).enabled is True

        fruit.get_component(Collectible).collected = True
        scene._animate_pickups()

        assert fruit.get_component(LightSource).enabled is False

    def test_a_collected_pickup_stops_floating(
        self, game_container: DIContainer
    ) -> None:
        scene = self._scene(game_container)
        fruit = self._fruit(scene, y=140.0, collected=True)
        scene._prepare_pickups()

        scene._elapsed += 1.0
        scene._animate_pickups()

        assert fruit.get_component(Transform).position.y == 140.0
