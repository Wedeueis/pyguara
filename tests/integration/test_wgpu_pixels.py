"""The wgpu renderer's pixels against the pygame renderer's.

The pygame backend is what games run on today, so it is the reference: the
same calls are made on both and the two frames compared. Nothing here is a
snapshot. A changed pixel is a disagreement between two live renderers,
which is why this can run on any machine with a graphics adapter and needs
no stored images.

**Two regimes, stated per test.** Rectangles, lines up to the widths games
use, text and polygons are **exact** -- every pixel within 2/255, which is
the rounding of an alpha blend done in bytes on one side and floats on the
other. Circles and rounded corners are **bounded**: a GPU tests each pixel
centre against a distance where pygame walks a midpoint algorithm, so a few
edge pixels differ, and the bound is on how many.

Skips when no adapter can be opened, so a runner with no GPU and no
software rasteriser sees a skip rather than a failure.
"""

from __future__ import annotations

import os
from collections.abc import Callable
from typing import Any

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

import pygame
import pytest

from pyguara.common.types import Color, Rect, Vector2
from pyguara.graphics.backends.pygame.pygame_renderer import PygameBackend
from pyguara.graphics.backends.pygame.types import PygameTexture
from pyguara.graphics.backends.pygame.ui_renderer import PygameUIRenderer
from pyguara.graphics.types import RenderBatch

WIDTH, HEIGHT = 240, 160
BACKGROUND = (20, 30, 40)
RED = Color(255, 40, 40)
GLASS = Color(40, 200, 255, 110)
WHITE = Color(255, 255, 255)


@pytest.fixture(scope="module")
def wgpu() -> Any:
    """The wgpu backend's classes, or a skip if no adapter opens."""
    pygame.init()
    if pygame.display.get_surface() is None:
        pygame.display.set_mode((64, 64))
    from pyguara.graphics.backends import wgpu as backend
    from tests.conftest import REQUIRE_GPU

    try:
        backend.GpuFrame(8, 8)
    except RuntimeError as error:
        if REQUIRE_GPU:
            pytest.fail(f"PYGUARA_REQUIRE_GPU is set and no adapter opened: {error}")
        pytest.skip(f"no graphics adapter for wgpu: {error}")
    return backend


def _frames(
    wgpu: Any, draw: Callable[[Any], None], ui: bool = False
) -> tuple[bytes, bytes]:
    """Draw the same thing with both renderers and return both frames."""
    surface = pygame.Surface((WIDTH, HEIGHT))
    surface.fill(BACKGROUND)
    draw((PygameUIRenderer if ui else PygameBackend)(surface))
    frame = wgpu.GpuFrame(WIDTH, HEIGHT)
    frame.gpu.clear(*BACKGROUND, 255)
    draw((wgpu.WgpuUIRenderer if ui else wgpu.WgpuRenderer)(frame))
    frame.gpu.end_frame()
    frame.after_frame()
    return pygame.image.tobytes(surface, "RGBA"), frame.gpu.read_pixels()


def _differing(reference: bytes, actual: bytes) -> int:
    """How many pixels differ by more than 2/255 in any channel."""
    assert len(reference) == len(actual)
    return sum(
        1
        for i in range(0, len(reference), 4)
        if max(
            abs(reference[i] - actual[i]),
            abs(reference[i + 1] - actual[i + 1]),
            abs(reference[i + 2] - actual[i + 2]),
        )
        > 2
    )


def _drawn(frame: bytes) -> int:
    """How many pixels are not the background: a guard against a blank pass."""
    return sum(
        1 for i in range(0, len(frame), 4) if tuple(frame[i : i + 3]) != BACKGROUND
    )


