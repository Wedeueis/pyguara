"""Steam end to end, over a fake Steam: lobby, admission, session, goodbye.

`FakeCloud` stands in for Steam's servers and `FakeSteam` for one player's
`NativeSteam`, with the behaviour the transport depends on: a message from
someone new raises `session_request` and is held until accepted, a peer you
have already sent to is accepted automatically, and lobby membership changes
reach every member. Above it, everything is real -- the Steam core,
`SteamTransport`, `SteamNetwork`, and the same `HostSession`/`ClientSession`
a UDP game uses.

What it cannot show is Steam itself: relay latency, real loss, the overlay.
That is the two-machine playtest (workstream 5e).
"""

from __future__ import annotations

from typing import Any

import pytest

from pyguara import native
from pyguara.net import Channel
from pyguara.net.session import (
    ClientSession,
    HostSession,
    Joined,
    Left,
    MessageReceived,
    PlayerJoined,
    PlayerLeft,
    SessionEvent,
    Versions,
)
from pyguara.net.steam import (
    STEAM_API_ENV,
    SteamNetwork,
    SteamTransport,
    find_steam_api,
    steam_api_candidates,
    steam_library_name,
)
from pyguara.net.steam_lobby import LobbyJoined, LobbyOpened, MemberAdmitted

needs_core = pytest.mark.skipif(
    native.native_module() is None, reason="extension not built"
)

HOST = 76561198000000001
GUEST = 76561198000000002
STRANGER = 76561198000000666
VERSIONS = Versions("0.6.0", "1.0", b"h" * 32)
DT = 1 / 60


class Clock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


class FakeCloud:
    """Steam's servers: who exists, which lobbies, and messages in flight."""

    def __init__(self) -> None:
        self.users: dict[int, FakeSteam] = {}
        self.lobbies: dict[int, dict[str, Any]] = {}
        self._next_lobby = 109775241000000001

    def new_lobby(self, owner: int, size: int) -> int:
        lobby = self._next_lobby
        self._next_lobby += 1
        self.lobbies[lobby] = {"owner": owner, "members": [owner], "size": size}
        return lobby

    def tell_members(self, lobby: int, about: int, joined: bool) -> None:
        for member in self.lobbies[lobby]["members"]:
            if member != about:
                self.users[member].callbacks.append(
                    ("lobby_member", lobby, about, joined)
                )


class FakeSteam:
    """One player's `NativeSteam`."""

    def __init__(self, cloud: FakeCloud, steam_id: int) -> None:
        self.cloud = cloud
        self.steam_id = steam_id
        self.callbacks: list[tuple[Any, ...]] = []
        self.inbox: list[tuple[int, bytes]] = []
        self.accepted: set[int] = set()
        self.sent_to: set[int] = set()
        self.held: dict[int, list[bytes]] = {}
        self.presence: dict[str, str] = {}
        self.accepts: list[int] = []
        self.is_shut_down = False
        cloud.users[steam_id] = self

    # Callbacks and messages.
    def run_callbacks(self) -> list[tuple[Any, ...]]:
        taken, self.callbacks = self.callbacks, []
        return taken

    def accept_session(self, steam_id: int) -> bool:
        self.accepts.append(steam_id)
        self.accepted.add(steam_id)
        for data in self.held.pop(steam_id, []):
            self.inbox.append((steam_id, data))
        return True

    def send(self, steam_id: int, data: bytes, reliable: bool = False) -> bool:
        self.sent_to.add(steam_id)
        peer = self.cloud.users.get(steam_id)
        if peer is None:
            return True
        if self.steam_id in peer.accepted or self.steam_id in peer.sent_to:
            peer.inbox.append((self.steam_id, data))
        else:
            if self.steam_id not in peer.held:
                peer.callbacks.append(("session_request", self.steam_id))
            peer.held.setdefault(self.steam_id, []).append(data)
        return True

    def receive(self) -> list[tuple[int, bytes]]:
        taken, self.inbox = self.inbox, []
        return taken

    def shutdown(self) -> None:
        self.is_shut_down = True

    # Lobbies.
    def create_lobby(self, max_members: int) -> None:
        lobby = self.cloud.new_lobby(self.steam_id, max_members)
        self.callbacks.append(("lobby_created", 1, lobby))

    def join_lobby(self, lobby_id: int) -> None:
        lobby = self.cloud.lobbies.get(lobby_id)
        if lobby is None:
            self.callbacks.append(("lobby_entered", lobby_id, 2))
            return
        if len(lobby["members"]) >= lobby["size"]:
            self.callbacks.append(("lobby_entered", lobby_id, 4))
            return
        lobby["members"].append(self.steam_id)
        self.callbacks.append(("lobby_entered", lobby_id, 1))
        self.cloud.tell_members(lobby_id, self.steam_id, True)

    def leave_lobby(self, lobby_id: int) -> None:
        lobby = self.cloud.lobbies.get(lobby_id)
        if lobby is not None and self.steam_id in lobby["members"]:
            self.cloud.tell_members(lobby_id, self.steam_id, False)
            lobby["members"].remove(self.steam_id)

    def lobby_owner(self, lobby_id: int) -> int:
        return int(self.cloud.lobbies[lobby_id]["owner"])

    def lobby_members(self, lobby_id: int) -> list[int]:
        return list(self.cloud.lobbies[lobby_id]["members"])

    def set_rich_presence(self, key: str, value: str) -> bool:
        self.presence[key] = value
        return True

    def clear_rich_presence(self) -> None:
        self.presence.clear()

    def open_invite_dialog(self, lobby_id: int) -> None:
        pass


