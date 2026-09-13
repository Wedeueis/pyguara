"""Default materials and shader sources.

Provides the standard sprite material used when renderables
don't specify a custom material.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from pyguara.graphics.materials.material import Material
from pyguara.graphics.materials.shader import Shader, ShaderCache

if TYPE_CHECKING:
    import moderngl

    from pyguara.resources.types import Texture


# Shader directory relative to this module
_SHADER_DIR = Path(__file__).parent.parent / "backends" / "moderngl" / "shaders"


# The default sprite shaders, read from the same files `ModernGLRenderer`
# compiles. These were inline copies "for quick access" until the sprite
# path grew a per-instance tint and the copies silently stopped matching
# the shaders actually in use -- one shader, one source.
DEFAULT_SPRITE_VERTEX = (_SHADER_DIR / "sprite.vert").read_text()
DEFAULT_SPRITE_FRAGMENT = (_SHADER_DIR / "sprite.frag").read_text()


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
        self._default_sprite_shader: Shader | None = None
        self._default_sprite_material: Material | None = None

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

    def get_default_sprite_material(self, texture: Texture | None = None) -> Material:
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


def create_default_material_manager(ctx: moderngl.Context) -> DefaultMaterialManager:
    """Create a default material manager with a new shader cache.

    Args:
        ctx: The ModernGL context.

    Returns:
        A configured DefaultMaterialManager.
    """
    shader_cache = ShaderCache(ctx)
    return DefaultMaterialManager(shader_cache)