class TestExact:
    @pytest.mark.parametrize(
        "draw",
        [
            pytest.param(
                lambda r: [
                    r.draw_rect(Rect(10 + i * 13, 8 + i * 5, 9 + i, 7 + i), RED)
                    for i in range(12)
                ],
                id="filled-rects",
            ),
            pytest.param(
                lambda r: [
                    r.draw_rect(Rect(10 + i * 9, 8 + i * 5, 40, 30), GLASS)
                    for i in range(10)
                ],
                id="translucent-rects-overlapping",
            ),
            pytest.param(
                lambda r: [
                    r.draw_rect(Rect(8 + i * 55, 10, 40, 60), RED, i + 1)
                    for i in range(4)
                ],
                id="rect-outlines",
            ),
            pytest.param(
                lambda r: r.draw_rect(Rect(20, 20, 100, 80), GLASS, 3),
                id="translucent-outline",
            ),
            pytest.param(
                lambda r: [
                    r.draw_line(Vector2(10, 10 + i * 9), Vector2(200, 10 + i * 9), RED)
                    for i in range(8)
                ],
                id="horizontal-lines",
            ),
            pytest.param(
                lambda r: [
                    r.draw_line(Vector2(12 + i * 9, 5), Vector2(12 + i * 9, 150), RED)
                    for i in range(8)
                ],
                id="vertical-lines",
            ),
            pytest.param(
                lambda r: [
                    r.draw_line(Vector2(10, 10), Vector2(200, 20 + i * 18), RED)
                    for i in range(7)
                ],
                id="diagonal-lines",
            ),
            pytest.param(
                lambda r: [
                    r.draw_line(
                        Vector2(10, 20 + i * 20), Vector2(200, 20 + i * 20), RED, 2
                    )
                    for i in range(5)
                ],
                id="even-width-lines",
            ),
            pytest.param(
                lambda r: [
                    r.draw_line(Vector2(10, 10), Vector2(200, 20 + i * 18), RED, 2)
                    for i in range(7)
                ],
                id="even-width-diagonals",
            ),
            pytest.param(
                lambda r: [
                    r.draw_text(
                        f"Floor {i} HP 73/100",
                        Vector2(8, 6 + i * 26),
                        WHITE,
                        14 + i * 2,
                    )
                    for i in range(5)
                ],
                id="text",
            ),
            pytest.param(
                lambda r: [
                    r.draw_text(
                        "-17",
                        Vector2(20 + i * 40, 60),
                        Color(255, 220, 80, 40 + i * 40),
                        22,
                    )
                    for i in range(5)
                ],
                id="fading-text",
            ),
            pytest.param(
                lambda r: [
                    r.draw_circle(Vector2(30 + i * 28, 80), radius, RED)
                    for i, radius in enumerate((1, 2, 3, 4, 5, 7, 8))
                ],
                id="small-circles",
            ),
        ],
    )
    def test_world_primitives(self, wgpu: Any, draw: Any) -> None:
        reference, actual = _frames(wgpu, draw)

        assert _drawn(reference) > 0
        assert _differing(reference, actual) == 0

    @pytest.mark.parametrize(
        "draw",
        [
            pytest.param(
                lambda r: r.draw_polygon([(20, 20), (200, 40), (120, 140)], RED),
                id="polygon",
            ),
            pytest.param(
                lambda r: r.draw_text(
                    "Salvage banked", Vector2(10, 10), WHITE, 20, bold=True
                ),
                id="bold-text",
            ),
            pytest.param(
                lambda r: r.draw_text(
                    "Iron Lung", Vector2(10, 10), WHITE, 20, italic=True
                ),
                id="italic-text",
            ),
            pytest.param(
                lambda r: r.draw_rect(Rect(15, 15, 120, 70), GLASS),
                id="scrim",
            ),
        ],
    )
    def test_ui_primitives(self, wgpu: Any, draw: Any) -> None:
        reference, actual = _frames(wgpu, draw, ui=True)

        assert _drawn(reference) > 0
        assert _differing(reference, actual) == 0

    def test_a_viewport_clips_and_clears_like_a_surface_clip(self, wgpu: Any) -> None:
        def draw(renderer: Any) -> None:
            renderer.set_viewport(Rect(40, 30, 100, 60))
            renderer.clear(Color(90, 10, 10))
            renderer.draw_rect(Rect(0, 0, WIDTH, 50), RED)
            renderer.reset_viewport()
            renderer.draw_rect(Rect(200, 120, 30, 30), RED)

        reference, actual = _frames(wgpu, draw)

        assert _differing(reference, actual) == 0

    def test_nested_ui_clips_intersect(self, wgpu: Any) -> None:
        def draw(renderer: Any) -> None:
            renderer.push_clip(Rect(20, 20, 120, 100))
            renderer.push_clip(Rect(80, 60, 140, 80))
            renderer.draw_rect(Rect(0, 0, WIDTH, HEIGHT), RED)
            renderer.pop_clip()
            renderer.draw_rect(Rect(0, 0, WIDTH, 40), GLASS)
            renderer.pop_clip()
            renderer.draw_rect(Rect(0, 150, WIDTH, 10), RED)

        reference, actual = _frames(wgpu, draw, ui=True)

        assert _differing(reference, actual) == 0


