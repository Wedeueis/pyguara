"""What crosses the wire for each component, and how it is packed.

A game names the components it replicates and how to quantise each field. Nothing
else is sent, and the same schema on both sides decides how bytes are read:

    schema = ReplicationSchema()
    schema.register(Transform, position=QuantisedVector(step=0.25), rotation=Angle())
    schema.register(Health, current=UInt16(), max_health=UInt16())

Every value is an integer on the wire, so a non-finite float cannot arrive. A value
that does not fit saturates and is counted rather than wrapping, because wrapping
would teleport an entity across the map, and that would look like a network bug.
"""

from __future__ import annotations

import dataclasses
import difflib
import enum
import math
import struct
import zlib
from collections.abc import Callable, Sequence
from typing import Any, Protocol

from pyguara.common.types import Vector2

_MAX_COMPONENTS = 16
_MAX_EVENTS = 256
_MAX_RECORD_BYTES = 512
_MAX_NET_ID = 65535
_INT16 = (-32768, 32767)
_INT32 = (-(2**31), 2**31 - 1)


class FieldCodec(Protocol):
    """How one field is packed. All codecs hold plain integers on the wire."""

    format: str
    interpolates: bool
    saturated: int

    def encode(self, value: Any) -> tuple[int, ...]:
        """Turn a live value into integers, saturating what does not fit."""
        ...

    def decode(self, packed: tuple[int, ...], start: int = 0) -> Any:
        """Turn integers back into a value.

        Args:
            packed: Integers, this field's among them.
            start: Where this field's begin.

        Raises:
            ValueError: If the integers cannot be a valid value.
        """
        ...

    def blend(self, older: Any, newer: Any, amount: float) -> Any:
        """Return a value `amount` of the way from `older` to `newer`."""
        ...


class _Codec:
    """Shared behaviour: no interpolation unless a codec says otherwise."""

    format = ""
    interpolates = False

    def __init__(self) -> None:
        self.saturated = 0

    def blend(self, older: Any, newer: Any, amount: float) -> Any:
        """Hold the older value, for a field that does not interpolate."""
        return older

    def _clamp(self, value: float, low: int, high: int) -> int:
        if not math.isfinite(value):
            self.saturated += 1
            return 0
        rounded = round(value)
        if rounded < low:
            self.saturated += 1
            return low
        if rounded > high:
            self.saturated += 1
            return high
        return rounded


class Quantised(_Codec):
    """A float, sent to the nearest `step`, and interpolated."""

    interpolates = True

    def __init__(self, step: float, wide: bool = False) -> None:
        """Choose precision and range.

        Args:
            step: The smallest difference to keep.
            wide: Use 32 bits. The default, 16, reaches about 32767 steps either way.

        Raises:
            ValueError: If `step` is not positive.
        """
        super().__init__()
        if not step > 0:
            raise ValueError("step must be positive")
        self._step = step
        self.format = "i" if wide else "h"
        self._low, self._high = _INT32 if wide else _INT16

    def encode(self, value: float) -> tuple[int, ...]:
        """See `FieldCodec.encode`."""
        return (self._clamp(value / self._step, self._low, self._high),)

    def decode(self, packed: tuple[int, ...], start: int = 0) -> float:
        """See `FieldCodec.decode`."""
        return packed[start] * self._step

    def blend(self, older: float, newer: float, amount: float) -> float:
        """See `FieldCodec.blend`."""
        return older + (newer - older) * amount