class Player:
    """A player's frame: Steam's callbacks, then the session."""

    def __init__(self, cloud: FakeCloud, steam_id: int, clock: Clock) -> None:
        self.steam = FakeSteam(cloud, steam_id)
        self.network = SteamNetwork(self.steam, clock=clock)
        self.session: HostSession | ClientSession | None = None
        self.lobby_events: list[object] = []
        self.events: list[SessionEvent] = []

    def frame(self) -> None:
        for event in self.network.update():
            self.lobby_events.append(event)
            if isinstance(event, LobbyOpened):
                self.session = HostSession(self.network.host_transport(3), VERSIONS)
            elif isinstance(event, LobbyJoined):
                transport = self.network.join_transport(VERSIONS.encode())
                self.session = ClientSession(transport)
        if self.session is not None:
            self.events.extend(self.session.poll())


def run(clock: Clock, *players: Player, seconds: float) -> None:
    for _ in range(round(seconds / DT)):
        clock.now += DT
        for player in players:
            player.frame()


def of(kind: type, events: list[Any]) -> list[Any]:
    return [e for e in events if isinstance(e, kind)]


def hosted_game() -> tuple[FakeCloud, Clock, Player, Player]:
    cloud, clock = FakeCloud(), Clock()
    host = Player(cloud, HOST, clock)
    host.network.lobby.host(4)
    run(clock, host, seconds=0.1)
    guest = Player(cloud, GUEST, clock)
    guest.network.lobby.join(host.network.lobby.lobby_id)
    run(clock, host, guest, seconds=1.0)
    return cloud, clock, host, guest


@needs_core
def test_a_guest_joins_through_the_lobby_and_plays() -> None:
    _, clock, host, guest = hosted_game()

    assert [e.versions for e in of(PlayerJoined, host.events)] == [VERSIONS]
    assert len(of(Joined, guest.events)) == 1
    assert of(MemberAdmitted, host.lobby_events) == [MemberAdmitted(GUEST)]

    assert guest.session is not None and host.session is not None
    assert guest.session.send(Channel.EVENTS, b"hello host")
    run(clock, host, guest, seconds=0.2)
    peer = of(PlayerJoined, host.events)[0].peer
    assert host.session.send(peer, Channel.EVENTS, b"hello guest")
    run(clock, host, guest, seconds=0.2)

    assert [e.data for e in of(MessageReceived, host.events)] == [b"hello host"]
    assert [e.data for e in of(MessageReceived, guest.events)] == [b"hello guest"]


@needs_core
def test_the_host_accepts_only_admitted_sessions() -> None:
    _, _, host, guest = hosted_game()

    assert host.steam.accepts == [GUEST]
    assert guest.steam.accepts == []


@needs_core
def test_a_stranger_outside_the_lobby_never_gets_a_session() -> None:
    cloud, clock, host, guest = hosted_game()
    stranger = FakeSteam(cloud, STRANGER)
    transport = SteamTransport.client(stranger, HOST, VERSIONS.encode(), clock=clock)

    for _ in range(60):
        clock.now += DT
        host.frame()
        guest.frame()
        transport.poll()

    assert STRANGER not in host.steam.accepts
    assert STRANGER in host.steam.held
    assert len(of(PlayerJoined, host.events)) == 1


@needs_core
def test_a_session_asked_for_before_the_lobby_admits_waits_then_is_accepted() -> None:
    cloud, clock = FakeCloud(), Clock()
    host = Player(cloud, HOST, clock)
    host.network.lobby.host(4)
    run(clock, host, seconds=0.1)
    lobby = host.network.lobby.lobby_id

    guest = Player(cloud, GUEST, clock)
    guest.network.lobby.join(lobby)
    # The guest's join reaches the host only after its first message does.
    entered = [c for c in host.steam.callbacks if c[0] == "lobby_member"]
    host.steam.callbacks = [c for c in host.steam.callbacks if c[0] != "lobby_member"]
    run(clock, guest, seconds=0.2)
    run(clock, host, seconds=0.1)
    assert host.steam.accepts == []

    host.steam.callbacks.extend(entered)
    run(clock, host, guest, seconds=1.0)

    assert host.steam.accepts == [GUEST]
    assert len(of(PlayerJoined, host.events)) == 1


