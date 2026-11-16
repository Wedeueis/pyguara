"""Keeping Python's garbage collector out of the frame.

A full collection walks every container object in the process. A game
holds tens of thousands, nearly all made while loading and alive until
the scene ends, so the walk can cost more than a frame.

`settle_memory()` unfreezes, collects, and then calls `gc.freeze()`,
which moves everything still alive out of the collector's reach. The
`Application` calls it whenever the scenes it runs change
(`PerformanceConfig.freeze_on_scene_change`); a game calls it after
any load the engine cannot see.
"""

from __future__ import annotations

import gc


def settle_memory() -> int:
    """Collect everything, then freeze what's alive so full collections skip it.

    Call it after loading, between frames: it runs one full collection, which
    costs about as much as the stall it prevents.

    Returns:
        How many objects are frozen now.
    """
    gc.unfreeze()
    gc.collect()
    gc.freeze()
    return gc.get_freeze_count()
