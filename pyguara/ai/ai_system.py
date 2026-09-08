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
        # Query entities with AI
        for entity in self.manager.get_entities_with(AIComponent):
            ai = entity.get_component(AIComponent)

            if not ai.enabled:
                continue

            # Update FSM if present
            if ai.fsm:
                ai.fsm.update(dt)

            # Update Behavior Tree if present. Pass an AIContext, not the bare
            # entity: WaitNode and any timing node read context.dt, which an
            # Entity has not got -- they would silently run on a fixed step.
            if ai.behavior_tree:
                context = AIContext(entity=entity, dt=dt, blackboard=ai.blackboard)
                ai.behavior_tree.tick(context)
