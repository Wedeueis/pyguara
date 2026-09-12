"""Echolocation: emitting a pulse, and remembering what it lit.

Genre-specific to "sound reveals the world" games -- a bat, a submarine's
sonar, a blind protagonist -- but not to any one of them: nothing here
names a cave or a jaguarundi. Two halves:

- `PulseEmitter`/`ActivePulse`: the wavefront's own life cycle, expressed
  as radius and intensity over time.
- `RevealMemory`: what the wavefront has touched and how brightly that is
  still remembered, which is what makes the world fade back to black
  instead of staying revealed forever.

The raycast fan (`sweep`) takes a callable rather than an `IPhysicsEngine`
so the kit stays independent of the physics backend -- and so it can be
tested against a fake without a physics world at all.
"""

from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass, field

from pyguara.common.types import Vector2
from pyguara.ecs.component import StrictComponent

# A ray that hits nothing still reveals the empty air it crossed, so the
# sweep reports the full length rather than dropping the sample.
RayCaster = Callable[[Vector2, Vector2], "tuple[Vector2, str | None] | None"]


@dataclass(slots=True)
class PulseEmitter(StrictComponent):
    """Tuning for one creature's two calls.

    Attributes:
        chirp_radius: How far a short chirp reaches.
        chirp_duration: Seconds a chirp takes to travel that far.
        scream_radius: How far a resonant scream reaches.
        scream_duration: Seconds a scream takes to travel that far.
        ray_count: Rays per pulse. Higher is a finer reveal and a linear
            cost; this is the knob that trades fidelity for frame time.
        cooldown: Seconds between calls.
        cooldown_remaining: Counts down; a call is refused above zero.
    """

    chirp_radius: float = 320.0
    chirp_duration: float = 0.55
    scream_radius: float = 660.0
    scream_duration: float = 1.15
    ray_count: int = 128
    cooldown: float = 0.32
    cooldown_remaining: float = 0.0

    @property
    def is_ready(self) -> bool:
        """Whether another pulse may be emitted."""
        return self.cooldown_remaining <= 0.0

    def __post_init__(self) -> None:
        """Initialise the StrictComponent state the dataclass __init__ skips."""
        StrictComponent.__init__(self)


@dataclass(slots=True)
class ActivePulse:
    """One wavefront in flight."""

    origin: Vector2
    max_radius: float
    duration: float
    elapsed: float = 0.0
    is_scream: bool = False

    @property
    def progress(self) -> float:
        """How far through its life this pulse is, 0..1."""
        if self.duration <= 0.0:
            return 1.0
        return min(1.0, self.elapsed / self.duration)

    @property
    def radius(self) -> float:
        """Current wavefront radius.

        Eased so the front leaves fast and slows as it spends itself,
        which is both how a real wavefront looks and what makes the
        reveal readable -- a linear ramp reads as a mechanical circle.
        """
        t = self.progress
        return self.max_radius * (1.0 - (1.0 - t) * (1.0 - t))

    @property
    def intensity(self) -> float:
        """Current brightness, fading to nothing as it expands."""
        return max(0.0, 1.0 - self.progress)

    @property
    def is_spent(self) -> bool:
        """Whether this pulse has finished."""
        return self.elapsed >= self.duration


def start_pulse(emitter: PulseEmitter, origin: Vector2, *, scream: bool) -> ActivePulse:
    """Begin a pulse and put the emitter on cooldown."""
    emitter.cooldown_remaining = emitter.cooldown
    return ActivePulse(
        origin=origin,
        max_radius=emitter.scream_radius if scream else emitter.chirp_radius,
        duration=emitter.scream_duration if scream else emitter.chirp_duration,
        is_scream=scream,
    )


def tick_cooldown(emitter: PulseEmitter, dt: float) -> None:
    """Advance the emitter's cooldown."""
    emitter.cooldown_remaining = max(0.0, emitter.cooldown_remaining - dt)


