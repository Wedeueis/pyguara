"""Module 2: ECS Components

Pure data containers. No logic allowed here!
"""

from dataclasses import dataclass
from pyguara.ecs.component import Component
from pyguara.common.types import Vector2, Color

@dataclass
class Transform(Component):
    """Stores position in world space."""
    position: Vector2
    
@dataclass
class Sprite(Component):
    """Visual representation (simple colored rect for now)."""
    color: Color
    size: Vector2
