"""Scene management and transitions."""

from pyguara.scene.base import Scene
from pyguara.scene.manager import SceneManager
from pyguara.scene.transitions import (
    Transition,
    TransitionConfig,
    TransitionState,
    EasingFunction,
    FadeTransition,
    SlideTransition,
    WipeTransition,
    CircularWipeTransition,
    TransitionManager,
)

__all__ = [
    # Base
    "Scene",
    "SceneManager",
    # Transitions
    "Transition",
    "TransitionConfig",
    "TransitionState",
    "EasingFunction",
    "FadeTransition",
    "SlideTransition",
    "WipeTransition",
    "CircularWipeTransition",
    "TransitionManager",
]
