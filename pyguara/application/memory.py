"""Keeping Python's garbage collector out of the frame.

CPython's cycle collector runs a *full* collection every so often, and a full
collection walks every container object the process has: each module, class,
function, loaded asset, component and system. A game holds tens of thousands of
those, nearly all made while loading and alive until the scene ends, so the walk
costs a frame or more and finds nothing. Measured on Reclaimer's host with four
players and 50 enemies, about 80,000 tracked objects: one full collection every
0.8 s, each adding 15 to 20 ms to its tick, which is a visible hitch at 60 Hz.

`gc.freeze()` moves everything alive into a generation the collector never walks.
Freezing once a scene has loaded cut that host's slowest 1% of ticks from 18.8 to
6.9 ms. Freezing has a price: a reference cycle among frozen objects is never
collected while it stays frozen. So `settle_memory()` unfreezes first and
collects, which frees the cycles the previous scene left, and only then freezes
what's still alive. The `Application` does this whenever the scenes it runs
change (`PerformanceConfig.freeze_on_scene_change`), and a game calls it itself
after any load the engine can't see: a level built inside a running scene, or a
world that arrives over the network.

The collector still runs, on everything made after the freeze -- shots, effects,
enemies spawned during play -- which is the garbage a game actually makes.
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
