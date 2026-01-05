"""Systems for updating AI logic."""

from pyguara.ai.components import AIComponent
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
            ai: AIComponent = entity.ai_component  # Using __getattr__ magic

            if not ai.enabled:
                continue

            # Update FSM if present
            if ai.fsm:
                ai.fsm.update(dt)

            # (Future) Update Behavior Tree if present
            # if ai.behavior_tree:
            #     ai.behavior_tree.tick(dt)
