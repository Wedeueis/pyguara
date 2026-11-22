"""Regression tests for the composition root (BOOT-1, BOOT-2, BOOT-3).

`_setup_container()`/`create_application()` never ran end to end before these
fixes: the Pygame backend, then the default, crashed on the first render, the
entry point raised before a window opened, and the component registry
silently lost every registration.
"""

import os

import pygame
import pytest

os.environ["SDL_VIDEODRIVER"] = "dummy"

from pyguara.application.bootstrap import (
    NoGraphicsAdapterError,
    _setup_container,
    create_application,
)
from pyguara.common.spatial import SpatialHash
from pyguara.common.types import Vector2
from pyguara.config.manager import ConfigManager
from pyguara.config.types import GameConfig, RenderingBackend
from pyguara.prefabs.registry import ComponentRegistry
from pyguara.random.service import RandomService
from tests.integration._scenes import ClearScene


@pytest.fixture
def app():
    application = create_application()
    yield application
    pygame.quit()


@pytest.mark.integration
def test_component_registry_is_registered_once_with_core_components():
    """BOOT-3: a second, empty ComponentRegistry no longer clobbers the first."""
    container = _setup_container()

    registry = container.get(ComponentRegistry)

    # Named, not counted. A bare count breaks every time a component is
    # legitimately added to core -- it did when `Sprite` and `ChildOf` were
    # registered for scene round-tripping -- while telling you nothing about
    # *which* component is present. The clobbering this test guards against
    # would empty the registry, so a handful of names catches it precisely.
    for name in ("Transform", "Tag", "RigidBody", "Sprite", "ChildOf"):
        assert registry.get(name) is not None, f"{name} missing from core registry"


@pytest.mark.integration
def test_the_core_registry_holds_no_kit_components():
    """Core registers core components, and only those.

    `PlatformerController` was registered here until it moved to
    `kits/platformer_movement` (#132). Registering a kit's component from
    core is the same layering break as importing one: it hands every game
    a genre's vocabulary whether or not it asked, and makes the kit look
    optional while the engine depends on it.

    Named rather than counted, because the count above cannot tell which
    component appeared -- and a kit component creeping back in is exactly
    what it would fail to describe.
    """
    container = _setup_container()
    registry = container.get(ComponentRegistry)

    registered = set(registry.list_components())

    assert "PlatformerController" not in registered
    assert "TopDownBody" not in registered
    # The core physics components it should still carry, so this cannot
    # pass by the registry being empty.
    assert {"RigidBody", "Collider", "TriggerVolume"} <= registered


@pytest.mark.integration
def test_random_service_is_registered_and_resolvable():
    container = _setup_container()

    service = container.get(RandomService)

    assert isinstance(service.stream("x").random(), float)


@pytest.mark.integration
def test_random_service_root_seed_comes_from_config(monkeypatch):
    """`debug.rng_seed` in the loaded config must reach `RandomService`."""
    original_load = ConfigManager.load

    def load_with_fixed_seed(self, file_path=None):
        result = original_load(self, file_path)
        self.config.debug.rng_seed = 12345
        return result

    monkeypatch.setattr(ConfigManager, "load", load_with_fixed_seed)

    container = _setup_container()

    assert container.get(RandomService).root_seed == 12345


@pytest.mark.integration
def test_spatial_hash_is_registered_and_resolvable():
    container = _setup_container()

    index = container.get(SpatialHash)

    assert index.query_radius(Vector2(0, 0), radius=10.0) == []


@pytest.mark.integration
def test_the_default_backend_is_wgpu_with_a_real_render_graph(app):
    """wgpu is the default renderer, with the render graph behind it."""
    from pyguara.graphics.pipeline.graph import RenderGraph

    config = app.container.get(ConfigManager).config
    assert config.display.backend is RenderingBackend.WGPU
    assert isinstance(app._render_graph, RenderGraph)


@pytest.mark.integration
def test_pygame_by_name_does_not_resolve_a_render_graph():
    """BOOT-1: the Pygame stub is resolvable but is not a real RenderGraph."""

    def software(config: GameConfig) -> None:
        config.display.backend = RenderingBackend.PYGAME

    application = create_application(software)
    try:
        assert application._render_graph is None
        application._render()
    finally:
        pygame.quit()


@pytest.mark.integration
def test_no_gpu_for_the_default_says_how_to_run_without_one(
    monkeypatch: pytest.MonkeyPatch,
):
    """No silent fallback: the two renderers look different."""
    from pyguara.graphics.backends.wgpu import window

    def no_adapter(self: object, config: object) -> bool:
        raise RuntimeError("no graphics adapter is available: none found")

    monkeypatch.setattr(window.WgpuWindow, "open", no_adapter)

    with pytest.raises(NoGraphicsAdapterError, match='display.backend = "pygame"'):
        create_application()


