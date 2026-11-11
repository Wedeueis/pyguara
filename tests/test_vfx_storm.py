"""Tests for `StormEffect`'s parameter plumbing.

What the rain and the bolt *look like* is the fragment shader's business,
held to ModernGL's on wgpu by `tests/integration/test_wgpu_graph.py`; these
cover the half that needs no GPU -- that the caller's weather reaches the
uniforms, and that a strike is a distinct event rather than a value that
drifts every frame.
"""

from unittest.mock import MagicMock

from pyguara.common.random import RandomStream
from pyguara.graphics.vfx.effects.storm import STORM, StormEffect
from tests.recording_device import RecordingDevice


def make_effect(**kwargs) -> StormEffect:
    """Build a StormEffect; it compiles nothing until it runs."""
    return StormEffect(**kwargs)


def apply_once(effect: StormEffect) -> dict[str, object]:
    """Apply the effect to mock framebuffers and return the uniforms set."""
    device = RecordingDevice()
    input_fbo, output_fbo = MagicMock(), MagicMock()
    input_fbo.width, input_fbo.height = 800, 600

    effect.apply(device, input_fbo, output_fbo)
    assert device.last.shader is STORM
    assert device.last.inputs == {"u_texture": input_fbo}
    assert device.last.output is output_fbo
    return device.last.uniforms


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
    def test_the_shader_comes_in_both_languages(self) -> None:
        """GLSL for ModernGL, WGSL for wgpu, until stage E."""
        assert STORM.glsl is not None and "u_bolt_seed" in STORM.glsl
        assert "u_bolt_seed: f32" in STORM.wgsl_source()

    def test_release_is_harmless(self) -> None:
        """The device owns the compiled shader; an effect has nothing to free."""
        effect = make_effect()

        effect.release()
        effect.release()