class QuantisedVector(_Codec):
    """A `Vector2`, sent to the nearest `step` on each axis, and interpolated.

    The default range, at a step of 0.25, is about 8000 units either way from the
    origin. Use `wide` for a world larger than that: saturating pins an entity to
    the edge of the range, and is counted in `saturated`.
    """

    interpolates = True

    def __init__(
        self, step: float, wide: bool = False, snap_distance: float | None = 256.0
    ) -> None:
        """Choose precision, range, and what counts as a teleport.

        Args:
            step: The smallest difference to keep.
            wide: Use 32 bits per axis instead of 16.
            snap_distance: A jump this large is drawn at once rather than as motion
                across everything in between. None never snaps.

        Raises:
            ValueError: If `step` is not positive.
        """
        super().__init__()
        if not step > 0:
            raise ValueError("step must be positive")
        self._step = step
        self.format = "ii" if wide else "hh"
        self._low, self._high = _INT32 if wide else _INT16
        self._snap_squared = None if snap_distance is None else snap_distance**2

    def encode(self, value: Any) -> tuple[int, ...]:
        """See `FieldCodec.encode`."""
        step, low, high = self._step, self._low, self._high
        return (
            self._clamp(value.x / step, low, high),
            self._clamp(value.y / step, low, high),
        )

    def decode(self, packed: tuple[int, ...], start: int = 0) -> Any:
        """See `FieldCodec.decode`."""
        step = self._step
        return Vector2(packed[start] * step, packed[start + 1] * step)

    def blend(self, older: Any, newer: Any, amount: float) -> Any:
        """See `FieldCodec.blend`.

        By coordinate rather than with `Vector2`'s operators, which were most of a
        client's frame: this runs per entity per frame.
        """
        old_x, old_y = older
        new_x, new_y = newer
        delta_x = new_x - old_x
        delta_y = new_y - old_y
        snap = self._snap_squared
        if snap is not None and delta_x * delta_x + delta_y * delta_y > snap:
            return newer
        return Vector2(old_x + delta_x * amount, old_y + delta_y * amount)


class Angle(_Codec):
    """An angle in radians, wrapping, and interpolated the short way round."""

    interpolates = True

    def __init__(self, bits: int = 8) -> None:
        """Choose precision.

        Args:
            bits: 8 or 16. 8 is about 1.4 degrees.

        Raises:
            ValueError: If `bits` is neither.
        """
        super().__init__()
        if bits not in (8, 16):
            raise ValueError("An angle is 8 or 16 bits")
        self.format = "B" if bits == 8 else "H"
        self._steps = 1 << bits

    def encode(self, value: float) -> tuple[int, ...]:
        """See `FieldCodec.encode`."""
        if not math.isfinite(value):
            self.saturated += 1
            return (0,)
        return (round(value / math.tau * self._steps) % self._steps,)

    def decode(self, packed: tuple[int, ...], start: int = 0) -> float:
        """See `FieldCodec.decode`."""
        return packed[start] / self._steps * math.tau

    def blend(self, older: float, newer: float, amount: float) -> float:
        """See `FieldCodec.blend`."""
        difference = (newer - older + math.pi) % math.tau - math.pi
        return older + difference * amount


class _Integer(_Codec):
    _low = 0
    _high = 0

    def encode(self, value: float) -> tuple[int, ...]:
        """See `FieldCodec.encode`."""
        return (self._clamp(value, self._low, self._high),)

    def decode(self, packed: tuple[int, ...], start: int = 0) -> int:
        """See `FieldCodec.decode`."""
        return packed[start]


class UInt8(_Integer):
    """A whole number from 0 to 255."""

    format = "B"
    _high = 255


class UInt16(_Integer):
    """A whole number from 0 to 65535."""

    format = "H"
    _high = 65535


class Int32(_Integer):
    """A whole number that fits in 32 bits."""

    format = "i"
    _low, _high = _INT32


class Flag(_Codec):
    """A bool."""

    format = "B"

    def encode(self, value: Any) -> tuple[int, ...]:
        """See `FieldCodec.encode`."""
        return (1 if value else 0,)

    def decode(self, packed: tuple[int, ...], start: int = 0) -> bool:
        """See `FieldCodec.decode`.

        Raises:
            ValueError: If the byte is neither 0 nor 1.
        """
        if packed[start] > 1:
            raise ValueError("A flag is 0 or 1")
        return bool(packed[start])


