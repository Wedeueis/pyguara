"""Module 4: Systems.

Input handling and Physics logic.
"""

from pyguara.ecs.manager import EntityManager
from pyguara.events.dispatcher import EventDispatcher
from pyguara.input.events import OnActionEvent
from pyguara.common.types import Vector2
from games.input_events.events import JumpEvent
from games.input_events.components import Transform, Velocity


class InputBridgeSystem:
    """Translates generic Input Actions into specific Game Events."""

    def __init__(self, dispatcher: EventDispatcher, player_id: str):
        """Initialize system."""
        self._dispatcher = dispatcher
        self._player_id = player_id
        # Listen for semantic actions defined in InputManager
        self._dispatcher.subscribe(OnActionEvent, self.on_action)

    def on_action(self, event: OnActionEvent) -> None:
        """Handle input action event."""
        # Check for "jump" action (mapped to Spacebar in Scene)
        # value > 0 means pressed (analog or digital)
        if event.action_name == "jump" and event.value > 0.5:
            print("InputBridge: 'jump' action detected -> Firing JumpEvent")
            # Dispatch gameplay event
            self._dispatcher.dispatch(JumpEvent(self._player_id, force=400.0))


class PlayerSystem:
    """Handles Player physics and reaction to JumpEvent."""

    def __init__(self, entity_manager: EntityManager, dispatcher: EventDispatcher):
        """Initialize system."""
        self._em = entity_manager
        # Listen for gameplay events
        dispatcher.subscribe(JumpEvent, self.on_jump)

    def on_jump(self, event: JumpEvent) -> None:
        """Handle jump event."""
        entity = self._em.get_entity(event.entity_id)
        if entity and entity.has_component(Velocity):
            vel = entity.get_component(Velocity)
            # Apply instant upward velocity (Negative Y is UP in screen coords)
            vel.value = Vector2(vel.value.x, -event.force)
            print(f"PlayerSystem: JumpEvent received. Velocity set to {vel.value}")

    def update(self, dt: float) -> None:
        """Update physics simulation."""
        gravity = 800.0
        floor_y = 500.0

        for entity in self._em.get_entities_with(Transform, Velocity):
            trans = entity.get_component(Transform)
            vel = entity.get_component(Velocity)

            # 1. Apply Gravity to Velocity
            new_vy = vel.value.y + gravity * dt
            vel.value = Vector2(vel.value.x, new_vy)

            # 2. Apply Velocity to Position
            # Vector2 supports operator overloading
            trans.position = trans.position + (vel.value * dt)

            # 3. Simple Floor Collision
            if trans.position.y > floor_y:
                trans.position = Vector2(trans.position.x, floor_y)
                vel.value = Vector2(vel.value.x, 0)
