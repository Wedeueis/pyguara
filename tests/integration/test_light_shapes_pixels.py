"""Real-GL pixel readback for the three light shapes.

`LightType.SPOT` and `DIRECTIONAL` are shapes cut in `light.frag`, so
there is nothing about them a CPU test can see -- `tests/test_lighting.py`
can prove the cone's cosine is precomputed and handed over, and no more.
Whether a fragment 30 degrees off the cone axis is actually dark is a
question only the GPU answers.

So this drives the real `LightPass` against a standalone context and a
real `FramebufferManager`, then reads the lightmap back. It is the same
shape as `test_moderngl_pixels.py`, for the same reason: the pass's other
tests run against mocks, and a mock cannot fail this.
"""

from __future__ import annotations

import math
from collections.abc import Iterator
from typing import Any

import numpy as np
import pytest

from pyguara.common.components import Transform
from pyguara.common.types import Color, Vector2
from pyguara.ecs.manager import EntityManager
from pyguara.graphics.components.camera import Camera2D
from pyguara.graphics.lighting.components import LightSource, LightType
from pyguara.graphics.lighting.light_system import LightingSystem
from pyguara.graphics.pipeline.framebuffer import FramebufferManager
from pyguara.graphics.pipeline.passes.light_pass import LIGHT_FBO_NAME, LightPass
from pyguara.graphics.pipeline.viewport import Viewport

pytestmark = pytest.mark.integration

_SIZE = 128
_CENTRE = _SIZE // 2


@pytest.fixture(scope="module")
def gl_ctx() -> Iterator[Any]:
    """A standalone GL context, or a skip on a machine without one."""
    moderngl = pytest.importorskip("moderngl")
    try:
        ctx = moderngl.create_standalone_context()
    except Exception as exc:  # pragma: no cover - depends on the machine
        pytest.skip(f"no standalone GL context available: {exc}")
    try:
        yield ctx
    finally:
        ctx.release()


class _Graph:
    """The one thing `LightPass.execute` reads off a render graph."""

    def __init__(self, fbo_manager: FramebufferManager) -> None:
        self.fbo_manager = fbo_manager


def render_light(gl_ctx: Any, light: LightSource) -> np.ndarray:
    """Draw one light into the lightmap and return the pixels.

    The light sits at the centre of the frame with the camera centred on
    it, so the readback is in the light's own frame regardless of what the
    world-to-screen transform does.

    Returns:
        An `(H, W, 3)` uint8 image of the lightmap.
    """
    entity_manager = EntityManager()
    entity = entity_manager.create_entity()
    entity.add_component(Transform(position=Vector2(_CENTRE, _CENTRE)))
    entity.add_component(light)

    lighting = LightingSystem(entity_manager)
    lighting.update(0.0)

    fbo_manager = FramebufferManager(gl_ctx, _SIZE, _SIZE)
    light_pass = LightPass(gl_ctx, lighting)
    camera = Camera2D(_SIZE, _SIZE)
    camera.position = Vector2(_CENTRE, _CENTRE)
    light_pass.set_camera(camera, Viewport(0, 0, _SIZE, _SIZE))

    try:
        light_pass.execute(gl_ctx, _Graph(fbo_manager))
        fbo = fbo_manager.get_or_create(LIGHT_FBO_NAME)
        raw = np.frombuffer(fbo.fbo.read(components=3), dtype=np.uint8)
        # Flipped on the way out: GL's origin is bottom-left, so a raw
        # readback arrives with its rows upside down relative to the
        # screen. Every other readback path in this tree pre-flips for the
        # same reason (`loaders.py`, `draw_text`). Without it, a test of a
        # *clockwise* angle convention would silently be testing an
        # anticlockwise one.
        return np.flipud(raw.reshape((_SIZE, _SIZE, 3))).copy()
    finally:
        light_pass.release()
        fbo_manager.release_all()


def at_angle(image: np.ndarray, degrees: float, distance: int = 30) -> int:
    """Sample the red channel `distance` px from centre, along `degrees`.

    Angles run clockwise from screen +x, matching the cone convention:
    screen Y points down, so a positive angle moves down the image.
    """
    radians = math.radians(degrees)
    x = int(round(_CENTRE + math.cos(radians) * distance))
    y = int(round(_CENTRE + math.sin(radians) * distance))
    return int(image[y, x, 0])