class EnumField(_Codec):
    """An enum member, by its position in the enum's definition."""

    format = "B"

    def __init__(self, enum_type: type[enum.Enum]) -> None:
        """Bind to an enum.

        Args:
            enum_type: The enum. At most 256 members.

        Raises:
            ValueError: If it has too many.
        """
        super().__init__()
        self._members = list(enum_type)
        if len(self._members) > 256:
            raise ValueError("An enum field holds at most 256 members")
        self._positions = {member: i for i, member in enumerate(self._members)}

    def encode(self, value: Any) -> tuple[int, ...]:
        """See `FieldCodec.encode`."""
        position = self._positions.get(value)
        if position is None:
            self.saturated += 1
            return (0,)
        return (position,)

    def decode(self, packed: tuple[int, ...], start: int = 0) -> Any:
        """See `FieldCodec.decode`.

        Raises:
            ValueError: If no member sits at that position.
        """
        if packed[start] >= len(self._members):
            raise ValueError("No such enum member")
        return self._members[packed[start]]


class Choice(_Codec):
    """One string from a fixed list, sent by its position: a skill's name, say.

    Only the listed values can arrive, so a name from the network can only ever
    choose among them.
    """

    format = "B"

    def __init__(self, values: Sequence[str]) -> None:
        """Fix the values.

        Args:
            values: Every value the field can hold, at most 256, each once. Both
                sides must list them in the same order.

        Raises:
            ValueError: If there are none, too many, or a repeat.
        """
        super().__init__()
        self._values = list(values)
        if not self._values or len(self._values) > 256:
            raise ValueError("A choice holds from 1 to 256 values")
        if len(set(self._values)) != len(self._values):
            raise ValueError("A choice lists each value once")
        self._positions = {value: i for i, value in enumerate(self._values)}
        self.signature = "|".join(self._values)

    def encode(self, value: Any) -> tuple[int, ...]:
        """See `FieldCodec.encode`. A value not listed is counted, and sends the first."""
        position = self._positions.get(value)
        if position is None:
            self.saturated += 1
            return (0,)
        return (position,)

    def decode(self, packed: tuple[int, ...], start: int = 0) -> str:
        """See `FieldCodec.decode`.

        Raises:
            ValueError: If no value sits at that position.
        """
        if packed[start] >= len(self._values):
            raise ValueError("No such choice")
        return self._values[packed[start]]


class EntityRef(_Codec):
    """An entity, in an event: the host's id going out, the client's own coming in.

    It travels as the entity's network id, so only replicated entities can be named.
    One that isn't replicated, or is gone, arrives as None, and a client resolves it
    when the event is applied, so it names the entity as it is then.
    """

    format = "i"

    def encode(self, value: Any) -> tuple[int, ...]:
        """See `FieldCodec.encode`. Takes a network id, or None."""
        return (-1 if value is None else int(value),)

    def decode(self, packed: tuple[int, ...], start: int = 0) -> int | None:
        """See `FieldCodec.decode`. Returns a network id, or None.

        Raises:
            ValueError: If it is outside the range of network ids.
        """
        value = packed[start]
        if value == -1:
            return None
        if not 0 <= value <= _MAX_NET_ID:
            raise ValueError("Not a network id")
        return value


class EventLayout:
    """How one event type is packed.

    Attributes:
        index: Its position in registration order, sent with each event.
        event_type: The event class, a dataclass.
        size: Bytes one event takes on the wire.
        signature: Its layout as text, for the schema's fingerprint.
    """

    def __init__(
        self, index: int, event_type: type, fields: dict[str, FieldCodec]
    ) -> None:
        """Compile the packing.

        Args:
            index: Its position in registration order.
            event_type: The event class.
            fields: Field name to codec, in wire order.
        """
        self.index = index
        self.event_type = event_type
        self._fields = list(fields.items())
        self._struct = struct.Struct("<" + "".join(c.format for c in fields.values()))
        self.size = self._struct.size
        self._slices: list[tuple[str, FieldCodec, int, bool]] = []
        position = 0
        for name, codec in self._fields:
            width = len(
                struct.unpack(
                    "<" + codec.format, bytes(struct.calcsize("<" + codec.format))
                )
            )
            self._slices.append((name, codec, position, isinstance(codec, EntityRef)))
            position += width
        self.signature = (
            f"{event_type.__name__}("
            + ",".join(
                f"{name}:{codec.format}{_extra_signature(codec)}"
                for name, codec in self._fields
            )
            + ")"
        )

    def encode(self, event: Any, net_id_of: Callable[[str], int | None]) -> bytes:
        """Pack an event.

        Args:
            event: The event.
            net_id_of: Turns an entity id into its network id, or None.
        """
        packed: list[int] = []
        for name, codec, _, is_entity in self._slices:
            value = getattr(event, name)
            if is_entity:
                value = None if value is None else net_id_of(value)
            packed.extend(codec.encode(value))
        return self._struct.pack(*packed)

    def decode(self, data: bytes, offset: int) -> tuple[Any, ...]:
        """Unpack one event's values, in field order, with entities as network ids.

        Raises:
            ValueError: If it does not fit, or a value is invalid for its field.
        """
        if offset + self.size != len(data):
            raise ValueError("An event does not fit its message")
        packed = self._struct.unpack_from(data, offset)
        return tuple(codec.decode(packed, start) for _, codec, start, _ in self._slices)

    def build(
        self, values: tuple[Any, ...], entity_of: Callable[[int], str | None]
    ) -> Any:
        """Make the event, naming entities as they are here.

        Args:
            values: From `decode`.
            entity_of: Turns a network id into a local entity id, or None.
        """
        arguments = {}
        for (name, _, _, is_entity), value in zip(self._slices, values, strict=True):
            if is_entity and value is not None:
                value = entity_of(value)
            arguments[name] = value
        return self.event_type(**arguments)

    def saturated(self) -> int:
        """Return how many values have not fit their field so far."""
        return sum(codec.saturated for _, codec in self._fields)


