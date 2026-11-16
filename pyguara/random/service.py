"""Deterministic, hierarchical random-number service.

`RandomService` owns a root seed and hands out named child
`RandomStream`s derived from it, so two runs with the same root seed
produce the same sequence for the same stream name, and one stream's
draws do not disturb another's.

Child seeds come from `hashlib.sha256(f"{root_seed}:{name}")`, not
`hash(name)`, which is salted per process. `get_state()` and
`restore_state()` cover the root seed and every stream requested so
far; any other stream is re-derived from the root seed when asked for.
"""

from __future__ import annotations

import hashlib
import secrets
from collections.abc import Mapping
from typing import Any

from pyguara.common.random import RandomStream

_SEED_BITS = 32


class RandomService:
    """Owns a root seed and named, independently seeded random streams."""

    def __init__(self, root_seed: int | None = None) -> None:
        """Create the service, optionally pinning its root seed."""
        self._root_seed = (
            root_seed if root_seed is not None else secrets.randbits(_SEED_BITS)
        )
        self._streams: dict[str, RandomStream] = {}

    @property
    def root_seed(self) -> int:
        """The seed every named stream is deterministically derived from."""
        return self._root_seed

    def reseed(self, root_seed: int) -> None:
        """Re-root every stream on a new seed, discarding draws so far.

        For replay: playback puts the service back on the root seed the
        recording ran under, before the first frame.

        Streams are dropped, not reseeded in place, so the next
        `stream(name)` derives from the new root as a fresh service would.

        Args:
            root_seed: The new root seed.
        """
        self._root_seed = root_seed
        self._streams = {}

    def stream(self, name: str) -> RandomStream:
        """Get the named stream, creating it deterministically on first use."""
        if name not in self._streams:
            self._streams[name] = RandomStream(self._derive_seed(name))
        return self._streams[name]

    def _derive_seed(self, name: str) -> int:
        digest = hashlib.sha256(f"{self._root_seed}:{name}".encode()).digest()
        return int.from_bytes(digest[:8], "big")

    def get_state(self) -> dict[str, Any]:
        """Return a snapshot covering the root seed and streams touched so far."""
        return {
            "root_seed": self._root_seed,
            "streams": {
                name: stream.get_state() for name, stream in self._streams.items()
            },
        }

    def restore_state(self, state: Mapping[str, Any]) -> None:
        """Restore a snapshot previously returned by `get_state()`."""
        self._root_seed = state["root_seed"]
        self._streams = {}
        for name, stream_state in state.get("streams", {}).items():
            stream = RandomStream()
            stream.restore_state(stream_state)
            self._streams[name] = stream
