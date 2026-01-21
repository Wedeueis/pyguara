"""ModernGL-compatible UI Renderer using hybrid pygame surface approach.

This renderer uses pygame for text and primitive rendering onto an offscreen
surface, then composites it onto the OpenGL framebuffer as a texture overlay.
This maintains compatibility with existing UI code while using ModernGL for
the main rendering pipeline.
"""

from typing import Tuple, Dict, Optional, Any

import moderngl
import numpy as np
import pygame

from pyguara.common.types import Rect, Color, Vector2
from pyguara.graphics.protocols import UIRenderer


# Shader source for UI overlay
_UI_VERT_SHADER = """
#version 330 core
layout(location = 0) in vec2 in_vert;
layout(location = 1) in vec2 in_uv;
out vec2 v_uv;

void main() {
    gl_Position = vec4(in_vert, 0.0, 1.0);
    v_uv = in_uv;
}
"""

_UI_FRAG_SHADER = """
#version 330 core
in vec2 v_uv;
out vec4 frag_color;
uniform sampler2D u_texture;

void main() {
    frag_color = texture(u_texture, v_uv);
}
"""


class GLUIRenderer(UIRenderer):
    """OpenGL-compatible UI renderer using pygame for text/primitives.

    Renders UI elements to an offscreen pygame surface, then uploads it
    as a texture to be composited on top of the 3D scene. This provides
    full compatibility with pygame-based text rendering and UI widgets.
    """

    def __init__(self, ctx: moderngl.Context, width: int, height: int) -> None:
        """Initialize the GL UI renderer.

        Args:
            ctx: ModernGL context for texture uploading and overlay rendering.
            width: Width of the UI surface in pixels.
            height: Height of the UI surface in pixels.
        """
        self._ctx = ctx
        self._width = width
        self._height = height

        # Initialize pygame font module if needed
        if not pygame.font.get_init():
            pygame.font.init()

        # Create offscreen surface for UI rendering (with alpha)
        self._surface = pygame.Surface((width, height), pygame.SRCALPHA)
        self._font_cache: Dict[int, pygame.font.Font] = {}

        # Create GL resources for overlay rendering
        self._program = self._ctx.program(
            vertex_shader=_UI_VERT_SHADER,
            fragment_shader=_UI_FRAG_SHADER,
        )

        # Fullscreen quad (NDC coordinates)
        # Note: UV is flipped vertically for OpenGL
        vertices = np.array(
            [
                # x     y    u    v
                -1.0,
                -1.0,
                0.0,
                0.0,
                1.0,
                -1.0,
                1.0,
                0.0,
                -1.0,
                1.0,
                0.0,
                1.0,
                1.0,
                1.0,
                1.0,
                1.0,
            ],
            dtype="f4",
        )
        self._vbo = self._ctx.buffer(vertices.tobytes())
        self._vao = self._ctx.vertex_array(
            self._program,
            [(self._vbo, "2f 2f", "in_vert", "in_uv")],
        )

        # Create texture for UI surface
        self._texture = self._ctx.texture((width, height), 4)
        self._texture.filter = (moderngl.LINEAR, moderngl.LINEAR)
        self._texture.swizzle = "BGRA"  # pygame uses BGRA internally

        self._dirty = False

    def clear(self) -> None:
        """Clear the UI surface for a new frame."""
        self._surface.fill((0, 0, 0, 0))  # Transparent
        self._dirty = True

    def _get_font(self, size: int) -> pygame.font.Font:
        """Retrieve or create a font of the specified size."""
        if size not in self._font_cache:
            self._font_cache[size] = pygame.font.SysFont("arial", size)
        return self._font_cache[size]

    def _to_pygame_color(self, color: Color) -> Tuple[int, int, int, int]:
        """Convert engine Color to pygame RGBA tuple."""
        return (color.r, color.g, color.b, getattr(color, "a", 255))

    def draw_rect(
        self, rect: Rect, color: Color, width: int = 0, border_radius: int = 0
    ) -> None:
        """Draw a filled or outlined rectangle."""
        pygame_rect = pygame.Rect(rect.x, rect.y, rect.width, rect.height)
        rgba = self._to_pygame_color(color)

        pygame.draw.rect(
            self._surface, rgba, pygame_rect, width, border_radius=border_radius
        )
        self._dirty = True

    def draw_circle(
        self, center: Vector2, radius: float, color: Color, width: int = 0
    ) -> None:
        """Draw a filled or outlined circle."""
        rgba = self._to_pygame_color(color)
        pygame.draw.circle(
            self._surface, rgba, (int(center.x), int(center.y)), int(radius), width
        )
        self._dirty = True

    def draw_line(
        self, start: Vector2, end: Vector2, color: Color, width: int = 1
    ) -> None:
        """Draw a line."""
        rgba = self._to_pygame_color(color)
        pygame.draw.line(
            self._surface,
            rgba,
            (int(start.x), int(start.y)),
            (int(end.x), int(end.y)),
            width,
        )
        self._dirty = True

    def draw_polygon(
        self, points: list[tuple[int, int]], color: Color, width: int = 0
    ) -> None:
        """Draw a filled or outlined polygon."""
        rgba = self._to_pygame_color(color)
        pygame.draw.polygon(self._surface, rgba, points, width)
        self._dirty = True

    def draw_text(
        self, text: str, position: Vector2, color: Color, size: int = 16
    ) -> None:
        """Render text to the UI surface."""
        if not text:
            return

        font = self._get_font(size)
        rgba = self._to_pygame_color(color)

        texture = font.render(text, True, rgba)
        self._surface.blit(texture, (int(position.x), int(position.y)))
        self._dirty = True

    def draw_texture(
        self, texture: Any, rect: Rect, color: Optional[Color] = None
    ) -> None:
        """Draw an image texture."""
        if not isinstance(texture, pygame.Surface):
            return

        target_rect = pygame.Rect(rect.x, rect.y, rect.width, rect.height)

        if texture.get_width() != rect.width or texture.get_height() != rect.height:
            scaled_tex = pygame.transform.scale(
                texture, (int(rect.width), int(rect.height))
            )
        else:
            scaled_tex = texture

        if color:
            rgba = self._to_pygame_color(color)
            tinted_tex = scaled_tex.copy()
            tinted_tex.fill(rgba[0:3], special_flags=pygame.BLEND_RGBA_MULT)
            self._surface.blit(tinted_tex, target_rect)
        else:
            self._surface.blit(scaled_tex, target_rect)

        self._dirty = True

    def get_text_size(self, text: str, size: int) -> Tuple[int, int]:
        """Calculate the width/height of a string."""
        font = self._get_font(size)
        txt_size = font.size(text)
        return (txt_size[0], txt_size[1])

    def present(self) -> None:
        """Upload UI surface to GPU and render as overlay.

        Should be called after all UI drawing is complete, before
        the window's buffer swap. Clears the UI surface after compositing
        to prepare for the next frame.
        """
        if not self._dirty:
            return

        # Flip surface vertically for OpenGL
        flipped = pygame.transform.flip(self._surface, False, True)

        # Get raw pixel data
        data = pygame.image.tobytes(flipped, "RGBA", False)

        # Upload to GPU texture
        self._texture.write(data)

        # Render fullscreen quad with UI texture
        self._texture.use(0)
        self._program["u_texture"] = 0
        self._vao.render(moderngl.TRIANGLE_STRIP)

        # Clear for next frame
        self._surface.fill((0, 0, 0, 0))
        self._dirty = False

    def release(self) -> None:
        """Release GPU resources."""
        if self._vao:
            self._vao.release()
        if self._vbo:
            self._vbo.release()
        if self._texture:
            self._texture.release()
        if self._program:
            self._program.release()