class TestPointLight:
    def test_a_point_light_is_bright_at_its_centre(self, gl_ctx: Any) -> None:
        image = render_light(
            gl_ctx,
            LightSource(color=Color(255, 0, 0), radius=60.0, intensity=1.0),
        )

        assert image[_CENTRE, _CENTRE, 0] > 200

    def test_a_point_light_falls_off_with_distance(self, gl_ctx: Any) -> None:
        image = render_light(
            gl_ctx,
            LightSource(color=Color(255, 0, 0), radius=60.0, intensity=1.0),
        )

        assert at_angle(image, 0, 10) > at_angle(image, 0, 40)

    def test_a_point_light_is_the_same_in_every_direction(self, gl_ctx: Any) -> None:
        """The baseline the cone tests are read against."""
        image = render_light(
            gl_ctx,
            LightSource(color=Color(255, 0, 0), radius=60.0, intensity=1.0),
        )

        # Not exactly equal: the quad spans an even number of pixels, so
        # its true centre falls between two of them and opposite samples
        # sit a half-pixel apart on the gradient.
        samples = [at_angle(image, d) for d in (0, 90, 180, 270)]
        assert max(samples) - min(samples) <= 8


class TestSpotLight:
    """`spot_angle` is the full opening, so 60 degrees reaches 30 either
    side of `spot_direction`."""

    def test_the_cone_lights_along_its_own_axis(self, gl_ctx: Any) -> None:
        image = render_light(
            gl_ctx,
            LightSource(
                color=Color(255, 0, 0),
                radius=60.0,
                light_type=LightType.SPOT,
                spot_angle=60.0,
                spot_direction=0.0,
            ),
        )

        assert at_angle(image, 0) > 100

    def test_the_cone_excludes_what_is_outside_it(self, gl_ctx: Any) -> None:
        """The half that mattered: before this, all three types drew the
        same disc, so a spot light lit everything behind it too."""
        image = render_light(
            gl_ctx,
            LightSource(
                color=Color(255, 0, 0),
                radius=60.0,
                light_type=LightType.SPOT,
                spot_angle=60.0,
                spot_direction=0.0,
            ),
        )

        assert at_angle(image, 90) < 10
        assert at_angle(image, 180) < 10

    def test_the_cone_points_where_spot_direction_says(self, gl_ctx: Any) -> None:
        """Rotating the light rotates the lit wedge with it, clockwise --
        a sign error here would light the opposite side of the scene."""
        image = render_light(
            gl_ctx,
            LightSource(
                color=Color(255, 0, 0),
                radius=60.0,
                light_type=LightType.SPOT,
                spot_angle=60.0,
                spot_direction=90.0,
            ),
        )

        assert at_angle(image, 90) > 100
        assert at_angle(image, 270) < 10

    def test_a_wider_angle_lights_more_of_the_disc(self, gl_ctx: Any) -> None:
        narrow = render_light(
            gl_ctx,
            LightSource(
                color=Color(255, 0, 0),
                radius=60.0,
                light_type=LightType.SPOT,
                spot_angle=30.0,
            ),
        )
        wide = render_light(
            gl_ctx,
            LightSource(
                color=Color(255, 0, 0),
                radius=60.0,
                light_type=LightType.SPOT,
                spot_angle=170.0,
            ),
        )

        assert at_angle(narrow, 45) < at_angle(wide, 45)


class TestDirectionalLight:
    def test_a_directional_light_covers_evenly_rather_than_falling_off(
        self, gl_ctx: Any
    ) -> None:
        """Parallel rays have no point to fall away from, so the quad is
        lit flat -- `radius` bounds the area instead of shaping it."""
        image = render_light(
            gl_ctx,
            LightSource(
                color=Color(255, 0, 0),
                radius=60.0,
                intensity=1.0,
                light_type=LightType.DIRECTIONAL,
            ),
        )

        near = at_angle(image, 0, 5)
        far = at_angle(image, 0, 45)
        assert near > 200
        assert abs(near - far) <= 4


class TestTypesDiffer:
    def test_the_three_types_no_longer_render_identically(self, gl_ctx: Any) -> None:
        """The headline defect: `light_type` had zero consumers, so all
        three `LightType`s rendered as the same point disc."""
        images = {
            light_type: render_light(
                gl_ctx,
                LightSource(
                    color=Color(255, 0, 0),
                    radius=60.0,
                    intensity=1.0,
                    light_type=light_type,
                    spot_angle=60.0,
                ),
            )
            for light_type in LightType
        }

        point = images[LightType.POINT]
        assert not np.array_equal(point, images[LightType.SPOT])
        assert not np.array_equal(point, images[LightType.DIRECTIONAL])
