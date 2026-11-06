"""Your own character responding at once, while the host stays in charge.

The client runs its own character immediately and sends what it did as commands, each
naming the host tick it applies to. The host applies one command per tick and sends back
the exact state, and the client checks that against what it predicted for that tick. If
they differ, it goes back to the host's state and replays the newer commands. The host
never accepts a position from a client, only commands, so a modified client can't move
faster than its commands allow.

A state "at tick N" includes every command before N. That one rule is what lines the
two machines up, and it's why no separate acknowledgement is needed.

The ways this could go wrong, and what handles each:

- **The command the client simulated differs from the one the host received**, because
  sending rounds it. The client simulates the decoded copy.
- **A command arrives late.** The host repeats the last one for a short time and then uses
  `neutral`, so a stalled player doesn't keep running. The client corrects from the next
  state.
- **The client runs too far ahead or behind.** The host reports how early commands actually
  arrived, and the client adds or skips ticks to hold a target. Each change starts a new
  epoch, which commands carry and the host echoes, so the client never acts twice on
  measurements from before its change arrived. Comparing ticks can't tell it that: commands
  from before a rewind have the larger numbers.
- **A correction would be a visible jump.** It's shown as an offset that fades, added after
  the fixed updates and removed before the next, so the simulation never sees it.
"""

from __future__ import annotations

import math
import struct
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Protocol

from pyguara.net.schema import ComponentSchema, FieldCodec
from pyguara.net.transport import Channel

_COMMANDS = 0xE6
_OWNER_STATE = 0xE7

_COMMANDS_HEADER = struct.Struct("<BIBB")
_OWNER_HEADER = struct.Struct("<BIBbB")

_MAX_COMMAND_BYTES = 64
_MAX_STATE_VALUES = 32
# Every packet repeats this many ticks, so a lost one usually costs nothing.
_REDUNDANT_COMMANDS = 10
_MAX_COMMANDS_PER_MESSAGE = 32
# Further ahead than this is more than two seconds of lead, and isn't honest play.
_MAX_TICKS_AHEAD = 120
_NO_SLACK = -128
_MAX_SLACK = 127
_REPLAY_WINDOW = 120
_INITIAL_LEAD_TICKS = 12
_LARGEST_CATCH_UP = 12
_LARGEST_GENTLE_REWIND = 12
_SLACK_BAND = 2
_EPOCHS = 256
_FADED = 0.01


class PredictedBody(Protocol):
    """What prediction needs from a character. Host and client must step it the same."""

    def capture(self) -> tuple[float, ...]:
        """Return everything the next step depends on, as finite numbers."""
        ...

    def restore(self, state: tuple[float, ...]) -> None:
        """Go back to a captured state."""
        ...

    def advance(self, command: Any, dt: float) -> None:
        """Run one step from one command, touching nothing but this character."""
        ...

    def position(self) -> tuple[float, float]:
        """Return where the character is, to measure a correction."""
        ...

    def show_offset(self, x: float, y: float) -> None:
        """Draw it this far from where it is, until the next `restore`."""
        ...


class CommandSchema[C]:
    """How a game's command is packed. Both sides must build the same one.

    Keep commands small, since one goes out every tick, and frozen, since they're held
    for replay:

        CommandSchema(Move, x=Quantised(step=1 / 64), y=Quantised(step=1 / 64))
    """

    def __init__(self, command_type: type[C], **fields: FieldCodec) -> None:
        """Compile the packing.

        Args:
            command_type: Built with these fields as keyword arguments.
            **fields: Field name to codec.

        Raises:
            ValueError: If it has no fields or is too large.
        """
        if not fields:
            raise ValueError("A command needs at least one field")
        self._type = command_type
        self._names = list(fields)
        self._packing = ComponentSchema(0, command_type, fields)
        self.size = self._packing.size
        if self.size > _MAX_COMMAND_BYTES:
            raise ValueError(f"A command is at most {_MAX_COMMAND_BYTES} bytes")

    def encode(self, command: C) -> bytes:
        """Pack a command, saturating what doesn't fit."""
        return self._packing.encode(command)

    def decode(self, data: bytes, offset: int = 0) -> C:
        """Unpack a command.

        Raises:
            ValueError: If a value is invalid for its field.
            struct.error: If it doesn't fit.
        """
        values = self._packing.decode(data, offset)
        return self._type(**dict(zip(self._names, values, strict=True)))


