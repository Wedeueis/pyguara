"""Rasterise ImGui draw data through the engine's own ModernGL context.

Written rather than taken from `imgui_bundle.python_backends` on purpose.
Those backends import `OpenGL.GL` (PyOpenGL), and an undeclared PyOpenGL
dependency is *precisely* what killed the previous editor: the import failed
in every install configuration, so the whole subsystem silently disabled
itself and never ran. `moderngl` is already a hard dependency of this
engine, so drawing through it adds no new GL stack to go missing -- and it
shares the context the renderer is already using instead of standing up a
second one.

ImGui 1.92's dynamic texture system is honoured: the font atlas arrives as
a texture *request* on the draw data each frame (`want_create`,
`want_updates`, `want_destroy`) rather than as a one-off atlas upload, which
is why `ImGuiBackendFlags_RendererHasTextures` is declared below.
"""

from __future__ import annotations

import ctypes
from pathlib import Path

import moderngl
from imgui_bundle import imgui

from pyguara.log import get_logger

logger = get_logger(__name__)

_SHADER_DIR = Path(__file__).parent / "shaders"

# sizeof(ImDrawVert): pos (2 x f32) + uv (2 x f32) + col (packed RGBA8).
# Verified against the raw buffer rather than assumed -- a wrong stride
# renders as plausible-looking garbage, not as an error.
_VERTEX_STRIDE = 20

# ImDrawIdx is a 32-bit unsigned int in imgui-bundle's build, which
# `ImVector_uint` in the draw data confirms.
_INDEX_SIZE = 4

# ImGui's per-vertex colour is four normalized unsigned bytes in R,G,B,A
# memory order (IM_COL32 packs R into the low byte, little-endian).
_VERTEX_FORMAT = "2f 2f 4f1"
_VERTEX_ATTRIBUTES = ("in_pos", "in_uv", "in_color")


