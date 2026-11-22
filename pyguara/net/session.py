"""Invites, version checks, and who is in the game.

Two machines that disagree about the rules should never start playing, so a
client carries its versions in the connection's user data and the host refuses a
mismatch aloud. Nothing in the game layer hears from a peer until the host has
admitted it.

A wrong protocol id or a wrong key is silent at the network layer, by design: an
unauthenticated reply is what a forged packet would want. So those show up here as
a timeout, and the message says what to check.
"""

from __future__ import annotations

import base64
import secrets
import struct
from dataclasses import dataclass, field
from enum import StrEnum

from pyguara.net.transport import (
    HOST_PEER,
    NET_PROTOCOL_VERSION,
    Channel,
    MessageDelivered,
    PeerConnected,
    PeerDisconnected,
    Transport,
    TransportFailed,
)

KEY_BYTES = 32
INVITE_PREFIX = "pyguara://"

_HELLO_MAGIC = b"PGH1"
_HELLO_HEADER = struct.Struct("<4sI")
_HASH_BYTES = 32
_MAX_VERSION_BYTES = 64
_MAX_REFUSAL_BYTES = 1024

# More than this before the host's answer means something is wrong: a reliable message
# can't be dropped silently, so the session ends instead.
_MAX_MESSAGES_BEFORE_WELCOME = 16_384

_WELCOME = b"\x01"
_REFUSED = b"\x02"
# Sent just before `_REFUSED`, on the same ordered channel: the refusal's code.
# Separate, so a client older than codes ignores it and still reads the text.
_REFUSAL_CODE = b"\x03"


class EndCode(StrEnum):
    """Why a player was refused, left, or lost the session, for a game to act on.

    `reason` beside it is English, for logs and as a fallback. A localised
    game keys its text on this; the values are stable, and safe as a key.
    """

    PROTOCOL_DIFFERS = "protocol_differs"
    """Refused: the network protocol differs; one side must update."""
    ENGINE_DIFFERS = "engine_differs"
    """Refused: the engine version differs."""
    GAME_DIFFERS = "game_differs"
    """Refused: the game version differs."""
    FILES_DIFFER = "files_differ"
    """Refused: the game's files differ from the host's."""
    UNREADABLE_VERSIONS = "unreadable_versions"
    """Refused: the host could not read what the player is running."""
    NO_ANSWER = "no_answer"
    """Left: the host never answered. A stale invite looks like this."""
    LOST_CONTACT = "lost_contact"
    """Left, or a player left: the connection timed out."""
    FULL = "full"
    """Left: the game is full."""
    HOST_ENDED = "host_ended"
    """Left: the host ended the connection, or the session."""
    PLAYER_LEFT = "player_left"
    """On the host: the player disconnected."""
    KICKED = "kicked"
    """On the host: this host removed the player."""
    DROPPED = "dropped"
    """On the host: the player broke the protocol or flooded the host."""
    TOO_MUCH_EARLY_DATA = "too_much_early_data"
    """Failed: the host sent too much before admitting us."""
    TRANSPORT_FAILED = "transport_failed"
    """Failed: the transport stopped working."""
    UNKNOWN = "unknown"
    """None of these, such as a refusal from a host older than codes."""


# The byte each refusal code travels as. Fixed: a new member gets a new byte.
_REFUSAL_BYTES = {
    EndCode.PROTOCOL_DIFFERS: 1,
    EndCode.ENGINE_DIFFERS: 2,
    EndCode.GAME_DIFFERS: 3,
    EndCode.FILES_DIFFER: 4,
    EndCode.UNREADABLE_VERSIONS: 5,
}
_REFUSAL_CODES = {byte: code for code, byte in _REFUSAL_BYTES.items()}


