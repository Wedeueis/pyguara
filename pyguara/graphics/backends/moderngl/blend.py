"""The GL blend state, and who owns it.

Blending used to be switched on by `PygameGLWindow.open()`, which meant a
renderer built over any other context -- a standalone one in a test, a second
window backend -- silently drew unblended, and `LightPass` had to restore the
alpha pair from a remembered constant after its additive stretch because there
was nothing to ask.

`ModernGLRenderer` owns it now: it applies `DEFAULT_BLEND_MODE` when it is
constructed and re-applies it at the start of every frame, so a pass that
leaves the state changed cannot bleed into the next one. A pass that needs a
different mode takes it through `blending()`, which puts the default back.

This module is also the place a third mode gets decided. Premultiplied alpha
in particular is not just another entry: `sprite.frag` multiplies the tint into
an unpremultiplied source, and the Pygame backend's `BLEND_RGBA_MULT` does the
same, so adding it here without changing both would make the two backends
disagree about what a tinted sprite looks like.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from enum import Enum

import moderngl


class BlendMode(Enum):
    """A named source/destination blend-factor pair."""

    ALPHA = "alpha"
    """Standard transparency: `src * a + dst * (1 - a)`."""

    ADDITIVE = "additive"
    """`src + dst`, so overlapping draws accumulate. Lights, not sprites."""


_BLEND_FUNCS: dict[BlendMode, tuple[int, int]] = {
    BlendMode.ALPHA: (moderngl.SRC_ALPHA, moderngl.ONE_MINUS_SRC_ALPHA),
    BlendMode.ADDITIVE: (moderngl.ONE, moderngl.ONE),
}

DEFAULT_BLEND_MODE = BlendMode.ALPHA
"""What the renderer sets up and what `blending()` restores."""


def apply_blend_mode(ctx: moderngl.Context, mode: BlendMode) -> None:
    """Enable blending on `ctx` and select `mode`'s factor pair.

    Args:
        ctx: The ModernGL context to set state on.
        mode: The blend mode to select.
    """
    ctx.enable(moderngl.BLEND)
    ctx.blend_func = _BLEND_FUNCS[mode]


@contextmanager
def blending(ctx: moderngl.Context, mode: BlendMode) -> Iterator[None]:
    """Draw under `mode`, then put `DEFAULT_BLEND_MODE` back.

    The restore is unconditional, so an exception inside the block cannot
    leave the context in a mode the next pass does not expect.

    Args:
        ctx: The ModernGL context to set state on.
        mode: The blend mode to select for the duration of the block.

    Yields:
        None.
    """
    apply_blend_mode(ctx, mode)
    try:
        yield
    finally:
        apply_blend_mode(ctx, DEFAULT_BLEND_MODE)
