"""Tests for `HeatHazeEffect`'s parameter plumbing.

What the shimmer and the dust *look like* is the fragment shader's
business and needs a GL context to judge; these cover the half that does
not -- that the caller's heat reaches the uniforms, and that a gust is a
decaying kick on top of the standing dust rather than a value the caller
has to wind back down itself.
"""

from unittest.mock import MagicMock, patch

from pyguara.graphics.vfx.effects.heat_haze import GUST_DECAY, HeatHazeEffect


def make_effect(**kwargs) -> HeatHazeEffect:
    """Build a HeatHazeEffect over a mock context, with no shader compiled."""
    ctx = MagicMock()
    ctx.program.return_value = MagicMock()
    ctx.vertex_array.return_value = MagicMock()
    return HeatHazeEffect(ctx, **kwargs)


def apply_once(effect: HeatHazeEffect) -> dict[str, object]:
    """Apply the effect to mock framebuffers and return the uniforms set."""
    ctx = MagicMock()
    input_fbo, output_fbo = MagicMock(), MagicMock()
    input_fbo.width, input_fbo.height = 800, 600

    uniforms: dict[str, object] = {}
    program = MagicMock()
    program.__setitem__ = lambda _self, key, value: uniforms.__setitem__(key, value)
    effect._program = program

    effect.apply(ctx, input_fbo, output_fbo)
    return uniforms


class TestUniforms:
    def test_the_heat_reaches_the_shader(self) -> None:
        effect = make_effect()
        effect.haze = 7.5
        effect.haze_scale = 9.0
        effect.wind = -0.4
        effect.horizon = 0.35
        effect.sun = 0.2

        uniforms = apply_once(effect)

        assert uniforms["u_haze"] == 7.5
        assert uniforms["u_haze_scale"] == 9.0
        assert uniforms["u_wind"] == -0.4
        assert uniforms["u_horizon"] == 0.35
        assert uniforms["u_sun"] == 0.2

    def test_the_resolution_comes_from_the_input_buffer(self) -> None:
        """Not from the window: the effect runs on whatever it is handed,
        which at half-resolution is not the window's size."""
        uniforms = apply_once(make_effect())

        assert uniforms["u_resolution"] == (800.0, 600.0)

    def test_the_clock_is_the_accumulated_update_time(self) -> None:
        effect = make_effect()
        effect.update(0.25)
        effect.update(0.25)

        assert apply_once(effect)["u_time"] == 0.5

    def test_nothing_is_drawn_without_a_program(self) -> None:
        effect = make_effect()
        effect._program = None
        output_fbo = MagicMock()

        effect.apply(MagicMock(), MagicMock(), output_fbo)

        output_fbo.bind.assert_not_called()


class TestGusts:
    def test_a_gust_rides_on_top_of_the_standing_dust(self) -> None:
        effect = make_effect(dust=0.2)
        effect.gust(0.5)

        assert apply_once(effect)["u_dust"] == 0.7
        # The standing level itself is the caller's, and is untouched.
        assert effect.dust == 0.2

    def test_gusts_accumulate(self) -> None:
        """A firefight raises more dust than a single shot."""
        effect = make_effect()
        effect.gust(0.3)
        effect.gust(0.3)

        assert effect.gust_level == 0.6

    def test_the_combined_dust_never_exceeds_full(self) -> None:
        """A long firefight should not white the frame out."""
        effect = make_effect(dust=0.8)
        for _ in range(10):
            effect.gust(0.5)

        assert effect.gust_level == 1.0
        assert apply_once(effect)["u_dust"] == 1.0

    def test_a_gust_settles_on_its_own(self) -> None:
        effect = make_effect()
        effect.gust(1.0)
        effect.update(0.5)

        assert effect.gust_level == 1.0 - GUST_DECAY * 0.5

    def test_a_gust_settles_no_further_than_clear(self) -> None:
        effect = make_effect()
        effect.gust(0.2)
        effect.update(10.0)

        assert effect.gust_level == 0.0


class TestResources:
    def test_the_shader_is_compiled_from_the_heat_haze_sources(self) -> None:
        ctx = MagicMock()
        with patch("pathlib.Path.read_text", return_value="// shader") as read_text:
            HeatHazeEffect(ctx)

        assert read_text.call_count == 2
        ctx.program.assert_called_once()

    def test_release_drops_both_gpu_objects(self) -> None:
        effect = make_effect()
        program, vao = effect._program, effect._vao

        effect.release()

        program.release.assert_called_once()
        vao.release.assert_called_once()
        assert effect._program is None
        assert effect._vao is None