@dataclass(frozen=True, slots=True)
class Invite:
    """What a player needs to join: where the host is, and the session key.

    Treat the string form as a secret. Anyone holding it can join, and anyone who
    also recorded the session's handshake can read that session. Make a new one
    per session.

    Attributes:
        host: The host's name or IP address.
        port: The host's UDP port.
        key: The 32-byte session key. Left out of `repr`, so it stays out of logs.
    """

    host: str
    port: int
    key: bytes = field(repr=False)

    @classmethod
    def create(cls, host: str, port: int) -> Invite:
        """Make an invite with a fresh random key.

        Args:
            host: The address players should connect to.
            port: The UDP port.

        Returns:
            The invite.
        """
        return cls(host, port, secrets.token_bytes(KEY_BYTES))

    def __str__(self) -> str:
        """Return the shareable form."""
        key = base64.b32encode(self.key).decode("ascii").rstrip("=")
        host = f"[{self.host}]" if ":" in self.host else self.host
        return f"{INVITE_PREFIX}{host}:{self.port}#{key}"

    @classmethod
    def parse(cls, text: str) -> Invite:
        """Read the shareable form.

        Args:
            text: A string from `str(invite)`. It comes from another person, so
                it is not trusted to be well formed.

        Returns:
            The invite.

        Raises:
            ValueError: If it is not a valid invite. The message never repeats the
                input, which may be a real key with a typo.
        """
        text = text.strip()
        if not text.startswith(INVITE_PREFIX) or "#" not in text:
            raise ValueError("That is not a PyGuara invite")
        location, _, encoded = text[len(INVITE_PREFIX) :].partition("#")
        host, _, port_text = location.rpartition(":")
        host = host.strip("[]")
        if not host or not port_text.isascii() or not port_text.isdigit():
            raise ValueError("The invite has no valid host and port")
        port = int(port_text)
        if not 0 < port < 65536:
            raise ValueError("The invite's port is out of range")
        try:
            padding = "=" * (-len(encoded) % 8)
            key = base64.b32decode(encoded.upper() + padding)
        except ValueError:
            raise ValueError("The invite's key is damaged") from None
        if len(key) != KEY_BYTES:
            raise ValueError("The invite's key is the wrong length")
        return cls(host, port, key)


@dataclass(frozen=True, slots=True)
class Versions:
    """What two machines must agree on before playing together.

    Attributes:
        engine: The engine's version.
        game: The game's version.
        content_hash: A hash of the game's content, 32 bytes.
        protocol: The network protocol. Leave this at its default.
    """

    engine: str
    game: str
    content_hash: bytes = bytes(_HASH_BYTES)
    protocol: int = NET_PROTOCOL_VERSION

    def encode(self) -> bytes:
        """Return the bytes carried in the connection's user data.

        Raises:
            ValueError: If a field cannot fit, which is a bug in the caller.
        """
        engine = self.engine.encode()
        game = self.game.encode()
        if len(engine) > _MAX_VERSION_BYTES or len(game) > _MAX_VERSION_BYTES:
            raise ValueError(f"A version is at most {_MAX_VERSION_BYTES} bytes")
        if len(self.content_hash) != _HASH_BYTES:
            raise ValueError(f"A content hash is {_HASH_BYTES} bytes")
        return (
            _HELLO_HEADER.pack(_HELLO_MAGIC, self.protocol)
            + self.content_hash
            + bytes([len(engine)])
            + engine
            + bytes([len(game)])
            + game
        )

    @classmethod
    def decode(cls, data: bytes) -> Versions | None:
        """Read user data sent by a peer, which is untrusted.

        Args:
            data: The bytes, padded with zeros to 256.

        Returns:
            The versions, or None if they are malformed. Never raises.
        """
        try:
            magic, protocol = _HELLO_HEADER.unpack_from(data, 0)
            if magic != _HELLO_MAGIC:
                return None
            offset = _HELLO_HEADER.size
            content_hash = data[offset : offset + _HASH_BYTES]
            if len(content_hash) != _HASH_BYTES:
                return None
            offset += _HASH_BYTES
            strings = []
            for _ in range(2):
                length = data[offset]
                offset += 1
                raw = data[offset : offset + length]
                if length > _MAX_VERSION_BYTES or len(raw) != length:
                    return None
                strings.append(raw.decode("utf-8"))
                offset += length
        except (struct.error, IndexError, UnicodeDecodeError):
            return None
        return cls(strings[0], strings[1], bytes(content_hash), protocol)

    def mismatch(self, other: Versions) -> str | None:
        """Describe how another machine differs, naming both sides.

        Args:
            other: The other machine's versions.

        Returns:
            A message for a player, or None if they match.
        """
        found = self.difference(other)
        return None if found is None else found[1]

    def difference(self, other: Versions) -> tuple[EndCode, str] | None:
        """Return how another machine differs, as a code and a message.

        Args:
            other: The other machine's versions.

        Returns:
            The first difference, or None if they match.
        """
        if self.protocol != other.protocol:
            return EndCode.PROTOCOL_DIFFERS, (
                f"Network protocol differs: host {self.protocol}, "
                f"you {other.protocol}. Update the game."
            )
        if self.engine != other.engine:
            return EndCode.ENGINE_DIFFERS, (
                f"Engine differs: host {self.engine}, you {other.engine}."
            )
        if self.game != other.game:
            return EndCode.GAME_DIFFERS, (
                f"Game version differs: host {self.game}, you {other.game}."
            )
        if self.content_hash != other.content_hash:
            return EndCode.FILES_DIFFER, (
                "Game files differ from the host's. Verify your installation."
            )
        return None


