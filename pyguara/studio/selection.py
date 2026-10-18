"""The editor's shared "which entities are being looked at" state.

Held by id rather than by `Entity`, so a selection cannot keep a destroyed
entity alive or hand a panel a detached object. Panels resolve the ids
against the live world every frame; an id that no longer resolves reads as
nothing selected.

A selection is an **ordered set with a primary**. Order is insertion order,
and the primary is the most recently added id -- the one a viewport gizmo
anchors to and the Inspector shows fields for when several entities are
selected. Both matter for a multi-select editor: "align to the last one I
clicked" is the common operation, and it needs a defined last.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Iterator


class Selection:
    """The currently selected entity ids, and who to tell when they change."""

    def __init__(self) -> None:
        """Start with nothing selected."""
        # A dict, not a set, because insertion order is part of the contract
        # and `set` has none. The values are unused -- `dict.fromkeys` is the
        # ordered-set idiom.
        self._entity_ids: dict[str, None] = {}
        self._listeners: list[Callable[[str | None], None]] = []

    @property
    def entity_id(self) -> str | None:
        """The primary selected id, or None when nothing is selected.

        The most recently added id. Kept as the singular name so
        single-selection callers -- which is most panels -- read unchanged.
        """
        if not self._entity_ids:
            return None
        return next(reversed(self._entity_ids))

    @property
    def entity_ids(self) -> tuple[str, ...]:
        """Every selected id, in the order it was added."""
        return tuple(self._entity_ids)

    def select(self, entity_id: str | None) -> None:
        """Select exactly `entity_id`, discarding any other selection.

        What a plain click does.

        Args:
            entity_id: The entity to select, or None to clear.
        """
        self.select_many(() if entity_id is None else (entity_id,))

    def select_many(self, entity_ids: Iterable[str]) -> None:
        """Select exactly `entity_ids`, discarding any other selection.

        What a marquee drag does.

        Args:
            entity_ids: The entities to select. Duplicates collapse, and
                the last occurrence decides the primary.
        """
        incoming = dict.fromkeys(entity_ids)
        if incoming == self._entity_ids:
            return
        self._entity_ids = incoming
        self._notify()

    def add(self, entity_id: str) -> None:
        """Add `entity_id` to the selection and make it primary.

        What ctrl-click does. Re-adding an already-selected id moves it to
        primary rather than doing nothing, because "the last one I clicked"
        is what the caller just said.

        Args:
            entity_id: The entity to add.
        """
        if self.entity_id == entity_id:
            return
        # Deleted first so re-inserting moves it to the end of the order.
        self._entity_ids.pop(entity_id, None)
        self._entity_ids[entity_id] = None
        self._notify()

    def remove(self, entity_id: str) -> None:
        """Drop `entity_id` from the selection.

        Unknown ids are ignored.

        Args:
            entity_id: The entity to deselect.
        """
        if entity_id not in self._entity_ids:
            return
        del self._entity_ids[entity_id]
        self._notify()

    def toggle(self, entity_id: str) -> None:
        """Add `entity_id` if absent, remove it if present.

        What ctrl-click actually maps to in most editors.

        Args:
            entity_id: The entity to toggle.
        """
        if entity_id in self._entity_ids:
            self.remove(entity_id)
        else:
            self.add(entity_id)

    def clear(self) -> None:
        """Select nothing."""
        self.select_many(())

    def is_selected(self, entity_id: str) -> bool:
        """Whether `entity_id` is selected at all, primary or not.

        Args:
            entity_id: The id to test.

        Returns:
            True if it is selected.
        """
        return entity_id in self._entity_ids

    def is_primary(self, entity_id: str) -> bool:
        """Whether `entity_id` is the primary selection.

        Args:
            entity_id: The id to test.

        Returns:
            True if it is the most recently added id.
        """
        return self.entity_id == entity_id

    def __len__(self) -> int:
        """How many entities are selected.

        Returns:
            The selection size.
        """
        return len(self._entity_ids)

    def __contains__(self, entity_id: object) -> bool:
        """Whether `entity_id` is selected.

        Args:
            entity_id: The id to test.

        Returns:
            True if it is selected.
        """
        return entity_id in self._entity_ids

    def __iter__(self) -> Iterator[str]:
        """Iterate the selected ids in insertion order.

        Returns:
            An iterator over a snapshot, so a listener may mutate the
            selection while a caller is walking it.
        """
        return iter(tuple(self._entity_ids))

    def subscribe(self, listener: Callable[[str | None], None]) -> None:
        """Register `listener` to be called when the selection changes.

        The listener receives the new *primary* id, or None when the
        selection is empty. It therefore fires with an unchanged argument
        when the set changed but the primary did not -- ctrl-clicking a
        second entity, say. That is a real change, and a listener that only
        cares about the primary should compare for itself.

        Args:
            listener: Called with the new primary id, or None.
        """
        self._listeners.append(listener)

    def unsubscribe(self, listener: Callable[[str | None], None]) -> None:
        """Remove a previously registered listener.

        Args:
            listener: The callback to drop. Unknown callbacks are ignored.
        """
        if listener in self._listeners:
            self._listeners.remove(listener)

    def _notify(self) -> None:
        """Tell every listener the selection changed.

        Iterates a copy, so a listener may subscribe or unsubscribe from
        inside the callback.
        """
        primary = self.entity_id
        for listener in list(self._listeners):
            listener(primary)
