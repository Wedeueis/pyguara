"""Rules that check a `GameConfig` for values the engine cannot honour."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from pyguara.config.types import (
    AudioConfig,
    GameConfig,
    InputConfig,
    PhysicsConfig,
    WindowConfig,
)

MIN_SCREEN_WIDTH = 640
MIN_SCREEN_HEIGHT = 480
MIN_COMFORTABLE_FPS = 30


class ValidationSeverity(Enum):
    """How badly a configuration issue affects the engine.

    Attributes:
        INFO: Worth knowing; harmless.
        WARNING: Legal but likely to disappoint, e.g. a very low frame target.
        ERROR: The engine will misbehave, but can still start.
        CRITICAL: The engine cannot start with this value.
    """

    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


@dataclass(frozen=True)
class ValidationIssue:
    """One problem found in a configuration.

    Attributes:
        severity: How badly this affects the engine.
        section: Config section the setting belongs to.
        setting: Field name within that section.
        message: What is wrong.
        suggestion: What to do about it, when there is an obvious answer.
    """

    severity: ValidationSeverity
    section: str
    setting: str
    message: str
    suggestion: str | None = None


class ConfigValidator:
    """Checks a `GameConfig` against the engine's operating limits."""

    def validate(self, config: GameConfig) -> list[ValidationIssue]:
        """Run every rule against a configuration.

        Args:
            config: The configuration to check.

        Returns:
            Every issue found, in section order. Empty when the config is
            sound.
        """
        return [
            *self._validate_display(config.display),
            *self._validate_audio(config.audio),
            *self._validate_input(config.input),
            *self._validate_physics(config.physics),
        ]

    def validate_section(
        self, config: GameConfig, section: str
    ) -> list[ValidationIssue]:
        """Run only the rules belonging to one section.

        Args:
            config: The configuration to check.
            section: Section name, e.g. `"audio"`.

        Returns:
            Issues for that section, or an empty list if it has no rules.
        """
        return [issue for issue in self.validate(config) if issue.section == section]

    def _validate_display(self, display: WindowConfig) -> list[ValidationIssue]:
        """Check window and rendering settings.

        Args:
            display: The display section.

        Returns:
            Issues found.
        """
        issues = []
        if display.screen_width < MIN_SCREEN_WIDTH:
            issues.append(
                ValidationIssue(
                    ValidationSeverity.ERROR,
                    "display",
                    "screen_width",
                    f"Width {display.screen_width} is below the {MIN_SCREEN_WIDTH} "
                    f"minimum.",
                    f"Use at least {MIN_SCREEN_WIDTH}.",
                )
            )
        if display.screen_height < MIN_SCREEN_HEIGHT:
            issues.append(
                ValidationIssue(
                    ValidationSeverity.ERROR,
                    "display",
                    "screen_height",
                    f"Height {display.screen_height} is below the "
                    f"{MIN_SCREEN_HEIGHT} minimum.",
                    f"Use at least {MIN_SCREEN_HEIGHT}.",
                )
            )
        if display.fps_target <= 0:
            issues.append(
                ValidationIssue(
                    ValidationSeverity.CRITICAL,
                    "display",
                    "fps_target",
                    f"FPS target must be positive, got {display.fps_target}.",
                    "Use 60 unless you have a reason not to.",
                )
            )
        elif display.fps_target < MIN_COMFORTABLE_FPS:
            issues.append(
                ValidationIssue(
                    ValidationSeverity.WARNING,
                    "display",
                    "fps_target",
                    f"FPS target {display.fps_target} is below "
                    f"{MIN_COMFORTABLE_FPS} and will feel sluggish.",
                )
            )
        return issues

    def _validate_audio(self, audio: AudioConfig) -> list[ValidationIssue]:
        """Check that every volume sits within 0.0-1.0.

        Args:
            audio: The audio section.

        Returns:
            Issues found.
        """
        return [
            ValidationIssue(
                ValidationSeverity.ERROR,
                "audio",
                name,
                f"{name} must be between 0.0 and 1.0, got {value}.",
                "Clamp the value to 0.0-1.0.",
            )
            for name, value in (
                ("master_volume", audio.master_volume),
                ("sfx_volume", audio.sfx_volume),
                ("music_volume", audio.music_volume),
            )
            if not 0.0 <= value <= 1.0
        ]

    def _validate_input(self, input_config: InputConfig) -> list[ValidationIssue]:
        """Check input tuning values.

        Args:
            input_config: The input section.

        Returns:
            Issues found.
        """
        issues = []
        if not 0.0 <= input_config.gamepad_deadzone < 1.0:
            issues.append(
                ValidationIssue(
                    ValidationSeverity.ERROR,
                    "input",
                    "gamepad_deadzone",
                    f"Deadzone must be within [0.0, 1.0), got "
                    f"{input_config.gamepad_deadzone}. A deadzone of 1.0 or more "
                    f"ignores the stick entirely.",
                )
            )
        if input_config.mouse_sensitivity <= 0.0:
            issues.append(
                ValidationIssue(
                    ValidationSeverity.ERROR,
                    "input",
                    "mouse_sensitivity",
                    f"Mouse sensitivity must be positive, got "
                    f"{input_config.mouse_sensitivity}.",
                )
            )
        return issues

    def _validate_physics(self, physics: PhysicsConfig) -> list[ValidationIssue]:
        """Check the fixed-timestep settings the game loop depends on.

        Args:
            physics: The physics section.

        Returns:
            Issues found.
        """
        issues = []
        if physics.fixed_timestep_hz <= 0:
            issues.append(
                ValidationIssue(
                    ValidationSeverity.CRITICAL,
                    "physics",
                    "fixed_timestep_hz",
                    f"Fixed timestep must be positive, got "
                    f"{physics.fixed_timestep_hz}. Application.run() divides by "
                    f"it on startup.",
                    "Use 60, or 120 for higher precision.",
                )
            )
        if physics.max_frame_time <= 0.0:
            issues.append(
                ValidationIssue(
                    ValidationSeverity.ERROR,
                    "physics",
                    "max_frame_time",
                    f"Max frame time must be positive, got "
                    f"{physics.max_frame_time}; the loop would never step.",
                    "0.25 is the usual ceiling.",
                )
            )
        return issues
