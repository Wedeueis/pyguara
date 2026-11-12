"""Input backend implementations.

Resolved on first use rather than imported here, so importing one backend
does not load another's library: `NativeClipboard` must not bring pygame.
"""

from __future__ import annotations

from typing import Any

_WHERE = {
    "PygameClipboard": "pyguara.input.backends.pygame_backend",
    "PygameInputBackend": "pyguara.input.backends.pygame_backend",
    "PygameJoystick": "pyguara.input.backends.pygame_backend",
    "NativeClipboard": "pyguara.input.backends.native_backend",
}

__all__ = sorted(_WHERE)


def __getattr__(name: str) -> Any:
    """Import a backend class the first time it is asked for."""
    module = _WHERE.get(name)
    if module is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    import importlib

    return getattr(importlib.import_module(module), name)
