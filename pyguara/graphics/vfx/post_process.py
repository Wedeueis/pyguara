"""Post-processing effect stack manager.

This module provides the PostProcessStack which chains multiple
screen-space effects using ping-pong framebuffers for efficient
multi-pass processing.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import TYPE_CHECKING

from pyguara.log import get_logger

if TYPE_CHECKING:
    import moderngl

    from pyguara.graphics.pipeline.framebuffer import Framebuffer, FramebufferManager


# Shader directory
_SHADER_DIR = Path(__file__).parent.parent / "backends" / "moderngl" / "shaders"


logger = get_logger(__name__)


class PostProcessEffect(ABC):
    """Base class for post-processing effects.

    Effects read from an input framebuffer and write to an output
    framebuffer, transforming the image in some way.
    """

    def __init__(self, name: str, *, enabled: bool = True) -> None:
        """Initialize the effect.

        Args:
            name: Unique identifier for this effect.
            enabled: Whether this effect is active.
        """
        self._name = name
        self._enabled = enabled

    @property
    def name(self) -> str:
        """Effect identifier."""
        return self._name

    @property
    def enabled(self) -> bool:
        """Whether this effect should be applied."""
        return self._enabled

    @enabled.setter
    def enabled(self, value: bool) -> None:
        """Enable or disable this effect."""
        self._enabled = value

    @abstractmethod
    def apply(
        self,
        ctx: moderngl.Context,
        input_fbo: Framebuffer,
        output_fbo: Framebuffer,
    ) -> None:
        """Apply this effect.

        Args:
            ctx: The ModernGL context.
            input_fbo: Framebuffer to read from.
            output_fbo: Framebuffer to write to.
        """
        ...

    def on_resize(self, width: int, height: int) -> None:
        """Handle viewport resize.

        Override if the effect needs to update internal state.

        Args:
            width: New viewport width.
            height: New viewport height.
        """
        pass

    def release(self) -> None:
        """Release GPU resources.

        Override if the effect owns GPU objects.
        """
        pass


class PostProcessStack:
    """Manager for chainable post-processing effects.

    Uses ping-pong framebuffers to efficiently chain multiple
    effects without excessive memory allocation.
    """

    def __init__(
        self,
        ctx: moderngl.Context,
        fbo_manager: FramebufferManager,
    ) -> None:
        """Initialize the post-processing stack.

        Args:
            ctx: The ModernGL context.
            fbo_manager: The framebuffer manager for creating temp FBOs.
        """
        self._ctx = ctx
        self._fbo_manager = fbo_manager
        self._effects: list[PostProcessEffect] = []

        # Ping-pong buffer names
        self._ping_name = "_pp_ping"
        self._pong_name = "_pp_pong"

    @property
    def effects(self) -> list[PostProcessEffect]:
        """The effects, in application order.

        A snapshot: change the stack through `add_effect()`,
        `insert_effect()` and `remove_effect()`. This used to hand back the
        live list, so `stack.effects.clear()` silently emptied the stack
        without releasing a single effect.
        """
        return list(self._effects)

    def add_effect(self, effect: PostProcessEffect) -> None:
        """Append an effect to the stack.

        Args:
            effect: The effect to add. Its name should be unique; effects are
                looked up by name, so a duplicate is unreachable through
                `get_effect()` and survives `remove_effect()`.
        """
        self._warn_if_name_taken(effect)
        self._effects.append(effect)

    def insert_effect(self, index: int, effect: PostProcessEffect) -> None:
        """Insert an effect at a position in the stack.

        Args:
            index: Position in the stack.
            effect: The effect to insert. Its name should be unique; see
                `add_effect()`.
        """
        self._warn_if_name_taken(effect)
        self._effects.insert(index, effect)

    def _warn_if_name_taken(self, effect: PostProcessEffect) -> None:
        """Report that an effect name now refers to more than one effect.

        Both apply -- the effect list is the source of truth -- but
        `get_effect()` returns only the first and `remove_effect()` removes
        only the first, so the second is unreachable by name. The sibling
        `RenderGraph` treats duplicate pass names the same way.

        Args:
            effect: The effect about to be added.
        """
        if any(existing.name == effect.name for existing in self._effects):
            logger.warning(
                f"A second post-process effect named '{effect.name}' is being "
                f"added. Both will apply, but get_effect() and remove_effect() "
                f"only ever reach the first. Give each effect a distinct name."
            )

    def remove_effect(self, name: str) -> PostProcessEffect | None:
        """Remove an effect by name.

        Args:
            name: The effect identifier.

        Returns:
            The removed effect, or None if not found.
        """
        for i, effect in enumerate(self._effects):
            if effect.name == name:
                return self._effects.pop(i)
        return None

    def get_effect(self, name: str) -> PostProcessEffect | None:
        """Get an effect by name.

        Args:
            name: The effect identifier.

        Returns:
            The effect if found, None otherwise.
        """
        for effect in self._effects:
            if effect.name == name:
                return effect
        return None

    def process(self, input_fbo: Framebuffer) -> Framebuffer:
        """Process the input through all enabled effects.

        Uses ping-pong buffers to chain effects efficiently.

        Args:
            input_fbo: The framebuffer to process.

        Returns:
            The final processed framebuffer.
        """
        # Get enabled effects
        enabled_effects = [e for e in self._effects if e.enabled]

        if not enabled_effects:
            # No effects to apply
            return input_fbo

        # Get or create ping-pong buffers
        ping = self._fbo_manager.get_or_create(self._ping_name)
        pong = self._fbo_manager.get_or_create(self._pong_name)

        # Start with input -> ping
        current_input = input_fbo
        current_output = ping

        for i, effect in enumerate(enabled_effects):
            effect.apply(self._ctx, current_input, current_output)

            # Swap for next effect
            if i < len(enabled_effects) - 1:
                # Alternate between ping and pong
                if current_output is ping:
                    current_input = ping
                    current_output = pong
                else:
                    current_input = pong
                    current_output = ping

        # Return the last output
        return current_output

    def on_resize(self, width: int, height: int) -> None:
        """Handle viewport resize.

        Args:
            width: New viewport width.
            height: New viewport height.
        """
        for effect in self._effects:
            effect.on_resize(width, height)

    def release(self) -> None:
        """Release all effects and resources."""
        for effect in self._effects:
            effect.release()
        self._effects.clear()
