"""Graphics-related event definitions.

Events are dispatched through the EventDispatcher and can be subscribed to
by game systems and components.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any


@dataclass
class AnimationFrameEvent:
    """Fired when a playing clip reaches a frame carrying a named event.

    `AnimationSystem` dispatches one of these per name returned by
    `Animator.update()`/`AnimationStateMachine.update()` -- see
    `AnimationClip.frame_events`. `kits/action_combat`'s
    `ActiveFrameWindow`/`ActiveFrameSystem` subscribe to this to toggle a
    Hitbox's active frames without a separate timer, but it carries no
    combat vocabulary of its own -- any subscriber (a footstep sound, a
    VFX spawn) can react to it the same way.

    Attributes:
        entity_id: The entity whose `Animator` fired this.
        clip_name: The clip playing when the frame was reached.
        name: The event name authored on that frame in
            `AnimationClip.frame_events`.
    """

    entity_id: str
    clip_name: str
    name: str
    timestamp: float = field(default_factory=time.time)
    source: Any = None
