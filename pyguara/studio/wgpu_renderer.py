"""Rasterise Dear ImGui draw data through the native wgpu frame.

The editor's renderer, on `NativeGpu.mesh`. A frame's draw lists become one
indexed triangle list, drawn command by command, each with its own texture
and clip rectangle, into whatever target is current -- the window, when
`ImGuiPass` runs.

ImGui 1.92's dynamic textures are honoured: the font atlas
arrives as a request on the draw data (`want_create`, `want_updates`,
`want_destroy`), so `ImGuiBackendFlags_RendererHasTextures` is declared.

A render target -- the game's frame, shown in the Viewport panel -- is
registered as it is, and sampled directly. Its rows run top-down, as
ImGui's do, so it needs no flip.
"""

from __future__ import annotations

import ctypes
from typing import Any

import numpy as np
from imgui_bundle import imgui

from pyguara.log import get_logger

logger = get_logger(__name__)

# sizeof(ImDrawVert): pos (2 x f32) + uv (2 x f32) + col (packed RGBA8).
_VERTEX_STRIDE = 20
# ImDrawIdx is 32-bit in imgui-bundle's build.
_INDEX_SIZE = 4

# What a texture id resolves to: an uploaded texture or a render target.
_IMAGE, _TARGET = 0, 1


class WgpuImGuiRenderer:
    """Draws ImGui draw data with the native frame's mesh step."""

    def __init__(self, frame: Any) -> None:
        """Declare renderer capabilities to ImGui.

        Args:
            frame: The `GpuFrame` the renderers draw into. Not owned.
        """
        self._gpu = frame.gpu
        # ImGui's id -> (kind, native id).
        self._textures: dict[int, tuple[int, int]] = {}
        self._next_texture_id = 1
        self._foreign_texture_ids: set[int] = set()
        self._foreign_ids_by_target: dict[int, int] = {}

        io = imgui.get_io()
        io.backend_flags |= imgui.BackendFlags_.renderer_has_textures.value

    def register_texture(self, texture: Any) -> int:
        """Make a render target drawable by ImGui, and return its id.

        Ownership stays with the caller. Idempotent: the same target always
        maps to the same id, so this is safe to call once per frame.

        Args:
            texture: A wgpu framebuffer from the render graph's manager.

        Returns:
            The id to hand `imgui.image()`.
        """
        target = getattr(texture, "target", None)
        if not isinstance(target, int):
            raise TypeError(f"{texture!r} is not a wgpu framebuffer")
        existing = self._foreign_ids_by_target.get(target)
        if existing is not None:
            return existing
        texture_id = self._next_texture_id
        self._next_texture_id += 1
        self._textures[texture_id] = (_TARGET, target)
        self._foreign_texture_ids.add(texture_id)
        self._foreign_ids_by_target[target] = texture_id
        return texture_id

    def unregister_texture(self, texture_id: int) -> None:
        """Stop resolving `texture_id`, without freeing the target.

        Args:
            texture_id: An id previously returned by `register_texture`.
        """
        if texture_id not in self._foreign_texture_ids:
            return
        found = self._textures.pop(texture_id, None)
        self._foreign_texture_ids.discard(texture_id)
        if found is not None:
            self._foreign_ids_by_target.pop(found[1], None)

    def render(self, draw_data: imgui.ImDrawData) -> None:
        """Queue one frame's ImGui output into the current target.

        Args:
            draw_data: The result of `imgui.render()` / `get_draw_data()`.
        """
        self._service_texture_requests(draw_data)
        scale_x = draw_data.framebuffer_scale.x
        scale_y = draw_data.framebuffer_scale.y
        if draw_data.display_size.x <= 0 or draw_data.display_size.y <= 0:
            return
        display_x, display_y = draw_data.display_pos.x, draw_data.display_pos.y

        vertex_parts: list[bytes] = []
        index_parts: list[np.ndarray] = []
        commands: list[tuple[int, int, int, int, int, int, int, int]] = []
        vertex_base = 0
        index_base = 0
        for cmd_list in draw_data.cmd_lists:
            vertex_count = cmd_list.vtx_buffer.size()
            index_count = cmd_list.idx_buffer.size()
            if vertex_count == 0 or index_count == 0:
                continue
            vertex_parts.append(
                ctypes.string_at(
                    cmd_list.vtx_buffer.data_address(), vertex_count * _VERTEX_STRIDE
                )
            )
            indices = np.frombuffer(
                ctypes.string_at(
                    cmd_list.idx_buffer.data_address(), index_count * _INDEX_SIZE
                ),
                dtype="<u4",
            )
            # One buffer for every list, so each list's indices move up past
            # the vertices before it.
            index_parts.append(indices + np.uint32(vertex_base))
            for command in cmd_list.cmd_buffer:
                if command.elem_count == 0:
                    continue
                found = self._textures.get(command.get_tex_id())
                if found is None:
                    continue
                clip = command.clip_rect
                left = (clip.x - display_x) * scale_x
                top = (clip.y - display_y) * scale_y
                right = (clip.z - display_x) * scale_x
                bottom = (clip.w - display_y) * scale_y
                if right <= left or bottom <= top:
                    continue
                commands.append(
                    (
                        found[0],
                        found[1],
                        int(left),
                        int(top),
                        int(right - left),
                        int(bottom - top),
                        index_base + command.idx_offset,
                        command.elem_count,
                    )
                )
            vertex_base += vertex_count
            index_base += index_count

        if not commands:
            return
        self._gpu.mesh(
            self._gpu.current_target,
            b"".join(vertex_parts),
            np.concatenate(index_parts).astype("<u4").tobytes(),
            commands,
            (
                display_x,
                display_y,
                draw_data.display_size.x,
                draw_data.display_size.y,
            ),
        )

    def _service_texture_requests(self, draw_data: imgui.ImDrawData) -> None:
        """Create, update and destroy textures ImGui asked about this frame."""
        for tex_data in draw_data.textures:
            status = tex_data.status
            if status == imgui.ImTextureStatus.want_create:
                self._create_texture(tex_data)
            elif status == imgui.ImTextureStatus.want_updates:
                self._update_texture(tex_data)
            elif status == imgui.ImTextureStatus.want_destroy:
                self._destroy_texture(tex_data)

    @staticmethod
    def _rgba(tex_data: imgui.ImTextureData) -> bytes:
        """Return the texture's pixels as RGBA; an Alpha8 atlas becomes white."""
        pixels = np.asarray(tex_data.get_pixels_array(), dtype=np.uint8).ravel()
        if tex_data.format == imgui.ImTextureFormat.alpha8:
            rgba = np.full((pixels.size, 4), 255, dtype=np.uint8)
            rgba[:, 3] = pixels
            return rgba.tobytes()
        return pixels.tobytes()

    def _create_texture(self, tex_data: imgui.ImTextureData) -> None:
        """Upload a new texture and hand ImGui its id."""
        native = self._gpu.create_texture(
            tex_data.width, tex_data.height, self._rgba(tex_data)
        )
        texture_id = self._next_texture_id
        self._next_texture_id += 1
        self._textures[texture_id] = (_IMAGE, native)
        tex_data.set_tex_id(texture_id)
        tex_data.set_status(imgui.ImTextureStatus.ok)

    def _update_texture(self, tex_data: imgui.ImTextureData) -> None:
        """Re-upload a texture whose pixels ImGui changed, whole."""
        found = self._textures.get(tex_data.get_tex_id())
        if found is None or found[0] != _IMAGE:
            self._create_texture(tex_data)
            return
        self._gpu.update_texture(
            found[1], tex_data.width, tex_data.height, self._rgba(tex_data)
        )
        tex_data.set_status(imgui.ImTextureStatus.ok)

    def _destroy_texture(self, tex_data: imgui.ImTextureData) -> None:
        """Release a texture ImGui is finished with."""
        found = self._textures.pop(tex_data.get_tex_id(), None)
        if found is not None and found[0] == _IMAGE:
            self._gpu.destroy_texture(found[1])
        tex_data.set_tex_id(0)
        tex_data.set_status(imgui.ImTextureStatus.destroyed)

    def release(self) -> None:
        """Free every texture this renderer made. Safe to call twice."""
        for texture_id, (kind, native) in self._textures.items():
            if kind == _IMAGE and texture_id not in self._foreign_texture_ids:
                self._gpu.destroy_texture(native)
        self._textures.clear()
        self._foreign_texture_ids.clear()
        self._foreign_ids_by_target.clear()
