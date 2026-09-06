"""Regression tests for scene-owned world/SystemManager and RenderSystem
wiring (wayfinder ticket 24), the Transform-Sprite position combination
(ticket 44), and fixed-timestep render interpolation (ticket 45).

Uses the real `create_application()`/`create_headless_application()`
bootstrap (not a hand-rolled container) so `Scene.resolve_dependencies()`
exercises the actual composition root.
"""

import os

os.environ["SDL_VIDEODRIVER"] = "dummy"
os.environ["SDL_AUDIODRIVER"] = "dummy"

import pygame
import pytest

from pyguara.ai.components import SteeringAgent
from pyguara.ai.steering_system import SteeringSystem
from pyguara.application.application import Application
from pyguara.application.bootstrap import (
    create_application,
    create_headless_application,
)
from pyguara.common.components import Transform
from pyguara.common.types import Vector2
from pyguara.ecs.entity import Entity
from pyguara.graphics.components.sprite import Sprite
from pyguara.graphics.protocols import TextureFactory
from pyguara.scene.base import Scene


class _TestScene(Scene):
    """Minimal concrete Scene relying entirely on the base class defaults."""

    def on_enter(self) -> None:
        pass

    def on_exit(self) -> None:
        pass

    def update(self, dt: float) -> None:
        pass


def _boot(app: Application) -> _TestScene:
    scene = _TestScene("test_scene", app._event_dispatcher)
    app._scene_manager.register(scene)
    app._scene_manager.switch_to(scene.name)
    return scene


def _add_wander_entity(scene: _TestScene) -> Entity:
    entity = scene.entity_manager.create_entity()
    entity.add_component(Transform(position=Vector2.zero()))
    entity.add_component(SteeringAgent(behavior="wander"))
    return entity


@pytest.fixture(autouse=True)
def _quit_pygame():
    yield
    pygame.quit()


def test_engine_systems_see_the_scenes_own_entities():
    """The auto-registered SteeringSystem queries this scene's own
    EntityManager, not an empty or unrelated one."""
    app = create_headless_application()
    scene = _boot(app)
    entity = _add_wander_entity(scene)

    steering_system = scene.system_manager.get_system(SteeringSystem)
    assert steering_system is not None
    assert entity.id not in steering_system._wander_targets

    scene.system_manager.update(1 / 60)

    assert entity.id in steering_system._wander_targets


def test_cleanup_empties_steering_system_wander_targets():
    """SystemManager.cleanup() (run on scene exit) clears per-entity wander
    state -- it dies with the scene, not pruned entity-by-entity."""
    app = create_headless_application()
    scene = _boot(app)
    _add_wander_entity(scene)

    steering_system = scene.system_manager.get_system(SteeringSystem)
    assert steering_system is not None
    scene.system_manager.update(1 / 60)
    assert len(steering_system._wander_targets) == 1

    scene.system_manager.cleanup()

    assert steering_system._wander_targets == {}


def test_pause_disables_system_ticking_via_set_enabled():
    """Pushing a scene over another disables the paused scene's own
    SystemManager (a second, independent gate alongside pause_below)."""
    app = create_headless_application()
    bottom = _boot(app)
    entity = _add_wander_entity(bottom)

    top = _TestScene("top_scene", app._event_dispatcher)
    app._scene_manager.register(top)

    assert bottom.system_manager.enabled is True

    app._scene_manager.push_scene("top_scene")
    assert bottom.system_manager.enabled is False

    # Disabled: ticking the SystemManager directly is a no-op.
    bottom.system_manager.update(1 / 60)
    steering_system = bottom.system_manager.get_system(SteeringSystem)
    assert steering_system is not None
    assert entity.id not in steering_system._wander_targets

    app._scene_manager.pop_scene()
    assert bottom.system_manager.enabled is True

    bottom.system_manager.update(1 / 60)
    assert entity.id in steering_system._wander_targets