def _extra_signature(codec: FieldCodec) -> str:
    extra = getattr(codec, "signature", None)
    return f"[{extra}]" if isinstance(extra, str) else ""


class ComponentSchema:
    """How one component type is packed.

    Attributes:
        index: This component's bit in a record's mask.
        component_type: The component.
        size: Bytes one instance takes on the wire.
        interpolates: Whether any field blends between snapshots.
    """

    def __init__(
        self, index: int, component_type: type, fields: dict[str, FieldCodec]
    ) -> None:
        """Compile the packing.

        Args:
            index: Its position in registration order.
            component_type: The component.
            fields: Field name to codec, in wire order.
        """
        self.index = index
        self.component_type = component_type
        self._fields = list(fields.items())
        self._struct = struct.Struct("<" + "".join(c.format for c in fields.values()))
        self.size = self._struct.size
        self.interpolates = any(c.interpolates for c in fields.values())
        self.signature = (
            f"{component_type.__name__}("
            + ",".join(
                f"{name}:{c.format}{_extra_signature(c)}" for name, c in self._fields
            )
            + ")"
        )
        self._slices: list[tuple[str, FieldCodec, int, int]] = []
        position = 0
        for name, codec in self._fields:
            count = struct.calcsize("<" + codec.format)
            width = len(struct.unpack("<" + codec.format, bytes(count)))
            self._slices.append((name, codec, position, width))
            position += width
        self._decoders = [(codec.decode, start) for _, codec, start, _ in self._slices]
        self._blenders = [(name, codec.blend) for name, codec, _, _ in self._slices]

    def encode(self, component: Any) -> bytes:
        """Pack a live component."""
        packed: list[int] = []
        for name, codec in self._fields:
            packed.extend(codec.encode(getattr(component, name)))
        return self._struct.pack(*packed)

    def decode(self, data: bytes, offset: int) -> tuple[Any, ...]:
        """Unpack one instance's values, in field order.

        Args:
            data: The message.
            offset: Where this instance starts. The caller checks it fits.

        Returns:
            The field values.

        Raises:
            ValueError: If a value is invalid for its field.
        """
        packed = self._struct.unpack_from(data, offset)
        return tuple([decode(packed, start) for decode, start in self._decoders])

    def apply(self, component: Any, values: tuple[Any, ...]) -> None:
        """Write decoded values to a component."""
        for (name, _, _, _), value in zip(self._slices, values, strict=True):
            setattr(component, name, value)

    def write_blended(
        self,
        component: Any,
        older: tuple[Any, ...],
        newer: tuple[Any, ...],
        amount: float,
    ) -> None:
        """Write values `amount` of the way from `older` to `newer` to a component.

        A field that did not change between the two is written as it is, without
        computing anything, since many never do: a flock's rotation, say.
        """
        for (name, blend), old, new in zip(self._blenders, older, newer, strict=True):
            setattr(component, name, old if old == new else blend(old, new, amount))

    def saturated(self) -> int:
        """Return how many values have not fit their field so far."""
        return sum(codec.saturated for _, codec in self._fields)


