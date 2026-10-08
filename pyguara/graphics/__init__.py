"""Graphics: the rendering pipeline, its components, and the backends.

Re-exported here so the rendering surface is reachable without knowing which
submodule each name lives in. `from pyguara.graphics import Sprite,
Camera2D, RenderSystem` used to find nothing at all -- only the nine-patch
helpers were exported -- which made the whole package undiscoverable without
reading it.

Backends are deliberately absent: importing this must not pull in pygame or
moderngl. Reach for `pyguara.graphics.backends.<name>` when you mean a
specific one, and otherwise take `IRenderer` from the DI container.
"""

from pyguara.graphics.animation_system import AnimationSystem
from pyguara.graphics.atlas import Atlas, AtlasRegion
from pyguara.graphics.components.animation import (
    AnimationClip,
    AnimationState,
    AnimationStateMachine,
    AnimationTransition,
    Animator,
)
from pyguara.graphics.components.camera import (
    Camera2D,
    CameraFollowConstraints,
    CameraFraming,
    CameraShake,
    CameraZoomTransition,
)
from pyguara.graphics.components.floating_text import FloatingText
from pyguara.graphics.components.sprite import Sprite
from pyguara.graphics.ninepatch import (
    NinePatchMetrics,
    NinePatchSprite,
    render_ninepatch,
)
from pyguara.graphics.pipeline.batch import Batcher
from pyguara.graphics.pipeline.queue import RenderQueue
from pyguara.graphics.pipeline.render_system import RenderSystem
from pyguara.graphics.pipeline.viewport import Viewport
from pyguara.graphics.protocols import (
    IRenderer,
    Renderable,
    UIRenderer,
)
from pyguara.graphics.spritesheet import SpriteSheet
from pyguara.graphics.types import Layer, RenderBatch, RenderCommand
from pyguara.graphics.window import Window

__all__ = [
    # Components
    "AnimationClip",
    "AnimationState",
    "AnimationStateMachine",
    "AnimationTransition",
    "Animator",
    "Camera2D",
    "CameraFollowConstraints",
    "CameraFraming",
    "CameraShake",
    "CameraZoomTransition",
    "FloatingText",
    "Sprite",
    # Pipeline
    "AnimationSystem",
    "Batcher",
    "RenderQueue",
    "RenderSystem",
    "Viewport",
    # Protocols
    "IRenderer",
    "Renderable",
    "UIRenderer",
    # Types
    "Layer",
    "RenderBatch",
    "RenderCommand",
    # Textures
    "Atlas",
    "AtlasRegion",
    "SpriteSheet",
    # Nine-patch
    "NinePatchMetrics",
    "NinePatchSprite",
    "render_ninepatch",
    # Window
    "Window",
]
