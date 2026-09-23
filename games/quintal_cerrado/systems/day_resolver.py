"""A night: everything the garden does while the player is asleep.

In the real-time build these systems ran every fixed tick, so the plot
changed under the cursor while the player was reading it. They are not
registered with the `SystemManager` any more (`scenes.GardenScene` drops the
engine's `AISystem` too); this resolver owns them and runs them once, in the
same order their old priorities gave them: soil, automation, shade,
syntropic, pest, growth, weeds -- then the weather turns for tomorrow.

Every constant these systems own is now expressed **per day** -- a species
grows in `stage_days`, soil loses `EVAPORATION_RATE` a day, a panel pays
`SOLAR_YIELD` a night. The old per-second numbers are gone, and with them
the fiction that a day was worth some number of simulated seconds.

Three systems act **once** a night, because what they do is an event and
not an accumulation: automation (solar pays, drip fills, the drone
collects), weeds (one spread roll each), and the weather (tomorrow's sky).

The rest are still stepped `SUB_STEPS` times across the night, for two
reasons. `PestSystem` integrates a coupled non-linear system -- spread is
proportional to current pressure, health drain is the product of two
quantities that move together -- so one whole-day step overshoots badly.
And the plant FSMs have to be driven between steps: `StateMachine.update`
applies at most one transition per call and each `on_enter` resets
`growth_progress`, so a night's growth applied in one lump would be thrown
away above the first stage boundary.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from games.quintal_cerrado.components import GardenConditions, PlantComponent
from games.quintal_cerrado.events import (
    OutbreakResolvedEvent,
    OutbreakStartedEvent,
    PlantHarvestedEvent,
    SolarIncomeEvent,
)
from games.quintal_cerrado.garden_grid import GardenGrid
from games.quintal_cerrado.species import SPECIES_TABLE
from games.quintal_cerrado.systems.automation_system import AutomationSystem
from games.quintal_cerrado.systems.pest_system import PestSystem
from games.quintal_cerrado.systems.plant_growth_system import PlantGrowthSystem
from games.quintal_cerrado.systems.shade_system import ShadeSystem
from games.quintal_cerrado.systems.soil_system import SoilSystem
from games.quintal_cerrado.systems.syntropic_system import SyntropicSystem
from games.quintal_cerrado.systems.weather_system import WeatherSystem
from games.quintal_cerrado.systems.weed_spread_system import WeedSpreadSystem
from pyguara.ai.components import AIComponent
from pyguara.ecs.entity import Entity
from pyguara.ecs.manager import EntityManager
from pyguara.events.dispatcher import EventDispatcher

SUB_STEPS = 4
"""How many steps a night's continuous systems are advanced in. Four is
enough that a plant crosses at most one stage boundary per step at any
realistic multiplier, which is what keeps the FSM from discarding growth,
and that the pest integration stays well-behaved."""

SUB_STEP = 1.0 / SUB_STEPS
"""One step, in days."""

ONE_DAY = 1.0
"""What a night advances the garden-conditions FSM by (`garden_states.py`)."""


@dataclass
class DayReport:
    """What happened overnight, for the morning to show.

    Attributes:
        day: The day that just ended.
        weather_id: The condition that was in force during the night.
        next_weather_id: What tomorrow brings.
        stages_grown: Species display names that reached a new stage.
        ripened: Species display names that became harvestable.
        lost: Species display names that died overnight.
        weeds_sprouted: New weeds that took hold.
        solar_income: Sementes the panels paid.
        drone_harvests: Plants the drone collected.
        outbreak_started: Whether pests broke out tonight.
        outbreak_resolved: `"organic"`, `"chemical"` or `""`.
        pest_peak: The worst pest pressure left on the plot.
    """

    day: int
    weather_id: str = ""
    next_weather_id: str = ""
    stages_grown: list[str] = field(default_factory=list)
    ripened: list[str] = field(default_factory=list)
    lost: list[str] = field(default_factory=list)
    weeds_sprouted: int = 0
    solar_income: int = 0
    drone_harvests: int = 0
    outbreak_started: bool = False
    outbreak_resolved: str = ""
    pest_peak: float = 0.0

    @property
    def quiet(self) -> bool:
        """Whether nothing worth reporting happened."""
        return not (
            self.stages_grown
            or self.ripened
            or self.lost
            or self.weeds_sprouted
            or self.solar_income
            or self.drone_harvests
            or self.outbreak_started
            or self.outbreak_resolved
        )


class DayResolver:
    """Owns the simulation systems and runs a night with them."""

    def __init__(
        self,
        entity_manager: EntityManager,
        grid: GardenGrid,
        conditions: GardenConditions,
        event_dispatcher: EventDispatcher,
        soil: SoilSystem,
        automation: AutomationSystem,
        shade: ShadeSystem,
        syntropic: SyntropicSystem,
        pest: PestSystem,
        growth: PlantGrowthSystem,
        weeds: WeedSpreadSystem,
        weather: WeatherSystem,
    ) -> None:
        """Bind the resolver to the plot and the systems that change it.

        Args:
            entity_manager: Where plants and the conditions entity live.
            grid: The plot.
            conditions: The garden's pest situation.
            event_dispatcher: Where the systems announce solar income and
                drone harvests, which this listens to for the report.
            soil: Moisture.
            automation: Solar, drip and the drone.
            shade: Canopy cover.
            syntropic: The companion bonus, which reads shade.
            pest: Spread, decay and the health it costs.
            growth: Stage progress.
            weeds: Propagation.
            weather: Tomorrow's condition.
        """
        self.entity_manager = entity_manager
        self.grid = grid
        self.conditions = conditions
        self.soil = soil
        self.automation = automation
        self.shade = shade
        self.syntropic = syntropic
        self.pest = pest
        self.growth = growth
        self.weeds = weeds
        self.weather = weather

        self._solar_income = 0
        self._drone_harvests = 0
        self._outbreak_started = False
        self._outbreak_resolved = ""
        event_dispatcher.subscribe(SolarIncomeEvent, self._on_solar_income)
        event_dispatcher.subscribe(PlantHarvestedEvent, self._on_drone_harvest)
        event_dispatcher.subscribe(OutbreakStartedEvent, self._on_outbreak_started)
        event_dispatcher.subscribe(OutbreakResolvedEvent, self._on_outbreak_resolved)

    def resolve(self, day: int) -> DayReport:
        """Run one night and report what it did.

        Args:
            day: The day that is ending, for the report.

        Returns:
            What changed, for the morning to show.
        """
        self._solar_income = 0
        self._drone_harvests = 0
        self._outbreak_started = False
        self._outbreak_resolved = ""
        before = self._snapshot()
        weather_id = self.weather.state.condition_id

        # The machines first: a panel pays, the drip fills its cells and the
        # drone collects, all before the night's own weather and growth run
        # against the soil they just changed.
        self.automation.resolve_night()

        for _ in range(SUB_STEPS):
            self.soil.update(SUB_STEP)
            self.shade.update(SUB_STEP)
            self.syntropic.update(SUB_STEP)
            self.pest.update(SUB_STEP)
            self.growth.update(SUB_STEP)
            self._drive_plants(SUB_STEP)
            self.entity_manager.flush_pending_removals()

        # After growth, so a plant that matured tonight can seed tonight.
        self.weeds.resolve_night()
        self.entity_manager.flush_pending_removals()

        # What was overhead tonight is the sky the player saw forecast
        # yesterday; this rolls tomorrow's.
        self._drive_conditions(ONE_DAY)
        self.weather.advance_day()

        return self._report(day, weather_id, before)

    def _snapshot(self) -> dict[str, tuple[str, str]]:
        """Every plant's `(species_id, stage)` right now, by entity id."""
        snapshot = {}
        for entity_id in self.grid.plant_at.values():
            plant = self._plant(entity_id)
            if plant is not None:
                snapshot[entity_id] = (plant.species_id, plant.growth_stage)
        return snapshot

    def _plant(self, entity_id: str) -> PlantComponent | None:
        entity = self.entity_manager.get_entity(entity_id)
        if entity is None or not entity.has_component(PlantComponent):
            return None
        return entity.get_component(PlantComponent)

    def _report(
        self, day: int, weather_id: str, before: dict[str, tuple[str, str]]
    ) -> DayReport:
        report = DayReport(
            day=day,
            weather_id=weather_id,
            next_weather_id=self.weather.state.condition_id,
            solar_income=self._solar_income,
            drone_harvests=self._drone_harvests,
            outbreak_started=self._outbreak_started,
            outbreak_resolved=self._outbreak_resolved,
            pest_peak=max(soil.pest_pressure for row in self.grid.soil for soil in row),
        )
        after = self._snapshot()
        for entity_id, (species_id, stage) in after.items():
            name = self._display_name(species_id)
            was = before.get(entity_id)
            if was is None:
                # New overnight: either a weed took hold or a crop spread.
                species = SPECIES_TABLE.get(species_id)
                if species is not None and species.is_weed:
                    report.weeds_sprouted += 1
                continue
            if was[1] == stage:
                continue
            if stage == "harvestable":
                report.ripened.append(name)
            elif stage == "dying":
                report.lost.append(name)
            else:
                report.stages_grown.append(name)
        return report

    @staticmethod
    def _display_name(species_id: str) -> str:
        species = SPECIES_TABLE.get(species_id)
        return species.display_name if species is not None else species_id

    def _drive_plants(self, step: float) -> None:
        """Advance every plant's own FSM, as `AISystem` used to.

        Only the plants: the garden-conditions machine runs on days, once a
        night, in `_drive_conditions`.
        """
        for entity_id in list(self.grid.plant_at.values()):
            entity = self.entity_manager.get_entity(entity_id)
            if entity is not None and entity.has_component(AIComponent):
                self._tick_fsm(entity, step)

    def _drive_conditions(self, days: float) -> None:
        """Advance the garden-conditions FSM by `days`."""
        for entity in self.entity_manager.get_entities_with(GardenConditions):
            if entity.has_component(AIComponent):
                self._tick_fsm(entity, days)

    @staticmethod
    def _tick_fsm(entity: Entity, dt: float) -> None:
        ai = entity.get_component(AIComponent)
        if ai.enabled and ai.fsm is not None:
            ai.fsm.update(dt)

    def _on_solar_income(self, event: SolarIncomeEvent) -> None:
        self._solar_income += event.amount

    def _on_drone_harvest(self, event: PlantHarvestedEvent) -> None:
        self._drone_harvests += 1

    def _on_outbreak_started(self, event: OutbreakStartedEvent) -> None:
        self._outbreak_started = True

    def _on_outbreak_resolved(self, event: OutbreakResolvedEvent) -> None:
        self._outbreak_resolved = event.method
