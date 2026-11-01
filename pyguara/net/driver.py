"""Plugging a session and replication into the frame loop.

    app.add_step_hook(HostDriver(app, session, replication))

Input is read, messages are taken, the simulation runs, and new state goes out, in that
order. Game messages arrive through `on_event`, so a scene never polls the session itself.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Protocol

from pyguara.net.replication import ReplicationClient, ReplicationHost
from pyguara.net.session import (
    ClientSession,
    HostSession,
    MessageReceived,
    PlayerJoined,
    PlayerLeft,
    SessionEvent,
)


class _HasFixedTick(Protocol):
    @property
    def fixed_tick(self) -> int: ...


class HostDriver:
    """Runs a host's session and replication around the fixed updates."""

    def __init__(
        self,
        clock: _HasFixedTick,
        session: HostSession,
        replication: ReplicationHost,
        on_event: Callable[[SessionEvent], None] | None = None,
    ) -> None:
        """Bind them together.

        Args:
            clock: Where ticks come from, normally the `Application`.
            session: The hosting session.
            replication: The world's replication.
            on_event: Called with every session event, after replication has seen it.
        """
        self._clock = clock
        self._session = session
        self._replication = replication
        self._on_event = on_event

    def before_fixed_updates(self, frame_time: float) -> None:
        """Take in what players sent."""
        for event in self._session.poll():
            if isinstance(event, PlayerJoined):
                self._replication.add_peer(event.peer, event.slot)
            elif isinstance(event, PlayerLeft):
                self._replication.remove_peer(event.peer)
            if self._on_event is not None:
                self._on_event(event)

    def after_fixed_updates(self, frame_time: float) -> None:
        """Send what the simulation produced."""
        self._replication.step(self._clock.fixed_tick)


class ClientDriver:
    """Runs a client's session and replication around the fixed updates."""

    def __init__(
        self,
        session: ClientSession,
        replication: ReplicationClient,
        on_event: Callable[[SessionEvent], None] | None = None,
    ) -> None:
        """Bind them together.

        Args:
            session: The client session.
            replication: The world's replication.
            on_event: Called with every session event replication did not consume.
        """
        self._session = session
        self._replication = replication
        self._on_event = on_event

    def before_fixed_updates(self, frame_time: float) -> None:
        """Take in what the host sent."""
        for event in self._session.poll():
            if isinstance(event, MessageReceived) and self._replication.handle_message(
                event.channel, event.data
            ):
                continue
            if self._on_event is not None:
                self._on_event(event)

    def after_fixed_updates(self, frame_time: float) -> None:
        """Write interpolated state for this frame."""
        self._replication.update(frame_time)
