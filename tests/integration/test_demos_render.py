"""Every demo must actually draw something.

`games/validate_demos.py` boots four demos and checks they do not crash. Not
crashing is a weaker property than rendering: a renderer that silently
submitted nothing, or cleared to a colour and drew no entities, passes it
comfortably.

These tests boot each demo headlessly and assert the frame is not a single
flat colour. That is deliberately a low bar -- it catches "the render path
produced nothing", not "the render path produced the wrong thing" -- but it is
the bar nothing was holding.

Scope: this exercises the pygame path only, and it reads the surface the
renderer blitted onto. It says nothing about whether a window appears on
screen; see docs/guides/agent-visual-inspection.md for why those differ.
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools.agent_view import DEMOS, is_blank  # noqa: E402

# boot_process only opens a window and draws nothing; that is its whole point
# as tutorial module 1, so a flat frame there is correct rather than a defect.
DEMOS_THAT_DRAW = sorted(set(DEMOS) - {"boot_process"})

FRAMES = 20


def render_demo(demo: str):
    """Boot a demo headlessly and return its last frame.

    Args:
        demo: Key from `tools.agent_view.DEMOS`.

    Returns:
        The display surface after `FRAMES` frames.
    """
    import pygame

    from pyguara.application.application import Application
    from pyguara.events.dispatcher import EventDispatcher

    bootstrap_mod, scenes_mod, scene_name = DEMOS[demo]
    configure = importlib.import_module(bootstrap_mod).configure_game_container
    scene_class = getattr(importlib.import_module(scenes_mod), scene_name)

    container = configure()
    app = container.get(Application)

    tick = 0
    captured: list[pygame.Surface] = []
    original_render = app._render

    def render_and_capture() -> None:
        nonlocal tick
        original_render()
        tick += 1
        if tick >= FRAMES:
            surface = pygame.display.get_surface()
            if surface is not None:
                # Copy: the live surface keeps being drawn over after this.
                captured.append(surface.copy())
            app._is_running = False

    app._render = render_and_capture  # type: ignore[method-assign]

    dispatcher = (
        container.get(EventDispatcher)
        if EventDispatcher in container._services
        else app._event_dispatcher
    )
    app.run(starting_scene=scene_class(dispatcher))

    assert captured, f"{demo} never reached frame {FRAMES}"
    return captured[0]


@pytest.mark.integration
@pytest.mark.parametrize("demo", DEMOS_THAT_DRAW)
def test_the_demo_draws_something(demo: str) -> None:
    """The demo's frame is not a single flat colour."""
    surface = render_demo(demo)

    assert not is_blank(surface), (
        f"{demo} rendered a flat frame after {FRAMES} frames. The render path "
        f"produced nothing -- entities, sprites or the UI never reached the "
        f"renderer. Reproduce with: "
        f"uv run python tools/agent_view.py {demo} --frames {FRAMES}"
    )


@pytest.mark.integration
def test_a_demo_that_draws_nothing_is_still_detected() -> None:
    """The check is only worth anything if it can fail.

    boot_process opens a window and draws nothing, so it doubles as the
    negative control: if this ever stops reading as blank, `is_blank` has
    become too lax and every assertion above is worthless.
    """
    assert is_blank(render_demo("boot_process"))
