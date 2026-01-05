"""Central configuration management."""

import json
import time
from pathlib import Path
from typing import Any, Optional, Union

from pyguara.config.events import (
    OnConfigurationChanged,
    OnConfigurationLoaded,
    OnConfigurationSaved,
)
from pyguara.config.types import GameConfig
from pyguara.config.validation import ConfigValidator
from pyguara.events.dispatcher import EventDispatcher
from pyguara.log.logger import EngineLogger


class ConfigManager:
    """Manages loading, saving, and updating game configuration."""

    def __init__(
        self,
        event_dispatcher: Optional[EventDispatcher] = None,
        logger: Optional[EngineLogger] = None,
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

    def load(self, file_path: Optional[Union[str, Path]] = None) -> bool:
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
            with open(target_path, "r", encoding="utf-8") as f:
                data = json.load(f)

            self._config = GameConfig.from_dict(data)

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
                self._logger.error(f"Failed to load config: {e}")
            return False

    def save(self, file_path: Optional[Union[str, Path]] = None) -> bool:
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
                self._logger.error(f"Failed to save config: {e}")
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
