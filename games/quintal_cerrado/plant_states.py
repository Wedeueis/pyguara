"""Plant lifecycle states, driven by the engine's own `AISystem`.

Every `Scene` auto-registers `AISystem` at priority 200
(`pyguara/scene/base.py`), which calls `ai.fsm.update(dt)` for any entity
carrying an `AIComponent` -- so nothing here drives the machine itself,
only defines what each stage does. `systems/plant_growth_system.py`
accumulates `PlantComponent.growth_progress`; a state's `update()` only
checks it against a per-stage budget and reports the next stage's name.

`build_plant_ai()` is the module's one entry point: a freshly planted
entity gets a brand new `Blackboard`/`StateMachine`/`AIComponent` triple,
never a shared one -- `AIComponent.fsm` is a single slot, so each plant
needs its own machine instance the same way each plant needs its own
`PlantComponent`.
"""

from __future__ import annotations

from games.quintal_cerrado.components import PlantComponent
from pyguara.ai.blackboard import Blackboard
from pyguara.ai.components import AIComponent
from pyguara.ai.fsm import State, StateMachine
from pyguara.ecs.entity import Entity

STAGE_THRESHOLD = 1.0
"""`growth_progress` needed to advance. `systems/plant_growth_system.py`
accumulates it as a fraction of `Species.stage_seconds`, and each state's
`on_enter()` resets it to 0 -- so this is a per-stage budget, not a
cumulative total across the whole lifecycle."""


class _PlantState(State):
    """Common plumbing every stage shares: the plant's own component.

    Not itself a `BaseComponent` subclass -- `State` is a plain controller
    object the data-only rule does not apply to, so unlike `PlantComponent`
    it is allowed to hold behaviour.
    """

    STAGE_NAME = ""

    @property
    def plant(self) -> PlantComponent:
        """The lifecycle-owning entity's `PlantComponent`."""
        return self.entity.get_component(PlantComponent)

    def on_enter(self) -> None:
        """Stamp the stage name onto `PlantComponent` and start its budget.

        `growth_stage` mirrors the FSM's current state name rather than
        being computed from it on demand, so anything that wants the
        stage -- the save schema, a future cell inspector -- reads a plain
        field instead of reaching into the FSM.
        """
        self.plant.growth_stage = self.STAGE_NAME
        self.plant.growth_progress = 0.0

    def on_exit(self) -> None:
        """Nothing to release -- see `on_enter()`'s docstring."""


class SeedlingState(_PlantState):
    """Freshly planted. Advances to `growing` once the budget fills."""

    STAGE_NAME = "seedling"

    def update(self, dt: float) -> str | None:
        """Advance to `growing` once the stage's growth budget fills."""
        if self.plant.growth_progress >= STAGE_THRESHOLD:
            return "growing"
        return None


class GrowingState(_PlantState):
    """Establishing. Advances to `mature` once the budget fills."""

    STAGE_NAME = "growing"

    def update(self, dt: float) -> str | None:
        """Advance to `mature` once the stage's growth budget fills."""
        if self.plant.growth_progress >= STAGE_THRESHOLD:
            return "mature"
        return None


class MatureState(_PlantState):
    """Full-grown. Advances to `harvestable` once the budget fills.

    Also the stage `systems/shade_system.py` treats as old enough to cast
    real shade -- a seedling canopy tree shading its neighbours would be
    backwards.
    """

    STAGE_NAME = "mature"

    def update(self, dt: float) -> str | None:
        """Advance to `harvestable` once the stage's growth budget fills."""
        if self.plant.growth_progress >= STAGE_THRESHOLD:
            return "harvestable"
        return None


class HarvestableState(_PlantState):
    """Ready. Terminal for now -- harvesting is Phase 3's economy system."""

    STAGE_NAME = "harvestable"

    def update(self, dt: float) -> str | None:
        """Stay put -- there is no harvest action yet."""
        return None


def build_plant_ai(entity: Entity) -> AIComponent:
    """Build a fresh lifecycle `AIComponent` for a just-planted entity.

    Args:
        entity: The planted entity. Must already carry a `PlantComponent`
            -- `set_initial_state()` below calls `SeedlingState.on_enter()`
            immediately, which reads it.

    Returns:
        An `AIComponent` ready to `entity.add_component()`.
    """
    blackboard = Blackboard()
    machine = StateMachine(entity, blackboard)
    machine.add_state("seedling", SeedlingState(entity, blackboard))
    machine.add_state("growing", GrowingState(entity, blackboard))
    machine.add_state("mature", MatureState(entity, blackboard))
    machine.add_state("harvestable", HarvestableState(entity, blackboard))
    machine.set_initial_state("seedling")
    return AIComponent(blackboard=blackboard, fsm=machine)
