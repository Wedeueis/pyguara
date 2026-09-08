"""Context object handed to a behavior tree by :class:`AISystem`."""

from dataclasses import dataclass

from pyguara.ai.blackboard import Blackboard
from pyguara.ecs.entity import Entity


@dataclass
class AIContext:
    """What a behavior-tree node receives as its ``context`` under ``AISystem``.

    ``AISystem`` ticks every ``AIComponent``'s tree once per frame with one of
    these, so nodes can reach the entity, the shared blackboard, and -- unlike
    passing the bare entity -- the frame delta. ``WaitNode`` and any custom
    timing node read ``context.dt``; without it they silently fall back to a
    fixed step and drift with the real frame rate.

    Attributes:
        entity: The entity whose AI is being updated.
        dt: Seconds elapsed since the previous AI update.
        blackboard: The component's shared blackboard.
    """

    entity: Entity
    dt: float
    blackboard: Blackboard
