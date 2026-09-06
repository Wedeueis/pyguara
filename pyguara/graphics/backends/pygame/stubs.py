"""No-op stand-ins for the ModernGL-only graphics features, for pygame.

The pygame backend has no framebuffers, no dynamic lighting and no
post-processing. These stubs let game code that uses those features run
unchanged on it, rendering a fully lit scene instead of failing.

Their entire value is interface parity: a method the real class has and the
stub does not is an `AttributeError` that appears only after switching
backend. `tests/test_pygame_stubs.py` compares each stub's public surface
against its counterpart, so drift is caught here rather than in a game.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from pyguara.common.types import Vector2
    from pyguara.ecs.manager import EntityManager


class PygameLightingSystem:
    """No-op lighting system for Pygame backend.

    The Pygame backend renders everything fully lit (no dynamic lighting).
    This stub allows game code to use lighting components without errors.
    """

    def __init__(self, entity_manager: EntityManager) -> None:
        """Initialize the stub lighting system.

        Args:
            entity_manager: The ECS entity manager (unused).
        """
        self._entity_manager = entity_manager

    @property
    def lights(self) -> list[Any]:
        """Return empty light list."""
        return []

    @property
    def ambient_color(self) -> tuple[int, int, int]:
        """Return full white ambient (fully lit)."""
        return (255, 255, 255)

    @property
    def ambient_intensity(self) -> float:
        """Return full intensity."""
        return 1.0

    def get_ambient_normalized(self) -> tuple[float, float, float]:
        """Return normalized full white."""
        return (1.0, 1.0, 1.0)

    def initialize(self) -> None:
        """No-op initialize."""
        pass

    def cleanup(self) -> None:
        """No-op cleanup."""
        pass

    def collect_lights_screen_space(
        self,
        camera_position: Vector2,
        camera_zoom: float,
        viewport_offset: Vector2,
    ) -> list[Any]:
        """Return no lights: this backend renders everything fully lit.

        Args:
            camera_position: Camera world position (unused).
            camera_zoom: Camera zoom factor (unused).
            viewport_offset: Viewport offset in screen space (unused).

        Returns:
            An empty list.
        """
        return []

    def update(self, dt: float) -> None:
        """No-op update."""
        pass


class PygamePostProcessStack:
    """Pass-through post-process stack for Pygame backend.

    Post-processing effects require FBOs which Pygame doesn't support.
    This stub returns the input unchanged.
    """

    def __init__(self) -> None:
        """Initialize the stub post-process stack."""
        self._effects: list[Any] = []

    @property
    def effects(self) -> list[Any]:
        """Return empty effect list."""
        return self._effects

    def add_effect(self, effect: Any) -> None:
        """Accept but ignore effects.

        Args:
            effect: Effect to add (ignored).
        """
        # Effects are accepted but won't be applied
        self._effects.append(effect)

    def insert_effect(self, index: int, effect: Any) -> None:
        """Accept but ignore effects.

        Args:
            index: Position (ignored).
            effect: Effect to add (ignored).
        """
        self._effects.insert(index, effect)

    def remove_effect(self, name: str) -> Any:
        """Remove an effect by name.

        Args:
            name: Effect name.

        Returns:
            None (no effects to remove).
        """
        for i, e in enumerate(self._effects):
            if hasattr(e, "name") and e.name == name:
                return self._effects.pop(i)
        return None

    def get_effect(self, name: str) -> Any:
        """Get an effect by name.

        Args:
            name: Effect name.

        Returns:
            None (effects aren't actually stored functionally).
        """
        for e in self._effects:
            if hasattr(e, "name") and e.name == name:
                return e
        return None

    def process(self, input_fbo: Any) -> Any:
        """Pass through unchanged.

        Args:
            input_fbo: Input (returned unchanged).

        Returns:
            The input unchanged.
        """
        return input_fbo

    def on_resize(self, width: int, height: int) -> None:
        """No-op resize handler.

        Args:
            width: New width (ignored).
            height: New height (ignored).
        """
        pass

    def release(self) -> None:
        """No-op release."""
        self._effects.clear()


class PygameFramebufferManager:
    """Stub framebuffer manager for Pygame backend.

    Pygame doesn't support framebuffer objects. This stub provides
    a compatible interface that returns None for all FBO requests.
    """

    def __init__(self, width: int, height: int) -> None:
        """Initialize the stub manager.

        Args:
            width: Viewport width.
            height: Viewport height.
        """
        self._width = width
        self._height = height

    @property
    def width(self) -> int:
        """Current viewport width."""
        return self._width

    @property
    def height(self) -> int:
        """Current viewport height."""
        return self._height

    def get_or_create(self, name: str, **kwargs: Any) -> None:
        """Return None (no FBO support).

        Args:
            name: FBO name (ignored).
            **kwargs: Creation options (ignored).

        Returns:
            None.
        """
        return None

    def get(self, name: str) -> None:
        """Return None (no FBO support).

        Args:
            name: FBO name (ignored).

        Returns:
            None.
        """
        return None

    def resize_all(self, width: int, height: int) -> None:
        """Update stored dimensions.

        Args:
            width: New width.
            height: New height.
        """
        self._width = width
        self._height = height

    def release_all(self) -> None:
        """No-op release."""
        pass

    def release(self, name: str) -> None:
        """No-op release.

        Args:
            name: FBO name (ignored).
        """
        pass


class PygameRenderGraph:
    """Stub render graph for Pygame backend.

    Pygame uses immediate-mode rendering without a multi-pass pipeline.
    This stub provides a compatible interface that does nothing.
    """

    def __init__(self, width: int, height: int) -> None:
        """Initialize the stub render graph.

        Args:
            width: Viewport width.
            height: Viewport height.
        """
        self._fbo_manager = PygameFramebufferManager(width, height)
        self._passes: list[Any] = []

    @property
    def fbo_manager(self) -> PygameFramebufferManager:
        """Get the stub framebuffer manager."""
        return self._fbo_manager

    @property
    def ctx(self) -> None:
        """Return None: there is no GL context behind the pygame backend.

        The real `RenderGraph` hands its `moderngl.Context` to each pass.
        Nothing consumes this on pygame -- `Application` branches on
        `isinstance(candidate, RenderGraph)` rather than on mere resolvability
        -- but the attribute has to exist for the surfaces to match.
        """
        return None

    @property
    def passes(self) -> list[Any]:
        """Get the pass list (always empty)."""
        return self._passes

    def add_pass(self, render_pass: Any) -> None:
        """Accept but ignore passes.

        Args:
            render_pass: Pass to add (ignored).
        """
        pass

    def insert_pass(self, index: int, render_pass: Any) -> None:
        """Accept but ignore passes.

        Args:
            index: Position (ignored).
            render_pass: Pass to add (ignored).
        """
        pass

    def remove_pass(self, name: str) -> None:
        """No-op remove.

        Args:
            name: Pass name (ignored).
        """
        return None

    def get_pass(self, name: str) -> None:
        """Return None (no passes).

        Args:
            name: Pass name (ignored).

        Returns:
            None.
        """
        return None

    def execute(self) -> None:
        """Do nothing - Pygame renders directly without passes."""
        pass

    def resize(self, width: int, height: int) -> None:
        """Handle resize.

        Args:
            width: New width.
            height: New height.
        """
        self._fbo_manager.resize_all(width, height)

    def release(self) -> None:
        """No-op release."""
        pass
