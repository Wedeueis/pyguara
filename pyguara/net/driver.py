"""Plugging a session and replication into the frame loop.

    app.add_step_hook(HostDriver(app, session, replication))

Input is read, messages are taken, the simulation runs, and new state goes out, in that
order. Game messages arrive through `on_event`, so a scene never polls the session itself.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, Protocol

from pyguara.net.prediction import PredictionClient, PredictionHost
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
        prediction: PredictionHost[Any] | None = None,
    ) -> None:
        """Bind them together.

        Args:
            clock: Where ticks come from, normally the `Application`.
            session: The hosting session.
            replication: The world's replication.
            on_event: Called with every session event, after replication has seen it.
            prediction: Takes players' commands, if their characters are predicted.
        """
        self._prediction = prediction
        self._clock = clock
        self._session = session
        self._replication = replication
        self._on_event = on_event

    def before_fixed_updates(self, frame_time: float) -> None:
        """Take in what players sent."""
        for event in self._session.poll():
            if isinstance(event, PlayerJoined):
                self._replication.add_peer(event.peer, event.slot)
                if self._prediction is not None:
                    self._prediction.add_peer(event.peer, event.slot)
            elif isinstance(event, PlayerLeft):
                self._replication.remove_peer(event.peer)
                if self._prediction is not None:
                    self._prediction.remove_peer(event.peer)
            elif (
                isinstance(event, MessageReceived)
                and self._prediction is not None
                and self._prediction.handle_message(
                    event.peer, event.channel, event.data
                )
            ):
                continue
            if self._on_event is not None:
                self._on_event(event)

    def after_fixed_updates(self, frame_time: float) -> None:
        """Send what the simulation produced."""
        tick = self._clock.fixed_tick
        self._replication.step(tick)
        if self._prediction is not None:
            self._prediction.step(tick)


class ClientDriver:
    """Runs a client's session and replication around the fixed updates."""

    def __init__(
        self,
        session: ClientSession,
        replication: ReplicationClient,
        on_event: Callable[[SessionEvent], None] | None = None,
        prediction: PredictionClient[Any] | None = None,
    ) -> None:
        """Bind them together.

        Args:
            session: The client session.
            replication: The world's replication.
            on_event: Called with every session event replication did not consume.
            prediction: Runs this player's own character, if it is predicted.
        """
        self._prediction = prediction
        self._session = session
        self._replication = replication
        self._on_event = on_event

    def before_fixed_updates(self, frame_time: float) -> None:
        """Take in what the host sent."""
        prediction = self._prediction
        if prediction is not None:
            prediction.begin_frame()
        for event in self._session.poll():
            if isinstance(event, MessageReceived):
                if prediction is not None and prediction.handle_message(
                    event.channel, event.data
                ):
                    continue
                if self._replication.handle_message(event.channel, event.data):
                    continue
            if self._on_event is not None:
                self._on_event(event)

    def after_fixed_updates(self, frame_time: float) -> None:
        """Write interpolated state for this frame, and send what the player did."""
        self._replication.update(frame_time)
        if self._prediction is not None:
            self._prediction.end_frame(frame_time)