@dataclass(frozen=True, slots=True)
class PlayerJoined:
    """On the host: a player was admitted.

    Attributes:
        peer: The connection's id. Random, and gone when the connection is.
        versions: What the player is running.
        slot: The player's seat in this game, from 1, since the host is 0. Use this
            rather than `peer` for anything per player, such as a drop's owner.
    """

    peer: int
    versions: Versions
    slot: int


@dataclass(frozen=True, slots=True)
class PlayerLeft:
    """On the host: an admitted player is gone."""

    peer: int
    reason: str
    code: EndCode = EndCode.UNKNOWN


@dataclass(frozen=True, slots=True)
class Joined:
    """On a client: the host admitted us.

    Attributes:
        slot: Our seat in this game. See `PlayerJoined`.
    """

    slot: int


@dataclass(frozen=True, slots=True)
class Refused:
    """On a client: the host would not admit us, and said why."""

    reason: str
    code: EndCode = EndCode.UNKNOWN


@dataclass(frozen=True, slots=True)
class Left:
    """On a client: the session is over."""

    reason: str
    code: EndCode = EndCode.UNKNOWN


@dataclass(frozen=True, slots=True)
class MessageReceived:
    """A game message from an admitted peer. Its contents are untrusted."""

    peer: int
    channel: int
    data: bytes


@dataclass(frozen=True, slots=True)
class SessionFailed:
    """The transport stopped working. The session delivers nothing more."""

    reason: str
    code: EndCode = EndCode.UNKNOWN


SessionEvent = (
    PlayerJoined
    | PlayerLeft
    | Joined
    | Refused
    | Left
    | MessageReceived
    | SessionFailed
)


class HostSession:
    """The host's view: who is admitted, and what they said."""

    def __init__(self, transport: Transport, versions: Versions) -> None:
        """Start admitting players.

        Args:
            transport: The hosting transport.
            versions: What a player must match.
        """
        self._transport = transport
        self._versions = versions
        self._players: dict[int, int] = {}

    @property
    def players(self) -> frozenset[int]:
        """The peers currently admitted."""
        return frozenset(self._players)

    def slot_of(self, peer: int) -> int | None:
        """Return an admitted peer's seat, or None if it has none."""
        return self._players.get(peer)

    def send(self, peer: int, channel: Channel, data: bytes) -> bool:
        """Send to an admitted player.

        Args:
            peer: The player.
            channel: How to deliver it. `Channel.CONTROL` is the session's own.
            data: The message.

        Returns:
            False if it was not accepted. See `Transport.send`.
        """
        if peer not in self._players:
            return False
        return self._transport.send(peer, channel, data)

    def kick(self, peer: int) -> None:
        """Remove a player."""
        self._transport.disconnect(peer)

    def poll(self) -> list[SessionEvent]:
        """Admit or refuse newcomers, and return what the game should hear."""
        events: list[SessionEvent] = []
        for event in self._transport.poll():
            if isinstance(event, MessageDelivered):
                # A peer that was not admitted, or a client writing to the
                # session's own channel, is simply not listened to.
                if event.peer in self._players and event.channel != Channel.CONTROL:
                    events.append(
                        MessageReceived(event.peer, event.channel, event.data)
                    )
            elif isinstance(event, PeerConnected):
                joined = self._admit(event)
                if joined is not None:
                    events.append(joined)
            elif isinstance(event, PeerDisconnected):
                if event.peer in self._players:
                    del self._players[event.peer]
                    events.append(
                        PlayerLeft(event.peer, event.reason, _code_for(event.reason))
                    )
            elif isinstance(event, TransportFailed):
                events.append(SessionFailed(event.reason, EndCode.TRANSPORT_FAILED))
        return events

    def _admit(self, event: PeerConnected) -> PlayerJoined | None:
        theirs = Versions.decode(event.user_data)
        if theirs is None:
            self._refuse(
                event.peer,
                EndCode.UNREADABLE_VERSIONS,
                "Could not read your version information.",
            )
            return None
        difference = self._versions.difference(theirs)
        if difference is not None:
            self._refuse(event.peer, *difference)
            return None
        taken = set(self._players.values())
        slot = next(s for s in range(1, len(taken) + 2) if s not in taken)
        self._players[event.peer] = slot
        self._transport.send(event.peer, Channel.CONTROL, _WELCOME + bytes([slot]))
        return PlayerJoined(event.peer, theirs, slot)

    def _refuse(self, peer: int, code: EndCode, reason: str) -> None:
        coded = _REFUSAL_CODE + bytes([_REFUSAL_BYTES[code]])
        self._transport.send(peer, Channel.CONTROL, coded)
        message = _REFUSED + reason.encode()[:_MAX_REFUSAL_BYTES]
        self._transport.send(peer, Channel.CONTROL, message)
        self._transport.disconnect(peer, flush=True)

    def close(self) -> None:
        """End the session for everyone."""
        self._transport.close()