@dataclass(slots=True)
class RayHit:
    """Where one ray of a sweep stopped, and on what."""

    point: Vector2
    entity_id: str | None
    distance: float


def sweep(
    raycast: RayCaster,
    origin: Vector2,
    radius: float,
    ray_count: int,
    *,
    start_angle: float = 0.0,
) -> list[RayHit]:
    """Cast `ray_count` rays evenly around `origin` out to `radius`.

    This is what makes the reveal obey the cave's shape: a ray stops at
    the first surface, so rock casts an acoustic shadow and nothing behind
    it is lit. Without it a pulse would light through walls.

    Args:
        raycast: Called as `(start, end)`; returns `(point, entity_id)` for
            a hit or `None` for a clear ray.
        origin: Where the pulse was emitted.
        radius: How far the wavefront has travelled.
        ray_count: How many rays to cast.
        start_angle: Rotates the whole fan, so consecutive pulses can be
            offset and avoid sampling the same angles every time.

    Returns:
        One `RayHit` per ray, in order. A ray that hit nothing reports the
        point at full `radius` with `entity_id` None.
    """
    hits: list[RayHit] = []
    if ray_count <= 0 or radius <= 0.0:
        return hits

    for i in range(ray_count):
        angle = start_angle + (2.0 * math.pi * i / ray_count)
        direction = Vector2(math.cos(angle), math.sin(angle))
        end = origin + direction * radius

        result = raycast(origin, end)
        if result is None:
            hits.append(RayHit(point=end, entity_id=None, distance=radius))
            continue
        point, entity_id = result
        hits.append(
            RayHit(point=point, entity_id=entity_id, distance=(point - origin).length)
        )

    return hits


@dataclass
class RevealMemory:
    """How brightly each key is still remembered, and by what.

    Keyed by whatever the game wants to reveal -- a tile coordinate, an
    entity id. Brightness decays toward zero, so the cave sinks back into
    darkness at a controlled rate instead of staying lit.
    """

    decay_per_second: float = 0.52
    floor: float = 0.0
    _brightness: dict[object, float] = field(default_factory=dict)

    def reveal(self, key: object, brightness: float = 1.0) -> None:
        """Light `key` up, keeping the brighter of old and new."""
        current = self._brightness.get(key, 0.0)
        self._brightness[key] = max(current, brightness)

    def brightness(self, key: object) -> float:
        """How brightly `key` is currently remembered, 0 if not at all."""
        return self._brightness.get(key, self.floor)

    def decay(self, dt: float) -> None:
        """Fade every memory, dropping the ones that have gone dark.

        Dropping rather than keeping a zero means the dict tracks what is
        *currently* visible, so iterating it to draw costs nothing for a
        cave the player explored ten minutes ago.
        """
        if not self._brightness:
            return
        faded = self.decay_per_second * dt
        for key in list(self._brightness):
            value = self._brightness[key] - faded
            if value <= self.floor:
                del self._brightness[key]
            else:
                self._brightness[key] = value

    def dim(self, factor: float, ceiling: float | None = None) -> None:
        """Scale every memory by `factor`, optionally capping each first.

        For the moment a game needs to take the world back from the player
        without erasing it outright -- a disorienting hit, a light going
        out -- where clearing would be too harsh and waiting for decay too
        slow.

        Args:
            factor: Multiplier applied to every remembered brightness.
            ceiling: If given, each value is capped to this before scaling,
                so a freshly-lit surface loses as much as a stale one
                rather than shrugging the hit off.
        """
        for key in list(self._brightness):
            value = self._brightness[key]
            if ceiling is not None:
                value = min(value, ceiling)
            value *= factor
            if value <= self.floor:
                del self._brightness[key]
            else:
                self._brightness[key] = value

    def items(self) -> list[tuple[object, float]]:
        """Every remembered key and its brightness."""
        return list(self._brightness.items())

    def clear(self) -> None:
        """Forget everything."""
        self._brightness.clear()
