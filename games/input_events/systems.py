"""Module 4: Systems.

Input handling. The chain this module teaches, end to end:

    a key -> InputManager -> OnActionEvent -> DashEvent -> the player moves

`InputBridgeSystem` owns the middle of it, and `PlayerSystem` only ever
sees the far end. Neither knows a keyboard exists.

There is deliberately **no physics here** -- no gravity, no velocity
integration, no collision. Movement is the direction the player is holding,
applied straight to the position. Module 5 (`physics_integration`) is where
a body first moves under forces, through `RigidBody` and `PhysicsSystem`;
doing a rough version of it here would teach the wrong answer one module
before the right one.
"""

from games.input_events.components import Movement, Transform
from games.input_events.events import DashEvent
from pyguara.common.types import Vector2
from pyguara.ecs.manager import EntityManager
from pyguara.events.dispatcher import EventDispatcher
from pyguara.input.events import OnActionEvent

# The four held directions, and which way each one points. Registered as
# HOLD actions in the scene, so each fires with value > 0 when the key goes
# down and value 0 when it comes back up.
_DIRECTIONS = {
    "move_left": Vector2(-1, 0),
    "move_right": Vector2(1, 0),
    "move_up": Vector2(0, -1),  # negative Y is up in screen coordinates
    "move_down": Vector2(0, 1),
}


class InputBridgeSystem:
    """Translates generic Input Actions into specific Game Events.

    Two different translations, and the difference is worth noticing:

    - the four *held* directions become **state** on the player's
      `Movement` component, because "am I still holding left" is a
      question about now, not about a moment;
    - the *pressed* dash becomes a **`DashEvent`**, because it happened
      once and anything that cares should hear about it once.

    Reaching for an event where state was wanted (or the reverse) is the
    commonest way this wiring goes wrong.
    """

    def __init__(
        self, entity_manager: EntityManager, dispatcher: EventDispatcher, player_id: str
    ):
        """Initialize system."""
        self._em = entity_manager
        self._dispatcher = dispatcher
        self._player_id = player_id
        self._held: set[str] = set()
        # Listen for semantic actions defined in InputManager
        self._dispatcher.subscribe(OnActionEvent, self.on_action)

    def on_action(self, event: OnActionEvent) -> None:
        """Handle input action event."""
        # value > 0 means pressed (analog or digital)
        pressed = event.value > 0.5

        if event.action_name in _DIRECTIONS:
            if pressed:
                self._held.add(event.action_name)
            else:
                self._held.discard(event.action_name)
            self._write_direction()
            return

        # Check for "dash" action (mapped to Spacebar in Scene)
        if event.action_name == "dash" and pressed:
            print("InputBridge: 'dash' action detected -> Firing DashEvent")
            # Dispatch gameplay event
            self._dispatcher.dispatch(DashEvent(self._player_id, distance=80.0))

    def _write_direction(self) -> None:
        """Sum the held directions onto the player's `Movement`."""
        player = self._em.get_entity(self._player_id)
        if player is None or not player.has_component(Movement):
            return

        direction = Vector2(0, 0)
        for action in self._held:
            direction = direction + _DIRECTIONS[action]

        # Diagonals would otherwise travel ~1.41x faster than the axes.
        if direction.length > 0:
            direction = direction.normalize()

        player.get_component(Movement).direction = direction


class PlayerSystem:
    """Moves the player, and reacts to DashEvent.

    Knows nothing about keys or actions -- only about the `Movement`
    component and the gameplay event. That is what lets the same system be
    driven by a gamepad, a replay or an AI without a line changing here.
    """

    # Keeps the square on screen. A clamp, not a collision test: there is
    # nothing here to collide with, and module 5 is where real collision
    # arrives.
    _BOUNDS_MIN = Vector2(0, 0)
    _BOUNDS_MAX = Vector2(760, 560)

    def __init__(self, entity_manager: EntityManager, dispatcher: EventDispatcher):
        """Initialize system."""
        self._em = entity_manager
        # Listen for gameplay events
        dispatcher.subscribe(DashEvent, self.on_dash)

    def on_dash(self, event: DashEvent) -> None:
        """Handle dash event: one instant hop the way the player is facing."""
        entity = self._em.get_entity(event.entity_id)
        if entity is None or not entity.has_component(Movement):
            return

        movement = entity.get_component(Movement)
        direction = movement.direction
        if direction.length == 0:
            direction = Vector2(1, 0)  # standing still: dash right

        transform = entity.get_component(Transform)
        transform.position = self._clamped(
            transform.position + direction * event.distance
        )
        print(f"PlayerSystem: DashEvent received. Moved to {transform.position}")

    def update(self, dt: float) -> None:
        """Apply the held direction to every movable entity's position."""
        for entity in self._em.get_entities_with(Transform, Movement):
            transform = entity.get_component(Transform)
            movement = entity.get_component(Movement)

            # Position, straight from intent. No velocity to integrate and
            # no forces to accumulate -- `dt` is here so that holding a key
            # covers the same distance per second on any machine.
            step = movement.direction * (movement.speed * dt)
            transform.position = self._clamped(transform.position + step)

    def _clamped(self, position: Vector2) -> Vector2:
        """Keep a position inside the visible area."""
        return Vector2(
            min(max(position.x, self._BOUNDS_MIN.x), self._BOUNDS_MAX.x),
            min(max(position.y, self._BOUNDS_MIN.y), self._BOUNDS_MAX.y),
        )