class ReplicationSchema:
    """Every replicated component and event. Both sides register the same, in order."""

    def __init__(self) -> None:
        """Start empty."""
        self.components: list[ComponentSchema] = []
        self.events: list[EventLayout] = []
        self._by_type: dict[type, ComponentSchema] = {}
        self._events_by_type: dict[type, EventLayout] = {}

    def register(self, component_type: type, **fields: FieldCodec) -> None:
        """Replicate these fields of this component.

        Args:
            component_type: The component.
            **fields: Field name to codec.

        Raises:
            ValueError: If it is already registered, has no fields, or would not fit.
        """
        if component_type in self._by_type:
            raise ValueError(f"{component_type.__name__} is already registered")
        if not fields:
            raise ValueError(f"{component_type.__name__} needs at least one field")
        if len(self.components) >= _MAX_COMPONENTS:
            raise ValueError(f"At most {_MAX_COMPONENTS} components can replicate")
        schema = ComponentSchema(len(self.components), component_type, fields)
        if schema.size > _MAX_RECORD_BYTES:
            raise ValueError(f"{component_type.__name__} is too large to replicate")
        self.components.append(schema)
        self._by_type[component_type] = schema

    def register_event(self, event_type: type, **fields: FieldCodec) -> None:
        """Send this event to clients, with these fields.

        A client builds the event from the fields alone, so every other field of the
        dataclass needs a default. Name entities with `EntityRef`.

        Args:
            event_type: The event, a dataclass.
            **fields: Field name to codec. May be empty, for an event that is only
                its type.

        Raises:
            ValueError: If it is already registered, isn't a dataclass, names a
                field it doesn't have, leaves out one without a default, or would
                not fit.
        """
        name = event_type.__name__
        if event_type in self._events_by_type:
            raise ValueError(f"{name} is already registered")
        if not dataclasses.is_dataclass(event_type):
            raise ValueError(f"{name} must be a dataclass to be sent as an event")
        if len(self.events) >= _MAX_EVENTS:
            raise ValueError(f"At most {_MAX_EVENTS} event types can be sent")
        declared = {f.name: f for f in dataclasses.fields(event_type) if f.init}
        for field_name in fields:
            if field_name not in declared:
                close = difflib.get_close_matches(field_name, declared, n=1)
                hint = f"; did you mean {close[0]!r}?" if close else ""
                raise ValueError(f"{name} has no field {field_name!r}{hint}")
        for field_name, declared_field in declared.items():
            required = (
                declared_field.default is dataclasses.MISSING
                and declared_field.default_factory is dataclasses.MISSING
            )
            if required and field_name not in fields:
                raise ValueError(
                    f"{name}.{field_name} has no default, so it must be sent"
                )
        layout = EventLayout(len(self.events), event_type, fields)
        if layout.size > _MAX_RECORD_BYTES:
            raise ValueError(f"{name} is too large to send")
        self.events.append(layout)
        self._events_by_type[event_type] = layout

    def event_layout(self, event_type: type) -> EventLayout | None:
        """Return an event's layout, or None if it is not sent."""
        return self._events_by_type.get(event_type)

    def for_type(self, component_type: type) -> ComponentSchema | None:
        """Return a component's schema, or None if it does not replicate."""
        return self._by_type.get(component_type)

    def fingerprint(self) -> int:
        """Return a hash of the wire layout, so two sides can check they agree."""
        layout = ";".join(c.signature for c in self.components)
        if self.events:
            layout += ";events:" + ";".join(e.signature for e in self.events)
        return zlib.crc32(layout.encode())

    def payload_size(self, mask: int) -> int | None:
        """Return the bytes a record with this mask holds, or None if it is invalid.

        Args:
            mask: Which components the record carries. It may come from the network.
        """
        if mask >> len(self.components):
            return None
        return sum(c.size for c in self.components if mask >> c.index & 1)
