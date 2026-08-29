"""Regression tests for the composition root (BOOT-1, BOOT-2, BOOT-3).

`_setup_container()`/`create_application()` never ran end to end before these
fixes: the default (Pygame) backend crashed on the first render, the
documented `python main.py` entry point raised before a window opened, and
the component registry silently lost every registration.
"""

import os
import subprocess
import sys

import pygame
import pytest

os.environ["SDL_VIDEODRIVER"] = "dummy"

from pyguara.application.bootstrap import create_application, _setup_container
from pyguara.prefabs.registry import ComponentRegistry
from games.boot_process.scenes import BootScene


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

    assert len(registry.list_components()) == 18
    assert registry.get("Transform") is not None


@pytest.mark.integration
def test_default_pygame_backend_does_not_resolve_a_render_graph(app):
    """BOOT-1: the Pygame stub is resolvable but is not a real RenderGraph."""
    assert app._render_graph is None


@pytest.mark.integration
def test_render_completes_without_raising_on_default_backend(app):
    """BOOT-1: `_render()` must use the direct path, not the GL graph path."""
    app._render()


@pytest.mark.integration
def test_boot_scene_constructs_with_dispatcher_only(app):
    """BOOT-2: `BootScene` takes only a dispatcher, matching `main.py`'s call."""
    scene = BootScene(app._event_dispatcher)

    assert scene.event_dispatcher is app._event_dispatcher


@pytest.mark.integration
def test_documented_entry_point_boots_and_runs(app):
    """`python main.py` (BOOT-1 + BOOT-2 + BOOT-3 combined) starts and ticks."""
    scene = BootScene(app._event_dispatcher)

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
def test_main_py_starts_without_crashing():
    """BOOT-2: `python main.py` must not raise before a window opens.

    `main.py` has no built-in way to stop the loop, so we run it as a
    subprocess and treat "still running after the timeout" as success. A
    crash (BOOT-1/2/3 regressing) exits early with a non-zero code instead.
    """
    env = {**os.environ, "SDL_VIDEODRIVER": "dummy", "SDL_AUDIODRIVER": "dummy"}

    proc = subprocess.Popen(
        [sys.executable, "main.py"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=env,
    )
    try:
        _, stderr = proc.communicate(timeout=2)
        pytest.fail(f"main.py exited early (code {proc.returncode}):\n{stderr}")
    except subprocess.TimeoutExpired:
        proc.terminate()
        proc.wait(timeout=5)