def _checker(size: int = 16) -> PygameTexture:
    """An image with no symmetry, so a flip or a turn the wrong way shows."""
    surface = pygame.Surface((size, size), pygame.SRCALPHA)
    surface.fill((0, 0, 0, 0))
    pygame.draw.rect(surface, (255, 60, 60, 255), (0, 0, size // 2, size // 2))
    pygame.draw.rect(surface, (60, 255, 60, 255), (size // 2, 0, size // 2, size // 4))
    pygame.draw.rect(surface, (60, 60, 255, 255), (0, size // 2, size // 4, size // 2))
    return PygameTexture("checker", surface)


class TestSprites:
    def test_an_unscaled_texture_is_exact(self, wgpu: Any) -> None:
        texture = _checker()

        reference, actual = _frames(
            wgpu, lambda r: r.draw_texture(texture, Vector2(60, 60))
        )

        assert _drawn(reference) > 0
        assert _differing(reference, actual) == 0

    @pytest.mark.parametrize("scale", [(2, 2), (-2, 2), (2, -2), (3, 1)])
    def test_whole_number_scales_and_flips_are_exact(
        self, wgpu: Any, scale: tuple[int, int]
    ) -> None:
        texture = _checker()

        reference, actual = _frames(
            wgpu,
            lambda r: r.draw_texture(texture, Vector2(80, 70), 0.0, Vector2(*scale)),
        )

        assert _differing(reference, actual) == 0

    @pytest.mark.parametrize("turn", [90.0, 180.0, 270.0])
    def test_quarter_turns_go_the_same_way(self, wgpu: Any, turn: float) -> None:
        # Not exact: pygame's `rotate` resamples. But a turn the wrong way
        # moves the red quadrant to another corner, far past this bound.
        texture = _checker(32)

        reference, actual = _frames(
            wgpu, lambda r: r.draw_texture(texture, Vector2(80, 70), turn)
        )

        assert _differing(reference, actual) <= 140

    def test_a_plain_batch_is_exact(self, wgpu: Any) -> None:
        batch = RenderBatch(
            texture=_checker(),
            destinations=[(10.0 + i * 20, 12.0 + i * 9) for i in range(9)],
        )

        reference, actual = _frames(wgpu, lambda r: r.render_batch(batch))

        assert _drawn(reference) > 0
        assert _differing(reference, actual) == 0

    def test_a_batch_of_atlas_regions_is_exact(self, wgpu: Any) -> None:
        batch = RenderBatch(
            texture=_checker(),
            destinations=[(10.0, 10.0), (60.0, 30.0), (110.0, 50.0)],
            source_rects=[Rect(0, 0, 8, 8), None, Rect(8, 0, 8, 4)],
            source_rects_enabled=True,
        )

        reference, actual = _frames(wgpu, lambda r: r.render_batch(batch))

        assert _differing(reference, actual) == 0

    def test_a_tinted_scaled_batch_is_exact(self, wgpu: Any) -> None:
        batch = RenderBatch(
            texture=_checker(),
            destinations=[(10.0, 10.0), (70.0, 30.0)],
            rotations=[0.0, 0.0],
            scales=[(2.0, 2.0), (3.0, 1.0)],
            transforms_enabled=True,
            colors=[(255, 255, 255, 255), (255, 128, 0, 128)],
            colors_enabled=True,
        )

        reference, actual = _frames(wgpu, lambda r: r.render_batch(batch))

        assert _differing(reference, actual) == 0


def _odd_batches() -> dict[str, RenderBatch]:
    """Batches that exercise every branch of the per-sprite placement."""
    import random

    rng = random.Random(7)
    texture = _checker(16)
    count = 40
    destinations = [(rng.uniform(-8, 230), rng.uniform(-8, 150)) for _ in range(count)]
    return {
        "plain": RenderBatch(texture, destinations),
        "integer destinations": RenderBatch(
            texture, [(i * 5, i * 3) for i in range(count)]
        ),
        "atlas, mixed with whole sprites": RenderBatch(
            texture,
            destinations,
            source_rects=[
                None if i % 3 == 0 else Rect(i % 8, 0, 8.7, 4.2) for i in range(count)
            ],
            source_rects_enabled=True,
        ),
        "turned and scaled, flips and fractions": RenderBatch(
            texture,
            destinations,
            rotations=[
                rng.choice([0.0, 30.0, -45.0, 90.0, 123.4]) for _ in range(count)
            ],
            scales=[
                rng.choice([(1.0, 1.0), (1.5, 0.75), (-1.3, 1.0), (1.0, -1.3)])
                for _ in range(count)
            ],
            transforms_enabled=True,
        ),
        "lists shorter than the batch": RenderBatch(
            texture,
            destinations,
            rotations=[45.0] * 10,
            scales=[(2.0, 2.0)] * 20,
            transforms_enabled=True,
            colors=[(255, 0, 0, 128)] * 5,
            colors_enabled=True,
        ),
        "lists given but switched off": RenderBatch(
            texture,
            destinations,
            rotations=[45.0] * count,
            scales=[(2.0, 2.0)] * count,
            colors=[(255, 0, 0, 128)] * count,
        ),
        "tinted, turned, in an atlas": RenderBatch(
            texture,
            destinations,
            rotations=[rng.uniform(0, 360) for _ in range(count)],
            scales=[(rng.uniform(0.5, 2), rng.uniform(0.5, 2)) for _ in range(count)],
            transforms_enabled=True,
            colors=[
                (
                    rng.randrange(256),
                    rng.randrange(256),
                    rng.randrange(256),
                    rng.randrange(256),
                )
                for _ in range(count)
            ],
            colors_enabled=True,
            source_rects=[Rect(4, 4, 8, 8)] * count,
            source_rects_enabled=True,
        ),
    }


class TestNativeBatch:
    """`render_batch`'s one native call against the loop it replaced.

    `sprites_one_by_one` is the per-sprite loop `render_batch` used to run,
    one `quad` call each. Both are drawn and the frames must be identical
    to the byte: the native path is a move of the same arithmetic, not an
    approximation of it.
    """

    @pytest.mark.parametrize("case", list(_odd_batches()))
    def test_the_native_batch_draws_what_the_loop_drew(
        self, wgpu: Any, case: str
    ) -> None:
        from pyguara.graphics.backends.wgpu.renderer import sprites_one_by_one

        batch = _odd_batches()[case]

        def draw(path: Callable[[Any], None]) -> bytes:
            frame = wgpu.GpuFrame(WIDTH, HEIGHT)
            frame.gpu.clear(*BACKGROUND, 255)
            path(frame)
            frame.gpu.end_frame()
            return bytes(frame.gpu.read_pixels())

        native = draw(lambda frame: wgpu.WgpuRenderer(frame).render_batch(batch))
        loop = draw(lambda frame: sprites_one_by_one(frame, batch))

        assert _drawn(loop) > 0
        assert native == loop

    def test_a_batch_is_one_call_however_many_sprites(self, wgpu: Any) -> None:
        frame = wgpu.GpuFrame(64, 64)
        calls: list[int] = []
        gpu = frame.gpu

        class Counting:
            def __getattr__(self, name: str) -> Any:
                value = getattr(gpu, name)
                if name in ("quad", "sprites"):
                    calls.append(1)
                return value

        renderer = wgpu.WgpuRenderer(frame)
        renderer._gpu = Counting()
        renderer.render_batch(RenderBatch(_checker(), [(i, i) for i in range(500)]))

        assert len(calls) == 1
        assert gpu.pending == 500


class TestFiltering:
    """`filter: linear` in a texture's meta reaches the sampler.

    The pygame renderer scales nearest whatever the meta says, so there is
    no pygame frame to hold a smooth texture to. What is held instead: a
    smooth texture blends where a nearest one cannot, and the same surface
    drawn nearest still matches pygame exactly.
    """

    @staticmethod
    def _two_tone(smooth: bool) -> PygameTexture:
        surface = pygame.Surface((2, 1), pygame.SRCALPHA)
        surface.set_at((0, 0), (255, 0, 0, 255))
        surface.set_at((1, 0), (0, 0, 255, 255))
        return PygameTexture("two-tone", surface, smooth=smooth)

    @staticmethod
    def _colours(frame: bytes) -> set[tuple[int, ...]]:
        return {
            tuple(frame[i : i + 3])
            for i in range(0, len(frame), 4)
            if tuple(frame[i : i + 3]) != BACKGROUND
        }

    def test_a_smooth_texture_blends_when_scaled(self, wgpu: Any) -> None:
        texture = self._two_tone(smooth=True)

        _, actual = _frames(
            wgpu,
            lambda r: r.draw_texture(texture, Vector2(80, 60), 0.0, Vector2(40, 40)),
        )

        # Red, blue, and the purples bilinear filtering puts between them.
        assert len(self._colours(actual)) > 10

    def test_a_nearest_texture_still_matches_pygame(self, wgpu: Any) -> None:
        texture = self._two_tone(smooth=False)

        reference, actual = _frames(
            wgpu,
            lambda r: r.draw_texture(texture, Vector2(80, 60), 0.0, Vector2(40, 40)),
        )

        assert self._colours(actual) == {(255, 0, 0), (0, 0, 255)}
        assert _differing(reference, actual) == 0

    def test_one_surface_drawn_both_ways_is_two_textures(self, wgpu: Any) -> None:
        frame = wgpu.GpuFrame(32, 32)
        surface = self._two_tone(smooth=False).native_handle
        before = frame.gpu.texture_count

        assert frame.image(surface, smooth=True) != frame.image(surface)
        assert frame.image(surface, smooth=True) == frame.image(surface, True)
        assert frame.gpu.texture_count == before + 2


class TestMaterials:
    """`SpriteShader` materials on wgpu, each against an equivalent plain draw.

    A material sprite is placed by the same vertex stage as a plain one, so
    the only thing a material may change is the colour its function
    returns. Each test picks a function whose result can also be produced
    without a material -- an identity, an inverted texture, a tint, a
    pre-masked texture -- and requires the two frames to be identical.
    """

    @staticmethod
    def _draw(wgpu: Any, *batches: RenderBatch) -> bytes:
        frame = wgpu.GpuFrame(WIDTH, HEIGHT)
        frame.gpu.clear(*BACKGROUND, 255)
        renderer = wgpu.WgpuRenderer(frame)
        for batch in batches:
            renderer.render_batch(batch)
        frame.gpu.end_frame()
        return bytes(frame.gpu.read_pixels())

    @staticmethod
    def _batch(texture: Any, material: Any = None) -> RenderBatch:
        """Turned, scaled, flipped, tinted sprites, some from an atlas region."""
        count = 6
        return RenderBatch(
            texture,
            [(12.0 + i * 36, 20.0 + (i % 3) * 40) for i in range(count)],
            rotations=[0.0, 30.0, 90.0, -45.0, 180.0, 12.5],
            scales=[
                (2.0, 2.0),
                (1.5, -1.0),
                (-2.0, 2.0),
                (1.0, 1.0),
                (2.5, 1.5),
                (1.0, 2.0),
            ],
            transforms_enabled=True,
            colors=[(255, 255, 255, 255), (255, 128, 0, 200)] * 3,
            colors_enabled=True,
            source_rects=[None, Rect(0, 0, 8, 8), None, Rect(8, 0, 8, 4), None, None],
            source_rects_enabled=True,
            material=material,
        )

    def test_the_identity_material_draws_the_plain_sprite(self, wgpu: Any) -> None:
        from pyguara.graphics.materials import Material, SpriteShader

        identity = SpriteShader(
            "identity",
            wgsl="fn material(sprite: Sprite) -> vec4<f32> {"
            " return textureSample(sprite_texture, sprite_sampler, sprite.uv)"
            " * sprite.color; }",
        )
        texture = _checker()

        plain = self._draw(wgpu, self._batch(texture))
        drawn = self._draw(wgpu, self._batch(texture, Material(identity)))

        assert _drawn(plain) > 0
        assert drawn == plain

    def test_inverting_is_drawing_the_inverted_texture(self, wgpu: Any) -> None:
        from pyguara.graphics.materials import Material, SpriteShader

        invert = SpriteShader(
            "invert",
            wgsl="fn material(sprite: Sprite) -> vec4<f32> {"
            " let texel = textureSample(sprite_texture, sprite_sampler, sprite.uv);"
            " return vec4<f32>(1.0 - texel.rgb, texel.a) * sprite.color; }",
        )
        texture = _checker()
        inverted = texture.native_handle.copy()
        for x in range(inverted.get_width()):
            for y in range(inverted.get_height()):
                r, g, b, a = inverted.get_at((x, y))
                inverted.set_at((x, y), (255 - r, 255 - g, 255 - b, a))

        drawn = self._draw(wgpu, self._batch(texture, Material(invert)))
        expected = self._draw(wgpu, self._batch(PygameTexture("inv", inverted)))

        assert drawn == expected

    def test_uniforms_reach_the_material(self, wgpu: Any) -> None:
        from pyguara.graphics.materials import Material, SpriteShader, Uniform

        tinted = SpriteShader(
            "tinted",
            # A float first, so the vec3 sits at offset 16: the layout matters.
            uniforms=(Uniform("unused"), Uniform("tint", "vec3")),
            wgsl="fn material(sprite: Sprite) -> vec4<f32> {"
            " return textureSample(sprite_texture, sprite_sampler, sprite.uv)"
            " * vec4<f32>(params.tint, 1.0); }",
        )
        texture = _checker()
        batch = RenderBatch(texture, [(20.0, 20.0), (90.0, 60.0)])
        batch.material = Material(
            tinted, uniforms={"unused": 9.0, "tint": (51 / 255, 153 / 255, 1.0)}
        )
        reference = RenderBatch(
            texture,
            batch.destinations,
            colors=[(51, 153, 255, 255)] * 2,
            colors_enabled=True,
        )

        assert self._draw(wgpu, batch) == self._draw(wgpu, reference)

    def test_a_material_texture_masks_the_sprite(self, wgpu: Any) -> None:
        from pyguara.graphics.materials import Material, SpriteShader

        masked = SpriteShader(
            "masked",
            texture=True,
            wgsl="fn material(sprite: Sprite) -> vec4<f32> {"
            " let texel = textureSample(sprite_texture, sprite_sampler, sprite.uv);"
            " let keep = textureSample(material_texture, material_sampler, sprite.uv).a;"
            " return vec4<f32>(texel.rgb, texel.a * keep) * sprite.color; }",
        )
        texture = _checker(16)
        mask = pygame.Surface((16, 16), pygame.SRCALPHA)
        mask.fill((0, 0, 0, 0))
        pygame.draw.circle(mask, (255, 255, 255, 255), (8, 8), 6)
        cut = texture.native_handle.copy()
        for x in range(16):
            for y in range(16):
                if mask.get_at((x, y)).a == 0:
                    cut.set_at((x, y), (0, 0, 0, 0))
        batch = RenderBatch(texture, [(20.0, 20.0), (90.0, 60.0)])
        batch.material = Material(masked, texture=PygameTexture("mask", mask))

        expected = self._draw(
            wgpu, RenderBatch(PygameTexture("cut", cut), batch.destinations)
        )
        assert self._draw(wgpu, batch) == expected

    def test_order_is_kept_around_a_material(self, wgpu: Any) -> None:
        """A plain sprite drawn after a material one lands on top of it."""
        from pyguara.graphics.materials import Material, SpriteShader

        white = SpriteShader(
            "white",
            wgsl="fn material(sprite: Sprite) -> vec4<f32> {"
            " return vec4<f32>(1.0, 1.0, 1.0, 1.0); }",
        )
        texture = _checker()
        under = RenderBatch(texture, [(40.0, 40.0)], material=Material(white))
        over = RenderBatch(texture, [(44.0, 44.0)])

        frame = wgpu.GpuFrame(WIDTH, HEIGHT)
        renderer = wgpu.WgpuRenderer(frame)
        renderer.render_batch(under)
        renderer.render_batch(over)
        assert frame.gpu.pending_runs == 2
        frame.gpu.end_frame()
        pixels = bytes(frame.gpu.read_pixels())

        top_left_of_over = (44 * WIDTH + 44) * 4
        assert tuple(pixels[top_left_of_over : top_left_of_over + 3]) == (255, 60, 60)

    def test_a_material_that_does_not_compile_says_why(self, wgpu: Any) -> None:
        from pyguara.graphics.materials import Material, SpriteShader

        broken = SpriteShader("broken", wgsl="fn material(s: Sprite) -> vec4<f32> {")
        batch = RenderBatch(_checker(), [(0.0, 0.0)], material=Material(broken))

        with pytest.raises(ValueError, match="the material does not compile"):
            self._draw(wgpu, batch)

    def test_a_missing_uniform_is_named(self, wgpu: Any) -> None:
        from pyguara.graphics.materials import Material, SpriteShader, Uniform

        glow = SpriteShader(
            "glow",
            uniforms=(Uniform("strength"),),
            wgsl="fn material(s: Sprite) -> vec4<f32> {"
            " return vec4<f32>(params.strength); }",
        )
        batch = RenderBatch(_checker(), [(0.0, 0.0)], material=Material(glow))

        with pytest.raises(KeyError, match="glow: no value for uniform 'strength'"):
            self._draw(wgpu, batch)


class TestEffects:
    """The native half of `GraphicsDevice.run`: targets and fullscreen passes."""

    @staticmethod
    def _solid(wgpu: Any, *, uniforms: tuple[Any, ...] = (), wgsl: str) -> Any:
        from pyguara.graphics.pipeline.device import FullscreenShader

        return FullscreenShader("test", uniforms=uniforms, wgsl=wgsl)

    def test_a_shader_that_does_not_compile_is_a_value_error(self, wgpu: Any) -> None:
        frame = wgpu.GpuFrame(16, 16)

        with pytest.raises(ValueError, match="does not compile"):
            frame.gpu.create_effect("this is not wgsl", 0, 0)

    def test_uniforms_reach_the_shader(self, wgpu: Any) -> None:
        from pyguara.graphics.pipeline.device import Uniform, WgpuDevice

        frame = wgpu.GpuFrame(16, 16)
        shader = self._solid(
            wgpu,
            uniforms=(Uniform("pad", "f32"), Uniform("colour", "vec3")),
            wgsl="@fragment fn fragment(in: Varying) -> @location(0) vec4<f32> "
            "{ return vec4<f32>(params.colour, 1.0); }",
        )

        WgpuDevice(frame).run(
            shader, {}, {"pad": 9.0, "colour": (0.2, 0.6, 1.0)}, None, blend="replace"
        )
        frame.gpu.end_frame()

        pixel = tuple(frame.gpu.read_pixels()[:3])
        assert pixel == (51, 153, 255)

    def test_additive_passes_add(self, wgpu: Any) -> None:
        from pyguara.graphics.pipeline.device import WgpuDevice

        frame = wgpu.GpuFrame(16, 16)
        frame.gpu.clear(0, 0, 0, 255)
        shader = self._solid(
            wgpu,
            wgsl="@fragment fn fragment(in: Varying) -> @location(0) vec4<f32> "
            "{ return vec4<f32>(0.25, 0.0, 0.0, 1.0); }",
        )
        device = WgpuDevice(frame)

        for _ in range(3):
            device.run(shader, {}, {}, None, blend="add")
        frame.gpu.end_frame()

        assert frame.gpu.read_pixels()[0] in (191, 192)

    def test_a_pass_cannot_read_what_it_writes(self, wgpu: Any) -> None:
        frame = wgpu.GpuFrame(16, 16)
        target = frame.gpu.create_target(16, 16)
        effect = frame.gpu.create_effect(
            "@group(0) @binding(1) var s: sampler;\n"
            "@group(0) @binding(2) var t: texture_2d<f32>;\n"
            "@vertex fn vertex(@builtin(vertex_index) i: u32) -> "
            "@builtin(position) vec4<f32> { return vec4<f32>(0.0); }\n"
            "@fragment fn fragment() -> @location(0) vec4<f32> "
            "{ return textureSample(t, s, vec2<f32>(0.0)); }",
            1,
            0,
        )

        with pytest.raises(ValueError, match="cannot read the target it writes"):
            frame.gpu.fullscreen(effect, target, [target], b"")

    def test_instance_rows_must_fill_whole_instances(self, wgpu: Any) -> None:
        from pyguara.graphics.pipeline.device import Attribute, InstancedShader

        frame = wgpu.GpuFrame(16, 16)
        shader = InstancedShader(
            "dots",
            attributes=(Attribute("pos", "vec2"),),
            wgsl="@vertex fn vertex(@builtin(vertex_index) i: u32, d: Instance) "
            "-> @builtin(position) vec4<f32> "
            "{ return vec4<f32>(quad_corner(i) + d.pos, 0.0, 1.0); }\n"
            "@fragment fn fragment() -> @location(0) vec4<f32> "
            "{ return vec4<f32>(1.0); }",
        )
        effect = frame.gpu.create_effect(shader.wgsl_source(), 0, 0, [2])
        target = frame.gpu.create_target(16, 16)

        with pytest.raises(ValueError, match="2 instances of 8 bytes are 16 bytes"):
            frame.gpu.instanced(effect, target, b"\0" * 12, 2, b"")
        with pytest.raises(ValueError, match="drawn with instanced"):
            frame.gpu.fullscreen(effect, target, [], b"")

    def test_drawing_into_a_target_leaves_the_screen_alone(self, wgpu: Any) -> None:
        frame = wgpu.GpuFrame(16, 16)
        renderer = wgpu.WgpuRenderer(frame)
        target = frame.gpu.create_target(16, 16)
        frame.gpu.clear(0, 0, 255, 255)

        frame.gpu.set_target(target)
        renderer.draw_rect(Rect(0, 0, 16, 16), RED)
        frame.gpu.set_target(0)
        frame.gpu.end_frame()

        assert tuple(frame.gpu.read_pixels()[:3]) == (0, 0, 255)
        assert tuple(frame.gpu.read_pixels(target)[:3]) == (RED.r, RED.g, RED.b)


class TestShapeBatchDirection:
    def test_a_batched_line_turns_the_way_its_angle_says(self, wgpu: Any) -> None:
        """A spark streak's row, as the pool packs one: atan2 in screen space."""
        import math

        from pyguara.graphics.types import ShapeBatch, ShapeKind

        frame = wgpu.GpuFrame(72, 72)
        frame.gpu.clear(0, 0, 0, 255)
        row = [35, 35, 35.0 + 2, 2.0, math.atan2(50, 50), 1, 1, 1, 1, 0.0, 2.0]
        wgpu.WgpuRenderer(frame).render_shapes(ShapeBatch(ShapeKind.LINE, [row]))
        frame.gpu.end_frame()
        pixels = frame.gpu.read_pixels()

        def lit(x: int, y: int) -> bool:
            return pixels[(y * 72 + x) * 4] > 100

        assert lit(15, 15)
        assert not lit(15, 55)


class TestBounded:
    @pytest.mark.parametrize("radius", [6, 9, 11, 13, 21, 40, 70])
    def test_a_circles_edge(self, wgpu: Any, radius: int) -> None:
        reference, actual = _frames(
            wgpu, lambda r: r.draw_circle(Vector2(110, 80), radius, RED)
        )

        # Measured: radii 1 to 5, 7 and 8 are exact (they are in
        # `TestExact`); 6, 9, 10 and 12 differ by 8 pixels and 11, 21 and
        # 40 by 16 -- one or two pixels in each octant. Centring the circle
        # on the pixel's middle instead gave 123 at r = 40.
        assert _differing(reference, actual) <= 2 * radius

    def test_a_translucent_polygon_outline(self, wgpu: Any) -> None:
        reference, actual = _frames(
            wgpu,
            lambda r: r.draw_polygon([(20, 20), (200, 40), (120, 140)], GLASS, 2),
            ui=True,
        )

        # One pixel, where two edges of the outline meet: pygame blends
        # the corner once, having drawn the outline opaque onto a scratch
        # surface first.
        assert _drawn(reference) > 0
        assert _differing(reference, actual) <= 2

    def test_a_ring(self, wgpu: Any) -> None:
        reference, actual = _frames(
            wgpu, lambda r: r.draw_circle(Vector2(110, 80), 30, RED, 3)
        )

        assert _differing(reference, actual) <= 60

    @pytest.mark.parametrize("width", [3, 5])
    def test_thick_diagonals(self, wgpu: Any, width: int) -> None:
        def draw(renderer: Any) -> None:
            for i in range(7):
                renderer.draw_line(
                    Vector2(10, 10), Vector2(200, 20 + i * 18), RED, width
                )

        reference, actual = _frames(wgpu, draw)

        # The ends: pygame cuts a thick line square to an axis.
        assert _differing(reference, actual) <= 4 * width

    @pytest.mark.parametrize("width", [0, 2])
    def test_rounded_corners(self, wgpu: Any, width: int) -> None:
        reference, actual = _frames(
            wgpu, lambda r: r.draw_rect(Rect(20, 20, 150, 90), RED, width, 12), ui=True
        )

        assert _differing(reference, actual) <= 24


class TestTheFrameItself:
    def test_text_is_rasterised_once_however_often_it_is_drawn(self, wgpu: Any) -> None:
        frame = wgpu.GpuFrame(64, 64)
        renderer = wgpu.WgpuRenderer(frame)
        before = frame.gpu.texture_count

        for alpha in range(10, 250, 20):
            renderer.draw_text("-17", Vector2(4, 4), Color(255, 220, 80, alpha), 18)
            renderer.draw_text("-17", Vector2(4, 30), Color(80, 220, 255, alpha), 18)

        assert frame.gpu.texture_count == before + 1

    def test_an_evicted_string_still_draws_in_the_frame_that_evicted_it(
        self, wgpu: Any, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # The first string is pushed, then pushed out of the cache by the
        # second, before the frame is drawn. Freeing it at once would drop
        # it from the frame it was already in.
        from pyguara.graphics.backends.wgpu import frame as frame_module

        monkeypatch.setattr(frame_module, "TEXT_CACHE_LIMIT", 1)
        frame = wgpu.GpuFrame(120, 40)
        frame.gpu.clear(0, 0, 0, 255)
        renderer = wgpu.WgpuRenderer(frame)

        renderer.draw_text("first", Vector2(2, 2), WHITE, 20)
        renderer.draw_text("second", Vector2(60, 2), WHITE, 20)
        held = frame.gpu.texture_count
        frame.gpu.end_frame()
        pixels = frame.gpu.read_pixels()
        frame.after_frame()

        left_half = sum(pixels[(y * 120 + x) * 4] for y in range(40) for x in range(55))
        assert left_half > 0
        assert frame.gpu.texture_count == held - 1

    def test_a_collected_image_frees_its_texture(self, wgpu: Any) -> None:
        import gc

        frame = wgpu.GpuFrame(64, 64)
        renderer = wgpu.WgpuRenderer(frame)
        texture = _checker()
        renderer.draw_texture(texture, Vector2(20, 20))
        frame.gpu.end_frame()
        frame.after_frame()
        held = frame.gpu.texture_count

        del texture
        gc.collect()
        frame.after_frame()

        assert frame.gpu.texture_count == held - 1

    def test_a_full_clear_drops_what_was_queued_behind_it(self, wgpu: Any) -> None:
        frame = wgpu.GpuFrame(32, 32)
        renderer = wgpu.WgpuRenderer(frame)

        for _ in range(50):
            renderer.draw_rect(Rect(0, 0, 8, 8), RED)
        renderer.clear(Color(1, 2, 3))

        assert frame.gpu.pending == 0

    def test_one_texture_is_one_draw_call(self, wgpu: Any) -> None:
        frame = wgpu.GpuFrame(64, 64)
        renderer = wgpu.WgpuRenderer(frame)

        for i in range(200):
            renderer.draw_rect(Rect(i % 60, i % 50, 4, 4), RED)
            renderer.draw_circle(Vector2(i % 60, i % 50), 3, GLASS)
            renderer.draw_line(Vector2(0, i % 60), Vector2(60, i % 50), RED)

        assert frame.gpu.pending == 600
        assert frame.gpu.pending_runs == 1
