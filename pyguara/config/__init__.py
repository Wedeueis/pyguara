"""Configuration subsystem."""

from pyguara.config.events import OnConfigurationChanged
from pyguara.config.manager import ConfigManager
from pyguara.config.sections import (
    SectionRegistry,
    SectionRegistryError,
    ValidatableSection,
)
from pyguara.config.types import (
    AudioConfig,
    DebugConfig,
    GameConfig,
    InputConfig,
    PhysicsConfig,
    WindowConfig,
)
from pyguara.config.validation import ValidationIssue, ValidationSeverity

__all__ = [
    "ConfigManager",
    "GameConfig",
    "WindowConfig",
    "AudioConfig",
    "InputConfig",
    "PhysicsConfig",
    "DebugConfig",
    "OnConfigurationChanged",
    "SectionRegistry",
    "SectionRegistryError",
    "ValidatableSection",
    "ValidationIssue",
    "ValidationSeverity",
]
