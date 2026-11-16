"""Checks for the optional libraries a backend is built on.

pygame is not installed by `pip install pyguara`. The software renderer
and the pygame audio backend need it, and each asks here before
importing it, so a missing install is reported by name with the command
that fixes it.
"""

from __future__ import annotations

import importlib.util


class MissingExtraError(ImportError):
    """A feature was chosen whose optional dependency is not installed."""


def require_pygame(feature: str) -> None:
    """Raise if pygame is not installed, naming what asked for it.

    Args:
        feature: What needs pygame, as it should read in the message,
            e.g. `'display.backend = "pygame"'`.

    Raises:
        MissingExtraError: If pygame cannot be imported.
    """
    try:
        found = importlib.util.find_spec("pygame") is not None
    except ValueError:
        # `sys.modules["pygame"] = None` makes `find_spec` raise.
        found = False
    if not found:
        raise MissingExtraError(
            f"{feature} needs pygame, which is not installed. Install it "
            f"with `pip install 'pyguara[pygame]'`, or use the default wgpu "
            f"renderer and native audio, which do not need it."
        )
