"""Material system for PyGuara's rendering pipeline.

This module provides:
- SpriteShader: A sprite's own shader, one WGSL function
- Uniform: One value a SpriteShader takes
- Material: Combines a shader, an optional second texture and uniforms
"""

from pyguara.graphics.materials.material import Material, reset_material_id_counter
from pyguara.graphics.pipeline.device import SpriteShader, Uniform

__all__ = [
    "Material",
    "SpriteShader",
    "Uniform",
    "reset_material_id_counter",
]
