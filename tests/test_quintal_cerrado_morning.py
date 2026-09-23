# ruff: noqa: F811  - pytest fixtures are imported by name from the growth suite
"""The morning report: the night's receipt.

A turn-based night resolves everything at once, so without this the player
wakes to a changed plot and no account of why.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

from games.quintal_cerrado.garden_widget import NIGHT_DARKNESS, SUNRISE_SECONDS
from games.quintal_cerrado.morning import MorningScene, report_lines
from games.quintal_cerrado.scenes import GardenScene
from games.quintal_cerrado.systems.day_resolver import DayReport
from pyguara.graphics.protocols import UIRenderer
from pyguara.scene.manager import SceneManager
from pyguara.ui.manager import UIManager
from pyguara.ui.types import UILayer
from tests.test_quintal_cerrado_growth import (  # noqa: F401
    _plant_at,
    _resolve,
    game_container,
    scene,
)


def _text(report: DayReport) -> str:
    return " | ".join(line.text for line in report_lines(report))


class TestWhatItSays:
    """Only what happened, so the card is worth reading."""

    def test_a_quiet_night_says_exactly_that(self) -> None:
        lines = report_lines(DayReport(day=2))

        assert len(lines) == 1
        assert "quiet" in lines[0].text.lower()

    def test_a_zero_is_left_out_rather_than_shown(self) -> None:
        """A report with the same shape every morning stops being read."""
        report = DayReport(day=2, solar_income=6)

        assert _text(report).count("|") == 0
        assert "6" in _text(report)

    def test_it_reports_what_grew_ripened_and_died(self) -> None:
        report = DayReport(
            day=3,
            stages_grown=["Guandu"],
            ripened=["Baru"],
            lost=["Cagaita"],
        )

        text = _text(report)
        assert "Guandu" in text and "Baru" in text and "Cagaita" in text

    def test_a_long_list_is_summarised(self) -> None:
        report = DayReport(day=3, ripened=["Guandu", "Baru", "Pequi", "Cagaita"])

        assert "and 2 more" in _text(report)

    def test_repeats_are_counted_not_repeated(self) -> None:
        """A night that grew four guandu says so once."""
        report = DayReport(day=3, stages_grown=["Guandu"] * 4)

        assert "4x Guandu" in _text(report)
        assert "Guandu, Guandu" not in _text(report)

    def test_an_outbreak_reads_as_bad_news(self) -> None:
        lines = report_lines(DayReport(day=4, outbreak_started=True))

        assert lines[0].color.r > 200 and lines[0].color.g < 150

    def test_a_resolution_names_how_it_was_answered(self) -> None:
        organic = _text(DayReport(day=4, outbreak_resolved="organic"))
        chemical = _text(DayReport(day=4, outbreak_resolved="chemical"))

        assert "slow" in organic
        assert "chemical" in chemical


class TestTheOverlay:
    """It opens on a night, and the plot wakes when it closes."""

    def _current(self, scene: GardenScene) -> Any:
        return scene.container.get(SceneManager).current_scene

    def test_sleeping_opens_the_report(self, scene: GardenScene) -> None:
        scene.end_day()

        assert isinstance(self._current(scene), MorningScene)
        assert self._current(scene).day == 2

    def test_the_plot_sleeps_dark_and_wakes_up(self, scene: GardenScene) -> None:
        assert scene._canvas is not None

        scene.end_day()
        assert scene._canvas.darkness == NIGHT_DARKNESS

        self._current(scene)._close()
        for _ in range(int(SUNRISE_SECONDS * 60) + 6):
            scene.update(1 / 60)

        assert scene._canvas.darkness == 0.0

    def test_the_garden_is_frozen_while_it_is_read(self, scene: GardenScene) -> None:
        scene.end_day()

        assert not scene.system_manager.enabled

    def test_it_draws_its_card(self, scene: GardenScene) -> None:
        _plant_at(scene, (2, 2), "guandu", stage="mature")
        scene.grid.water((2, 2))
        scene.end_day()
        report_scene = self._current(scene)
        renderer = MagicMock(spec=UIRenderer)
        renderer.get_text_size.return_value = (30, 12)

        ui = scene.container.get(UIManager)
        for element in ui.elements(UILayer.OVERLAY):
            element.render(renderer)

        assert renderer.draw_rect.called
        assert renderer.draw_text.called
        assert isinstance(report_scene, MorningScene)
