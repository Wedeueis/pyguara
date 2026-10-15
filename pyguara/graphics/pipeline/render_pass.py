"""Base classes for render passes in the pipeline.

Render passes are discrete stages in the rendering pipeline. Each pass
reads from zero or more input framebuffers and writes to an output
framebuffer (or the screen).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import moderngl

    from pyguara.graphics.pipeline.graph import RenderGraph


class BaseRenderPass(ABC):
    """Abstract base class for render passes.

    Subclasses implement specific rendering stages (world, lighting,
    post-processing, UI compositing).
    """

    def __init__(
        self, name: str, *, enabled: bool = True, after_ui: bool = False
    ) -> None:
        """Initialize the render pass.

        Args:
            name: Unique identifier for this pass.
            enabled: Whether this pass should execute.
            after_ui: Run after the game's UI has been composited rather
                than with the rest of the chain. For an overlay that must
                sit on top of everything the game drew -- an editor, a
                debug surface. Without it the pass runs mid-chain and the
                game's HUD composites over it, which looks like the
                overlay is behind the game.
        """
        self._name = name
        self._enabled = enabled
        self._after_ui = after_ui

    @property
    def name(self) -> str:
        """Unique identifier for this pass."""
        return self._name

    @property
    def after_ui(self) -> bool:
        """Whether this pass runs after the game's UI is composited."""
        return self._after_ui

    @property
    def enabled(self) -> bool:
        """Whether this pass should execute."""
        return self._enabled

    @enabled.setter
    def enabled(self, value: bool) -> None:
        """Enable or disable this pass."""
        self._enabled = value

    @abstractmethod
    def execute(self, ctx: moderngl.Context, graph: RenderGraph) -> None:
        """Execute this render pass.

        Args:
            ctx: The ModernGL rendering context.
            graph: The RenderGraph orchestrating this pass.
        """
        ...

    def on_resize(self, width: int, height: int) -> None:
        """Handle viewport resize.

        Override this method if the pass needs to respond to
        window size changes (e.g., recreate projection matrices).

        Args:
            width: New viewport width.
            height: New viewport height.
        """
        pass

    def release(self) -> None:
        """Release any GPU resources owned by this pass.

        Override this method if the pass owns shader programs,
        VAOs, or other GL objects.
        """
        pass
