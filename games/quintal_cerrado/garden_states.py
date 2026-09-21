"""The garden-wide pest FSM: `stable -> outbreak -> resolved_* -> stable`.

A second `StateMachine` on a singleton `garden_conditions` entity, driven
by the same engine `AISystem` as every plant's own -- proof the FSM
machinery is reusable across *kinds* of entity, not just plants. It paces
the PRD's "fork in the road" beat: `stable` waits until the plot has
enough established plants to be worth infesting, `outbreak` seeds pest
pressure on a couple of them and stays until the pressure is gone, and
`resolved_organic`/`resolved_chemical` -- chosen by how the player last
answered -- rest for a cooldown before letting the next outbreak come.

What actually spreads, decays and kills is `systems/pest_system.py`; this
machine only decides *when* an outbreak starts and when it counts as over,
and tells the scene through `events.py`.
"""

from __future__ import annotations

from games.quintal_cerrado.components import GardenConditions, PlantComponent
from games.quintal_cerrado.events import OutbreakResolvedEvent, OutbreakStartedEvent
from games.quintal_cerrado.garden_grid import GardenGrid
from pyguara.ai.blackboard import Blackboard
from pyguara.ai.components import AIComponent
from pyguara.ai.fsm import State, StateMachine
from pyguara.common.grid import Cell
from pyguara.common.random import RandomStream
from pyguara.ecs.entity import Entity
from pyguara.ecs.manager import EntityManager
from pyguara.events.dispatcher import EventDispatcher

OUTBREAK_DELAY = 20.0
"""Seconds `stable` waits, with enough plants established, before an outbreak."""

OUTBREAK_MIN_PLANTS = 3
"""Established plants the plot needs before an outbreak is worth having."""

OUTBREAK_CELLS = 2
"""How many plants an outbreak starts on."""

OUTBREAK_SEED_PRESSURE = 0.8
"""Pest pressure an outbreak starts its cells at -- well past
`plant_states.INFEST_THRESHOLD`, so the plant is infested at once."""

RESOLVED_COOLDOWN = 15.0
"""Seconds a `resolved_*` state rests before the next outbreak can begin."""

CLEAR_PRESSURE = 0.05
"""Highest pest pressure anywhere on the plot at which an outbreak counts as
over."""

_ESTABLISHED_STAGES = frozenset({"growing", "mature", "harvestable"})
"""Stages an outbreak can start on -- a seedling is too small to be a
target, and an already-infested plant is already one."""


class _ConditionState(State):
    """What every conditions state shares: the plot and where to report."""

    PHASE = ""

    def __init__(
        self,
        entity: Entity,
        blackboard: Blackboard,
        grid: GardenGrid,
        entity_manager: EntityManager,
        dispatcher: EventDispatcher,
        rng: RandomStream,
    ) -> None:
        """Bind the state to the plot it watches.

        Args:
            entity: The `garden_conditions` entity.
            blackboard: This machine's scratch space.
            grid: The plot.
            entity_manager: Where the plants live.
            dispatcher: Where outbreak events are announced.
            rng: Picks which plants an outbreak starts on.
        """
        super().__init__(entity, blackboard)
        self.grid = grid
        self.entity_manager = entity_manager
        self.dispatcher = dispatcher
        self.rng = rng

    @property
    def conditions(self) -> GardenConditions:
        """The garden's `GardenConditions` component."""
        return self.entity.get_component(GardenConditions)

    def on_enter(self) -> None:
        """Mirror the phase name onto `GardenConditions`."""
        self.conditions.phase = self.PHASE
        self.blackboard.set("elapsed", 0.0)

    def on_exit(self) -> None:
        """Nothing to release."""

    def _tick(self, dt: float) -> float:
        """Advance and return this state's own clock, in seconds."""
        elapsed = float(self.blackboard.get("elapsed", 0.0)) + dt
        self.blackboard.set("elapsed", elapsed)
        return elapsed

    def _established_plants(self) -> list[Cell]:
        """Cells holding a plant an outbreak could start on."""
        cells = []
        for cell, entity_id in self.grid.plant_at.items():
            entity = self.entity_manager.get_entity(entity_id)
            if entity is None or not entity.has_component(PlantComponent):
                continue
            if entity.get_component(PlantComponent).growth_stage in _ESTABLISHED_STAGES:
                cells.append(cell)
        return cells

    def _peak_pressure(self) -> float:
        """The highest pest pressure on any cell of the plot."""
        return max(soil.pest_pressure for row in self.grid.soil for soil in row)


