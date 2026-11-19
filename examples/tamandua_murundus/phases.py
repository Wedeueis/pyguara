"""The run clock, the phase table, and what each phase asks of the night.

A run is one loop of the ambient cycle: dusk at phase 0, dawn at phase 1.
That is deliberate -- the *time of day is the run clock*, so there is one
number driving the light, the swarm's tint and the spawn rate, and no way
for them to drift apart.

**On the spawn schedule.** This is time-keyed: a phase says how many
insects a mound releases per feed, and the clock says which phase it is.
`kits/spawn`'s `SpawnDirector` was the obvious thing to reach for and was
deliberately not used -- its model was a release-rate *budget*, which
every consumer in this repository bypassed (`budget=0.0, cost=0.0`).
That finding was reported upward and the budget is now gone: the director
gates on a time-keyed schedule and an alive cap instead (#163).

This still does not use it, for a different and smaller reason: the phase
curve is continuous, not a queue of waves, and the *time of day is the run
clock* -- one number driving the light, the tint and the spawn rate. A
director would bring a second clock alongside it.
"""

from __future__ import annotations

from dataclasses import dataclass

from pyguara.common.types import Color
from pyguara.graphics.lighting.cycle import LightKeyframe

# One run, in seconds. Four minutes, not the GDD's original twelve: run
# length is a balance problem with no engine payoff, and a twelve-minute
# run cannot be iterated on through `agent_view` frame captures.
RUN_SECONDS = 240.0

# The clearing's light through one run. Phase 0 is dusk, where the run
# starts; the cycle wraps back to it at dawn, which is why there is no
# keyframe at 1.0 -- the last one interpolates round to the first.
#
# The intensities matter more than the colours: `glow_for_intensity()`
# below reads the swarm's bioluminescence straight off them, so these
# numbers are the tint curve as much as they are the light curve.
CYCLE_KEYFRAMES = [
    LightKeyframe(0.00, Color(158, 162, 196), 0.66),  # dusk
    LightKeyframe(0.33, Color(96, 104, 150), 0.40),  # nightfall
    LightKeyframe(0.62, Color(44, 52, 92), 0.17),  # night
    LightKeyframe(0.86, Color(30, 36, 74), 0.11),  # deep night
    LightKeyframe(0.95, Color(255, 186, 142), 0.58),  # dawn
]

# Where the run stops, just short of the wrap. A cycle is a *ring*: let it
# reach 1.0 and it is back at phase 0, which is dusk -- so a run allowed to
# tick past the end flashes from first light to nightfall and holds there.
# Stopping a hair early holds the clearing at dawn instead.
DAWN_HOLD_PHASE = 0.98

# The ambient intensities the swarm's glow is read between. Full
# bioluminescence at the darkest keyframe above, none at the brightest.
BRIGHTEST = 0.66
DARKEST = 0.11


@dataclass(frozen=True)
class Phase:
    """One named stretch of the run.

    Attributes:
        name: What the HUD calls it.
        starts_at: Cycle phase this stretch begins at, 0..1.
        release_per_feed: How many insects each mound releases per feed
            during it. This is the whole difficulty curve.
    """

    name: str
    starts_at: float
    release_per_feed: int


# Read in order; the last one whose `starts_at` has passed is current.
#
# These are aligned to the *light*, not spaced evenly, and the alignment
# is the whole point: the peak-density phase has to sit in the darkest
# stretch of the curve above, or the run's climax is announced while the
# clearing is already brightening toward dawn. An earlier table put
# REVOADA at 0.86 and did exactly that -- the HUD read REVOADA over a
# frame that looked like dusk.
PHASES = [
    Phase("ANOITECER", 0.00, 1),  # ambient 0.66 -> 0.40
    Phase("NOITE", 0.30, 2),  # 0.40 -> 0.20
    Phase("NOITE FECHADA", 0.55, 3),  # 0.20 -> 0.14
    Phase("REVOADA", 0.75, 4),  # the darkest stretch: 0.14 -> 0.11
    Phase("AMANHECER", 0.88, 0),  # first light, as the curve turns back up
]

# These multipliers, against `Murundu.feed_interval`, are set so that an
# *idle* player -- one who kills nothing -- sees the swarm reach
# `SWARM_CAP` during REVOADA and not before. An earlier pairing filled it
# by the halfway mark, which made the last two phases add no pressure at
# all: the difficulty curve went flat exactly where it was supposed to
# peak. A player who is actually eating holds the count below the cap,
# which is the game.


def phase_at(cycle_phase: float) -> Phase:
    """Return the phase covering `cycle_phase`.

    Args:
        cycle_phase: Where the run is, 0..1. Wrapped, so a caller passing
            an unnormalised clock still gets an answer.

    Returns:
        The current phase.
    """
    cycle_phase %= 1.0
    current = PHASES[0]
    for phase in PHASES:
        if cycle_phase >= phase.starts_at:
            current = phase
    return current


def glow_for_intensity(intensity: float) -> float:
    """How bioluminescent the swarm is under an ambient of `intensity`.

    The swarm lights up exactly as the clearing goes dark, because it is
    the *same* number read from the other end -- which is what makes the
    tint honestly "driven by the time-of-day curve" rather than a second
    curve that happens to run alongside it.

    Args:
        intensity: The ambient light's current intensity.

    Returns:
        0.0 at the cycle's brightest keyframe, 1.0 at its darkest.
    """
    span = BRIGHTEST - DARKEST
    if span <= 0.0:
        return 0.0
    return max(0.0, min(1.0, (BRIGHTEST - intensity) / span))
