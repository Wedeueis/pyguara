"""Resource lifecycle events.

`ResourceManager.reload()` swaps the *cache entry*; it does not mutate the
instance anything already holds. So a system that loaded a texture once and
kept the object keeps the stale one, and hot-reloading a sprite changes
nothing on screen -- `AssetReloadWatcher`'s own docstring records that, and
told callers to re-`load()` without giving them any way to know when.

This is that way. #40 asked for either a `Handle<T>` indirection or an
event; the event is the smaller change and needs nothing from existing
callers, who keep holding plain resources.
"""

import time
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ResourceReloaded:
    """Fired after a resource was re-read from disk and swapped in the cache.

    Subscribe and re-`load()` the key to pick up the new instance. Dispatched
    on the main thread, during the frame the reload was applied, so a handler
    may touch the renderer or the GL context.

    Development-only in practice: nothing reloads assets unless
    `Application.enable_asset_hot_reload()` turned the watcher on.

    Attributes:
        key: The `ResourceManager` cache key that was reloaded -- the
            resolved path, which is what `load()` takes.
        timestamp: Unix time the event was created.
        source: Whatever raised the event, if it identified itself.
    """

    key: str
    timestamp: float = field(default_factory=time.time)
    source: Any = None
