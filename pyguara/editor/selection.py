"""The editor's shared "which entity is being looked at" state.

Held by id rather than by `Entity`, so a selection cannot keep a destroyed
entity alive or hand a panel a detached object. Panels resolve the id
against the live world every frame; an id that no longer resolves reads as
nothing selected.
"""

from __future__ import annotations

from collections.abc import Callable


class Selection:
    """The currently selected entity id, and who to tell when it changes."""

    def __init__(self) -> None:
        """Start with nothing selected."""
        self._entity_id: str | None = None
        self._listeners: list[Callable[[str | None], None]] = []

    @property
    def entity_id(self) -> str | None:
        """The selected entity id, or None."""
        return self._entity_id

    def select(self, entity_id: str | None) -> None:
        """Select `entity_id`, notifying listeners only on a real change.

        Args:
            entity_id: The entity to select, or None to clear.
        """
        if entity_id == self._entity_id:
            return
        self._entity_id = entity_id
        for listener in list(self._listeners):
            listener(entity_id)

    def clear(self) -> None:
        """Select nothing."""
        self.select(None)

    def is_selected(self, entity_id: str) -> bool:
        """Whether `entity_id` is the current selection.

        Args:
            entity_id: The id to test.

        Returns:
            True if it is selected.
        """
        return self._entity_id == entity_id

    def subscribe(self, listener: Callable[[str | None], None]) -> None:
        """Register `listener` to be called with each new selection.

        Args:
            listener: Called with the new entity id, or None when cleared.
        """
        self._listeners.append(listener)

    def unsubscribe(self, listener: Callable[[str | None], None]) -> None:
        """Remove a previously registered listener.

        Args:
            listener: The callback to drop. Unknown callbacks are ignored.
        """
        if listener in self._listeners:
            self._listeners.remove(listener)
