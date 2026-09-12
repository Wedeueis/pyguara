"""Sound-reveals-the-world echolocation: pulses, occlusion sweeps, memory.

Genre-specific (a bat, sonar, a blind protagonist) but not tied to any one
game: nothing here names a cave or a creature. The raycast sweep takes a
callable rather than an `IPhysicsEngine`, so the kit neither depends on a
physics backend nor needs a physics world to be tested.
`games/mourisco_ressonancia` is this kit's first consumer.
"""

from pyguara.kits.echolocation.pulse import (
    ActivePulse,
    PulseEmitter,
    RayCaster,
    RayHit,
    RevealMemory,
    start_pulse,
    sweep,
    tick_cooldown,
)

__all__ = [
    "ActivePulse",
    "PulseEmitter",
    "RayCaster",
    "RayHit",
    "RevealMemory",
    "start_pulse",
    "sweep",
    "tick_cooldown",
]
