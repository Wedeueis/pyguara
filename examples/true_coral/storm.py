"""True Coral - the weather director.

The forest floor is never quite dry: a drizzle falls throughout, and it
turns torrential while the star's effect is running -- the same
"makes it rain" cue `StarEffect` has always announced, now with a sky
behind it.

This class decides *what the weather is doing*. Nothing here draws: it
produces numbers that three different consumers read on the same frame --
`StormEffect`'s uniforms (the rain and the bolt), the scene's ambient
light (a strike genuinely brightens the arena), and the camera shake (a
close strike lands with a thump). Keeping the schedule in one place is
what keeps those three in sync; when each owned its own timer they drifted
apart within seconds.

Strikes flicker rather than blink. A real discharge is several returns
down the same channel a few tens of milliseconds apart, and an envelope
with one peak reads as a camera flash instead of lightning.
"""

from __future__ import annotations

from dataclasses import dataclass

from pyguara.common.random import RandomStream

# Rain depth (0..1) in each weather state.
CALM_RAIN = 0.42
STORM_RAIN = 1.0

# Seconds to cross between them. Rain visibly picks up rather than
# snapping on, so the star's arrival has a moment of build.
RAIN_RAMP = 1.6

# Seconds between strikes, drawn uniformly from each range.
CALM_INTERVAL = (7.0, 16.0)
STORM_INTERVAL = (1.1, 3.0)

# A strike closer than this is overhead: it draws its bolt, shakes the
# arena and lifts the ambient light hard. Beyond it, the sky just glows.
NEAR_DISTANCE = 0.45


@dataclass(slots=True)
class _Blip:
    """One return stroke inside a single strike."""

    start: float  # seconds after the strike began
    duration: float
    peak: float  # 0..1 contribution to the sheet flash
    draws_bolt: bool