class ClientSession:
    """A joining player's view."""

    def __init__(self, transport: Transport) -> None:
        """Start waiting for the host's answer.

        Args:
            transport: The client transport, whose user data carries this
                player's encoded `Versions`.
        """
        self._transport = transport
        self._joined = False
        self._ended = False
        self._refusal_code = EndCode.UNKNOWN
        # Channels aren't ordered against each other, so a reliable message can overtake
        # the welcome when the welcome's packet is lost. Dropping it would be permanent.
        self._early: list[MessageDelivered] = []

    @property
    def joined(self) -> bool:
        """Whether the host has admitted us."""
        return self._joined

    def send(self, channel: Channel, data: bytes) -> bool:
        """Send to the host.

        Args:
            channel: How to deliver it.
            data: The message.

        Returns:
            False if it was not accepted, which includes before joining.
        """
        if not self._joined:
            return False
        return self._transport.send(HOST_PEER, channel, data)

    def poll(self) -> list[SessionEvent]:
        """Return what the game should hear."""
        events: list[SessionEvent] = []
        for event in self._transport.poll():
            if isinstance(event, MessageDelivered):
                self._on_message(event, events)
            elif isinstance(event, PeerDisconnected):
                if not self._ended:
                    self._ended = True
                    self._joined = False
                    events.append(Left(_explain(event.reason), _code_for(event.reason)))
            elif isinstance(event, TransportFailed):
                self._joined = False
                events.append(SessionFailed(event.reason, EndCode.TRANSPORT_FAILED))
        return events

    def _on_message(self, event: MessageDelivered, events: list[SessionEvent]) -> None:
        if event.channel != Channel.CONTROL:
            if self._joined:
                events.append(MessageReceived(event.peer, event.channel, event.data))
            elif not self._ended:
                self._early.append(event)
                if len(self._early) > _MAX_MESSAGES_BEFORE_WELCOME:
                    self._ended = True
                    self._early.clear()
                    events.append(
                        SessionFailed(
                            "Too much data before being admitted.",
                            EndCode.TOO_MUCH_EARLY_DATA,
                        )
                    )
            return
        if len(event.data) == 2 and event.data[:1] == _WELCOME and not self._joined:
            self._joined = True
            events.append(Joined(event.data[1]))
            events.extend(
                MessageReceived(m.peer, m.channel, m.data) for m in self._early
            )
            self._early.clear()
        elif event.data[:1] == _REFUSAL_CODE and not self._joined:
            # Untrusted: a byte this does not know is simply no code.
            byte = event.data[1] if len(event.data) == 2 else -1
            self._refusal_code = _REFUSAL_CODES.get(byte, EndCode.UNKNOWN)
        elif event.data[:1] == _REFUSED and not self._joined:
            self._ended = True
            self._early.clear()
            raw = event.data[1 : 1 + _MAX_REFUSAL_BYTES]
            text = raw.decode("utf-8", errors="replace")
            events.append(Refused(text, self._refusal_code))

    def close(self) -> None:
        """Leave the session."""
        self._transport.close()


_TRANSPORT_CODES = {
    "ConnectionRequestTimedOut": EndCode.NO_ANSWER,
    "ConnectionResponseTimedOut": EndCode.NO_ANSWER,
    "ConnectionTimedOut": EndCode.LOST_CONTACT,
    "ConnectionDenied": EndCode.FULL,
    "DisconnectedByServer": EndCode.HOST_ENDED,
    "DisconnectedByClient": EndCode.PLAYER_LEFT,
    # The host's own words, from `rust/src/net/core.rs` and `steam_core.rs`.
    "left": EndCode.PLAYER_LEFT,
    "timed out": EndCode.LOST_CONTACT,
    "disconnected by the host": EndCode.KICKED,
    "removed from the room": EndCode.KICKED,
    "the host closed": EndCode.HOST_ENDED,
}


def _code_for(reason: str) -> EndCode:
    """Name a transport's disconnect reason."""
    if reason.startswith("dropped:"):
        return EndCode.DROPPED
    return _TRANSPORT_CODES.get(reason, EndCode.UNKNOWN)


def _explain(reason: str) -> str:
    """Turn a transport's reason into something a player can act on."""
    if reason in ("ConnectionRequestTimedOut", "ConnectionResponseTimedOut"):
        return (
            "No answer from the host. Check the invite is current, and that the "
            "host is running and reachable."
        )
    if reason == "ConnectionTimedOut":
        return "Lost contact with the host."
    if reason == "ConnectionDenied":
        return "The game is full."
    if reason == "DisconnectedByServer":
        return "The host ended the connection."
    return reason
