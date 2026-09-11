"""Named, independently-rooted-and-migrated persistence scopes.

"Run vs meta" is roguelike naming for "save scope A vs B" -- a campaign
game might call its two scopes "chapter"/"profile" instead. The engine
only provides named stores; what a game calls them, and how many it wants,
is game config, never hardcoded here.
"""

from __future__ import annotations

import os
from collections.abc import Iterable
from typing import Any

from pyguara.log import get_logger
from pyguara.persistence.manager import PersistenceManager
from pyguara.persistence.storage import FileStorageBackend

logger = get_logger(__name__)


class MultiScopePersistence:
    """A named collection of independent `PersistenceManager`s.

    Each scope is a full `PersistenceManager` -- its own storage root, its
    own migration version -- so "run" and "meta" saves never collide even
    when they use the same keys, and can be on different schema versions
    entirely.
    """

    def __init__(self, stores: dict[str, PersistenceManager]) -> None:
        """Wrap an already-built collection of named stores.

        Args:
            stores: Scope name to the `PersistenceManager` that owns it.
        """
        self._stores = stores

    @classmethod
    def from_directories(
        cls, base_path: str, scope_names: Iterable[str]
    ) -> MultiScopePersistence:
        """Build one `FileStorageBackend`-rooted store per named scope.

        Args:
            base_path: Parent directory. Each scope gets its own
                subdirectory, `{base_path}/{scope_name}`.
            scope_names: The scopes to create, e.g. `("run", "meta")`.

        Returns:
            A `MultiScopePersistence` with a plain `PersistenceManager` (no
            migration manager) per scope. Replace a scope's store
            afterwards via the constructor if it needs one.
        """
        return cls(
            {
                name: PersistenceManager(
                    FileStorageBackend(base_path=os.path.join(base_path, name))
                )
                for name in scope_names
            }
        )

    def store(self, scope_name: str) -> PersistenceManager:
        """Return the named store.

        Raises:
            KeyError: If no store is registered under `scope_name`.
        """
        return self._stores[scope_name]

    def begin_run(self, scope_name: str = "run") -> SaveProfile:
        """Open a `SaveProfile` tying the named scope to a run's lifecycle.

        Args:
            scope_name: Which scope this run's data lives in. "run" is the
                roguelike default; a campaign game might pass "chapter".

        Returns:
            A handle for saving/loading within this run, and ending it.
        """
        return SaveProfile(self.store(scope_name), scope_name)


class SaveProfile:
    """Ties one named store to a run's lifecycle.

    Created via `MultiScopePersistence.begin_run()` when a run starts;
    `end()` closes it out. Deliberately independent of
    `DIContainer.run_scope` (#65) -- a game wanting a run's DI scope and
    save data torn down together calls both itself; this class only ever
    touches storage.
    """

    def __init__(self, store: PersistenceManager, scope_name: str) -> None:
        """Store the scope this profile wraps.

        Args:
            store: The scope's `PersistenceManager`.
            scope_name: The scope's name, for logging.
        """
        self._store = store
        self.scope_name = scope_name
        self.ended = False

    def save(self, key: str, data: Any, **kwargs: Any) -> bool:
        """Save under this run's scope. See `PersistenceManager.save_data`.

        Raises:
            RuntimeError: If this profile has already ended.
        """
        self._require_active()
        return self._store.save_data(key, data, **kwargs)

    def load(self, key: str, **kwargs: Any) -> Any | None:
        """Load from this run's scope. See `PersistenceManager.load_data`.

        Raises:
            RuntimeError: If this profile has already ended.
        """
        self._require_active()
        return self._store.load_data(key, **kwargs)

    def end(self, delete_data: bool = True) -> None:
        """End the run.

        Args:
            delete_data: If True (the default -- permadeath), every key in
                this scope's store is deleted. False leaves the data in
                place, for a "run" a game lets a player resume later.

        Calling this twice is a no-op.
        """
        if self.ended:
            return
        if delete_data:
            for key in self._store.storage.list_keys():
                self._store.storage.delete(key)
            logger.info(f"Run ended: '{self.scope_name}' scope data deleted.")
        else:
            logger.info(f"Run ended: '{self.scope_name}' scope data retained.")
        self.ended = True

    def _require_active(self) -> None:
        if self.ended:
            raise RuntimeError(
                f"SaveProfile for scope '{self.scope_name}' has already "
                f"ended; call MultiScopePersistence.begin_run() again for "
                f"a new one."
            )
