"""Configuration validation logic."""

from dataclasses import dataclass
from enum import Enum
from typing import List, Optional

from pyguara.config.types import GameConfig, WindowConfig, AudioConfig


class ValidationSeverity(Enum):
    """Severity levels for validation issues."""

    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


@dataclass
class ValidationIssue:
    """Report of a configuration issue."""

    severity: ValidationSeverity
    section: str
    setting: str
    message: str
    suggestion: Optional[str] = None


class ConfigValidator:
    """Validates GameConfig state against defined rules."""

    def validate(self, config: GameConfig) -> List[ValidationIssue]:
        """Run all validation rules."""
        issues = []
        issues.extend(self._validate_display(config.display))
        issues.extend(self._validate_audio(config.audio))
        return issues

    def _validate_display(self, display: WindowConfig) -> List[ValidationIssue]:
        """Validate display settings."""
        issues = []
        if display.screen_width < 640:
            issues.append(
                ValidationIssue(
                    ValidationSeverity.ERROR,
                    "display",
                    "screen_width",
                    f"Width {display.screen_width} is too small (min 640).",
                )
            )

        if display.fps_target < 30:
            issues.append(
                ValidationIssue(
                    ValidationSeverity.WARNING,
                    "display",
                    "fps_target",
                    "FPS target below 30 may cause poor experience.",
                )
            )
        return issues

    def _validate_audio(self, audio: AudioConfig) -> List[ValidationIssue]:
        """Validate audio settings."""
        issues = []
        if not (0.0 <= audio.master_volume <= 1.0):
            issues.append(
                ValidationIssue(
                    ValidationSeverity.ERROR,
                    "audio",
                    "master_volume",
                    "Volume must be between 0.0 and 1.0.",
                )
            )
        return issues