class ModernGLImGuiRenderer:
    """Draws ImGui draw data with a ModernGL program, buffers and textures.

    Owns GL resources, so it must be constructed on the thread and context
    that will draw, and `release()`d before the context goes away.
    """

    def __init__(self, ctx: moderngl.Context) -> None:
        """Compile the program and declare renderer capabilities to ImGui.

        Args:
            ctx: The engine's ModernGL context. Not owned -- never released
                here.
        """
        self._ctx = ctx
        self._program = ctx.program(
            vertex_shader=(_SHADER_DIR / "imgui.vert").read_text(),
            fragment_shader=(_SHADER_DIR / "imgui.frag").read_text(),
        )

        self._vbo: moderngl.Buffer | None = None
        self._ibo: moderngl.Buffer | None = None
        self._vao: moderngl.VertexArray | None = None
        self._vbo_capacity = 0
        self._ibo_capacity = 0

        # ImGui hands out an opaque 64-bit texture id; these are the ones
        # this renderer minted, so a draw command can be resolved back to a
        # live ModernGL texture.
        self._textures: dict[int, moderngl.Texture] = {}
        self._next_texture_id = 1

        io = imgui.get_io()
        # Without this ImGui asserts in `new_frame()` ("font atlas is not
        # built") because it expects a legacy backend to have uploaded the
        # atlas itself.
        io.backend_flags |= imgui.BackendFlags_.renderer_has_textures.value

    def render(self, draw_data: imgui.ImDrawData) -> None:
        """Draw one frame's ImGui output to the currently bound framebuffer.

        Args:
            draw_data: The result of `imgui.render()` / `get_draw_data()`.
        """
        # Texture requests are serviced first: a command list in this very
        # frame may reference a texture ImGui only just asked for.
        self._service_texture_requests(draw_data)

        framebuffer_width = int(
            draw_data.display_size.x * draw_data.framebuffer_scale.x
        )
        framebuffer_height = int(
            draw_data.display_size.y * draw_data.framebuffer_scale.y
        )
        if framebuffer_width <= 0 or framebuffer_height <= 0:
            return

        # Item assignment rather than `.value =`: `program[name]` is typed
        # as a union of uniform/attribute/varying, and only `__setitem__`
        # is available across all of them (`final_pass.py` does the same).
        self._program["u_display_pos"] = (
            draw_data.display_pos.x,
            draw_data.display_pos.y,
        )
        self._program["u_display_size"] = (
            draw_data.display_size.x,
            draw_data.display_size.y,
        )
        self._program["u_texture"] = 0

        # ImGui draws back-to-front in one 2D layer: depth testing and
        # culling would reject geometry, and blending is how it composites.
        self._ctx.enable(moderngl.BLEND)
        self._ctx.blend_func = (moderngl.SRC_ALPHA, moderngl.ONE_MINUS_SRC_ALPHA)
        self._ctx.disable(moderngl.DEPTH_TEST | moderngl.CULL_FACE)

        try:
            for cmd_list in draw_data.cmd_lists:
                self._render_cmd_list(
                    cmd_list, draw_data, framebuffer_width, framebuffer_height
                )
        finally:
            # A scissor left set would clip whatever the engine draws next,
            # which is the kind of state bleed `blending()` exists to stop.
            self._ctx.scissor = None

    def _render_cmd_list(
        self,
        cmd_list: imgui.ImDrawList,
        draw_data: imgui.ImDrawData,
        framebuffer_width: int,
        framebuffer_height: int,
    ) -> None:
        """Upload one command list's buffers and issue its draw commands.

        Args:
            cmd_list: The ImGui draw list to render.
            draw_data: The frame's draw data, for display offset and scale.
            framebuffer_width: Target width in pixels.
            framebuffer_height: Target height in pixels.
        """
        vertex_count = cmd_list.vtx_buffer.size()
        index_count = cmd_list.idx_buffer.size()
        if vertex_count == 0 or index_count == 0:
            return

        vertex_bytes = ctypes.string_at(
            cmd_list.vtx_buffer.data_address(), vertex_count * _VERTEX_STRIDE
        )
        index_bytes = ctypes.string_at(
            cmd_list.idx_buffer.data_address(), index_count * _INDEX_SIZE
        )

        self._ensure_buffers(len(vertex_bytes), len(index_bytes))
        assert self._vbo is not None and self._ibo is not None
        assert self._vao is not None
        self._vbo.write(vertex_bytes)
        self._ibo.write(index_bytes)

        display_x = draw_data.display_pos.x
        display_y = draw_data.display_pos.y
        scale_x = draw_data.framebuffer_scale.x
        scale_y = draw_data.framebuffer_scale.y

        for command in cmd_list.cmd_buffer:
            if command.elem_count == 0:
                continue

            texture = self._textures.get(command.get_tex_id())
            if texture is None:
                # Nothing sensible to draw with; skipping beats binding
                # whatever happens to be in texture unit 0.
                continue
            texture.use(0)

            clip = command.clip_rect
            min_x = (clip.x - display_x) * scale_x
            min_y = (clip.y - display_y) * scale_y
            max_x = (clip.z - display_x) * scale_x
            max_y = (clip.w - display_y) * scale_y
            if max_x <= min_x or max_y <= min_y:
                continue

            # GL's scissor origin is bottom-left, ImGui's clip rect is
            # top-left, hence the flip against the framebuffer height.
            self._ctx.scissor = (
                int(min_x),
                int(framebuffer_height - max_y),
                int(max_x - min_x),
                int(max_y - min_y),
            )

            # `vtx_offset` is always 0 because this renderer does not
            # declare `renderer_has_vtx_offset`; ImGui then splits draw
            # lists itself rather than emitting a base-vertex offset, which
            # ModernGL's `render()` has no parameter for.
            self._vao.render(
                moderngl.TRIANGLES,
                vertices=command.elem_count,
                first=command.idx_offset,
            )

    def _ensure_buffers(self, vertex_bytes: int, index_bytes: int) -> None:
        """Grow the vertex/index buffers to hold at least this much.

        Args:
            vertex_bytes: Required vertex buffer size in bytes.
            index_bytes: Required index buffer size in bytes.
        """
        if (
            self._vao is not None
            and vertex_bytes <= self._vbo_capacity
            and index_bytes <= self._ibo_capacity
        ):
            return

        self._release_buffers()
        # Round up so a slowly growing UI does not reallocate every frame.
        self._vbo_capacity = max(vertex_bytes, self._vbo_capacity * 2, 65536)
        self._ibo_capacity = max(index_bytes, self._ibo_capacity * 2, 16384)
        self._vbo = self._ctx.buffer(reserve=self._vbo_capacity, dynamic=True)
        self._ibo = self._ctx.buffer(reserve=self._ibo_capacity, dynamic=True)
        self._vao = self._ctx.vertex_array(
            self._program,
            [(self._vbo, _VERTEX_FORMAT, *_VERTEX_ATTRIBUTES)],
            self._ibo,
            index_element_size=_INDEX_SIZE,
        )

    def _service_texture_requests(self, draw_data: imgui.ImDrawData) -> None:
        """Create, update and destroy textures ImGui asked about this frame.

        Args:
            draw_data: The frame's draw data, carrying the texture list.
        """
        for tex_data in draw_data.textures:
            status = tex_data.status
            if status == imgui.ImTextureStatus.want_create:
                self._create_texture(tex_data)
            elif status == imgui.ImTextureStatus.want_updates:
                self._update_texture(tex_data)
            elif status == imgui.ImTextureStatus.want_destroy:
                self._destroy_texture(tex_data)

    def _create_texture(self, tex_data: imgui.ImTextureData) -> None:
        """Upload a new texture and hand ImGui its id.

        Args:
            tex_data: The texture ImGui wants created.
        """
        components = self._components(tex_data)
        texture = self._ctx.texture(
            (tex_data.width, tex_data.height),
            components,
            data=tex_data.get_pixels_array().tobytes(),
        )
        # Linear filtering on a glyph atlas blurs text at 1:1; ImGui's own
        # backends use nearest for exactly this reason.
        texture.filter = (moderngl.NEAREST, moderngl.NEAREST)

        texture_id = self._next_texture_id
        self._next_texture_id += 1
        self._textures[texture_id] = texture

        tex_data.set_tex_id(texture_id)
        tex_data.set_status(imgui.ImTextureStatus.ok)

    def _update_texture(self, tex_data: imgui.ImTextureData) -> None:
        """Re-upload a texture whose pixels ImGui changed.

        The whole image is written rather than only `tex_data.updates`'
        dirty rectangles. A partial write would have to slice each rect out
        of a flat, pitch-strided buffer, and this fires only when the atlas
        grows new glyphs -- rarely, and never per frame.

        Args:
            tex_data: The texture ImGui wants refreshed.
        """
        texture = self._textures.get(tex_data.get_tex_id())
        if texture is None:
            # Never created, or created by a previous renderer instance.
            # Treat it as new so the frame still draws.
            self._create_texture(tex_data)
            return

        texture.write(tex_data.get_pixels_array().tobytes())
        tex_data.set_status(imgui.ImTextureStatus.ok)

    def _destroy_texture(self, tex_data: imgui.ImTextureData) -> None:
        """Release a texture ImGui is finished with.

        Args:
            tex_data: The texture ImGui wants destroyed.
        """
        texture = self._textures.pop(tex_data.get_tex_id(), None)
        if texture is not None:
            texture.release()
        tex_data.set_tex_id(0)
        tex_data.set_status(imgui.ImTextureStatus.destroyed)

    @staticmethod
    def _components(tex_data: imgui.ImTextureData) -> int:
        """Return the channel count for a texture's pixel format.

        Args:
            tex_data: The texture to inspect.

        Returns:
            4 for RGBA32, 1 for Alpha8.
        """
        if tex_data.format == imgui.ImTextureFormat.alpha8:
            return 1
        return 4

    def _release_buffers(self) -> None:
        """Release the VAO and its buffers, if they exist."""
        for resource in (self._vao, self._vbo, self._ibo):
            if resource is not None:
                resource.release()
        self._vao = None
        self._vbo = None
        self._ibo = None

    def release(self) -> None:
        """Release every GL resource this renderer owns.

        Safe to call more than once; the context itself is not touched.
        """
        self._release_buffers()
        self._vbo_capacity = 0
        self._ibo_capacity = 0

        for texture in self._textures.values():
            texture.release()
        self._textures.clear()
        self._program.release()
