"""Steam lobbies, against a fake Steam: who is admitted and where a guest goes.

The fake records what the lobby asked Steam to do and answers the queries a
real Steam would. The callback tuples fed in are the shapes
`NativeSteam.run_callbacks()` returns, so a change to either side shows here.
"""

from __future__ import annotations

import pytest

from pyguara.net.steam_lobby import (
    JoinRequested,
    LobbyFailed,
    LobbyJoined,
    LobbyOpened,
    LobbyState,
    MemberAdmitted,
    MemberRemoved,
    SteamLobby,
    lobby_from_args,
    lobby_from_connect,
    parse_lobby_id,
)

ME = 76561198000000001
FRIEND = 76561198000000002
OTHER = 76561198000000003
LOBBY = 109775241000000001
ELSEWHERE = 109775241000000002


class FakeSteam:
    def __init__(self, steam_id: int = ME) -> None:
        self.steam_id = steam_id
        self.calls: list[tuple[object, ...]] = []
        self.owner = 0
        self.members: list[int] = []
        self.presence: dict[str, str] = {}

    def create_lobby(self, max_members: int) -> None:
        self.calls.append(("create_lobby", max_members))

    def join_lobby(self, lobby_id: int) -> None:
        self.calls.append(("join_lobby", lobby_id))

    def leave_lobby(self, lobby_id: int) -> None:
        self.calls.append(("leave_lobby", lobby_id))

    def lobby_owner(self, lobby_id: int) -> int:
        return self.owner

    def lobby_members(self, lobby_id: int) -> list[int]:
        return list(self.members)

    def set_rich_presence(self, key: str, value: str) -> bool:
        self.presence[key] = value
        return True

    def clear_rich_presence(self) -> None:
        self.presence.clear()

    def open_invite_dialog(self, lobby_id: int) -> None:
        self.calls.append(("open_invite_dialog", lobby_id))


def hosting(steam: FakeSteam | None = None) -> tuple[SteamLobby, FakeSteam]:
    steam = steam or FakeSteam()
    lobby = SteamLobby(steam)
    lobby.host(4)
    steam.members = [ME]
    lobby.handle(("lobby_created", 1, LOBBY))
    return lobby, steam


def test_hosting_opens_a_friends_lobby_and_shows_join_game() -> None:
    steam = FakeSteam()
    lobby = SteamLobby(steam)

    lobby.host(4)
    steam.members = [ME]
    events = lobby.handle(("lobby_created", 1, LOBBY))

    assert steam.calls == [("create_lobby", 4)]
    assert events == [LobbyOpened(LOBBY)]
    assert lobby.state is LobbyState.HOSTING
    assert lobby.lobby_id == LOBBY
    assert steam.presence == {"connect": f"+connect_lobby {LOBBY}"}


def test_a_failed_creation_says_so_and_leaves_the_lobby_idle() -> None:
    steam = FakeSteam()
    lobby = SteamLobby(steam)
    lobby.host(4)

    events = lobby.handle(("lobby_created", 2, 0))

    assert events == [LobbyFailed("Steam could not create a lobby (EResult 2)")]
    assert lobby.state is LobbyState.IDLE
    assert steam.presence == {}


def test_members_entering_and_leaving_are_admitted_and_removed() -> None:
    lobby, _ = hosting()

    entered = lobby.handle(("lobby_member", LOBBY, FRIEND, True))
    again = lobby.handle(("lobby_member", LOBBY, FRIEND, True))
    left = lobby.handle(("lobby_member", LOBBY, FRIEND, False))
    left_again = lobby.handle(("lobby_member", LOBBY, FRIEND, False))

    assert entered == [MemberAdmitted(FRIEND)]
    assert again == []
    assert left == [MemberRemoved(FRIEND)]
    assert left_again == []
    assert lobby.admitted == frozenset()


def test_someone_who_entered_before_creation_finished_is_admitted() -> None:
    steam = FakeSteam()
    lobby = SteamLobby(steam)
    lobby.host(4)
    steam.members = [ME, FRIEND]

    events = lobby.handle(("lobby_created", 1, LOBBY))

    assert events == [LobbyOpened(LOBBY), MemberAdmitted(FRIEND)]


def test_the_host_never_admits_itself_or_another_lobby_s_members() -> None:
    lobby, _ = hosting()

    assert lobby.handle(("lobby_member", LOBBY, ME, True)) == []
    assert lobby.handle(("lobby_member", ELSEWHERE, FRIEND, True)) == []
    assert lobby.admitted == frozenset()


def test_a_guest_joins_and_is_pointed_at_the_owner() -> None:
    steam = FakeSteam(FRIEND)
    steam.owner = ME
    lobby = SteamLobby(steam)

    lobby.join(LOBBY)
    events = lobby.handle(("lobby_entered", LOBBY, 1))

    assert steam.calls == [("join_lobby", LOBBY)]
    assert events == [LobbyJoined(LOBBY, ME)]
    assert lobby.state is LobbyState.JOINED
    assert steam.presence == {"connect": f"+connect_lobby {LOBBY}"}