@dataclass(slots=True)
class _Player[C]:
    peer: int
    commands: dict[int, C]
    last: C
    newest: int | None = None
    repeats: int = 0
    smallest_slack: int | None = None
    epoch: int = 0
    body: PredictedBody | None = None


class PredictionHost[C]:
    """The host's side: takes each player's commands, and tells them what happened.

    Attributes:
        malformed: Command messages that could not be read, which are dropped.
        out_of_window: Commands for a tick already past or too far ahead, which are
            dropped. Some are normal, since each packet repeats earlier ticks.
        late_commands: Ticks a player's command had not arrived in time.
        dropped_states: State messages the transport would not accept.
    """

    def __init__(
        self,
        schema: CommandSchema[C],
        neutral: C,
        send: Callable[[int, Channel, bytes], bool],
        state_interval_ticks: int = 3,
        max_repeat_ticks: int = 6,
    ) -> None:
        """Start with no players.

        Args:
            schema: How commands are packed.
            neutral: What a player with no recent command is doing: standing still.
            send: Sends a message to a peer, returning False if it was not accepted.
            state_interval_ticks: Fixed ticks between state messages.
            max_repeat_ticks: How long a late player's last command keeps being used
                before `neutral`. 6 is 100 ms at 60 Hz.
        """
        self._schema = schema
        self._neutral = neutral
        self._send = send
        self._interval = state_interval_ticks
        self._max_repeat = max_repeat_ticks
        self._players: dict[int, _Player[C]] = {}
        self._slot_of: dict[int, int] = {}
        self._tick = 0
        self._last_state_tick: int | None = None
        self.malformed = 0
        self.out_of_window = 0
        self.late_commands = 0
        self.dropped_states = 0

    def add_peer(self, peer: int, slot: int) -> None:
        """Start listening to a player.

        Args:
            peer: The connection. A message can only ever speak for its own.
            slot: Its player slot.
        """
        self._players[slot] = _Player(peer, {}, self._neutral)
        self._slot_of[peer] = slot

    def remove_peer(self, peer: int) -> None:
        """Stop listening to a player."""
        slot = self._slot_of.pop(peer, None)
        if slot is not None:
            del self._players[slot]

    def bind(self, slot: int, body: PredictedBody | None) -> None:
        """Say which character a player controls, so its state gets sent to them.

        Args:
            slot: The player. One that hasn't joined is ignored.
            body: The character, or None when it's gone.
        """
        player = self._players.get(slot)
        if player is not None:
            player.body = body

    def handle_message(self, peer: int, channel: int, data: bytes) -> bool:
        """Take a message from a player. Hostile bytes are dropped, never raised.

        Args:
            peer: Who sent it, from the authenticated connection.
            channel: The channel it came on.
            data: The message.

        Returns:
            True if it was prediction's, False if it is for the game.
        """
        if channel != Channel.COMMANDS or not data or data[0] != _COMMANDS:
            return False
        slot = self._slot_of.get(peer)
        if slot is not None:
            try:
                self._on_commands(self._players[slot], data)
            except (struct.error, ValueError):
                self.malformed += 1
        return True

    def _on_commands(self, player: _Player[C], data: bytes) -> None:
        _, newest, epoch, count = _COMMANDS_HEADER.unpack_from(data, 0)
        size = self._schema.size
        if (
            not 0 < count <= _MAX_COMMANDS_PER_MESSAGE
            or len(data) != _COMMANDS_HEADER.size + count * size
        ):
            raise ValueError("A command message has the wrong length")
        # Everything is decoded before anything is kept, so one bad value discards
        # the message whole rather than leaving part of it.
        offset = _COMMANDS_HEADER.size
        decoded = []
        for back in range(count):
            decoded.append((newest - back, self._schema.decode(data, offset)))
            offset += size
        age = (player.epoch - epoch) % _EPOCHS
        if 0 < age < _EPOCHS // 2:
            # From before the client's last change, arriving late. It no longer applies.
            return
        if age != 0:
            player.epoch = epoch
            player.smallest_slack = None
            player.newest = None
            # What it sent before a rewind is for ticks it's going to send again.
            player.commands = {t: c for t, c in player.commands.items() if t <= newest}
        earliest = self._tick
        latest = self._tick + _MAX_TICKS_AHEAD
        for tick, command in decoded:
            if earliest <= tick <= latest:
                player.commands[tick] = command
            else:
                self.out_of_window += 1
        # A message that's entirely too late still counts here. It's how the client finds
        # out it needs more lead, so ignoring it would leave it stuck behind for good.
        if newest <= latest and (player.newest is None or newest > player.newest):
            player.newest = newest

    def take(self, slot: int, tick: int) -> C:
        """Return what a player does on this tick. Call once per fixed update.

        This is the only way a command takes effect, so however many a client sends,
        its character gets one per tick.

        Args:
            slot: The player.
            tick: The tick about to be simulated: `Application.fixed_tick`, read during
                the fixed update.

        Returns:
            Their command, or a stand-in if it hasn't arrived.
        """
        self._tick = tick
        player = self._players.get(slot)
        if player is None:
            return self._neutral
        if player.newest is not None:
            slack = player.newest - tick
            if player.smallest_slack is None or slack < player.smallest_slack:
                player.smallest_slack = slack
        command = player.commands.pop(tick, None)
        if command is not None:
            player.last = command
            player.repeats = 0
            return command
        if player.newest is not None:
            self.late_commands += 1
        player.repeats += 1
        if player.repeats > self._max_repeat:
            player.last = self._neutral
        return player.last

    def step(self, tick: int) -> None:
        """Send each player their character's state, when due. Call after the simulation.

        Args:
            tick: The fixed tick the world is at.
        """
        self._tick = tick
        if (
            self._last_state_tick is not None
            and tick - self._last_state_tick < self._interval
        ):
            return
        self._last_state_tick = tick
        for player in self._players.values():
            self._forget_past(player, tick)
            if player.body is not None:
                self._send_state(player, player.body, tick)
            player.smallest_slack = None

    @staticmethod
    def _forget_past(player: _Player[C], tick: int) -> None:
        # Normally `take` empties these. A game not calling it must not grow them.
        if len(player.commands) > _MAX_TICKS_AHEAD + 1:
            player.commands = {t: c for t, c in player.commands.items() if t >= tick}

    def _send_state(self, player: _Player[C], body: PredictedBody, tick: int) -> None:
        state = body.capture()
        slack = player.smallest_slack
        message = _OWNER_HEADER.pack(
            _OWNER_STATE,
            tick,
            player.epoch,
            _NO_SLACK if slack is None else max(_NO_SLACK + 1, min(_MAX_SLACK, slack)),
            len(state),
        ) + struct.pack(f"<{len(state)}d", *state)
        if not self._send(player.peer, Channel.SNAPSHOT, message):
            self.dropped_states += 1


