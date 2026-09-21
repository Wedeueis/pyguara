"""Plant lifecycle states, driven by the engine's own `AISystem`.

Every `Scene` auto-registers `AISystem` at priority 200
(`pyguara/scene/base.py`), which calls `ai.fsm.update(dt)` for any entity
carrying an `AIComponent` -- so nothing here drives the machine itself,
only defines what each stage does. `systems/plant_growth_system.py`
accumulates `PlantComponent.growth_progress`; a state's `update()` only
checks it against a per-stage budget and reports the next stage's name.

Pests (Phase 3) live in the *same* machine, not a second one:
`AIComponent.fsm` is a single slot, so a plant that can be infested needs
`infested`/`dying` as branches of its lifecycle. A growing, mature or
harvestable plant whose cell's pest pressure crosses `INFEST_THRESHOLD`
moves to `infested`, remembering the stage and progress it left in the
state machine's `Blackboard` -- the one thing the blackboard is for here,
transient per-plant scratch nothing else reads -- and returns to exactly
that stage once the pressure falls below `RECOVER_THRESHOLD`. If its
health runs out first it moves to `dying`, which is terminal.

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

INFEST_THRESHOLD = 0.5
"""`PlantComponent.pest_pressure` at which a plant becomes infested."""

RECOVER_THRESHOLD = 0.2
"""Pressure an infested plant must fall below to recover. Lower than
`INFEST_THRESHOLD` on purpose -- a plant hovering around one number would
flicker between the two states every tick."""

_RESUME_STAGE = "resume_stage"
_RESUME_PROGRESS = "resume_progress"


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
        resumed = self.blackboard.get(_RESUME_PROGRESS)
        self.plant.growth_progress = resumed if resumed is not None else 0.0
        self.blackboard.set(_RESUME_PROGRESS, None)

    def on_exit(self) -> None:
        """Nothing to release -- see `on_enter()`'s docstring."""

    def _infestation(self) -> str | None:
        """`"infested"`, after remembering where to return to, if pests hit.

        Returns:
            The next state's name when pest pressure has crossed
            `INFEST_THRESHOLD`, else None.
        """
        if self.plant.pest_pressure < INFEST_THRESHOLD:
            return None
        self.blackboard.set(_RESUME_STAGE, self.STAGE_NAME)
        self.blackboard.set(_RESUME_PROGRESS, self.plant.growth_progress)
        return "infested"


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
        """Get infested, or advance to `mature` once the budget fills."""
        if (infested := self._infestation()) is not None:
            return infested
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
        """Get infested, or advance to `harvestable` once the budget fills."""
        if (infested := self._infestation()) is not None:
            return infested
        if self.plant.growth_progress >= STAGE_THRESHOLD:
            return "harvestable"
        return None


class HarvestableState(_PlantState):
    """Ready to harvest. Stays put until the player does, or pests arrive."""

    STAGE_NAME = "harvestable"

    def update(self, dt: float) -> str | None:
        """Get infested; otherwise wait for the harvest tool."""
        return self._infestation()


class InfestedState(_PlantState):
    """Under pest pressure. Recovers to where it was, or dies trying.

    Unlike its siblings this does *not* reset `growth_progress` on entry:
    the progress it left with is parked in the blackboard, and is handed
    back by whichever stage it returns to.
    """

    STAGE_NAME = "infested"

    def on_enter(self) -> None:
        """Mark the plant infested, leaving its growth progress alone."""
        self.plant.growth_stage = self.STAGE_NAME

    def update(self, dt: float) -> str | None:
        """Die if health runs out; recover if the pressure lifts."""
        if self.plant.health <= 0.0:
            return "dying"
        if self.plant.pest_pressure < RECOVER_THRESHOLD:
            return self.blackboard.get(_RESUME_STAGE, "growing")
        return None


class DyingState(_PlantState):
    """Terminal. The harvest tool clears it for nothing."""

    STAGE_NAME = "dying"

    def update(self, dt: float) -> str | None:
        """Stay put -- there is no coming back."""
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
    machine.add_state("infested", InfestedState(entity, blackboard))
    machine.add_state("dying", DyingState(entity, blackboard))
    machine.set_initial_state("seedling")
    return AIComponent(blackboard=blackboard, fsm=machine)
