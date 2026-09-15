"""Every shader in the backend compiles and links.

A GLSL error is a runtime error: nothing compiles a shader until the pass
or effect that owns it first draws with it. `vignette.frag` had no test of
any kind and `bloom_composite.frag` is only reached once a demo runs with
bloom enabled, so a typo in either shipped and waited.

Linking, not just compiling, is the useful bar. A fragment shader reading
a varying its vertex shader does not write is a *link* error, and that is
exactly what breaks when the instance layout or a pass's interface
changes on one side only -- which is a live risk here, since
`materials.defaults` hands `DEFAULT_SPRITE_VERTEX` to shaders written
elsewhere.

The pairs below are how the engine itself compiles them; `PROGRAMS` is
checked against the shader directory, so a new shader fails this module
until it is listed.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

pytestmark = pytest.mark.integration

SHADER_DIR = (
    Path(__file__).resolve().parent.parent.parent
    / "pyguara"
    / "graphics"
    / "backends"
    / "moderngl"
    / "shaders"
)

FULLSCREEN = "fullscreen_quad.vert"

# vertex shader -> fragment shaders compiled against it, mirroring the
# pairings in `renderer.py`, `materials/defaults.py`, the passes and the
# vfx effects.
PROGRAMS: dict[str, tuple[str, ...]] = {
    "sprite.vert": ("sprite.frag",),
    "shape.vert": ("shape.frag",),
    "light.vert": ("light.frag",),
    "pulse_ring.vert": ("pulse_ring.frag",),
    FULLSCREEN: (
        "blit.frag",
        "bloom_composite.frag",
        "bloom_threshold.frag",
        "blur.frag",
        "composite.frag",
        "heat_haze.frag",
        "storm.frag",
        "vignette.frag",
    ),
}

PAIRS = [
    (vertex, fragment)
    for vertex, fragments in PROGRAMS.items()
    for fragment in fragments
]


def test_every_shader_file_is_covered() -> None:
    """A shader nobody compiles here is a shader nothing type-checks.

    This fails for a newly added file until it is paired above, which is
    the prompt to decide what it links against.
    """
    listed = set(PROGRAMS) | {frag for frags in PROGRAMS.values() for frag in frags}
    on_disk = {
        path.name for path in SHADER_DIR.iterdir() if path.suffix in {".vert", ".frag"}
    }

    assert on_disk == listed


@pytest.mark.parametrize(
    ("vertex", "fragment"), PAIRS, ids=[f"{v}+{f}" for v, f in PAIRS]
)
def test_the_pair_compiles_and_links(vertex: str, fragment: str, gl_ctx: Any) -> None:
    program = gl_ctx.program(
        vertex_shader=(SHADER_DIR / vertex).read_text(),
        fragment_shader=(SHADER_DIR / fragment).read_text(),
    )

    try:
        assert list(program) != []
    finally:
        program.release()
