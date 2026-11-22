"""Code hot-reload: a running system takes its module's new code.

Each test writes a real module to a temporary directory, imports it, and
edits it on disk, so `importlib.reload` runs as it does in a game.
"""

from __future__ import annotations

import itertools
import os
import sys
import textwrap
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from pyguara.dev.code_reload import SystemCodeReloader
from pyguara.systems.manager import SystemManager

_names = itertools.count()

COUNTER = """
class Counter:
    def __init__(self, start):
        self.count = start

    def update(self, dt):
        self.count += {step}
"""


class Game:
    """A module on disk, a manager with its system, and a reloader."""

    def __init__(self, directory: Path) -> None:
        self.name = f"reload_game_{next(_names)}"
        self.path = directory / f"{self.name}.py"
        self.manager = SystemManager()
        self.reloader = SystemCodeReloader(lambda: [self.manager])

    def write(self, source: str) -> None:
        mtime = self.path.stat().st_mtime if self.path.exists() else 0.0
        self.path.write_text(textwrap.dedent(source), encoding="utf-8")
        # A later mtime even within the filesystem's resolution, so both the
        # watcher and the import system see an edit.
        os.utime(self.path, (mtime + 2, mtime + 2))

    def load(self) -> Any:
        __import__(self.name)
        return sys.modules[self.name]


@pytest.fixture
def game(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Game]:
    monkeypatch.syspath_prepend(str(tmp_path))
    monkeypatch.setattr(sys, "dont_write_bytecode", True)
    made = Game(tmp_path)
    yield made
    made.reloader.stop()
    sys.modules.pop(made.name, None)


def _counter(game: Game, step: int = 1, start: int = 0) -> Any:
    game.write(COUNTER.format(step=step))
    module = game.load()
    system = module.Counter(start)
    game.manager.register(system)
    return system


def test_a_reloaded_system_runs_the_new_code_and_keeps_its_state(game: Game) -> None:
    system = _counter(game, step=1, start=5)
    game.manager.update(1 / 60)
    assert system.count == 6

    game.write(COUNTER.format(step=10))
    result = game.reloader.reload(game.name)

    assert result.error is None
    assert result.systems == 1
    game.manager.update(1 / 60)
    assert system.count == 16
    assert game.manager.get_all_systems() == [system]


def test_it_is_found_by_its_old_class_and_its_new_one(game: Game) -> None:
    system = _counter(game)
    old = type(system)

    game.write(COUNTER.format(step=2))
    game.reloader.reload(game.name)
    new = type(system)

    assert new is not old
    assert game.manager.get_system(old) is system
    assert game.manager.get_system(new) is system
    game.manager.unregister(new)
    assert game.manager.get_system(old) is None
    assert game.manager.system_count == 0


@pytest.mark.parametrize(
    "broken",
    [
        "class Counter(:\n",
        "raise RuntimeError('half written')\n",
        COUNTER.format(step=2)
        + "\nfrom enum import Enum\nclass Mode(Enum):\n    A = 1\n",
    ],
    ids=["syntax error", "raises on import", "defines a non-system"],
)
def test_a_failed_reload_leaves_the_old_code_running(game: Game, broken: str) -> None:
    system = _counter(game, step=1)
    module = sys.modules[game.name]
    before = dict(vars(module))

    game.write(broken)
    result = game.reloader.reload(game.name)

    assert result.error is not None
    assert result.systems == 0
    assert vars(module) == before
    game.manager.update(1 / 60)
    assert system.count == 1


def test_a_syntax_error_says_where(game: Game) -> None:
    _counter(game)
    game.write("class Counter(:\n")

    result = game.reloader.reload(game.name)

    assert result.error is not None
    assert "SyntaxError" in result.error
    assert f"{game.name}.py" in result.error


def test_on_reload_sets_up_what_the_new_code_needs(game: Game) -> None:
    system = _counter(game)
    game.write(
        """
        class Counter:
            def on_reload(self):
                self.hits = []

            def update(self, dt):
                self.hits.append(dt)
        """
    )

    assert game.reloader.reload(game.name).error is None
    game.manager.update(0.5)
    assert system.hits == [0.5]
    assert system.count == 0


def test_an_on_reload_that_raises_puts_everything_back(game: Game) -> None:
    system = _counter(game)
    old = type(system)
    game.write(
        """
        class Counter:
            def on_reload(self):
                raise ValueError("no")

            def update(self, dt):
                pass
        """
    )

    result = game.reloader.reload(game.name)

    assert result.error is not None
    assert "ValueError" in result.error
    assert type(system) is old
    assert sys.modules[game.name].Counter is old
    game.manager.update(1 / 60)
    assert system.count == 1


def test_a_class_the_new_code_dropped_keeps_its_old_code(game: Game) -> None:
    system = _counter(game)
    game.write("class Other:\n    def update(self, dt):\n        pass\n")

    result = game.reloader.reload(game.name)

    assert result.error is None
    assert result.systems == 0
    game.manager.update(1 / 60)
    assert system.count == 1


def test_only_game_modules_of_nothing_but_systems_are_watched(
    game: Game, tmp_path: Path
) -> None:
    from pyguara.systems.manager import SystemManager as EngineThing

    _counter(game)
    mixed_name = f"{game.name}_mixed"
    (tmp_path / f"{mixed_name}.py").write_text(
        "class Data:\n    pass\n\nclass Mover:\n    def update(self, dt):\n        pass\n",
        encoding="utf-8",
    )
    mixed = __import__(mixed_name)
    game.manager.register(mixed.Mover())

    class EngineSystem(EngineThing):
        def update(self, dt: float) -> None:
            pass

    EngineSystem.__module__ = "pyguara.systems.example"
    game.manager.register(EngineSystem())
    try:
        game.reloader.refresh()
        assert game.reloader.watched_modules == (game.name,)
    finally:
        sys.modules.pop(mixed_name, None)


def test_an_edit_on_disk_is_applied_at_the_next_drain(game: Game) -> None:
    system = _counter(game)
    game.reloader.refresh()

    game.write(COUNTER.format(step=100))
    game.reloader.check_now()
    [result] = game.reloader.drain()

    assert result.module == game.name
    assert result.error is None
    game.manager.update(1 / 60)
    assert system.count == 100
    assert game.reloader.drain() == []


def test_a_built_game_refuses_code_reload(monkeypatch: pytest.MonkeyPatch) -> None:
    import pygame

    from pyguara.application.bootstrap import create_headless_application

    os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
    app = create_headless_application()
    try:
        monkeypatch.setattr(sys, "frozen", True, raising=False)
        with pytest.raises(RuntimeError, match="development tool"):
            app.enable_code_hot_reload()
    finally:
        app.shutdown()
        pygame.quit()


def test_the_application_applies_an_edit_between_frames(game: Game) -> None:
    import pygame

    from pyguara.application.bootstrap import create_headless_application
    from tests.integration._scenes import ClearScene

    os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
    app = create_headless_application()
    try:
        scene = ClearScene(app._event_dispatcher)
        app.begin(scene)
        game.write(COUNTER.format(step=1))
        system = game.load().Counter(0)
        scene.system_manager.register(system)
        app.enable_code_hot_reload()
        assert app._code_reloader is not None
        assert game.name in app._code_reloader.watched_modules

        game.write(COUNTER.format(step=7))
        app._code_reloader.check_now()
        app._update(1 / 60)
        scene.system_manager.update(1 / 60)

        assert system.count == 7
    finally:
        app.shutdown()
        pygame.quit()
