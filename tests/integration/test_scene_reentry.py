"""A scene entered a second time works as it did the first time.

An exit drops a scene's systems and disposes its scope. Entering it again,
back to the menu from a game, used to leave it with neither, and nothing
said so: its tweens, animations, AI and audio just stopped.
"""

from __future__ import annotations

import os

os.environ["SDL_VIDEODRIVER"] = "dummy"
os.environ["SDL_AUDIODRIVER"] = "dummy"

import logging

import pygame
import pytest

from pyguara.animation.tweener import TweenSystem
from pyguara.application.application import Application
from pyguara.application.bootstrap import create_headless_application
from pyguara.ecs.events import EntityDestroyed
from pyguara.events.dispatcher import EventDispatcher
from pyguara.scene.manager import SceneManager
from pyguara.scene.transitions import FadeTransition, TransitionConfig
from tests.integration._scenes import ClearScene

ENGINE_SYSTEMS = 5


@pytest.fixture(autouse=True)
def _quit_pygame():
    yield
    pygame.quit()


class _Named(ClearScene):
    def __init__(self, dispatcher: EventDispatcher, name: str) -> None:
        super().__init__(dispatcher)
        self.name = name
        self.entries = 0

    def on_enter(self) -> None:
        self.entries += 1


class _Ticker:
    def __init__(self) -> None:
        self.ticks = 0

    def update(self, dt: float) -> None:
        self.ticks += 1


def _app() -> tuple[Application, SceneManager, _Named, _Named]:
    app = create_headless_application()
    manager = app._scene_manager
    menu, game = (_Named(app._event_dispatcher, n) for n in ("Menu", "Game"))
    manager.register(menu)
    manager.register(game)
    return app, manager, menu, game


def _systems(scene: _Named) -> int:
    return len(scene.system_manager._systems)


def _is_live(scene: _Named) -> bool:
    return (
        _systems(scene) == ENGINE_SYSTEMS
        and scene.system_manager.get_system(TweenSystem) is not None
        and scene.scope is not None
        and not scene.scope.disposed
    )


def test_back_to_the_menu_it_has_its_systems_and_scope() -> None:
    _, manager, menu, game = _app()
    manager.switch_to("Menu")
    manager.switch_to("Game")
    assert not _is_live(menu)

    manager.switch_to("Menu")

    assert _is_live(menu)
    assert menu.entries == 2


def test_switching_to_the_current_scene_enters_it_afresh() -> None:
    _, manager, menu, _ = _app()
    manager.switch_to("Menu")

    manager.switch_to("Menu")

    assert _is_live(menu)
    assert menu.entries == 2


def test_a_popped_scene_pushed_again_has_its_systems() -> None:
    _, manager, _, game = _app()
    manager.switch_to("Menu")
    manager.push_scene("Game")
    manager.pop_scene()

    manager.push_scene("Game")

    assert _is_live(game)


def test_a_layer_added_again_has_its_systems() -> None:
    app, manager, _, _ = _app()
    hud = _Named(app._event_dispatcher, "Hud")
    manager.register(hud)
    manager.switch_to("Menu")
    manager.add_layer("Hud")
    manager.remove_layer("Hud")

    manager.add_layer("Hud")

    assert _is_live(hud)


def test_entering_again_through_a_transition_has_its_systems() -> None:
    _, manager, menu, _ = _app()
    manager.switch_to("Menu")
    manager.switch_to("Game")
    fade = FadeTransition(TransitionConfig(duration=0.1))

    manager.switch_to("Menu", transition=fade)
    for _ in range(20):
        manager.update(0.02)

    assert manager.current_scene is menu
    assert _is_live(menu)


def test_registering_a_scene_twice_wires_it_once(
    caplog: pytest.LogCaptureFixture,
) -> None:
    _, manager, menu, _ = _app()
    scope = menu.scope

    with caplog.at_level(logging.WARNING):
        manager.register(menu)

    assert _systems(menu) == ENGINE_SYSTEMS
    assert menu.scope is scope
    assert "second system" not in caplog.text


def test_begin_keeps_a_scene_already_switched_to_as_it_is() -> None:
    """Systems added between the switch and `begin()` used to be dropped."""
    app, manager, menu, _ = _app()
    manager.switch_to("Menu")
    ticker = _Ticker()
    menu.system_manager.register(ticker)

    app.begin(menu)
    for _ in range(5):
        app.step()

    assert ticker.ticks == 5
    assert menu.entries == 1
    assert _systems(menu) == ENGINE_SYSTEMS + 1


def test_removals_are_reported_once_after_entering_again() -> None:
    app, manager, menu, _ = _app()
    seen: list[EntityDestroyed] = []
    app._event_dispatcher.subscribe(EntityDestroyed, seen.append)
    manager.switch_to("Menu")
    manager.switch_to("Game")
    manager.switch_to("Menu")

    entity = menu.entity_manager.create_entity()
    menu.entity_manager.remove_entity(entity.id)

    assert len(seen) == 1
