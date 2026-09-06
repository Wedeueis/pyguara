"""Central configuration management."""

import contextlib
import json
import os
import time
from pathlib import Path
from typing import Any

from pyguara.config.events import (
    OnConfigurationChanged,
    OnConfigurationLoaded,
    OnConfigurationSaved,
)
from pyguara.config.types import GameConfig, RenderingBackend
from pyguara.config.validation import ConfigValidator
from pyguara.events.dispatcher import EventDispatcher
from pyguara.log.logger import EngineLogger
from pyguara.log.types import LogLevel


class ConfigManager:
    """Manages loading, saving, and updating game configuration."""

    def __init__(
        self,
        event_dispatcher: EventDispatcher | None = None,
        logger: EngineLogger | None = None,
    ) -> None:
        """Initialize the manager."""
        self._config = GameConfig()
        self._file_path = Path("config/game_config.json")
        self._dispatcher = event_dispatcher
        self._logger = logger
        self._validator = ConfigValidator()

    @property
    def config(self) -> GameConfig:
        """Access the raw config object."""
        return self._config

    def load(self, file_path: str | Path | None = None) -> bool:
        """Load configuration from JSON file."""
        target_path = Path(file_path) if file_path else self._file_path

        if not target_path.exists():
            if self._logger:
                self._logger.warning(
                    f"Config file not found: {target_path}. Using defaults."
                )
            self.save(target_path)
            return True

        try:
            with open(target_path, encoding="utf-8") as f:
                data = json.load(f)

            self._config = GameConfig.from_dict(data)

            self._apply_env_overrides()

            # Run validation after load
            issues = self._validator.validate(self._config)
            if issues and self._logger:
                for issue in issues:
                    self._logger.warning(f"Config Validation: {issue.message}")

            if self._dispatcher:
                self._dispatcher.dispatch(
                    OnConfigurationLoaded(config_file=str(target_path), success=True)
                )

            return True

        except Exception as e:
            if self._logger:
                self._logger.error(f"Failed to load config from {target_path}: {e}")
            return False

    def save(self, file_path: str | Path | None = None) -> bool:
        """Save current configuration to JSON file."""
        target_path = Path(file_path) if file_path else self._file_path

        try:
            target_path.parent.mkdir(parents=True, exist_ok=True)

            with open(target_path, "w", encoding="utf-8") as f:
                json.dump(self._config.to_dict(), f, indent=4)

            if self._dispatcher:
                self._dispatcher.dispatch(
                    OnConfigurationSaved(config_file=str(target_path), success=True)
                )
            return True

        except Exception as e:
            if self._logger:
                self._logger.error(f"Failed to save config to {target_path}: {e}")
            return False

    def update_setting(self, section: str, setting: str, value: Any) -> bool:
        """Update a specific setting and fire change events."""
        if not hasattr(self._config, section):
            return False

        section_obj = getattr(self._config, section)
        if not hasattr(section_obj, setting):
            return False

        old_value = getattr(section_obj, setting)

        # Basic Type Check
        if not isinstance(value, type(old_value)) and old_value is not None:
            if self._logger:
                self._logger.warning(
                    f"Type mismatch for {section}.{setting}. "
                    f"Expected {type(old_value)}, got {type(value)}"
                )

        setattr(section_obj, setting, value)

        if self._dispatcher:
            self._dispatcher.dispatch(
                OnConfigurationChanged(
                    section=section,
                    setting=setting,
                    old_value=old_value,
                    new_value=value,
                    timestamp=time.time(),
                )
            )

        return True

    def _apply_env_overrides(self) -> None:
        """Allow environment variables to override config."""
        # --- Debug / Engine Settings ---
        # Map PYGUARA_LOG_LEVEL -> config.debug.log_level
        env_log = os.getenv("PYGUARA_LOG_LEVEL")
        if env_log:
            # An unrecognised level keeps the configured default.
            with contextlib.suppress(KeyError):
                self._config.debug.log_level = LogLevel[env_log.upper()]

        # --- Display Settings ---
        # Map PYGUARA_BACKEND -> config.display.backend
        env_backend = os.getenv("PYGUARA_BACKEND")
        if env_backend:
            with contextlib.suppress(ValueError):
                self._config.display.backend = RenderingBackend(env_backend.lower())

        # Map PYGUARA_WINDOW_WIDTH -> config.display.screen_width
        env_width = os.getenv("PYGUARA_WINDOW_WIDTH")
        if env_width:
            with contextlib.suppress(ValueError):
                self._config.display.screen_width = int(env_width)

        # Map PYGUARA_WINDOW_HEIGHT -> config.display.screen_height
        env_height = os.getenv("PYGUARA_WINDOW_HEIGHT")
        if env_height:
            with contextlib.suppress(ValueError):
                self._config.display.screen_height = int(env_height)

        return
