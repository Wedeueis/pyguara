"""Events emitted by the configuration subsystem."""

import time
from dataclasses import dataclass, field
from typing import Any

from pyguara.events.protocols import Event


@dataclass
class OnConfigurationChanged(Event):
    """Dispatched when a setting is changed through `ConfigManager`.

    Attributes:
        section: Config section name, e.g. `"display"`.
        setting: Field name within that section.
        old_value: Value before the change.
        new_value: Value after the change.
        timestamp: Unix time the event was created.
        source: Whatever raised the event, if it identified itself.
    """

    section: str
    setting: str
    old_value: Any
    new_value: Any
    timestamp: float = field(default_factory=time.time)
    source: Any = None


@dataclass
class OnConfigurationLoaded(Event):
    """Dispatched after configuration is read from a file.

    Attributes:
        config_file: Path that was read.
        success: Whether the file parsed.
        timestamp: Unix time the event was created.
        source: Whatever raised the event, if it identified itself.
    """

    config_file: str
    success: bool
    timestamp: float = field(default_factory=time.time)
    source: Any = None


@dataclass
class OnConfigurationSaved(Event):
    """Dispatched after configuration is written to a file.

    Attributes:
        config_file: Path that was written.
        success: Whether the write completed.
        timestamp: Unix time the event was created.
        source: Whatever raised the event, if it identified itself.
    """

    config_file: str
    success: bool
    timestamp: float = field(default_factory=time.time)
    source: Any = None
