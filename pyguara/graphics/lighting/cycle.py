"""Ambient light driven around a loop of keyframes -- a day/night cycle.

**Core, not a kit.** "Dawn", "dusk", "the long night" are a game's
vocabulary, and a 24-hour clock is a world model; neither belongs in the
engine. What does is the mechanism underneath both: interpolate an
`AmbientLight` along a ring of keyframes by a normalised phase. A kit
whose entire content would be four named colour constants is not a kit.

The cycle is opt-in per entity and requires `AmbientLight` beside it, so
`LightingSystem` needs no changes at all -- it already re-reads
`AmbientLight` from the ECS every tick -- and a scene with no cycle
behaves exactly as it did before this existed.

`sample_cycle()` is a free function over plain data, mirroring the
`StatBlock`/`get_stat` and `Health`/`apply_damage` split the repo already
uses. A game that wants its fog, its particles or its UI tinted by the
same phase calls it directly, rather than reaching into a system.

**Ownership:** a cycle owns the `AmbientLight` on its entity outright,
overwriting colour and intensity every tick it plays. A transient flash --
lightning, an explosion lighting the sky -- is therefore either a
`LightSource` (arguably what lightning is) or a `playing = False` for its
duration, not a second writer racing the cycle for the same field.
"""

from __future__ import annotations

import bisect
from dataclasses import dataclass, field

from pyguara.common.types import Color
from pyguara.ecs.component import StrictComponent
from pyguara.ecs.manager import EntityManager
from pyguara.graphics.lighting.components import AmbientLight


@dataclass(frozen=True)
class LightKeyframe:
    """One point on the cycle: what the ambient light is at a given phase.

    Attributes:
        phase: Where on the loop this keyframe sits, 0.0 to 1.0. The loop
            wraps, so the last keyframe interpolates back round to the
            first through 1.0/0.0 -- there is no need for a keyframe at
            both ends.
        color: The ambient colour at this point.
        intensity: The ambient brightness at this point.
    """

    phase: float
    color: Color
    intensity: float


@dataclass(slots=True)
class AmbientCycle(StrictComponent):
    """Pure data: a loop of keyframes and where in it this entity is.

    Goes on the same entity as the `AmbientLight` it drives.

    Attributes:
        keyframes: The points to interpolate between. Need not be sorted;
            `sample_cycle()` sorts a copy. An empty list samples nothing
            and the system leaves the light alone.
        duration: Real seconds for one full loop. A game's "day length".
        phase: Current position in the loop, 0.0 to 1.0.
        playing: Whether the system advances and writes. Set False to hand
            the `AmbientLight` back to whatever else wants to write it.
    """

    keyframes: list[LightKeyframe] = field(default_factory=list)
    duration: float = 60.0
    phase: float = 0.0
    playing: bool = True

    def __post_init__(self) -> None:
        """Initialise the StrictComponent state the dataclass __init__ skips.

        Calls the base explicitly rather than via `super()`: with
        `slots=True` the decorator returns a *new* class, and a
        zero-argument `super()` still resolves against the discarded
        original, raising TypeError on every instantiation.
        """
        StrictComponent.__init__(self)


def sample_cycle(
    keyframes: list[LightKeyframe], phase: float
) -> tuple[Color, float] | None:
    """Interpolate the keyframes at `phase`, wrapping round the loop.

    Args:
        keyframes: The points to interpolate between, in any order.
        phase: Where to sample. Wrapped into 0.0-1.0, so 1.25 and -0.75
            both sample 0.25 -- a caller advancing a phase never has to
            normalise it first.

    Returns:
        The `(color, intensity)` at that phase, or None if there are no
        keyframes to sample.
    """
    if not keyframes:
        return None

    ordered = sorted(keyframes, key=lambda k: k.phase)
    if len(ordered) == 1:
        only = ordered[0]
        return only.color, only.intensity

    phase %= 1.0

    # The segment containing `phase` is the one starting at the last
    # keyframe at or before it. Before the first keyframe (and after the
    # last) that segment is the wrap: last -> first, across 1.0/0.0.
    index = bisect.bisect_right([k.phase for k in ordered], phase) - 1
    start = ordered[index]  # ordered[-1] when phase precedes every keyframe
    end = ordered[(index + 1) % len(ordered)]

    span = (end.phase - start.phase) % 1.0
    if span == 0.0:
        # Every keyframe sits at the same phase; there is no segment to
        # walk along, so the one we landed on is the answer.
        return start.color, start.intensity

    t = ((phase - start.phase) % 1.0) / span
    return start.color.lerp(end.color, t), start.intensity + (
        end.intensity - start.intensity
    ) * t


class AmbientCycleSystem:
    """Advances each `AmbientCycle` and writes what it samples.

    Requires `AmbientCycle` and `AmbientLight` on the same entity; an
    entity carrying only one of the two is not a cycle and is skipped by
    the query.
    """

    def __init__(self, entity_manager: EntityManager) -> None:
        """Store the entity source.

        Args:
            entity_manager: Source of cycling entities.
        """
        self._entity_manager = entity_manager

    def update(self, dt: float) -> None:
        """Advance every playing cycle by `dt` and write its ambient light.

        A non-positive `duration` would divide by zero or run the loop
        backwards, so it holds the phase instead -- the light still gets
        written, which keeps `duration = 0` meaning "frozen at this phase"
        rather than "silently stops driving the light".
        """
        for entity in self._entity_manager.get_entities_with(
            AmbientCycle, AmbientLight
        ):
            cycle = entity.get_component(AmbientCycle)
            if not cycle.playing:
                continue

            if cycle.duration > 0.0:
                cycle.phase = (cycle.phase + dt / cycle.duration) % 1.0

            sampled = sample_cycle(cycle.keyframes, cycle.phase)
            if sampled is None:
                continue

            color, intensity = sampled
            ambient = entity.get_component(AmbientLight)
            ambient.color = color
            ambient.intensity = intensity
