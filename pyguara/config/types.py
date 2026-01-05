"""Configuration data structures."""

from dataclasses import dataclass, field, asdict
from typing import Dict, Any
from pyguara.common.types import Color


@dataclass
class WindowConfig:
    """Display and rendering configuration."""

    screen_width: int = 1200
    screen_height: int = 800
    fps_target: int = 60
    fullscreen: bool = False
    vsync: bool = True
    ui_scale: float = 1.0
    default_color: Color = field(default_factory=lambda: Color(0, 0, 0))
    title: str = "Pyguara Engine"


@dataclass
class AudioConfig:
    """Audio configuration."""

    master_volume: float = 1.0
    sfx_volume: float = 0.8
    music_volume: float = 0.6
    muted: bool = False


@dataclass
class InputConfig:
    """Input configuration."""

    mouse_sensitivity: float = 1.0
    gamepad_enabled: bool = True
    gamepad_deadzone: float = 0.2


@dataclass
class GameConfig:
    """Master configuration container."""

    display: WindowConfig = field(default_factory=WindowConfig)
    audio: AudioConfig = field(default_factory=AudioConfig)
    input: InputConfig = field(default_factory=InputConfig)

    # Metadata
    version: str = "1.0"

    def to_dict(self) -> Dict[str, Any]:
        """Serialize config to dictionary."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "GameConfig":
        """Create config from dictionary (manual for safety/speed)."""
        cfg = cls()

        # Display
        if "display" in data:
            d = data["display"]
            cfg.display = WindowConfig(
                **{k: v for k, v in d.items() if k in WindowConfig.__annotations__}
            )

        # Audio
        if "audio" in data:
            a = data["audio"]
            cfg.audio = AudioConfig(
                **{k: v for k, v in a.items() if k in AudioConfig.__annotations__}
            )

        # Input
        if "input" in data:
            i = data["input"]
            cfg.input = InputConfig(
                **{k: v for k, v in i.items() if k in InputConfig.__annotations__}
            )

        return cfg
