"""Systems for updating AI logic."""

from pyguara.ai.components import AIComponent
from pyguara.ai.context import AIContext
from pyguara.ecs.manager import EntityManager


class AISystem:
    """Updates AI decision making (FSMs/Trees)."""

    def __init__(self, entity_manager: EntityManager):
        """Initialize the AI system for all Entities."""
        self.manager = entity_manager

    def update(self, dt: float) -> None:
        """Update all AI components."""
        # Runs once per agent per tick, so the attribute reads are taken once
        # each and compared with `is not None` (neither a machine nor a tree
        # defines truthiness, so it is the same test as before, cheaper).
        for entity in self.manager.get_entities_with(AIComponent):
            ai = entity.get_component(AIComponent)

            if not ai.enabled:
                continue

            fsm = ai.fsm
            if fsm is not None:
                fsm.update(dt)

            # Update Behavior Tree if present. Pass an AIContext, not the bare
            # entity: WaitNode and any timing node read context.dt, which an
            # Entity has not got -- they would silently run on a fixed step.
            tree = ai.behavior_tree
            if tree is not None:
                context = AIContext(entity=entity, dt=dt, blackboard=ai.blackboard)
                tree.tick(context)
