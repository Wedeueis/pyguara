"""Online play through Steam: the transport, and the hub that drives it.

`SteamTransport` is a `Transport`, so `HostSession` and `ClientSession` run
over it unchanged. Underneath is the Steam core (`rust/src/net/steam_core.rs`):
`renet` keyed by Steam ID, carried by Steam's peer-to-peer messages, which go
through Valve's relays -- no port forwarding, and no player's IP address is
shown to another.

`SteamNetwork` owns the three things that share Steam's one callback stream:
Steam itself, the `SteamLobby`, and the transport once there is one. Call
`update()` once a frame, before the session's `poll()`::

    network = SteamNetwork.open()
    network.lobby.host(max_players=4)
    ...
    for event in network.update():
        if isinstance(event, LobbyOpened):
            session = HostSession(network.host_transport(3), versions)
        elif isinstance(event, LobbyJoined):
            session = ClientSession(network.join_transport(versions.encode()))
    for event in session.poll():
        ...

**Being in the host's lobby is what admits a player.** The hub turns members
entering and leaving the lobby into `allow` and `revoke` on the host's
transport, and the transport accepts Steam sessions only from admitted players
(or, on a client, only from its host).

Unlike `UdpTransport` there is no native thread: Steam's API is pumped from
the frame, so a stalled frame delays acknowledgements too. The core's
timeout is 10 seconds, far above any frame.

`steam_api` is Valve's library, which this engine cannot ship: the game ships
it beside its executable (`pyguara dist steam --steam-api`), and
`find_steam_api` looks for it there.
"""

from __future__ import annotations

import os
import sys
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any, Protocol

from pyguara.net.steam_lobby import (
    LobbyEvent,
    LobbyState,
    MemberAdmitted,
    MemberRemoved,
    SteamLobby,
    SteamLobbyApi,
)
from pyguara.net.transport import (
    DEFAULT_SEND_BYTES_PER_TICK,
    NativeTransport,
    TransportEvent,
    load_core,
)

STEAM_API_ENV = "PYGUARA_STEAM_API"
"""An explicit path to `steam_api`, for development."""

_MAX_PENDING_SESSIONS = 64


class SteamMessagesApi(Protocol):
    """The part of `NativeSteam` a transport uses."""

    @property
    def steam_id(self) -> int:
        """The local player's Steam ID."""
        ...

    def accept_session(self, steam_id: int) -> bool:
        """Accept a session a peer asked for."""
        ...

    def send(self, steam_id: int, data: bytes, reliable: bool = False) -> bool:
        """Send one message to a peer."""
        ...

    def receive(self) -> list[tuple[int, bytes]]:
        """Take the messages waiting."""
        ...


class SteamApi(SteamLobbyApi, SteamMessagesApi, Protocol):
    """Everything `SteamNetwork` uses: `NativeSteam`, or a fake in tests."""

    def run_callbacks(self) -> list[tuple[Any, ...]]:
        """Drain Steam's callbacks."""
        ...

    def shutdown(self) -> None:
        """Shut Steam down."""
        ...


def steam_library_name() -> str:
    """Return the file name `steam_api` has on this platform."""
    if sys.platform == "win32":
        return "steam_api64.dll"
    if sys.platform == "darwin":
        return "libsteam_api.dylib"
    return "libsteam_api.so"


def steam_api_candidates(explicit: str | Path | None = None) -> list[Path]:
    """Return where `find_steam_api` looks, in order.

    An explicit path, then `PYGUARA_STEAM_API`, then beside the running
    executable (where a built game ships it), PyInstaller's bundle directory,
    and the working directory.
    """
    name = steam_library_name()
    places: list[Path] = []
    if explicit is not None:
        places.append(Path(explicit))
    if os.environ.get(STEAM_API_ENV):
        places.append(Path(os.environ[STEAM_API_ENV]))
    if getattr(sys, "frozen", False):
        places.append(Path(sys.executable).resolve().parent / name)
    bundle = getattr(sys, "_MEIPASS", None)
    if bundle:
        places.append(Path(bundle) / name)
    places.append(Path.cwd() / name)
    return places


def find_steam_api(explicit: str | Path | None = None) -> Path:
    """Find `steam_api`.

    Args:
        explicit: A path to use before looking anywhere else.

    Returns:
        The first candidate that exists.

    Raises:
        FileNotFoundError: None does; the message lists where it looked.
    """
    places = steam_api_candidates(explicit)
    for place in places:
        if place.is_file():
            return place
    looked = "\n".join(f"  {place}" for place in places)
    raise FileNotFoundError(
        f"{steam_library_name()} was not found. It is Valve's library, from the "
        f"Steamworks SDK's redistributable_bin; ship it beside the game "
        f"(`pyguara dist steam --steam-api`) or set {STEAM_API_ENV}. "
        f"Looked in:\n{looked}"
    )


