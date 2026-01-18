"""Base scene abstraction."""

from abc import ABC, abstractmethod
from typing import Optional

from pyguara.di.container import DIContainer  # Import Container
from pyguara.ecs.manager import EntityManager
from pyguara.events.dispatcher import EventDispatcher
from pyguara.graphics.protocols import UIRenderer, IRenderer
from pyguara.graphics.components.animation import Animator, AnimationStateMachine


class Scene(ABC):
    """
    Abstract base class for all game scenes.

    Manages the lifecycle of a specific game state (Menu, Gameplay, etc).
    """

    def __init__(self, name: str, event_dispatcher: EventDispatcher) -> None:
        """Initialize the scene."""
        self.name = name
        self.event_dispatcher = event_dispatcher
        self.entity_manager = EntityManager()

        # New: Application will set this before on_enter
        self.container: Optional[DIContainer] = None

    def resolve_dependencies(self, container: DIContainer) -> None:
        """
        Call by the Application/SceneManager to inject the container.

        Override this if you want to grab specific services immediately,
        or just use self.container.get() in on_enter().
        """
        self.container = container

    def update_animations(self, dt: float) -> None:
        """
        Update all animation components in the scene.

        Automatically updates all Animator and AnimationStateMachine components.
        Call this in your scene's update() method to enable automatic animation updates.

        Args:
            dt (float): Delta time in seconds.

        Example:
            def update(self, dt: float) -> None:
                self.update_animations(dt)  # Update all animations
                # ... rest of scene logic
        """
        # Update AnimationStateMachine components (higher priority)
        for entity in self.entity_manager.get_entities_with(AnimationStateMachine):
            fsm = entity.get_component(AnimationStateMachine)
            fsm.update(dt)

        # Update standalone Animator components (if not controlled by FSM)
        for entity in self.entity_manager.get_entities_with(Animator):
            # Skip if entity also has AnimationStateMachine (FSM updates animator)
            if not entity.has_component(AnimationStateMachine):
                animator = entity.get_component(Animator)
                animator.update(dt)

    @abstractmethod
    def on_enter(self) -> None:
        """Lifecycle hook: Called when scene becomes active."""
        ...

    @abstractmethod
    def on_exit(self) -> None:
        """Lifecycle hook: Called when scene is removed/swapped."""
        ...

    def on_pause(self) -> None:
        """Lifecycle hook: Called when scene is covered by another scene.

        Override this to pause game logic, music, etc. when the scene is no longer
        the top of the stack. By default, does nothing.
        """
        pass

    def on_resume(self) -> None:
        """Lifecycle hook: Called when scene becomes top of stack again.

        Override this to resume game logic, music, etc. when returning to this scene
        after a scene above it is popped. By default, does nothing.
        """
        pass

    def fixed_update(self, fixed_dt: float) -> None:
        """Fixed-rate update for physics and deterministic game logic.

        Called at a fixed rate (default 60 Hz) regardless of display framerate.
        Override this method to implement physics, collision detection, and
        game logic that must behave consistently regardless of frame rate.

        Args:
            fixed_dt: Fixed delta time in seconds (e.g., 1/60 for 60 Hz physics).

        Example:
            def fixed_update(self, fixed_dt: float) -> None:
                # Physics updates at consistent rate
                self.physics_system.update(fixed_dt)
                # AI decisions at fixed rate for determinism
                self.ai_system.update(fixed_dt)
        """
        pass  # Default: no fixed update logic

    @abstractmethod
    def update(self, dt: float) -> None:
        """Variable-rate update for animations and visual effects.

        Called once per frame at display framerate. Use this for:
        - Smooth animations and tweens
        - Camera smoothing
        - Particle effects
        - Audio updates

        For physics and game logic, use fixed_update() instead.

        Args:
            dt: Variable delta time in seconds (frame time).
        """
        ...

    @abstractmethod
    def render(self, world_renderer: IRenderer, ui_renderer: UIRenderer) -> None:
        """Frame render logic."""
        ...
