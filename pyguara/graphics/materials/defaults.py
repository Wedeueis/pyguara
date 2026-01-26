"""Default materials and shader sources.

Provides the standard sprite material used when renderables
don't specify a custom material.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Optional

from pyguara.graphics.materials.material import Material
from pyguara.graphics.materials.shader import Shader, ShaderCache

if TYPE_CHECKING:
    import moderngl

    from pyguara.resources.types import Texture


# Shader directory relative to this module
_SHADER_DIR = Path(__file__).parent.parent / "backends" / "moderngl" / "shaders"


# Default sprite vertex shader (inline for quick access)
DEFAULT_SPRITE_VERTEX = """#version 330 core

// Quad vertex attributes (static geometry)
layout(location = 0) in vec2 in_vert;   // Quad vertex position (-0.5 to 0.5)
layout(location = 1) in vec2 in_uv;     // Texture coordinates (0.0 to 1.0)

// Per-instance attributes (dynamic, changes per sprite)
layout(location = 2) in vec2 in_pos;    // Screen position (pixels)
layout(location = 3) in float in_rot;   // Rotation (radians)
layout(location = 4) in vec2 in_scale;  // Scale factor
layout(location = 5) in vec2 in_size;   // Texture dimensions (pixels)

// Uniforms
uniform mat4 u_projection;

// Output to fragment shader
out vec2 v_uv;

void main() {
    // Apply size and scale to the base quad vertex
    vec2 sized = in_vert * in_size * in_scale;

    // Apply rotation (2D rotation matrix)
    float c = cos(in_rot);
    float s = sin(in_rot);
    vec2 rotated = mat2(c, -s, s, c) * sized;

    // Translate to screen position and project
    gl_Position = u_projection * vec4(rotated + in_pos, 0.0, 1.0);

    // Pass UV coordinates to fragment shader
    v_uv = in_uv;
}
"""

# Default sprite fragment shader (inline for quick access)
DEFAULT_SPRITE_FRAGMENT = """#version 330 core

// Input from vertex shader
in vec2 v_uv;

// Output color
out vec4 frag_color;

// Texture sampler
uniform sampler2D u_texture;

void main() {
    // Sample the texture and output with alpha
    frag_color = texture(u_texture, v_uv);
}
"""


class DefaultMaterialManager:
    """Manager for default materials.

    Provides lazy initialization of default materials to avoid
    creating GPU resources before the context is ready.
    """

    def __init__(self, shader_cache: ShaderCache) -> None:
        """Initialize the default material manager.

        Args:
            shader_cache: The shader cache for compiling shaders.
        """
        self._shader_cache = shader_cache
        self._default_sprite_shader: Optional[Shader] = None
        self._default_sprite_material: Optional[Material] = None

    @property
    def default_sprite_shader(self) -> Shader:
        """Get the default sprite shader (lazy initialization)."""
        if self._default_sprite_shader is None:
            self._default_sprite_shader = self._shader_cache.get_or_compile(
                "default_sprite",
                DEFAULT_SPRITE_VERTEX,
                DEFAULT_SPRITE_FRAGMENT,
            )
        return self._default_sprite_shader

    def get_default_sprite_material(
        self, texture: Optional["Texture"] = None
    ) -> Material:
        """Get a default sprite material.

        Args:
            texture: Optional texture for the material.

        Returns:
            A Material using the default sprite shader.
        """
        return Material(
            shader=self.default_sprite_shader,
            texture=texture,
        )

    def get_or_create_default(self) -> Material:
        """Get the singleton default sprite material (no texture).

        Returns:
            The default sprite material.
        """
        if self._default_sprite_material is None:
            self._default_sprite_material = Material(
                shader=self.default_sprite_shader,
                texture=None,
            )
        return self._default_sprite_material


def create_default_material_manager(ctx: "moderngl.Context") -> DefaultMaterialManager:
    """Create a default material manager with a new shader cache.

    Args:
        ctx: The ModernGL context.

    Returns:
        A configured DefaultMaterialManager.
    """
    shader_cache = ShaderCache(ctx)
    return DefaultMaterialManager(shader_cache)
