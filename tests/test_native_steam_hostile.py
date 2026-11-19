"""`NativeSteam` given whatever a `steam_api` hands back.

The real library is Valve's and cannot be driven into its corners, so these
load a stand-in (`tests/fakes/fake_steam_api.c`, built here with the system
C compiler) that delivers callbacks of any id and size, claims more
messages than were asked for, and returns null where Steam would not. The
extension must neither crash nor read past what it was given, and must free
each callback before asking for the next, as manual dispatch requires.
"""

from __future__ import annotations

import ctypes
import shutil
import struct
import subprocess
import sys
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from pyguara import native

pytestmark = pytest.mark.skipif(
    sys.platform != "linux" or shutil.which("cc") is None,
    reason="builds a shared library with the system C compiler",
)

SOURCE = Path(__file__).with_name("fakes") / "fake_steam_api.c"

# Steamworks' callback ids and the sizes of their structs on Linux.
CALL_COMPLETED = 703
LOBBY_CREATED = 513
LOBBY_CHAT_UPDATE = 506
LOBBY_JOIN_REQUESTED = 333
RICH_PRESENCE_JOIN_REQUESTED = 337
SESSION_REQUEST = 1251
SESSION_FAILED = 1252


@pytest.fixture(scope="module")
def library(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """The stand-in, built once."""
    path = tmp_path_factory.mktemp("steam") / "libsteam_api.so"
    subprocess.run(  # noqa: S603 - the system compiler on our own source
        ["cc", "-shared", "-fPIC", "-O1", "-o", str(path), str(SOURCE)],  # noqa: S607
        check=True,
    )
    return path


@pytest.fixture
def fake(library: Path) -> Any:
    """The stand-in's controls, reset."""
    loaded: Any = ctypes.CDLL(str(library))
    loaded.fake_next_call.restype = ctypes.c_uint64
    loaded.fake_reset()
    return loaded


@pytest.fixture
def steam(library: Path, fake: Any) -> Iterator[Any]:
    """`NativeSteam` opened on the stand-in, shut down after."""
    extension: Any = native.require_extension("tests")
    opened = extension.NativeSteam(str(library))
    yield opened
    opened.shutdown()


def _queue(fake: Any, callback: int, param: bytes) -> None:
    fake.fake_queue(callback, param, len(param))


def test_a_receive_count_beyond_the_buffer_is_not_trusted(
    steam: Any, fake: Any
) -> None:
    """Three messages and a claimed count far past the 256 asked for."""
    fake.fake_messages(3, 1000)

    received = steam.receive()

    assert received == [(1000, b"\x00"), (1001, b"\x01"), (1002, b"\x02")]
    assert fake.fake_released() == 3


def test_a_null_persona_name_is_empty_not_a_crash(steam: Any, fake: Any) -> None:
    fake.fake_null(0, 0, 1)
    assert steam.persona_name == ""


@pytest.mark.parametrize("missing", ["user", "utils"])
def test_a_steam_api_missing_an_interface_is_refused(
    library: Path, fake: Any, missing: str
) -> None:
    """Refused at open, before anything calls through a null interface."""
    fake.fake_null(missing == "user", missing == "utils", 0)
    extension: Any = native.require_extension("tests")

    with pytest.raises(RuntimeError, match="interfaces"):
        extension.NativeSteam(str(library))
    # And Steam can be opened again once it is.
    fake.fake_null(0, 0, 0)
    extension.NativeSteam(str(library)).shutdown()


def test_an_oversized_call_result_still_answers_the_request(
    steam: Any, fake: Any
) -> None:
    """A request always yields its one event, as a failure if unreadable."""
    handle = fake.fake_next_call()
    steam.create_lobby(4)
    _queue(fake, CALL_COMPLETED, struct.pack("<QiI", handle, LOBBY_CREATED, 5000))

    assert steam.run_callbacks() == [("lobby_created", 2, 0)]


def test_a_created_lobby_is_read_at_this_platforms_offset(
    steam: Any, fake: Any
) -> None:
    """`LobbyCreated_t` is packed to 4 on Linux: the id follows the result."""
    handle = fake.fake_next_call()
    steam.create_lobby(4)
    created = struct.pack("<iQ", 1, 109775240917430272)
    fake.fake_result(created, len(created))
    _queue(
        fake, CALL_COMPLETED, struct.pack("<QiI", handle, LOBBY_CREATED, len(created))
    )

    assert steam.run_callbacks() == [("lobby_created", 1, 109775240917430272)]


def test_every_callback_is_freed_once_before_the_next_is_read(
    steam: Any, fake: Any
) -> None:
    """Truncated, unknown and well-formed callbacks alike."""
    lobby, member = 109775240917430272, 76561197960265730
    delivered = [
        (9999, b"\x01" * 64),  # an id this does not handle
        (LOBBY_CHAT_UPDATE, b"\x00" * 27),  # one byte short
        (LOBBY_JOIN_REQUESTED, b"\x00" * 15),
        (RICH_PRESENCE_JOIN_REQUESTED, b"\x00" * 263),
        (SESSION_REQUEST, b"\x00" * 135),
        (SESSION_FAILED, b"\x00" * 311),
        (CALL_COMPLETED, b"\x00" * 15),
        (LOBBY_CHAT_UPDATE, struct.pack("<QQQI", lobby, member, member, 0x2)),
        (LOBBY_JOIN_REQUESTED, struct.pack("<QQ", lobby, member)),
    ]
    for callback, param in delivered:
        _queue(fake, callback, param)

    events = steam.run_callbacks()

    assert events == [("lobby_member", lobby, member, False), ("join_requested", lobby)]
    assert fake.fake_frees() == len(delivered)
    assert fake.fake_reads_while_held() == 0


def test_a_connect_string_is_cut_at_its_buffer_and_decoded_lossily(
    steam: Any, fake: Any
) -> None:
    """A friend's connect string with no terminator and invalid UTF-8."""
    _queue(fake, RICH_PRESENCE_JOIN_REQUESTED, struct.pack("<Q", 1) + b"\xff" * 256)

    [(kind, connect)] = steam.run_callbacks()

    assert kind == "connect_requested"
    assert connect == "�" * 256


def test_a_session_failure_reads_its_reason_and_bounded_detail(
    steam: Any, fake: Any
) -> None:
    peer = 76561197960265731
    info = bytearray(696)
    info[0:8] = struct.pack("<Q", peer)
    info[180:184] = struct.pack("<i", 4002)
    info[184 : 184 + 128] = b"x" * 128  # no terminator inside the field
    info[312:320] = b"overflow"
    _queue(fake, SESSION_FAILED, bytes(info))

    assert steam.run_callbacks() == [("session_failed", peer, 4002, "x" * 128)]
