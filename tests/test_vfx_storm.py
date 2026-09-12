"""Tests for `StormEffect`'s parameter plumbing.

What the rain and the bolt *look like* is the fragment shader's business
and needs a GL context to judge; these cover the half that does not --
that the caller's weather reaches the uniforms, and that a strike is a
distinct event rather than a value that drifts every frame.
"""

from unittest.mock import MagicMock, patch

from pyguara.common.random import RandomStream
from pyguara.graphics.vfx.effects.storm import StormEffect


def make_effect(**kwargs) -> StormEffect:
    """Build a StormEffect over a mock context, with no shader compiled."""
    ctx = MagicMock()
    ctx.program.return_value = MagicMock()
    ctx.vertex_array.return_value = MagicMock()
    return StormEffect(ctx, **kwargs)


def apply_once(effect: StormEffect) -> dict[str, object]:
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
    def test_the_weather_reaches_the_shader(self) -> None:
        effect = make_effect()
        effect.rain = 0.75
        effect.wind = -0.3
        effect.flash = 0.4
        effect.bolt = 0.9

        uniforms = apply_once(effect)

        assert uniforms["u_rain"] == 0.75
        assert uniforms["u_wind"] == -0.3
        assert uniforms["u_flash"] == 0.4
        assert uniforms["u_bolt"] == 0.9

    def test_the_resolution_comes_from_the_input_buffer(self) -> None:
        """Not from the window: the effect runs on whatever it is handed,
        which at half-resolution is not the window's size."""
        uniforms = apply_once(make_effect())

        assert uniforms["u_resolution"] == (800.0, 600.0)

    def test_the_clock_is_the_accumulated_update_time(self) -> None:
        effect = make_effect()
        effect.update(0.5)
        effect.update(0.25)

        assert effect.time == 0.75
        assert apply_once(effect)["u_time"] == 0.75

    def test_nothing_is_drawn_without_a_program(self) -> None:
        effect = make_effect()
        effect.release()

        ctx, input_fbo, output_fbo = MagicMock(), MagicMock(), MagicMock()
        effect.apply(ctx, input_fbo, output_fbo)

        output_fbo.bind.assert_not_called()


class TestStrike:
    def test_a_strike_reshapes_the_bolt(self) -> None:
        """The seed has to change, or every strike is the same bolt."""
        effect = make_effect(rng=RandomStream(7))
        effect.strike()
        first = apply_once(effect)["u_bolt_seed"]
        effect.strike()

        assert apply_once(effect)["u_bolt_seed"] != first

    def test_a_strike_can_be_placed(self) -> None:
        effect = make_effect()
        effect.strike(x=0.25)

        assert effect.bolt_x == 0.25

    def test_an_unplaced_strike_stays_clear_of_the_edges(self) -> None:
        """A bolt at x=0 is mostly off-frame, which reads as a bug."""
        effect = make_effect(rng=RandomStream(3))

        for _ in range(50):
            effect.strike()
            assert 0.1 <= effect.bolt_x <= 0.9

    def test_a_strike_does_not_light_itself(self) -> None:
        """Brightness is an envelope the caller owns; `strike()` only
        reshapes. Setting `bolt` here would make every strike a step
        function, which is what lightning is not."""
        effect = make_effect()
        effect.strike()

        assert effect.bolt == 0.0
        assert effect.flash == 0.0


class TestResources:
    def test_the_shader_is_compiled_from_the_storm_sources(self) -> None:
        ctx = MagicMock()
        with patch(
            "pyguara.graphics.vfx.effects.storm.Path.read_text",
            return_value="// shader",
        ):
            StormEffect(ctx)

        ctx.program.assert_called_once()

    def test_release_drops_both_gpu_objects(self) -> None:
        effect = make_effect()
        program, vao = effect._program, effect._vao

        effect.release()

        program.release.assert_called_once()
        vao.release.assert_called_once()
        assert effect._program is None
