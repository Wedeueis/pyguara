"""Saves the garden on a timer.

The PRD's "the game state must save automatically every 60 seconds". Kept
apart from `persistence_schema.py` on purpose: that module knows what a save
*is*, this one only knows *when* to ask for one, so it takes a plain
`save` callable and can be tested with a stub instead of a whole garden.

Runs on the scene's `SystemManager`, which the engine pauses while an
overlay (the store, the pause menu) is up -- so the clock only advances
while the garden is actually being played, and a paused game is not
"autosaving" the same moment over and over.

Registered last (see `scenes.py`), so a save captures the tick's settled state.
"""

from __future__ import annotations

from collections.abc import Callable

from games.quintal_cerrado.events import AutosavedEvent
from pyguara.events.dispatcher import EventDispatcher

AUTOSAVE_INTERVAL = 60.0
"""Seconds of play between autosaves."""


class AutosaveSystem:
    """Calls `save` every `interval` seconds and announces the result."""

    def __init__(
        self,
        save: Callable[[], bool],
        dispatcher: EventDispatcher,
        interval: float = AUTOSAVE_INTERVAL,
    ) -> None:
        """Initialize the system.

        Args:
            save: Writes the save; returns whether it worked.
            dispatcher: Where `AutosavedEvent` is announced.
            interval: Seconds between saves.
        """
        self._save = save
        self._dispatcher = dispatcher
        self._interval = interval
        self._elapsed = 0.0

    def update(self, dt: float) -> None:
        """Save if the interval has passed."""
        self._elapsed += dt
        if self._elapsed < self._interval:
            return
        self._elapsed = 0.0
        self._dispatcher.dispatch(AutosavedEvent(success=self._save()))
