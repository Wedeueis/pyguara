"""The swarm in Python, for comparing the native one against.

It allocates slots, generations and ids exactly as `rust/src/swarm.rs`
does, finds neighbours in the order `rust/src/grid.rs` returns them, and
sums them in the same operations, so the two agree bit for bit. It is
slow, which is why it is test code. Never compare the native swarm with
itself in its place.
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Sequence
from dataclasses import astuple

from pyguara.ai.swarm import SwarmKind
from pyguara.common.types import Vector2

_SLOT_BITS = 32
_SLOT_MASK = (1 << _SLOT_BITS) - 1
_NAN = float("nan")
_U64 = (1 << 64) - 1


class _Grid:
    """`rust/src/grid.rs`'s `Grid`: the same buckets, hash and visit order."""

    def __init__(self, xs: list[float], ys: list[float], cell_size: float) -> None:
        self.cell_size = cell_size
        buckets = max(16, 1 << max(0, (len(xs) * 2 - 1).bit_length()))
        self.mask = buckets - 1
        self.items: list[list[int]] = [[] for _ in range(buckets)]
        for slot, (x, y) in enumerate(zip(xs, ys, strict=True)):
            self.items[self._bucket(self._cell(x), self._cell(y))].append(slot)

    def _cell(self, value: float) -> int:
        # Rust's `as i64` saturates, and sends NaN, a free slot, to 0.
        return 0 if value != value else math.floor(value / self.cell_size)

    def _bucket(self, cx: int, cy: int) -> int:
        hashed = ((cx & _U64) * 0x9E3779B97F4A7C15 & _U64) ^ (
            (cy & _U64) * 0xC2B2AE3D27D4EB4F & _U64
        )
        return (hashed ^ (hashed >> 29)) & self.mask

    def neighbours(
        self, x: float, y: float, radius: float, xs: list[float], ys: list[float]
    ) -> list[int]:
        """Slots within `radius` of `(x, y)`, in the grid's order."""
        found: list[int] = []
        visited: set[int] = set()
        radius_sq = radius * radius
        for cx in range(self._cell(x - radius), self._cell(x + radius) + 1):
            for cy in range(self._cell(y - radius), self._cell(y + radius) + 1):
                bucket = self._bucket(cx, cy)
                if bucket in visited:
                    continue
                visited.add(bucket)
                for slot in self.items[bucket]:
                    offset_x = xs[slot] - x
                    offset_y = ys[slot] - y
                    if offset_x * offset_x + offset_y * offset_y <= radius_sq:
                        found.append(slot)
        return found


def _scaled_to(x: float, y: float, length: float, target: float) -> tuple[float, float]:
    if length != 0.0:
        return (x / length) * target, (y / length) * target
    return 0.0, 0.0


