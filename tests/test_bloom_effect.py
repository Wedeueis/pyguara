"""Resource bookkeeping for `BloomEffect`.

Against a mock context, like `test_post_process_stack.py`: what the bloom
*looks* like needs a live GL context and belongs with the ModernGL
integration tests, but how many GL objects it creates per frame is
countable here -- and was wrong.
"""

from unittest.mock import MagicMock, mock_open, patch

from pyguara.graphics.vfx.effects.bloom import BloomEffect


def make_effect() -> tuple[BloomEffect, MagicMock]:
    """Build a bloom effect over a mock context, returning both."""
    ctx = MagicMock()
    ctx.program.side_effect = lambda *a, **k: MagicMock()
    ctx.vertex_array.side_effect = lambda *a, **k: MagicMock()
    with patch("builtins.open", mock_open(read_data="shader source")):
        effect = BloomEffect(ctx, MagicMock())
    return effect, ctx


def test_the_vaos_are_built_once_at_construction() -> None:
    """One VAO per program, and none of them per-frame."""
    _, ctx = make_effect()

    assert ctx.vertex_array.call_count == 3


def test_applying_the_effect_creates_no_gl_objects() -> None:
    """`apply()` rebuilt all three VAOs on every frame -- two were released
    each time, and the third was overwritten without being released at all,
    leaking one VAO per frame for the life of the effect. A fullscreen-quad
    VAO binds no buffers (the vertices come from `gl_VertexID`), so there
    was never anything about it to rebuild."""
    effect, ctx = make_effect()
    before = ctx.vertex_array.call_count

    for _ in range(3):
        effect.apply(ctx, MagicMock(), MagicMock())

    assert ctx.vertex_array.call_count == before


def test_release_drops_every_vao() -> None:
    """Whatever `apply()` stops creating still has to be cleaned up once."""
    effect, _ = make_effect()
    vaos = [effect._threshold_vao, effect._blur_vao, effect._composite_vao]

    effect.release()

    for vao in vaos:
        assert vao is not None
        vao.release.assert_called_once()
    assert effect._threshold_vao is None
    assert effect._blur_vao is None
    assert effect._composite_vao is None


def test_release_is_idempotent() -> None:
    """A stack releasing an effect twice must not raise on the second."""
    effect, _ = make_effect()

    effect.release()
    effect.release()