@pytest.mark.parametrize(
    "factory",
    [create_application, create_headless_application],
    ids=["pygame", "headless"],
)
def test_default_render_submits_visible_sprites_and_flushes(factory) -> None:
    """Scene.render()'s default implementation actually drives the backend:
    submits every visible Sprite-bearing entity and flushes, on both
    backends under test."""
    app = factory()
    scene = _boot(app)

    # Backend-appropriate texture (PygameTexture for the real backend,
    # HeadlessTexture for the headless one) via the same DI-registered
    # TextureFactory the engine itself uses -- a texture built for one
    # backend's native_handle expectations won't satisfy the other's.
    texture_factory = app._container.get(TextureFactory)  # type: ignore[type-abstract]
    texture = texture_factory.create_from_bytes(
        "test", bytes(8 * 8 * 4), width=8, height=8
    )
    visible = scene.entity_manager.create_entity()
    visible.add_component(Sprite(texture=texture, visible=True))
    hidden = scene.entity_manager.create_entity()
    hidden.add_component(Sprite(texture=texture, visible=False))

    assert scene.render_system is not None
    backend = scene.render_system._backend
    calls = {"begin_frame": 0, "end_frame": 0, "render_batch": 0}

    original_begin, original_end, original_batch = (
        backend.begin_frame,
        backend.end_frame,
        backend.render_batch,
    )

    def spy_begin_frame() -> None:
        calls["begin_frame"] += 1
        original_begin()

    def spy_end_frame() -> None:
        calls["end_frame"] += 1
        original_end()

    def spy_render_batch(batch) -> None:
        calls["render_batch"] += 1
        original_batch(batch)

    backend.begin_frame = spy_begin_frame  # type: ignore[method-assign]
    backend.end_frame = spy_end_frame  # type: ignore[method-assign]
    backend.render_batch = spy_render_batch  # type: ignore[method-assign]

    scene.render(app._world_renderer, app._ui_renderer)

    assert calls["begin_frame"] == 1
    assert calls["end_frame"] == 1
    # Only the visible sprite gets batched -- one batch for the one texture.
    assert calls["render_batch"] == 1

    app.shutdown()


def _spy_submitted_positions(scene: _TestScene) -> list:
    """Capture each RenderCommand.world_position submitted this render(),
    since RenderSystem.flush() consumes/clears the queue before render()
    returns -- there's nothing left to inspect on the queue afterward."""
    assert scene.render_system is not None
    positions: list = []
    original_push = scene.render_system._queue.push

    def spy_push(cmd) -> None:
        positions.append(cmd.world_position)
        original_push(cmd)

    scene.render_system._queue.push = spy_push  # type: ignore[method-assign]
    return positions


def test_default_render_combines_transform_and_sprite_offset() -> None:
    """An entity with both Transform and Sprite submits at
    transform.position + sprite.position (an offset, not an overwrite) --
    and sprite.position itself is never mutated by rendering."""
    app = create_headless_application()
    scene = _boot(app)

    texture_factory = app._container.get(TextureFactory)  # type: ignore[type-abstract]
    texture = texture_factory.create_from_bytes(
        "test", bytes(8 * 8 * 4), width=8, height=8
    )

    entity = scene.entity_manager.create_entity()
    entity.add_component(Transform(position=Vector2(100, 100)))
    sprite = Sprite(texture=texture, visible=True, position=Vector2(5, -5))
    entity.add_component(sprite)

    positions = _spy_submitted_positions(scene)

    scene.render(app._world_renderer, app._ui_renderer)

    assert positions == [Vector2(105, 95)]
    # The stored offset survives rendering unmutated.
    assert sprite.position == Vector2(5, -5)

    app.shutdown()


def test_default_render_uses_sprite_position_when_no_transform() -> None:
    """A Sprite with no Transform submits at its own position, unchanged --
    the standalone case."""
    app = create_headless_application()
    scene = _boot(app)

    texture_factory = app._container.get(TextureFactory)  # type: ignore[type-abstract]
    texture = texture_factory.create_from_bytes(
        "test", bytes(8 * 8 * 4), width=8, height=8
    )

    entity = scene.entity_manager.create_entity()
    entity.add_component(Sprite(texture=texture, visible=True, position=Vector2(42, 7)))

    positions = _spy_submitted_positions(scene)

    scene.render(app._world_renderer, app._ui_renderer)

    assert positions == [Vector2(42, 7)]

    app.shutdown()


