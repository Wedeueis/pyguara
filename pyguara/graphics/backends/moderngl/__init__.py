"""ModernGL rendering backend with GPU-accelerated hardware instancing.

This module provides a high-performance rendering backend using ModernGL
for GPU-accelerated sprite rendering with hardware instancing support.

Key Features:
- OpenGL 3.3+ Core Profile rendering
- Hardware instancing for batch rendering 10,000+ sprites at 60 FPS
- Alpha blending with correct ordering
- Coordinate system matching Pygame (top-left origin, Y-down)
- Hybrid UI rendering using pygame for text/primitives

Usage:
    Set `backend: moderngl` in your window configuration to enable
    the ModernGL backend instead of the default Pygame backend.
"""

from pyguara.graphics.backends.moderngl.window import PygameGLWindow
from pyguara.graphics.backends.moderngl.renderer import ModernGLRenderer
from pyguara.graphics.backends.moderngl.texture import GLTexture, GLTextureFactory
from pyguara.graphics.backends.moderngl.loaders import GLTextureLoader
from pyguara.graphics.backends.moderngl.ui_renderer import GLUIRenderer

__all__ = [
    "PygameGLWindow",
    "ModernGLRenderer",
    "GLTexture",
    "GLTextureFactory",
    "GLTextureLoader",
    "GLUIRenderer",
]
