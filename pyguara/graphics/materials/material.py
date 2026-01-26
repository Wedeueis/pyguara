"""Material system for combining shaders, textures, and uniforms.

A Material defines the visual appearance of rendered objects by
combining a shader program with textures and uniform parameters.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Optional

if TYPE_CHECKING:
    from pyguara.graphics.materials.shader import Shader
    from pyguara.resources.types import Texture


# Global material ID counter for sorting
_next_material_id: int = 0


def _generate_material_id() -> int:
    """Generate a unique material ID."""
    global _next_material_id
    _next_material_id += 1
    return _next_material_id


@dataclass
class Material:
    """Defines the visual properties of a rendered object.

    Materials combine:
    - A shader program for GPU processing
    - A primary texture (for sprite materials)
    - Custom uniform values

    Materials are sorted by ID during batching to minimize
    shader/texture switches.
    """

    shader: "Shader"
    texture: Optional["Texture"] = None
    uniforms: dict[str, Any] = field(default_factory=dict)

    # Unique ID for sorting (assigned at creation)
    _id: int = field(default_factory=_generate_material_id, repr=False)

    @property
    def id(self) -> int:
        """Unique material identifier for sorting."""
        return self._id

    def bind(self) -> None:
        """Bind this material for rendering.

        Activates the shader and sets all uniforms.
        """
        self.shader.use()

        # Set custom uniforms
        for name, value in self.uniforms.items():
            self.shader.set_uniform(name, value)

        # Bind primary texture if present
        if self.texture is not None:
            gl_texture = self.texture.native_handle
            if gl_texture is not None:
                gl_texture.use(0)
                self.shader.set_uniform("u_texture", 0)

    def set_uniform(self, name: str, value: Any) -> None:
        """Set a uniform value.

        Args:
            name: The uniform name.
            value: The value to set.
        """
        self.uniforms[name] = value

    def get_uniform(self, name: str, default: Any = None) -> Any:
        """Get a uniform value.

        Args:
            name: The uniform name.
            default: Default value if uniform not set.

        Returns:
            The uniform value or default.
        """
        return self.uniforms.get(name, default)

    def clone(self) -> "Material":
        """Create a copy of this material with a new ID.

        Useful for creating variations with different uniforms.

        Returns:
            A new Material with the same shader/texture but new ID.
        """
        return Material(
            shader=self.shader,
            texture=self.texture,
            uniforms=self.uniforms.copy(),
        )


def reset_material_id_counter() -> None:
    """Reset the material ID counter.

    Primarily for testing purposes.
    """
    global _next_material_id
    _next_material_id = 0
