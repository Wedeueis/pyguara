"""Deterministic randomness for PyGuara.

`RandomService` is registered as a DI singleton; `RandomStream`, the value
type it hands out, lives in `pyguara.common.random`.
"""

from pyguara.common.random import RandomStream
from pyguara.random.service import RandomService

__all__ = ["RandomService", "RandomStream"]
