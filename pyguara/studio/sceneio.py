"""Saving, loading and emptying the open scene.

Studio's session owns a world and a history; it does not own the scene
object or the serializer, and both live in the engine container. This is
the small piece that joins them, so the operations can offer Save and Open
without reaching into the container themselves -- a handler that did would
work in the editor and fail in every test that builds a session by hand.

Without one, `StudioSession.scene_io` is None and the operations say what
is missing rather than failing somewhere deeper.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from pyguara.log import get_logger

logger = get_logger(__name__)


class SceneIO:
    """Reaches the serializer and the live scene on a session's behalf."""

    def __init__(
        self,
        serializer: Any,
        scene_provider: Callable[[], Any],
    ) -> None:
        """Initialize the accessor.

        Args:
            serializer: A `SceneSerializer`.
            scene_provider: Returns the live `Scene`, or None. A callable
                rather than the scene itself, because the scene is
                replaced on every switch and a held one would be saved
                instead of the one on screen.
        """
        self._serializer = serializer
        self._scene_provider = scene_provider

    @property
    def scene(self) -> Any:
        """Return the live scene.

        Returns:
            The scene, or None when none is active.
        """
        try:
            return self._scene_provider()
        except Exception as exc:  # pragma: no cover - a torn-down container
            logger.debug(f"No scene available: {exc}")
            return None

    def save(self, name: str) -> bool:
        """Write the open scene under `name`.

        Args:
            name: The save key.

        Returns:
            True when the data reached storage.
        """
        scene = self.scene
        if scene is None:
            return False
        return bool(self._serializer.save_scene(scene, name))

    def load(self, name: str) -> bool:
        """Replace the open scene's contents with the save under `name`.

        Args:
            name: The save key.

        Returns:
            True when the save was found and applied.
        """
        scene = self.scene
        if scene is None:
            return False
        return bool(self._serializer.load_scene(scene, name))

    def saves(self) -> list[str]:
        """Return every save key the backend holds.

        Returns:
            The keys, sorted, so a menu lists them in a stable order.
        """
        try:
            return sorted(self._serializer.persistence.list_saves())
        except Exception as exc:  # pragma: no cover - depends on the backend
            logger.debug(f"Could not list saves: {exc}")
            return []

    def exists(self, name: str) -> bool:
        """Whether a save exists under `name`.

        Args:
            name: The save key.

        Returns:
            True when the backend holds it.
        """
        try:
            return bool(self._serializer.persistence.exists(name))
        except Exception as exc:  # pragma: no cover - depends on the backend
            logger.debug(f"Could not check for a save: {exc}")
            return False