@dataclass(slots=True)
class _Sent[C]:
    command: C
    wire: bytes


@dataclass(slots=True)
class _OwnerState:
    tick: int
    epoch: int
    slack: int
    state: tuple[float, ...]


class PredictionClient[C]:
    """A client's side: runs its own character now, and corrects from the host.

    Attributes:
        malformed: State messages that could not be read, which are dropped.
        stale_states: State messages older than one already seen, which are dropped.
        unsent_commands: Command messages the transport would not accept.
        corrections: How many times a host state moved the character.
        last_correction: How far the most recent one moved it, in world units.
        largest_correction: The largest so far, in world units.
        replayed_ticks: Ticks simulated again because of corrections.
        tick_adjustments: How many times the lead over the host was changed.
    """

    def __init__(
        self,
        schema: CommandSchema[C],
        neutral: C,
        send: Callable[[Channel, bytes], bool],
        dt: float = 1 / 60,
        target_slack_ticks: int = 2,
        smoothing_half_life: float = 0.05,
        snap_distance: float = 64.0,
    ) -> None:
        """Start with no character.

        Args:
            schema: How commands are packed.
            neutral: What the host assumes when it has no command. Must match the host's.
            send: Sends a message to the host, returning False if it was not accepted.
            dt: The fixed step in seconds. Must match the host's.
            target_slack_ticks: How early commands should reach the host. 2 is about 33
                ms, enough to ride out a little jitter and a lost packet.
            smoothing_half_life: Seconds for half of a correction to fade.
            snap_distance: A correction at least this large is shown at once. Gliding
                across that much of the screen would look worse than the jump.
        """
        self._schema = schema
        self._neutral = neutral
        self._send = send
        self._dt = dt
        self._target = target_slack_ticks
        self._half_life = smoothing_half_life
        self._snap = snap_distance
        self._body: PredictedBody | None = None
        self._tick: int | None = None
        self._advancing: int | None = None
        self._sim: tuple[float, ...] | None = None
        self._states: dict[int, tuple[float, ...]] = {}
        self._commands: dict[int, _Sent[C]] = {}
        self._pending: _OwnerState | None = None
        self._last_state_tick: int | None = None
        self._catch_up = 0
        self._hold = 0
        self._epoch = 0
        self._offset_x = 0.0
        self._offset_y = 0.0
        self._new_commands = False
        self.malformed = 0
        self.stale_states = 0
        self.unsent_commands = 0
        self.corrections = 0
        self.last_correction = 0.0
        self.largest_correction = 0.0
        self.replayed_ticks = 0
        self.tick_adjustments = 0

    @property
    def tick(self) -> int | None:
        """The host tick being predicted, or None before there's a character to predict."""
        return self._tick

    @property
    def advancing(self) -> int | None:
        """The host tick the character is stepping through, while its `advance` runs.

        Read it from inside `advance`, to act as the host does on that tick, such as
        firing a shot numbered by it. `tick` can't tell you: one `step` may advance
        several ticks to catch up, and a correction replays past ones from inside
        `handle_message`. None outside an `advance`.
        """
        return self._advancing

    def bind(self, body: PredictedBody | None) -> None:
        """Say which character this player controls.

        Args:
            body: The character, or None when it's gone.
        """
        self._body = body
        self._tick = None
        self._sim = None
        self._states.clear()
        self._commands.clear()
        self._catch_up = 0
        self._hold = 0
        self._epoch = (self._epoch + 1) % _EPOCHS
        self._offset_x = self._offset_y = 0.0
        if body is not None and self._pending is not None:
            pending = self._pending
            self._pending = None
            self._apply(pending)

    def handle_message(self, channel: int, data: bytes) -> bool:
        """Take a message from the host. Hostile bytes are dropped, never raised.

        Args:
            channel: The channel it came on.
            data: The message.

        Returns:
            True if it was prediction's, False if it wasn't.
        """
        if channel != Channel.SNAPSHOT or not data or data[0] != _OWNER_STATE:
            return False
        try:
            owner = self._decode(data)
        except (struct.error, ValueError):
            self.malformed += 1
            return True
        if self._last_state_tick is not None and owner.tick <= self._last_state_tick:
            self.stale_states += 1
            return True
        self._last_state_tick = owner.tick
        if self._body is None:
            self._pending = owner
        else:
            self._apply(owner)
        return True

    @staticmethod
    def _decode(data: bytes) -> _OwnerState:
        _, tick, epoch, slack, count = _OWNER_HEADER.unpack_from(data, 0)
        if (
            count == 0
            or count > _MAX_STATE_VALUES
            or len(data) != _OWNER_HEADER.size + count * 8
        ):
            raise ValueError("A state message has the wrong length")
        state = struct.unpack_from(f"<{count}d", data, _OWNER_HEADER.size)
        if not all(map(math.isfinite, state)):
            raise ValueError("A state message holds a non-finite value")
        return _OwnerState(tick, epoch, slack, state)

    def _apply(self, owner: _OwnerState) -> None:
        body = self._body
        assert body is not None
        if len(body.capture()) != len(owner.state):
            self.malformed += 1
            return
        if self._tick is None:
            body.restore(owner.state)
            self._sim = owner.state
            self._tick = owner.tick + _INITIAL_LEAD_TICKS
            return
        self._reconcile(body, owner)
        self._steer(owner)
        for old in [t for t in self._states if t < owner.tick]:
            del self._states[old]

    def _reconcile(self, body: PredictedBody, owner: _OwnerState) -> None:
        assert self._tick is not None
        tick = owner.tick
        if self._states.get(tick) == owner.state:
            return
        before_x, before_y = body.position()
        body.restore(owner.state)
        # A host ahead of us, or too far behind to replay from, leaves nothing to re-run.
        if self._tick - _REPLAY_WINDOW <= tick < self._tick:
            self._replay(body, tick)
        elif tick >= self._tick:
            self._tick = tick
            self._states.clear()
        else:
            self._tick = tick
            self._states.clear()
            self._commands.clear()
        self._sim = body.capture()
        after_x, after_y = body.position()
        self._note_correction(before_x - after_x, before_y - after_y)

    def _replay(self, body: PredictedBody, start: int) -> None:
        assert self._tick is not None
        last: C = self._neutral
        for tick in range(start, self._tick):
            sent = self._commands.get(tick)
            if sent is not None:
                last = sent.command
            self._states[tick] = body.capture()
            self._advance(body, last, tick)
            self.replayed_ticks += 1

    def _note_correction(self, error_x: float, error_y: float) -> None:
        distance = math.hypot(error_x, error_y)
        if distance == 0.0:
            return
        self.corrections += 1
        self.last_correction = distance
        self.largest_correction = max(self.largest_correction, distance)
        offset_x = self._offset_x + error_x
        offset_y = self._offset_y + error_y
        if math.hypot(offset_x, offset_y) >= self._snap:
            offset_x = offset_y = 0.0
        self._offset_x = offset_x
        self._offset_y = offset_y

    def _steer(self, owner: _OwnerState) -> None:
        """Hold commands at the target earliness, using what the host measured."""
        assert self._tick is not None
        # Measured before our last change reached the host, so acting on it would correct
        # the same error twice.
        if owner.slack == _NO_SLACK or owner.epoch != self._epoch:
            return
        error = owner.slack - self._target
        if -_LARGEST_CATCH_UP <= error < 0:
            self._catch_up = -error
        elif error < 0:
            # Too far behind to simulate through. The host stands in for the gap.
            self._tick -= error
            oldest = self._tick - _REPLAY_WINDOW
            self._commands = {t: c for t, c in self._commands.items() if t >= oldest}
            self._states = {t: s for t, s in self._states.items() if t >= oldest}
        elif error > _LARGEST_GENTLE_REWIND:
            self._tick -= error
            self._states = {t: s for t, s in self._states.items() if t < self._tick}
            self._commands = {t: c for t, c in self._commands.items() if t < self._tick}
        elif error > _SLACK_BAND:
            self._hold = 1
        else:
            return
        self.tick_adjustments += 1
        self._epoch = (self._epoch + 1) % _EPOCHS

    def step(self, command: C) -> None:
        """Run this tick's command. Call once per fixed update.

        Args:
            command: What the player is doing now. A velocity must be a pure function of
                it, or a replay has nothing to re-run.
        """
        body = self._body
        if body is None or self._tick is None:
            return
        if self._hold > 0:
            self._hold -= 1
            return
        wire = self._schema.encode(command)
        # What the host will decode, not what the game passed: packing rounds it.
        sent = _Sent(self._schema.decode(wire), wire)
        for _ in range(1 + self._catch_up):
            tick = self._tick
            self._states[tick] = body.capture()
            self._commands[tick] = sent
            self._commands.pop(tick - _REPLAY_WINDOW, None)
            self._states.pop(tick - _REPLAY_WINDOW, None)
            self._advance(body, sent.command, tick)
            self._tick = tick + 1
        self._catch_up = 0
        self._new_commands = True

    def _advance(self, body: PredictedBody, command: C, tick: int) -> None:
        self._advancing = tick
        try:
            body.advance(command, self._dt)
        finally:
            self._advancing = None

    def begin_frame(self) -> None:
        """Take away what was only for display. Call before messages and fixed updates."""
        if self._body is not None and self._sim is not None:
            self._body.restore(self._sim)

    def end_frame(self, frame_time: float) -> None:
        """Send this frame's commands and show the character. Call after fixed updates.

        Args:
            frame_time: Seconds this frame covers.
        """
        body = self._body
        if body is None or self._tick is None:
            return
        self._sim = body.capture()
        if self._new_commands:
            self._new_commands = False
            self._send_commands()
        fade = 0.5 ** (frame_time / self._half_life)
        self._offset_x *= fade
        self._offset_y *= fade
        if math.hypot(self._offset_x, self._offset_y) < _FADED:
            self._offset_x = self._offset_y = 0.0
        else:
            body.show_offset(self._offset_x, self._offset_y)

    def _send_commands(self) -> None:
        assert self._tick is not None
        newest = self._tick - 1
        parts: list[bytes] = []
        for back in range(_REDUNDANT_COMMANDS):
            sent = self._commands.get(newest - back)
            if sent is None:
                break
            parts.append(sent.wire)
        if not parts or newest < 0:
            return
        header = _COMMANDS_HEADER.pack(_COMMANDS, newest, self._epoch, len(parts))
        if not self._send(Channel.COMMANDS, header + b"".join(parts)):
            self.unsent_commands += 1
