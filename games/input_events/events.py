"""Module 4: Events.

Custom game events.
"""

from dataclasses import dataclass
from pyguara.events.protocols import Event


@dataclass
class JumpEvent(Event):
    """Fired when the player should jump."""

    entity_id: str
    force: float
