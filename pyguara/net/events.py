"""Sending the host's game events to its clients as they happen.

    relay = EventRelay(dispatcher, replication, app)

The host's game dispatches its events as it always does, and its own screen reacts to
them as before. The relay also sends every event type registered on the replication
schema, and a client's `ReplicationClient(on_event=dispatcher.dispatch)` dispatches
them there, so the same presentation code runs on both. A client doesn't run the
simulation, so nothing is dispatched twice.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, Protocol

from pyguara.events.dispatcher import EventDispatcher
from pyguara.net.replication import ReplicationHost


class _HasFixedTick(Protocol):
    @property
    def fixed_tick(self) -> int: ...


class EventRelay:
    """Sends a host's registered events to its clients."""

    def __init__(
        self,
        dispatcher: EventDispatcher,
        replication: ReplicationHost,
        clock: _HasFixedTick,
        slot_of: Callable[[Any], int | None] | None = None,
    ) -> None:
        """Start relaying every event type registered on the replication schema.

        Args:
            dispatcher: Where the host's game dispatches its events.
            replication: Sends them.
            clock: Where ticks come from, normally the `Application`. An event made
                during a fixed update is stamped with the tick after it, the first
                whose state includes it.
            slot_of: Returns the one player slot an event is for, or None for all.
                Everyone hears everything without it.
        """
        self._dispatcher = dispatcher
        self._replication = replication
        self._clock = clock
        self._slot_of = slot_of
        for layout in replication.schema.events:
            dispatcher.subscribe(layout.event_type, self._send, owner=self)

    def close(self) -> None:
        """Stop relaying."""
        self._dispatcher.clear_subscribers(owner=self)

    def _send(self, event: Any) -> None:
        slot = None if self._slot_of is None else self._slot_of(event)
        self._replication.send_event(event, self._clock.fixed_tick + 1, slot)