def _no_gpu(monkeypatch: pytest.MonkeyPatch, message: str) -> list[str]:
    """Make the wgpu window open, then fail to find a device; record closes."""
    from pyguara.graphics.backends.wgpu import window

    closed: list[str] = []

    class OpenedWindow:
        def close(self) -> None:
            closed.append("window")

    def opened_then_no_gpu(self: window.WgpuWindow, config: object) -> bool:
        self._window = OpenedWindow()
        raise RuntimeError(message)

    monkeypatch.setattr(window.WgpuWindow, "open", opened_then_no_gpu)
    return closed


def _fallback(config: GameConfig) -> None:
    config.display.software_fallback = True


@pytest.mark.integration
def test_a_game_that_opts_in_starts_on_software_without_a_gpu(
    monkeypatch: pytest.MonkeyPatch,
):
    from pyguara import crash
    from pyguara.application.clock import Clock
    from pyguara.graphics.backends.pygame.pygame_renderer import PygameBackend
    from pyguara.graphics.protocols import IRenderer
    from pyguara.input.backends.pygame_backend import PygameInputBackend
    from pyguara.input.protocols import IInputBackend

    closed = _no_gpu(monkeypatch, "no graphics adapter is available: none found")

    application = create_application(_fallback)
    try:
        container = application.container
        assert closed == ["window"]
        assert container.get(ConfigManager).config.display.backend is (
            RenderingBackend.PYGAME
        )
        assert isinstance(container.get(IRenderer), PygameBackend)
        assert isinstance(container.get(IInputBackend), PygameInputBackend)
        assert type(container.get(Clock)).__name__ == "PygameClock"
        assert "software fallback" in crash._notes["renderer"]
        application._render()
    finally:
        pygame.quit()


@pytest.mark.integration
def test_a_device_that_cannot_open_is_a_missing_gpu_too(
    monkeypatch: pytest.MonkeyPatch,
):
    _no_gpu(monkeypatch, "the graphics device could not be opened: lost")

    with pytest.raises(NoGraphicsAdapterError, match="software_fallback"):
        create_application()


@pytest.mark.integration
def test_the_fallback_without_pygame_installed_says_which_extra(
    monkeypatch: pytest.MonkeyPatch,
):
    import sys

    _no_gpu(monkeypatch, "no graphics adapter is available: none found")
    monkeypatch.setitem(sys.modules, "pygame", None)

    with pytest.raises(NoGraphicsAdapterError, match=r"pyguara\[pygame\]"):
        create_application(_fallback)


@pytest.mark.integration
def test_other_window_failures_are_not_called_a_missing_gpu(
    monkeypatch: pytest.MonkeyPatch,
):
    from pyguara.graphics.backends.wgpu import window

    def broken(self: object, config: object) -> bool:
        raise RuntimeError("the window cannot be drawn to")

    monkeypatch.setattr(window.WgpuWindow, "open", broken)

    with pytest.raises(RuntimeError, match="cannot be drawn to") as error:
        create_application()
    assert not isinstance(error.value, NoGraphicsAdapterError)


@pytest.mark.integration
def test_render_completes_without_raising_on_default_backend(app):
    """BOOT-1: `_render()` must use the direct path, not the GL graph path."""
    app._render()


@pytest.mark.integration
def test_documented_entry_point_boots_and_runs(app):
    """A bootstrapped application runs a scene and ticks (BOOT-1 to BOOT-3)."""
    scene = ClearScene(app._event_dispatcher)

    ticks = 0
    original_update = app._update

    def patched_update(dt: float) -> None:
        nonlocal ticks
        ticks += 1
        if ticks >= 3:
            app._is_running = False
        original_update(dt)

    app._update = patched_update

    app.run(scene)

    assert ticks == 3


@pytest.mark.integration
def test_scene_manager_gets_real_window_dimensions_at_init(app):
    """Scene lifecycle repair (wayfinder ticket 29): `Application.__init__`
    must call `scene_manager.set_screen_size()` with the real window
    dimensions, not leave `TransitionManager` on its hardcoded 800x600
    default."""
    transition_manager = app._scene_manager._transition_manager

    assert transition_manager.screen_width == app._window.width
    assert transition_manager.screen_height == app._window.height
    # The default WindowConfig is 1200x800, not TransitionManager's
    # hardcoded 800x600 default -- if these still matched by coincidence,
    # this assertion would catch it.
    assert transition_manager.screen_width != 800
    assert transition_manager.screen_height != 600