class ReferenceSwarm:
    """`Swarm`'s API and arithmetic, in Python."""

    def __init__(self, cell_size: float = 64.0) -> None:
        """Create an empty swarm."""
        self.cell_size = cell_size
        self._kinds: list[tuple[float, ...]] = []
        self.x: list[float] = []
        self.y: list[float] = []
        self.vx: list[float] = []
        self.vy: list[float] = []
        self.kind: list[int] = []
        self.alive: list[bool] = []
        self.generation: list[int] = []
        self.seek: list[tuple[float, float] | None] = []
        self.free: list[int] = []
        self.counts: list[int] = []

    @property
    def count(self) -> int:
        """How many agents are alive."""
        return sum(self.alive)

    def _id(self, slot: int) -> int:
        return (self.generation[slot] << _SLOT_BITS) | slot

    def _resolve(self, agent: int) -> int:
        slot = agent & _SLOT_MASK
        if (
            slot < len(self.alive)
            and self.alive[slot]
            and self.generation[slot] == agent >> _SLOT_BITS
        ):
            return slot
        raise KeyError(agent)

    def add_kind(self, kind: SwarmKind) -> int:
        """Register a kind."""
        self._kinds.append(astuple(kind))
        return len(self._kinds) - 1

    def spawn(
        self,
        kind: int,
        positions: Sequence[Vector2],
        velocities: Sequence[Vector2] | None = None,
    ) -> list[int]:
        """Add agents, reusing the last-freed slot first."""
        ids = []
        for index, position in enumerate(positions):
            velocity = velocities[index] if velocities is not None else Vector2(0, 0)
            if self.free:
                slot = self.free.pop()
            else:
                for column in (self.x, self.y, self.vx, self.vy):
                    column.append(0.0)
                self.kind.append(0)
                self.alive.append(False)
                self.generation.append(0)
                self.seek.append(None)
                slot = len(self.alive) - 1
            self.x[slot], self.y[slot] = position.x, position.y
            self.vx[slot], self.vy[slot] = velocity.x, velocity.y
            self.kind[slot] = kind
            self.alive[slot] = True
            self.seek[slot] = None
            ids.append(self._id(slot))
        return ids

    def kill(self, ids: Iterable[int]) -> None:
        """Remove agents."""
        for slot in [self._resolve(agent) for agent in ids]:
            self.alive[slot] = False
            self.generation[slot] = (self.generation[slot] + 1) & 0xFFFFFFFF
            self.x[slot] = self.y[slot] = _NAN
            self.free.append(slot)

    def ids(self) -> list[int]:
        """Every live agent's id, in slot order."""
        return [self._id(slot) for slot, alive in enumerate(self.alive) if alive]

    def set_kind_seek(self, kind: int, target: Vector2 | None) -> None:
        """Point every live agent of a kind at a target."""
        for slot, alive in enumerate(self.alive):
            if alive and self.kind[slot] == kind:
                self.seek[slot] = None if target is None else (target.x, target.y)

    def set_seek(self, ids: Sequence[int], targets: Sequence[Vector2]) -> None:
        """Point each agent at its own target."""
        for agent, target in zip(ids, targets, strict=True):
            self.seek[self._resolve(agent)] = (target.x, target.y)

    def query_radius(self, centre: Vector2, radius: float) -> list[int]:
        """Ids within `radius` of `centre`, sorted."""
        radius_sq = radius * radius
        found = []
        for slot, alive in enumerate(self.alive):
            offset_x = self.x[slot] - centre.x
            offset_y = self.y[slot] - centre.y
            if alive and offset_x * offset_x + offset_y * offset_y <= radius_sq:
                found.append(self._id(slot))
        return sorted(found)

    def update(self, dt: float) -> None:  # noqa: C901, PLR0912, PLR0915 - one transcription
        """Steer and move every agent from the tick's starting state."""
        snap_x, snap_y = list(self.x), list(self.y)
        snap_vx, snap_vy = list(self.vx), list(self.vy)
        live = [slot for slot, alive in enumerate(self.alive) if alive]
        grid = _Grid(snap_x, snap_y, self.cell_size)
        self.counts = [0] * len(self.alive)
        for slot in live:
            (
                max_speed,
                max_force,
                mass,
                neighbor_radius,
                separation_radius,
                cohesion_weight,
                alignment_weight,
                separation_weight,
                seek_weight,
            ) = self._kinds[self.kind[slot]]
            x, y = snap_x[slot], snap_y[slot]
            separation_radius_sq = separation_radius * separation_radius
            count = 0
            sum_x = sum_y = sum_vx = sum_vy = push_x = push_y = 0.0
            for other in grid.neighbours(x, y, neighbor_radius, snap_x, snap_y):
                if other == slot:
                    continue
                count += 1
                neighbor_x, neighbor_y = snap_x[other], snap_y[other]
                if cohesion_weight != 0.0:
                    sum_x += neighbor_x
                    sum_y += neighbor_y
                if alignment_weight != 0.0:
                    sum_vx += snap_vx[other]
                    sum_vy += snap_vy[other]
                if separation_weight == 0.0:
                    continue
                offset_x = x - neighbor_x
                offset_y = y - neighbor_y
                distance_sq = offset_x * offset_x + offset_y * offset_y
                if distance_sq >= separation_radius_sq:
                    continue
                if distance_sq < 1e-06:
                    push_x += max_speed
                    continue
                distance = math.sqrt(distance_sq)
                scale = (1.0 - distance / separation_radius) * max_speed / distance
                push_x += offset_x * scale
                push_y += offset_y * scale

            self.counts[slot] = count
            velocity_x, velocity_y = snap_vx[slot], snap_vy[slot]
            force_x = force_y = 0.0
            if count:
                inverse_count = 1.0 / count
                if cohesion_weight != 0.0:
                    direction_x = sum_x * inverse_count - x
                    direction_y = sum_y * inverse_count - y
                    direction_sq = direction_x * direction_x + direction_y * direction_y
                    if direction_sq >= 1e-06:
                        scale = max_speed / math.sqrt(direction_sq)
                        force_x += (direction_x * scale - velocity_x) * cohesion_weight
                        force_y += (direction_y * scale - velocity_y) * cohesion_weight
                if alignment_weight != 0.0:
                    average_x = sum_vx * inverse_count
                    average_y = sum_vy * inverse_count
                    average_sq = average_x * average_x + average_y * average_y
                    if average_sq > max_speed * max_speed:
                        scale = max_speed / math.sqrt(average_sq)
                        average_x *= scale
                        average_y *= scale
                    force_x += (average_x - velocity_x) * alignment_weight
                    force_y += (average_y - velocity_y) * alignment_weight
                if separation_weight != 0.0:
                    push_sq = push_x * push_x + push_y * push_y
                    if push_sq > max_speed * max_speed:
                        scale = max_speed / math.sqrt(push_sq)
                        push_x *= scale
                        push_y *= scale
                    force_x += push_x * separation_weight
                    force_y += push_y * separation_weight

            target = self.seek[slot]
            if seek_weight != 0.0 and target is not None:
                direction_x = target[0] - x
                direction_y = target[1] - y
                length = math.sqrt(
                    direction_x * direction_x + direction_y * direction_y
                )
                if length >= 0.001:
                    desired_x, desired_y = _scaled_to(
                        direction_x, direction_y, length, max_speed
                    )
                    force_x += (desired_x - velocity_x) * seek_weight
                    force_y += (desired_y - velocity_y) * seek_weight

            force_length = math.sqrt(force_x * force_x + force_y * force_y)
            if force_length > max_force:
                force_x, force_y = _scaled_to(force_x, force_y, force_length, max_force)
            inverse_mass = 1.0 / mass
            new_vx = velocity_x + force_x * inverse_mass * dt
            new_vy = velocity_y + force_y * inverse_mass * dt
            speed = math.sqrt(new_vx * new_vx + new_vy * new_vy)
            if speed > max_speed:
                new_vx, new_vy = _scaled_to(new_vx, new_vy, speed, max_speed)
            self.vx[slot], self.vy[slot] = new_vx, new_vy
            self.x[slot] = x + new_vx * dt
            self.y[slot] = y + new_vy * dt

    def state(self) -> list[tuple[int, float, float, float, float]]:
        """`(id, x, y, vx, vy)` per live agent, in slot order."""
        return [
            (self._id(slot), self.x[slot], self.y[slot], self.vx[slot], self.vy[slot])
            for slot, alive in enumerate(self.alive)
            if alive
        ]

    def neighbour_counts(self) -> list[int]:
        """Flockmates per live agent last tick, in `ids()` order."""
        return [self.counts[slot] for slot, alive in enumerate(self.alive) if alive]
