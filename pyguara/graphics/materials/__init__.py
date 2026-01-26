"""Material system for PyGuara's rendering pipeline.

This module provides:
- Shader: Wrapper around GPU shader programs
- ShaderCache: Caches compiled shaders to avoid redundant compilation
- Material: Combines shader + texture + uniforms for rendering
- DefaultMaterialManager: Provides standard sprite materials
"""

from pyguara.graphics.materials.material import Material, reset_material_id_counter
from pyguara.graphics.materials.shader import Shader, ShaderCache
from pyguara.graphics.materials.defaults import (
    DefaultMaterialManager,
    create_default_material_manager,
    DEFAULT_SPRITE_VERTEX,
    DEFAULT_SPRITE_FRAGMENT,
)

__all__ = [
    "Material",
    "Shader",
    "ShaderCache",
    "DefaultMaterialManager",
    "create_default_material_manager",
    "reset_material_id_counter",
    "DEFAULT_SPRITE_VERTEX",
    "DEFAULT_SPRITE_FRAGMENT",
]