class SteamTransport(NativeTransport):
    """A `Transport` over Steam's peer-to-peer messages.

    Attributes:
        endpoint: The Steam core, a `NativeSteamEndpoint`.
    """

    def __init__(
        self,
        endpoint: Any,
        steam: SteamMessagesApi,
        *,
        host_steam_id: int | None = None,
        open_room: bool = False,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        """Wrap a Steam core; `host` and `client` are the usual way in.

        Args:
            endpoint: A `NativeSteamEndpoint`.
            steam: Steam's messages.
            host_steam_id: The host to talk to, for a client; None for a host.
            open_room: A host that accepts sessions from anyone.
            clock: Seconds, monotonic.
        """
        super().__init__(endpoint)
        self._steam = steam
        self._host_steam_id = host_steam_id
        self._open_room = open_room
        self._clock = clock
        self._last = clock()
        self._allowed: set[int] = set()
        self._pending: dict[int, None] = {}
        self._failures: list[tuple[int, int, str]] = []

    @classmethod
    def host(
        cls,
        steam: SteamMessagesApi,
        max_clients: int = 8,
        *,
        open_room: bool = False,
        send_bytes_per_tick: int = DEFAULT_SEND_BYTES_PER_TICK,
        clock: Callable[[], float] = time.monotonic,
    ) -> SteamTransport:
        """Start hosting, admitting only Steam IDs passed to `allow`.

        Args:
            steam: Steam, usually a `NativeSteam`.
            max_clients: How many may connect.
            open_room: Admit anyone, for development.
            send_bytes_per_tick: Send budget per peer, per tick.
            clock: Seconds, monotonic.

        Raises:
            RuntimeError: If the native extension is missing or stale.
        """
        core = load_core()
        endpoint = core.NativeSteamEndpoint.host(
            max_clients, send_bytes_per_tick, open_room
        )
        return cls(endpoint, steam, open_room=open_room, clock=clock)

    @classmethod
    def client(
        cls,
        steam: SteamMessagesApi,
        host_steam_id: int,
        user_data: bytes = b"",
        *,
        send_bytes_per_tick: int = DEFAULT_SEND_BYTES_PER_TICK,
        clock: Callable[[], float] = time.monotonic,
    ) -> SteamTransport:
        """Start joining the host with Steam ID `host_steam_id`.

        Args:
            steam: Steam, usually a `NativeSteam`.
            host_steam_id: The host's Steam ID, from `LobbyJoined`.
            user_data: Up to 256 bytes the host receives with the connection.
            send_bytes_per_tick: Send budget per tick.
            clock: Seconds, monotonic.

        Raises:
            RuntimeError: If the native extension is missing or stale.
        """
        core = load_core()
        endpoint = core.NativeSteamEndpoint.client(
            host_steam_id, user_data, send_bytes_per_tick
        )
        return cls(endpoint, steam, host_steam_id=host_steam_id, clock=clock)

    @property
    def is_host(self) -> bool:
        """Whether this transport hosts."""
        return self._host_steam_id is None

    @property
    def failures(self) -> list[tuple[int, int, str]]:
        """Steam sessions that failed, as `(steam_id, reason, detail)`."""
        return list(self._failures)

    def allow(self, steam_id: int) -> None:
        """Admit a Steam ID (a host's), accepting its session if it waits."""
        if not self.is_host:
            return
        self._allowed.add(steam_id)
        self.endpoint.allow(steam_id)
        if steam_id in self._pending:
            del self._pending[steam_id]
            self._steam.accept_session(steam_id)

    def revoke(self, steam_id: int) -> None:
        """Stop admitting a Steam ID, dropping it if connected."""
        if not self.is_host:
            return
        self._allowed.discard(steam_id)
        self._pending.pop(steam_id, None)
        self.endpoint.revoke(steam_id)

    def handle(self, callback: tuple[Any, ...]) -> None:
        """Take one tuple from `NativeSteam.run_callbacks()`; others ignored."""
        match callback:
            case ("session_request", int(peer)):
                self._on_session_request(peer)
            case ("session_failed", int(peer), int(reason), str(detail)):
                self._failures = [*self._failures[-15:], (peer, reason, detail)]

    def poll(self) -> list[TransportEvent]:
        """Move messages through Steam, then see `Transport.poll`."""
        self._pump()
        return super().poll()

    def close(self) -> None:
        """Say goodbye to every peer, sending it now; see `Transport.close`."""
        super().close()
        self._flush()

    def _permitted(self, peer: int) -> bool:
        if self._host_steam_id is not None:
            return peer == self._host_steam_id
        return self._open_room or peer in self._allowed

    def _on_session_request(self, peer: int) -> None:
        if self._permitted(peer):
            self._steam.accept_session(peer)
        elif self.is_host:
            # Entering the lobby and asking for a session race; hold the
            # request until the lobby admits them, but only a few strangers'.
            self._pending.pop(peer, None)
            self._pending[peer] = None
            while len(self._pending) > _MAX_PENDING_SESSIONS:
                del self._pending[next(iter(self._pending))]

    def _pump(self) -> None:
        for source, data in self._steam.receive():
            self.endpoint.receive(str(source), data)
        now = self._clock()
        self.endpoint.tick(max(0.0, now - self._last))
        self._last = now
        self._flush()

    def _flush(self) -> None:
        for destination, data in self.endpoint.drain_transmit():
            self._steam.send(int(destination), data, False)


class SteamNetwork:
    """Steam, its lobby, and the transport, fed from one callback stream.

    Attributes:
        steam: Steam itself.
        lobby: This player's lobby.
        transport: The transport, once `host_transport` or `join_transport`
            made one.
    """

    def __init__(
        self, steam: SteamApi, *, clock: Callable[[], float] = time.monotonic
    ) -> None:
        """Wrap a started Steam; `open` starts one.

        Args:
            steam: Steam, usually a `NativeSteam`.
            clock: Seconds, monotonic, for the transport.
        """
        self.steam = steam
        self.lobby = SteamLobby(steam)
        self.transport: SteamTransport | None = None
        self._clock = clock

    @classmethod
    def open(cls, library: str | Path | None = None) -> SteamNetwork:
        """Find `steam_api`, start Steam, and reach Valve's relays.

        The app ID comes from Steam: launched through the client in a
        release, or `steam_appid.txt` / `SteamAppId` during development.

        Args:
            library: Where `steam_api` is, before `find_steam_api` looks.

        Raises:
            FileNotFoundError: `steam_api` was not found.
            RuntimeError: The extension is missing, or Steam would not start
                (not running, not logged in, out of date); the message says
                which.
        """
        core = load_core()
        steam = core.NativeSteam(str(find_steam_api(library)))
        steam.init_relay()
        return cls(steam)

    def update(self) -> list[LobbyEvent]:
        """Drain Steam's callbacks; call once a frame, before the session.

        Returns:
            What happened to the lobby. Admission is already applied to the
            host's transport.
        """
        events: list[LobbyEvent] = []
        for callback in self.steam.run_callbacks():
            if self.transport is not None:
                self.transport.handle(callback)
            for event in self.lobby.handle(callback):
                self._admit(event)
                events.append(event)
        return events

    def host_transport(
        self,
        max_clients: int,
        *,
        send_bytes_per_tick: int = DEFAULT_SEND_BYTES_PER_TICK,
    ) -> SteamTransport:
        """Start the host's transport, admitting the lobby's members.

        Args:
            max_clients: How many may connect, the host not included.
            send_bytes_per_tick: Send budget per peer, per tick.

        Raises:
            RuntimeError: Not hosting a lobby, or a transport already runs.
        """
        self._require(LobbyState.HOSTING, "host a lobby")
        transport = SteamTransport.host(
            self.steam,
            max_clients,
            send_bytes_per_tick=send_bytes_per_tick,
            clock=self._clock,
        )
        for member in self.lobby.admitted:
            transport.allow(member)
        self.transport = transport
        return transport

    def join_transport(
        self,
        user_data: bytes = b"",
        *,
        send_bytes_per_tick: int = DEFAULT_SEND_BYTES_PER_TICK,
    ) -> SteamTransport:
        """Start connecting to the host of the lobby this player joined.

        Args:
            user_data: Up to 256 bytes the host receives with the connection.
            send_bytes_per_tick: Send budget per tick.

        Raises:
            RuntimeError: Not in a joined lobby, or a transport already runs.
        """
        self._require(LobbyState.JOINED, "join a lobby")
        self.transport = SteamTransport.client(
            self.steam,
            self.lobby.host_steam_id,
            user_data,
            send_bytes_per_tick=send_bytes_per_tick,
            clock=self._clock,
        )
        return self.transport

    def leave(self) -> None:
        """Close the transport, telling peers, and leave the lobby."""
        if self.transport is not None:
            self.transport.close()
            self.transport = None
        self.lobby.leave()

    def close(self) -> None:
        """Leave, then shut Steam down."""
        self.leave()
        self.steam.shutdown()

    def _require(self, state: LobbyState, what: str) -> None:
        if self.lobby.state is not state:
            raise RuntimeError(f"{what} first; the lobby is {self.lobby.state.value}")
        if self.transport is not None:
            raise RuntimeError("a transport is already running; leave first")

    def _admit(self, event: LobbyEvent) -> None:
        if self.transport is None:
            return
        if isinstance(event, MemberAdmitted):
            self.transport.allow(event.steam_id)
        elif isinstance(event, MemberRemoved):
            self.transport.revoke(event.steam_id)