class StormDirector:
    """Schedules rain and lightning, and reports both as plain numbers."""

    def __init__(self, rng: RandomStream | None = None) -> None:
        """Start calm, with the first strike already scheduled.

        Args:
            rng: Random stream driving strike timing, placement and
                shape. Defaults to a fresh, unseeded stream; pass a
                seeded one to make a run reproducible.
        """
        self._rng = rng if rng is not None else RandomStream()
        self._storming = False

        self._rain = CALM_RAIN
        self._target_rain = CALM_RAIN

        self._blips: list[_Blip] = []
        self._strike_time = 0.0
        self._strike_distance = 1.0
        self._next_strike = self._rng.uniform(*CALM_INTERVAL)

        self._flash = 0.0
        self._bolt = 0.0
        self._bolt_x = 0.5
        self._shake = 0.0
        self._strike_started = False

    # ---- state in --------------------------------------------------

    @property
    def is_storming(self) -> bool:
        """Whether the downpour (rather than the drizzle) is running."""
        return self._storming

    def set_storming(self, storming: bool) -> None:
        """Switch between the drizzle and the downpour.

        The rain ramps toward the new state over `RAIN_RAMP`; strikes
        change cadence immediately, but only from the next one -- a
        strike already in flight finishes as it started.

        Args:
            storming: True for the downpour.
        """
        if storming == self._storming:
            return
        self._storming = storming
        self._target_rain = STORM_RAIN if storming else CALM_RAIN
        # Re-roll the wait so the cadence changes at once rather than
        # after one last strike on the old schedule.
        self._next_strike = min(self._next_strike, self._interval())

    def update(self, dt: float) -> None:
        """Advance the rain ramp, the strike clock, and any live strike.

        Args:
            dt: Seconds since the last frame.
        """
        self._rain = _approach(self._rain, self._target_rain, dt / RAIN_RAMP)

        self._strike_started = False
        self._next_strike -= dt
        if self._next_strike <= 0.0:
            self._begin_strike()

        self._advance_strike(dt)

    # ---- state out -------------------------------------------------

    @property
    def rain(self) -> float:
        """Downpour amount, 0..1, for `StormEffect.rain`."""
        return self._rain

    @property
    def flash(self) -> float:
        """Sheet-lightning brightness, 0..1, for `StormEffect.flash`."""
        return self._flash

    @property
    def bolt(self) -> float:
        """Bolt brightness, 0..1, for `StormEffect.bolt`."""
        return self._bolt

    @property
    def bolt_x(self) -> float:
        """Where the current bolt falls, 0..1 across the frame."""
        return self._bolt_x

    @property
    def light_boost(self) -> float:
        """Extra ambient intensity a strike adds to the scene's light map.

        Separate from `flash` because they do different jobs: the flash
        washes over the finished frame, while this reveals the arena --
        the leaf litter, the snake's bands -- for the instant the sky is
        lit. Scaled below `flash` so a distant strike glows without
        turning the floor into daylight.
        """
        return self._flash * 0.85

    @property
    def strike_started(self) -> bool:
        """Whether a new strike began on this frame.

        True for exactly one `update()`. The scene reads it to reshape
        the bolt (`StormEffect.strike()`), which must happen once per
        strike rather than once per frame.
        """
        return self._strike_started

    def take_shake(self) -> float:
        """Consume the pending shake magnitude in pixels, if any.

        Returns:
            The magnitude for a close strike, 0.0 otherwise. Reading it
            clears it, so a caller that forgets to read one frame does
            not get a delayed jolt on the next.
        """
        shake, self._shake = self._shake, 0.0
        return shake

    # ---- internals -------------------------------------------------

    def _interval(self) -> float:
        low, high = STORM_INTERVAL if self._storming else CALM_INTERVAL
        return self._rng.uniform(low, high)

    def _begin_strike(self) -> None:
        """Roll a fresh strike: how close, how it flickers, where it falls."""
        self._next_strike = self._interval()
        self._strike_time = 0.0
        self._strike_started = True

        # Storms crowd the strikes overhead; in calm weather most of them
        # are somewhere over the canopy, seen only as a glow.
        self._strike_distance = (
            self._rng.uniform(0.0, 0.7)
            if self._storming
            else self._rng.uniform(0.3, 1.0)
        )
        near = self._strike_distance < NEAR_DISTANCE
        brightness = 1.0 - self._strike_distance * 0.75

        self._bolt_x = self._rng.uniform(0.1, 0.9)
        self._blips = self._roll_blips(brightness, near)
        self._shake = 7.0 * brightness if near else 0.0

    def _roll_blips(self, brightness: float, near: bool) -> list[_Blip]:
        """Build one strike's return strokes, front-loaded and decaying."""
        blips = [_Blip(start=0.0, duration=0.09, peak=brightness, draws_bolt=near)]

        for _ in range(self._rng.randint(1, 3)):
            start = blips[-1].start + blips[-1].duration + self._rng.uniform(0.02, 0.09)
            decay = self._rng.uniform(0.35, 0.8)
            blips.append(
                _Blip(
                    start=start,
                    duration=self._rng.uniform(0.05, 0.12),
                    peak=brightness * decay,
                    # A return stroke re-lights the same channel, so the
                    # bolt reappears with it rather than only on the first.
                    draws_bolt=near and decay > 0.5,
                )
            )

        # The afterglow: the cloud keeps carrying light for a beat after
        # the channel has gone. Without it a strike ends abruptly.
        blips.append(
            _Blip(
                start=blips[-1].start + blips[-1].duration,
                duration=self._rng.uniform(0.25, 0.5),
                peak=brightness * 0.22,
                draws_bolt=False,
            )
        )
        return blips

    def _advance_strike(self, dt: float) -> None:
        """Evaluate the live strike's envelope into `flash` and `bolt`."""
        if not self._blips:
            self._flash = 0.0
            self._bolt = 0.0
            return

        self._strike_time += dt
        flash = 0.0
        bolt = 0.0

        for blip in self._blips:
            local = self._strike_time - blip.start
            if local < 0.0 or local > blip.duration:
                continue
            # Instant attack, quadratic release -- the shape of a
            # discharge, and the reason a linear fade looks like a lamp.
            level = blip.peak * (1.0 - local / blip.duration) ** 2
            flash = max(flash, level)
            if blip.draws_bolt:
                bolt = max(bolt, level)

        self._flash = flash
        self._bolt = bolt

        last = self._blips[-1]
        if self._strike_time > last.start + last.duration:
            self._blips = []


def _approach(value: float, target: float, step: float) -> float:
    """Move `value` toward `target` by at most `step`, without overshooting."""
    if value < target:
        return min(target, value + step)
    return max(target, value - step)
