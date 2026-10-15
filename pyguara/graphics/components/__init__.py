"""The graphics components: what a renderer draws, as data.

Every name here is a component or one of its close data types. Behaviour
lives in the matching system -- `AnimationSystem` for `Animator`, the
camera systems for `Camera2D`, `RenderSystem` for `Sprite`.

This module previously held a verbatim copy of
`pyguara/ui/components/__init__.py`, exporting `Button`, `Panel`,
`TextInput` and the rest of the widget set from a graphics package. It
broke nothing only because no caller imports this package root -- every
call site reaches for the submodule directly -- but it inverted the
layering: importing anything under `pyguara.graphics.components` pulled
`pyguara.ui` in behind it. `tests/test_graphics_exports.py` now holds a
test for that, because nothing else would have caught it coming back.
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
    Particle,
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
    "Particle",
    "ParticleEmitterConfig",
    "ParticleSystem",
    "ScreenFlash",
]
