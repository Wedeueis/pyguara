"""System management for orchestrating game logic."""

from pyguara.systems.manager import SystemManager
from pyguara.systems.protocols import (
    System,
    InitializableSystem,
    CleanupSystem,
)

__all__ = [
    "SystemManager",
    "System",
    "InitializableSystem",
    "CleanupSystem",
]
