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
