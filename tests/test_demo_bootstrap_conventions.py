"""A demo that builds a `RenderGraph` must share the graph's framebuffers.

`RenderGraph` constructs a `FramebufferManager`, and every pass
resolves its buffers through that one. A demo that builds a second
manager gets framebuffers the graph never reads, and a named buffer
declared on it never reaches the graph.

A source check, not a runtime one, so it needs no GPU.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

GAMES_DIR = Path(__file__).resolve().parent.parent / "games"

BOOTSTRAPS = sorted(GAMES_DIR.glob("*/bootstrap.py"))

CONSTRUCTS_A_MANAGER = re.compile(r"\bFramebufferManager\s*\(")


@pytest.mark.parametrize("bootstrap", BOOTSTRAPS, ids=lambda p: str(p.parent.name))
def test_no_demo_builds_its_own_framebuffer_manager(bootstrap: Path) -> None:
    source = bootstrap.read_text(encoding="utf-8")

    assert not CONSTRUCTS_A_MANAGER.search(source), (
        f"{bootstrap.parent.name}/bootstrap.py constructs its own "
        "FramebufferManager. Use `render_graph.fbo_manager` -- a second "
        "manager allocates a parallel set of buffers the graph never reads."
    )


def test_the_glob_found_the_demos() -> None:
    """A typo'd path would make every test above pass vacuously."""
    assert len(BOOTSTRAPS) >= 5


# `boot_process` is module 1, and assembling the container by hand *is* its
# lesson -- it is the one demo that should not call the engine's bootstrap.
HAND_WIRED_ON_PURPOSE = {"boot_process"}


ENGINE_BOOTSTRAP_FACTORIES = frozenset(
    {"create_container", "create_application", "create_sandbox_application"}
)


def _calls_engine_bootstrap(source: str) -> bool:
    """Whether `source` actually calls one of the engine's factories.

    Parsed rather than matched: every one of these bootstraps *names*
    `create_container()` in a docstring, so a regex for it reports every
    file as compliant -- including one whose body builds a bare
    `DIContainer()`. Caught by regressing a converted demo and watching the
    check stay green.

    Args:
        source: A bootstrap module's source text.

    Returns:
        True if a call to an engine bootstrap factory appears.
    """
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        name = (
            func.id
            if isinstance(func, ast.Name)
            else func.attr
            if isinstance(func, ast.Attribute)
            else None
        )
        if name in ENGINE_BOOTSTRAP_FACTORIES:
            return True
    return False


@pytest.mark.parametrize("bootstrap", BOOTSTRAPS, ids=lambda p: str(p.parent.name))
def test_a_demo_builds_its_container_through_the_engine(bootstrap: Path) -> None:
    """A demo asks the engine for the wiring every game needs.

    Hand-rolling it is not just duplication -- it drifts. Before #196, no
    demo at all registered `RandomService`, so
    `protocolo_bandeira/ai_behaviors.py` reached for bare `random.random()`
    and that demo cannot be reproduced or replayed; only two of twelve
    registered `SpatialHash`. Neither could have happened to a demo that
    started from `create_container()`.

    Every demo but `boot_process` now goes through the engine, so this
    holds the line rather than chasing a backlog.
    """
    demo = bootstrap.parent.name
    if demo in HAND_WIRED_ON_PURPOSE:
        pytest.skip(f"{demo} is hand-wired on purpose; see the set above")

    assert _calls_engine_bootstrap(bootstrap.read_text(encoding="utf-8")), (
        f"{demo}/bootstrap.py wires its own container. Call "
        "`pyguara.application.bootstrap.create_container()` and add only "
        "what is specific to this demo on top of it."
    )


def test_the_exception_sets_name_demos_that_exist() -> None:
    """A renamed or deleted demo must not leave a waiver behind.

    A stale name is a waiver for nothing, and the next demo to take that
    name would inherit it silently.
    """
    demos = {path.parent.name for path in BOOTSTRAPS}
    stale = HAND_WIRED_ON_PURPOSE - demos

    assert stale == set(), f"{stale} are named as exceptions but do not exist"


# `RenderGraph` builds the one real manager every pass resolves through.
# Anything else that constructs one produces a parallel set of buffers that
# the graph never reads.
PYGUARA_DIR = Path(__file__).resolve().parent.parent / "pyguara"
MAY_BUILD_A_MANAGER = {PYGUARA_DIR / "graphics" / "pipeline" / "graph.py"}


def _builds_a_framebuffer_manager(path: Path) -> bool:
    """Whether `path` calls `FramebufferManager(...)`.

    Args:
        path: A module to parse.

    Returns:
        True if the constructor is called anywhere in it.
    """
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Call):
            func = node.func
            name = (
                func.id
                if isinstance(func, ast.Name)
                else func.attr
                if isinstance(func, ast.Attribute)
                else None
            )
            if name == "FramebufferManager":
                return True
    return False


def test_only_the_render_graph_builds_a_framebuffer_manager() -> None:
    """The engine must not hand games an orphaned manager either.

    The `FramebufferManager` registered in the container has to be the
    `RenderGraph`'s own. If bootstrap built a second one and registered
    that, a game declaring an HDR buffer on `container.get(
    FramebufferManager)` would declare it on a manager no pass reads.
    """
    offenders = sorted(
        str(path.relative_to(PYGUARA_DIR))
        for path in PYGUARA_DIR.rglob("*.py")
        if path not in MAY_BUILD_A_MANAGER and _builds_a_framebuffer_manager(path)
    )

    assert offenders == [], (
        f"{offenders} construct a FramebufferManager. Only RenderGraph may; "
        "everything else uses `render_graph.fbo_manager`, or a second set of "
        "buffers is allocated that no pass ever reads."
    )


SCENES = sorted(GAMES_DIR.glob("*/scenes.py"))

CONSTRUCTS_A_CAMERA = re.compile(r"\bCamera2D\s*\(")
ASSIGNS_THE_SCENE_CAMERA = re.compile(r"\bself\.camera\s*=")


@pytest.mark.parametrize("scenes", SCENES, ids=lambda p: str(p.parent.name))
def test_a_scene_with_its_own_camera_assigns_it(scenes: Path) -> None:
    """`Scene.camera` is the camera the scene renders with.

    Studio's viewport, its picking and the transform gizmo read it. A
    scene that overrides `render()` and draws with a camera of its own
    must assign that camera to the attribute. Otherwise the frame looks
    right and the editor draws its gizmo away from the entity.
    """
    source = scenes.read_text(encoding="utf-8")
    if not CONSTRUCTS_A_CAMERA.search(source):
        return

    assert ASSIGNS_THE_SCENE_CAMERA.search(source), (
        f"{scenes.parent.name}/scenes.py builds a Camera2D of its own but "
        f"never assigns `self.camera`. Everything that maps world to "
        f"screen from outside the frame -- Studio's viewport, picking and "
        f"the gizmo -- reads `Scene.camera`, and would use the base "
        f"class's untouched one at the origin instead."
    )
