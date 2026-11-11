"""Material system for PyGuara's rendering pipeline.

This module provides:
- Shader: Wrapper around GPU shader programs
- ShaderCache: Caches compiled shaders to avoid redundant compilation
- SpriteShader: A sprite's own shader, in WGSL, for every GPU backend
- Uniform: One value a SpriteShader takes
- Material: Combines shader + texture + uniforms for rendering
- DefaultMaterialManager: Provides standard sprite materials
"""

from pyguara.graphics.materials.defaults import (
    DEFAULT_SPRITE_FRAGMENT,
    DEFAULT_SPRITE_VERTEX,
    DefaultMaterialManager,
    create_default_material_manager,
)
from pyguara.graphics.materials.material import Material, reset_material_id_counter
from pyguara.graphics.materials.shader import Shader, ShaderCache
from pyguara.graphics.pipeline.device import SpriteShader, Uniform

__all__ = [
    "Material",
    "Shader",
    "ShaderCache",
    "SpriteShader",
    "Uniform",
    "DefaultMaterialManager",
    "create_default_material_manager",
    "reset_material_id_counter",
    "DEFAULT_SPRITE_VERTEX",
    "DEFAULT_SPRITE_FRAGMENT",
]
