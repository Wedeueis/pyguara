"""Configuration event definitions."""

from dataclasses import dataclass
from typing import Any

from pyguara.events.protocols import Event


@dataclass
class OnConfigurationChanged(Event):
    """Dispatched when configuration settings are modified."""

    section: str
    setting: str
    old_value: Any
    new_value: Any
    # Event protocol requirements
    timestamp: float = 0.0
    source: Any = None


@dataclass
class OnConfigurationLoaded(Event):
    """Dispatched when configuration is loaded from file."""

    config_file: str
    success: bool
    timestamp: float = 0.0
    source: Any = None


@dataclass
class OnConfigurationSaved(Event):
    """Dispatched when configuration is saved to file."""

    config_file: str
    success: bool
    timestamp: float = 0.0
    source: Any = None
