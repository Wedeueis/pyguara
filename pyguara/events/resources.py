"""Resource lifecycle events.

`ResourceManager.reload()` swaps the cache entry; it does not mutate
the instance a caller already holds. The event here tells such a
caller when to `load()` again.
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