class StableState(_ConditionState):
    """Nothing wrong. Counts down while there is something to infest."""

    PHASE = "stable"

    def update(self, dt: float) -> str | None:
        """Begin an outbreak once the plot has been established long enough."""
        if len(self._established_plants()) < OUTBREAK_MIN_PLANTS:
            self.blackboard.set("elapsed", 0.0)
            return None
        if self._tick(dt) >= OUTBREAK_DELAY:
            return "outbreak"
        return None


class OutbreakState(_ConditionState):
    """Pests are loose. Ends when the pressure is gone, however it went."""

    PHASE = "outbreak"

    def on_enter(self) -> None:
        """Seed pest pressure on a few established plants and announce it."""
        super().on_enter()
        self.conditions.last_treatment = ""

        candidates = self._established_plants()
        self.rng.shuffle(candidates)
        started = candidates[:OUTBREAK_CELLS]
        for cell in started:
            self.grid.soil_at(cell).pest_pressure = OUTBREAK_SEED_PRESSURE
        self.dispatcher.dispatch(OutbreakStartedEvent(cells=started))

    def update(self, dt: float) -> str | None:
        """Resolve once no cell carries meaningful pest pressure."""
        if self._peak_pressure() > CLEAR_PRESSURE:
            return None
        if self.conditions.last_treatment == "chemical":
            return "resolved_chemical"
        return "resolved_organic"


class ResolvedOrganicState(_ConditionState):
    """The outbreak ended the slow way. Rests, then goes back to `stable`."""

    PHASE = "resolved_organic"

    def on_enter(self) -> None:
        """Count the resolution and announce it."""
        super().on_enter()
        self.conditions.organic_resolutions += 1
        self.dispatcher.dispatch(OutbreakResolvedEvent(method="organic"))

    def update(self, dt: float) -> str | None:
        """Return to `stable` after the cooldown."""
        return "stable" if self._tick(dt) >= RESOLVED_COOLDOWN else None


class ResolvedChemicalState(_ConditionState):
    """The outbreak ended the fast way. Rests, then goes back to `stable`."""

    PHASE = "resolved_chemical"

    def on_enter(self) -> None:
        """Count the resolution and announce it."""
        super().on_enter()
        self.conditions.chemical_resolutions += 1
        self.dispatcher.dispatch(OutbreakResolvedEvent(method="chemical"))

    def update(self, dt: float) -> str | None:
        """Return to `stable` after the cooldown."""
        return "stable" if self._tick(dt) >= RESOLVED_COOLDOWN else None


def build_conditions_ai(
    entity: Entity,
    grid: GardenGrid,
    entity_manager: EntityManager,
    dispatcher: EventDispatcher,
    rng: RandomStream | None = None,
) -> AIComponent:
    """Build the `garden_conditions` entity's `AIComponent`.

    Args:
        entity: The singleton conditions entity. Must already carry a
            `GardenConditions` component -- `set_initial_state()` below
            calls `StableState.on_enter()` immediately, which reads it.
        grid: The plot.
        entity_manager: Where the plants live.
        dispatcher: Where outbreak events are announced.
        rng: Randomness for picking outbreak cells. Pass a seeded stream
            for a reproducible outbreak.

    Returns:
        An `AIComponent` ready to `entity.add_component()`.
    """
    blackboard = Blackboard()
    stream = rng if rng is not None else RandomStream()
    machine = StateMachine(entity, blackboard)
    for name, state_class in (
        ("stable", StableState),
        ("outbreak", OutbreakState),
        ("resolved_organic", ResolvedOrganicState),
        ("resolved_chemical", ResolvedChemicalState),
    ):
        machine.add_state(
            name,
            state_class(entity, blackboard, grid, entity_manager, dispatcher, stream),
        )
    machine.set_initial_state("stable")
    return AIComponent(blackboard=blackboard, fsm=machine)