def test_a_guest_admits_no_one() -> None:
    steam = FakeSteam(FRIEND)
    steam.owner = ME
    lobby = SteamLobby(steam)
    lobby.join(LOBBY)
    lobby.handle(("lobby_entered", LOBBY, 1))

    assert lobby.handle(("lobby_member", LOBBY, OTHER, True)) == []


@pytest.mark.parametrize(
    ("response", "reason"),
    [
        (4, "the lobby is full"),
        (2, "the lobby no longer exists"),
        (99, "could not join (99)"),
    ],
)
def test_a_refused_join_names_why(response: int, reason: str) -> None:
    steam = FakeSteam(FRIEND)
    lobby = SteamLobby(steam)
    lobby.join(LOBBY)

    events = lobby.handle(("lobby_entered", LOBBY, response))

    assert events == [LobbyFailed(reason)]
    assert lobby.state is LobbyState.IDLE
    assert steam.presence == {}


def test_a_lobby_with_no_host_is_left_rather_than_joined() -> None:
    steam = FakeSteam(FRIEND)
    lobby = SteamLobby(steam)
    lobby.join(LOBBY)

    events = lobby.handle(("lobby_entered", LOBBY, 1))

    assert events == [LobbyFailed("the lobby has no host")]
    assert steam.calls[-1] == ("leave_lobby", LOBBY)


def test_a_result_for_another_lobby_is_ignored() -> None:
    steam = FakeSteam(FRIEND)
    steam.owner = ME
    lobby = SteamLobby(steam)
    lobby.join(LOBBY)

    assert lobby.handle(("lobby_entered", ELSEWHERE, 1)) == []
    assert lobby.handle(("lobby_created", 1, ELSEWHERE)) == []
    assert lobby.state is LobbyState.JOINING


def test_session_callbacks_and_unknown_shapes_are_not_the_lobby_s() -> None:
    lobby, _ = hosting()

    for callback in [
        ("session_request", FRIEND),
        ("session_failed", FRIEND, 5001, "timed out"),
        ("lobby_member", LOBBY, FRIEND),
        ("lobby_member", LOBBY, "x", True),
        ("something_new", 1, 2),
        (),
    ]:
        assert lobby.handle(callback) == []


def test_starting_twice_is_refused_until_leaving() -> None:
    lobby, steam = hosting()

    with pytest.raises(RuntimeError, match="already hosting"):
        lobby.join(ELSEWHERE)
    lobby.leave()
    lobby.join(ELSEWHERE)

    assert ("leave_lobby", LOBBY) in steam.calls
    assert lobby.state is LobbyState.JOINING


def test_leaving_clears_join_game_and_the_admitted_set() -> None:
    lobby, steam = hosting()
    lobby.handle(("lobby_member", LOBBY, FRIEND, True))

    lobby.leave()

    assert steam.presence == {}
    assert lobby.admitted == frozenset()
    assert lobby.lobby_id == 0
    assert lobby.state is LobbyState.IDLE


def test_invite_opens_the_overlay_only_from_inside_a_lobby() -> None:
    lobby, steam = hosting()
    lobby.invite()
    assert steam.calls[-1] == ("open_invite_dialog", LOBBY)

    lobby.leave()
    with pytest.raises(RuntimeError, match="not in a lobby"):
        lobby.invite()


def test_overlay_and_rich_presence_joins_are_reported_not_acted_on() -> None:
    lobby, steam = hosting()
    calls = list(steam.calls)

    by_invite = lobby.handle(("join_requested", ELSEWHERE))
    by_presence = lobby.handle(("connect_requested", f"+connect_lobby {ELSEWHERE}"))
    to_own_lobby = lobby.handle(("join_requested", LOBBY))

    assert by_invite == [JoinRequested(ELSEWHERE)]
    assert by_presence == [JoinRequested(ELSEWHERE)]
    assert to_own_lobby == []
    assert steam.calls == calls


@pytest.mark.parametrize(
    "connect",
    [
        "",
        "+connect_lobby",
        "+connect_lobby 0",
        "+connect_lobby -5",
        "+connect_lobby 18446744073709551616",
        "+connect_lobby 12 34",
        "+connect 109775241000000002",
        "+connect_lobby ١٢٣",
        "+connect_lobby 0x10",
        "+connect_lobby 999999999999999999999999",
    ],
)
def test_a_hostile_connect_string_requests_nothing(connect: str) -> None:
    lobby, _ = hosting()

    assert lobby_from_connect(connect) is None
    assert lobby.handle(("connect_requested", connect)) == []


def test_lobby_ids_parse_strictly() -> None:
    assert parse_lobby_id(str(LOBBY)) == LOBBY
    assert parse_lobby_id(" 42 ") == 42
    assert parse_lobby_id("18446744073709551615") == 2**64 - 1
    for bad in ["", "0", "1e5", "+5", "4_2", "18446744073709551616", "²"]:
        assert parse_lobby_id(bad) is None, bad


def test_the_launch_argument_names_the_lobby() -> None:
    assert lobby_from_args(["game.exe", "+connect_lobby", str(LOBBY)]) == LOBBY
    assert lobby_from_args(["game.exe", "+connect_lobby"]) is None
    assert lobby_from_args(["game.exe", "+connect_lobby", "nope"]) is None
    assert lobby_from_args(["game.exe"]) is None
