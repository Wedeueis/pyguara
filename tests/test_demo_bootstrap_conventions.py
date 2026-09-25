"""A demo that builds a `RenderGraph` must share the graph's framebuffers.

`RenderGraph` constructs a `FramebufferManager` internally, and every pass
resolves its buffers through *that* one. A demo that builds a second manager
gets a parallel set of framebuffers the graph never looks at: wasted VRAM
today, and a trap later, because a named buffer claimed on the demo's manager
silently never reaches the graph.

`mourisco_ressonancia` did exactly that until it was fixed; the two demos
written after it avoid it and say why in a comment. This is the guard that
keeps the next one from repeating it -- a source check rather than a runtime
one, because the ModernGL demos need a GL context the test suite has no way
to provide (see `tests/integration/test_demos_render.py`).
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
    source = bootstrap.read_text()

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

# Not yet converted (#196). This set only ever shrinks: a demo removed from
# it can never drift back, because the test below then holds it to the
# convention. Delete the set, and this comment, when it empties.
NOT_YET_CONVERTED = {
    "guara_falcao",
    "mourisco_ressonancia",
    "protocolo_bandeira",
    "quintal_cerrado",
    "tamandua_murundus",
    "true_coral",
    "vinagre_matilha",
}

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

    Hand-rolling it is not just duplication -- it drifts. Before #196, **no
    demo at all** registered `RandomService`, so
    `protocolo_bandeira/ai_behaviors.py` reached for bare `random.random()`
    and that demo cannot be reproduced or replayed; only two of twelve
    registered `SpatialHash`. Neither could have happened to a demo that
    started from `create_container()`.

    This is the guard that keeps the list of hand-wired demos shrinking
    rather than growing.
    """
    demo = bootstrap.parent.name
    if demo in HAND_WIRED_ON_PURPOSE or demo in NOT_YET_CONVERTED:
        pytest.skip(f"{demo} is a known exception; see the sets above")

    assert _calls_engine_bootstrap(bootstrap.read_text()), (
        f"{demo}/bootstrap.py wires its own container. Call "
        "`pyguara.application.bootstrap.create_container()` and add only "
        "what is specific to this demo on top of it."
    )


def test_the_exception_sets_name_demos_that_exist() -> None:
    """A renamed or deleted demo must not leave a waiver behind.

    A stale name in `NOT_YET_CONVERTED` is a waiver for nothing, and would
    quietly stop the set from ever emptying.
    """
    demos = {path.parent.name for path in BOOTSTRAPS}
    stale = (HAND_WIRED_ON_PURPOSE | NOT_YET_CONVERTED) - demos

    assert stale == set(), f"{stale} are named as exceptions but do not exist"
