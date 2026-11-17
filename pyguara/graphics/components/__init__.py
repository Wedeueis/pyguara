"""The graphics components: what a renderer draws, as data.

Every name here is a component or one of its close data types. Behaviour
lives in the matching system -- `AnimationSystem` for `Animator`, the
camera systems for `Camera2D`, `RenderSystem` for `Sprite`.

Nothing here imports `pyguara.ui`.
"""

from pyguara.graphics.components.animation import (
    AnimationClip,
    AnimationState,
    AnimationStateMachine,
    AnimationTransition,
    Animator,
    PlaybackMode,
    TransitionCondition,
)
from pyguara.graphics.components.camera import (
    Camera2D,
    CameraFollowConstraints,
    CameraFraming,
    CameraShake,
    CameraZoomTransition,
)
from pyguara.graphics.components.floating_text import FloatingText
from pyguara.graphics.components.geometry import Box, Circle, Geometry
from pyguara.graphics.components.particles import (
    ParticleEmitterConfig,
    ParticleSystem,
)
from pyguara.graphics.components.screen_flash import ScreenFlash
from pyguara.graphics.components.sprite import Sprite

__all__ = [
    # Animation
    "AnimationClip",
    "AnimationState",
    "AnimationStateMachine",
    "AnimationTransition",
    "Animator",
    "PlaybackMode",
    "TransitionCondition",
    # Camera
    "Camera2D",
    "CameraFollowConstraints",
    "CameraFraming",
    "CameraShake",
    "CameraZoomTransition",
    # Drawing
    "Box",
    "Circle",
    "FloatingText",
    "Geometry",
    "Sprite",
    # Effects
    "ParticleEmitterConfig",
    "ParticleSystem",
    "ScreenFlash",
]
