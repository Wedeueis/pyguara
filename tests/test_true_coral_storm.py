"""Tests for True Coral's weather director.

`StormDirector` is the one piece of the demo's visual layer that is pure
logic: no GL context, no renderer, just a schedule. That is deliberate --
three separate consumers read it on the same frame (the storm shader, the
scene's ambient light, the screen shake), and they only stay in sync
because one object decides when a strike happens.
"""

from games.true_coral.storm import (
    CALM_RAIN,
    RAIN_RAMP,
    STORM_RAIN,
    StormDirector,
)
from pyguara.common.random import RandomStream


def make_director(seed: int = 11) -> StormDirector:
    """A director with a seeded stream, so a run is reproducible."""
    return StormDirector(RandomStream(seed))


def run_for(director: StormDirector, seconds: float, step: float = 1 / 60) -> None:
    """Advance the director by `seconds`, one frame at a time."""
    for _ in range(int(seconds / step)):
        director.update(step)


class TestRain:
    def test_it_starts_drizzling(self) -> None:
        assert make_director().rain == CALM_RAIN

    def test_the_downpour_ramps_rather_than_snapping_on(self) -> None:
        director = make_director()
        director.set_storming(True)
        director.update(RAIN_RAMP / 4)

        assert CALM_RAIN < director.rain < STORM_RAIN

    def test_the_downpour_arrives(self) -> None:
        director = make_director()
        director.set_storming(True)
        run_for(director, RAIN_RAMP + 0.5)

        assert director.rain == STORM_RAIN

    def test_it_eases_back_to_a_drizzle(self) -> None:
        director = make_director()
        director.set_storming(True)
        run_for(director, RAIN_RAMP + 0.5)

        director.set_storming(False)
        run_for(director, RAIN_RAMP + 0.5)

        assert director.rain == CALM_RAIN

    def test_asking_for_the_state_it_is_in_changes_nothing(self) -> None:
        director = make_director()
        director.set_storming(False)

        assert not director.is_storming
        assert director.rain == CALM_RAIN


class TestStrikes:
    def test_a_storm_strikes_more_often_than_calm_weather(self) -> None:
        calm, storm = make_director(), make_director()
        storm.set_storming(True)

        calm_strikes = storm_strikes = 0
        for _ in range(60 * 30):  # thirty seconds
            calm.update(1 / 60)
            storm.update(1 / 60)
            calm_strikes += calm.strike_started
            storm_strikes += storm.strike_started

        assert storm_strikes > calm_strikes

    def test_a_strike_is_announced_for_exactly_one_frame(self) -> None:
        """The scene reshapes the bolt on this flag. Left true, every
        frame of one flash would draw a differently shaped bolt."""
        director = make_director()
        director.set_storming(True)

        announcements = 0
        frames_with_flash = 0
        for _ in range(60 * 10):
            director.update(1 / 60)
            announcements += director.strike_started
            frames_with_flash += director.flash > 0.0

        assert announcements > 0
        assert frames_with_flash > announcements

    def test_a_strike_flashes_and_then_stops(self) -> None:
        director = make_director()
        director.set_storming(True)

        while not director.strike_started:
            director.update(1 / 60)
        assert director.flash > 0.0

        for _ in range(120):  # two seconds is longer than any envelope
            director.update(1 / 60)
            if director.flash == 0.0:
                break
        else:
            raise AssertionError("the flash never finished")

    def test_the_flash_flickers_rather_than_fading_once(self) -> None:
        """A discharge is several return strokes. One smooth decay reads
        as a camera flash, so the envelope must go back up at least once."""
        director = make_director()
        director.set_storming(True)
        while not director.strike_started:
            director.update(1 / 60)

        levels = []
        for _ in range(90):
            levels.append(director.flash)
            director.update(1 / 60)

        rises = sum(
            1
            for before, after in zip(levels, levels[1:], strict=False)
            if after > before + 1e-6
        )
        assert rises >= 1

    def test_the_light_boost_tracks_the_flash(self) -> None:
        """The scene's ambient light and the shader's wash come from the
        same strike, or a bolt lights the frame on a different frame from
        the one it appears on."""
        director = make_director()
        director.set_storming(True)
        while not director.strike_started:
            director.update(1 / 60)

        assert director.light_boost > 0.0
        assert director.light_boost < director.flash


class TestShake:
    def test_shake_is_consumed_once(self) -> None:
        """A caller that misses a frame should not be handed a stale jolt
        later, so reading clears it."""
        director = make_director()
        director.set_storming(True)

        for _ in range(60 * 20):
            director.update(1 / 60)
            shake = director.take_shake()
            if shake > 0.0:
                assert director.take_shake() == 0.0
                return
        raise AssertionError("no close strike in twenty seconds of storm")

    def test_only_a_strike_close_enough_to_draw_a_bolt_shakes(self) -> None:
        """Distant strikes glow on the horizon; only overhead ones land.

        A shake with no bolt on screen is a jolt from nowhere, which is
        worse feedback than no jolt at all.
        """
        director = make_director()
        director.set_storming(True)
        shakes = 0

        for _ in range(60 * 60):
            director.update(1 / 60)
            if director.take_shake() > 0.0:
                shakes += 1
                assert director.bolt > 0.0

        assert shakes > 0
