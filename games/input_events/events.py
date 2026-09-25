"""Module 4: Events.

Custom game events.
"""

from dataclasses import dataclass

from pyguara.events.protocols import Event


@dataclass
class DashEvent(Event):
    """Fired when the player should dash in their facing direction.

    A gameplay event, not an input one: `InputBridgeSystem` turns the
    engine's `OnActionEvent` into this, and `PlayerSystem` reacts to this
    without knowing a key exists. That indirection is the module's whole
    point -- the dash could later come from a gamepad, a replay or an AI
    and nothing downstream would change.
    """

    entity_id: str
    distance: float