def test_default_render_reflects_live_transform_changes_between_frames() -> None:
    """Moving Transform.position between two render() calls changes the
    submitted world position on the next call -- proving the combination is
    computed live at submission time, not cached from an earlier tick."""
    app = create_headless_application()
    scene = _boot(app)

    texture_factory = app._container.get(TextureFactory)  # type: ignore[type-abstract]
    texture = texture_factory.create_from_bytes(
        "test", bytes(8 * 8 * 4), width=8, height=8
    )

    entity = scene.entity_manager.create_entity()
    transform = Transform(position=Vector2(0, 0))
    entity.add_component(transform)
    entity.add_component(Sprite(texture=texture, visible=True))

    positions = _spy_submitted_positions(scene)
    scene.render(app._world_renderer, app._ui_renderer)
    assert positions == [Vector2(0, 0)]

    # Simulate a physics step moving the entity, with no system tick at all.
    transform.position = Vector2(50, 25)
    scene.render(app._world_renderer, app._ui_renderer)
    assert positions == [Vector2(0, 0), Vector2(50, 25)]

    app.shutdown()


def test_interpolated_transform_lerps_by_render_alpha() -> None:
    """A Transform.interpolate=True entity submits at
    lerp(previous_position, position, render_alpha), not the raw current
    position."""
    app = create_headless_application()
    scene = _boot(app)

    texture_factory = app._container.get(TextureFactory)  # type: ignore[type-abstract]
    texture = texture_factory.create_from_bytes(
        "test", bytes(8 * 8 * 4), width=8, height=8
    )

    entity = scene.entity_manager.create_entity()
    transform = Transform(position=Vector2(100, 0), interpolate=True)
    transform.previous_position = Vector2(0, 0)
    entity.add_component(transform)
    entity.add_component(Sprite(texture=texture, visible=True))

    positions = _spy_submitted_positions(scene)

    scene.render_alpha = 0.5
    scene.render(app._world_renderer, app._ui_renderer)
    assert positions == [Vector2(50, 0)]

    scene.render_alpha = 1.0
    scene.render(app._world_renderer, app._ui_renderer)
    assert positions == [Vector2(50, 0), Vector2(100, 0)]

    app.shutdown()


def test_non_interpolated_transform_ignores_render_alpha() -> None:
    """A Transform with interpolate=False (the default) always submits at its
    raw current position, regardless of render_alpha."""
    app = create_headless_application()
    scene = _boot(app)

    texture_factory = app._container.get(TextureFactory)  # type: ignore[type-abstract]
    texture = texture_factory.create_from_bytes(
        "test", bytes(8 * 8 * 4), width=8, height=8
    )

    entity = scene.entity_manager.create_entity()
    transform = Transform(position=Vector2(100, 0))
    transform.previous_position = Vector2(0, 0)  # would matter if interpolated
    entity.add_component(transform)
    entity.add_component(Sprite(texture=texture, visible=True))

    positions = _spy_submitted_positions(scene)

    scene.render_alpha = 0.5
    scene.render(app._world_renderer, app._ui_renderer)

    assert positions == [Vector2(100, 0)]

    app.shutdown()


def test_fixed_update_snapshots_previous_position_before_any_system_runs() -> None:
    """SceneManager.fixed_update() snapshots previous_position once, before
    any system (engine or scene-registered) moves the Transform this tick --
    not after, which would make previous_position == position and defeat
    interpolation entirely."""
    app = create_headless_application()
    scene = _boot(app)

    entity = scene.entity_manager.create_entity()
    transform = Transform(position=Vector2(0, 0), interpolate=True)
    entity.add_component(transform)

    class _MoveSystem:
        def update(self, dt: float) -> None:
            transform.position = transform.position + Vector2(10, 0)

    scene.system_manager.register(_MoveSystem(), priority=999)

    app._scene_manager.fixed_update(1 / 60)

    assert transform.previous_position == Vector2(0, 0)
    assert transform.position == Vector2(10, 0)

    # A second tick: previous_position picks up where the first tick left off.
    app._scene_manager.fixed_update(1 / 60)
    assert transform.previous_position == Vector2(10, 0)
    assert transform.position == Vector2(20, 0)

    app.shutdown()


def test_fixed_update_does_not_snapshot_non_interpolated_transforms() -> None:
    """A Transform with interpolate=False never has previous_position
    touched by SceneManager.fixed_update() -- no wasted work for entities
    that don't opt in."""
    app = create_headless_application()
    scene = _boot(app)

    entity = scene.entity_manager.create_entity()
    transform = Transform(position=Vector2(5, 5))
    transform.previous_position = Vector2(-1, -1)  # sentinel, must stay put
    entity.add_component(transform)

    app._scene_manager.fixed_update(1 / 60)

    assert transform.previous_position == Vector2(-1, -1)

    app.shutdown()