@needs_core
def test_leaving_the_lobby_removes_the_player_from_the_game() -> None:
    _, clock, host, guest = hosted_game()

    guest.steam.leave_lobby(host.network.lobby.lobby_id)
    run(clock, host, seconds=0.5)

    assert [e.reason for e in of(PlayerLeft, host.events)] == ["removed from the room"]


@needs_core
def test_a_guest_leaving_tells_the_host_at_once() -> None:
    _, clock, host, guest = hosted_game()

    guest.network.leave()
    run(clock, host, seconds=0.2)

    assert len(of(PlayerLeft, host.events)) == 1
    assert GUEST not in host.network.lobby.admitted


@needs_core
def test_the_host_leaving_ends_the_guest_s_session() -> None:
    _, clock, host, guest = hosted_game()

    host.network.leave()
    run(clock, guest, seconds=0.2)

    assert len(of(Left, guest.events)) == 1


@needs_core
def test_a_silent_host_times_out_rather_than_hanging() -> None:
    _, clock, host, guest = hosted_game()

    run(clock, guest, seconds=11.0)

    assert len(of(Left, guest.events)) == 1


@needs_core
def test_close_shuts_steam_down() -> None:
    _, _, host, _ = hosted_game()

    host.network.close()

    assert host.steam.is_shut_down
    assert host.network.transport is None
    assert host.steam.presence == {}


@needs_core
def test_transports_need_the_lobby_first() -> None:
    cloud, clock = FakeCloud(), Clock()
    player = Player(cloud, HOST, clock)

    with pytest.raises(RuntimeError, match="host a lobby first"):
        player.network.host_transport(3)
    with pytest.raises(RuntimeError, match="join a lobby first"):
        player.network.join_transport()

    player.network.lobby.host(4)
    run(clock, player, seconds=0.1)
    with pytest.raises(RuntimeError, match="already running"):
        player.network.host_transport(3)


@needs_core
def test_failed_sessions_are_kept_for_diagnosis_but_bounded() -> None:
    _, _, host, _ = hosted_game()
    transport = host.network.transport
    assert transport is not None

    for i in range(40):
        transport.handle(("session_failed", GUEST, 5000 + i, "relay timed out"))

    assert len(transport.failures) == 16
    assert transport.failures[-1] == (GUEST, 5039, "relay timed out")


@needs_core
def test_pending_strangers_are_bounded() -> None:
    _, _, host, _ = hosted_game()
    transport = host.network.transport
    assert transport is not None

    for i in range(10_000):
        transport.handle(("session_request", STRANGER + i))
    transport.allow(STRANGER)
    transport.allow(STRANGER + 9_999)

    assert STRANGER not in host.steam.accepts
    assert STRANGER + 9_999 in host.steam.accepts


def test_the_library_name_matches_the_extension_s() -> None:
    module = native.native_module()
    if module is None:
        pytest.skip("extension not built")
    assert steam_library_name() == module.steam_library_name()


def test_find_steam_api_prefers_the_explicit_path_then_the_environment(
    tmp_path: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    explicit = tmp_path / "explicit" / steam_library_name()
    from_env = tmp_path / "env" / steam_library_name()
    for path in (explicit, from_env):
        path.parent.mkdir()
        path.write_bytes(b"")
    monkeypatch.setenv(STEAM_API_ENV, str(from_env))
    monkeypatch.chdir(tmp_path)

    assert find_steam_api(explicit) == explicit
    assert find_steam_api() == from_env


def test_a_frozen_game_looks_beside_its_executable(
    tmp_path: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    library = tmp_path / steam_library_name()
    library.write_bytes(b"")
    monkeypatch.delenv(STEAM_API_ENV, raising=False)
    monkeypatch.setattr("sys.frozen", True, raising=False)
    monkeypatch.setattr("sys.executable", str(tmp_path / "Game.exe"))
    monkeypatch.chdir(tmp_path.parent)

    assert find_steam_api() == library


def test_a_missing_library_says_where_it_looked(
    tmp_path: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv(STEAM_API_ENV, raising=False)
    monkeypatch.chdir(tmp_path)

    with pytest.raises(FileNotFoundError) as error:
        find_steam_api()

    message = str(error.value)
    assert "--steam-api" in message and STEAM_API_ENV in message
    for place in steam_api_candidates():
        assert str(place) in message
