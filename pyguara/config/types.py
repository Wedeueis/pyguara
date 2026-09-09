"""Configuration data structures."""

from dataclasses import asdict, dataclass, field, fields, is_dataclass
from enum import Enum
from typing import Any, get_type_hints

from pyguara.common.types import Color
from pyguara.log import get_logger
from pyguara.log.types import LogLevel

logger = get_logger(__name__)


class RenderingBackend(Enum):
    """Available rendering backend options.

    PYGAME: Software rendering using Pygame's SDL2 backend.
            Compatible with all systems, lower performance.

    MODERNGL: GPU-accelerated rendering using ModernGL.
              Requires OpenGL 3.3+, higher performance with hardware instancing.
    """

    PYGAME = "pygame"
    MODERNGL = "moderngl"


@dataclass
class WindowConfig:
    """Display and rendering configuration."""

    screen_width: int = 1200
    screen_height: int = 800
    fps_target: int = 60
    fullscreen: bool = False
    vsync: bool = True
    default_color: Color = field(default_factory=lambda: Color(0, 0, 0))
    title: str = "Pyguara Engine"
    backend: RenderingBackend = RenderingBackend.PYGAME


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
class PhysicsConfig:
    """Physics simulation configuration."""

    # Fixed timestep for physics updates (Hz)
    # 60 Hz is standard for most games, 120 Hz for precision
    fixed_timestep_hz: int = 60

    # Maximum frame time to prevent spiral of death
    # If a frame takes longer than this, we clamp the accumulator
    max_frame_time: float = 0.25

    # Gravity for platformers (pixels/second^2). Use (0,0) for top-down.
    gravity_x: float = 0.0
    gravity_y: float = 0.0

    # Solver steps per physics tick. Chipmunk has no continuous collision
    # detection, so a body jumps velocity/tick pixels and passes through
    # anything thinner. Measured against a 10px wall, 1/2/4 substeps stop a
    # body up to roughly 200/400/900 px/s. 4 is the default: its cost is
    # modest at the body counts a roguelike scene reaches, and the headroom
    # matters for knockback and explosion-flung props. Drop to 2 only with
    # many hundreds of fast bodies. 1 disables substepping.
    substeps: int = 4

    # Fraction of any remaining collider overlap resolved per 1/60s.
    # Chipmunk's own default of 0.1 loses to gravity: a character that lands
    # inside the floor climbs out at a fraction of a pixel per tick and looks
    # stuck in the ground for seconds.
    penetration_recovery: float = 0.3

    # Seconds a body must be still before Chipmunk lets it sleep and stop
    # consuming solver time. Chipmunk's own default never sleeps anything, so
    # a room full of settled props and debris is simulated forever. Any
    # direct state write (position, velocity, impulse) wakes a body. 0
    # disables sleeping.
    sleep_time_threshold: float = 0.5

    @property
    def fixed_dt(self) -> float:
        """The fixed timestep in seconds.

        Returns:
            Seconds per physics tick, `1 / fixed_timestep_hz`.

        Raises:
            ValueError: If `fixed_timestep_hz` is not positive. Application.run()
                reads this on every startup, so a zero from a config file used
                to surface as a bare ZeroDivisionError with no mention of
                config.
        """
        if self.fixed_timestep_hz <= 0:
            raise ValueError(
                f"physics.fixed_timestep_hz must be positive, got "
                f"{self.fixed_timestep_hz}."
            )
        return 1.0 / self.fixed_timestep_hz


@dataclass
class DebugConfig:
    """Engine debugging and logging configuration."""

    # Logging
    log_level: LogLevel = LogLevel.INFO
    log_to_file: bool = True
    log_file_path: str = "logs/engine.log"
    console_logging: bool = True

    # Tooling
    enable_profiler: bool = False
    enable_inspector: bool = False

    # Visual Debugging
    show_colliders: bool = False
    show_fps: bool = False


@dataclass
class GameConfig:
    """Master configuration container."""

    display: WindowConfig = field(default_factory=WindowConfig)
    audio: AudioConfig = field(default_factory=AudioConfig)
    input: InputConfig = field(default_factory=InputConfig)
    physics: PhysicsConfig = field(default_factory=PhysicsConfig)
    debug: DebugConfig = field(default_factory=DebugConfig)

    # Metadata
    version: str = "1.0"

    def to_dict(self) -> dict[str, Any]:
        """Serialize config to dictionary.

        `asdict()` alone leaves `RenderingBackend` as a plain `Enum` instance
        (unlike `LogLevel`, an `IntEnum` that's already JSON-safe), which
        `json.dump()` then rejects -- converted to its string `.value` here
        to match what `from_dict()` already expects on the way back in.
        """
        data = asdict(self)
        data["display"]["backend"] = self.display.backend.value
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "GameConfig":
        """Build a config from a decoded JSON document.

        Unknown keys are ignored and logged rather than raising, so a config
        written by a newer engine still loads. Nested values are coerced back
        to their declared types -- `Color` from its dict form, enums from their
        string or integer value -- which plain construction would not do.

        The input is never mutated.

        Args:
            data: Decoded configuration document.

        Returns:
            The populated config. Sections absent from `data` keep their
            defaults.
        """
        config = cls()
        for section_name in ("display", "audio", "input", "physics", "debug"):
            section_data = data.get(section_name)
            if section_data is None:
                continue
            current = getattr(config, section_name)
            setattr(
                config,
                section_name,
                _build_section(type(current), section_data, section_name),
            )

        version = data.get("version")
        if isinstance(version, str):
            config.version = version

        return config


def _build_section(
    section_type: type[Any], data: dict[str, Any], section_name: str
) -> Any:
    """Construct one config section, coercing each value to its declared type.

    Args:
        section_type: The dataclass to build.
        data: That section's raw values.
        section_name: Section name, for log messages.

    Returns:
        The constructed section.
    """
    hints = get_type_hints(section_type)
    known = {f.name for f in fields(section_type)}

    kwargs: dict[str, Any] = {}
    for key, value in data.items():
        if key not in known:
            logger.warning(
                f"Unknown config key '{section_name}.{key}' ignored. "
                f"Check for a typo, or a setting from a different engine version."
            )
            continue
        kwargs[key] = _coerce(hints[key], value, f"{section_name}.{key}")

    return section_type(**kwargs)


def _coerce(target_type: Any, value: Any, label: str) -> Any:
    """Convert a decoded JSON value to the type a config field declares.

    JSON has no enums and no dataclasses, so a round trip through a file turns
    `Color` into a dict and `RenderingBackend` into a string. Without this,
    `default_color` came back as a plain dict and every reader of it broke on
    attribute access.

    Args:
        target_type: The field's declared type.
        value: The decoded value.
        label: Dotted field name, for log messages.

    Returns:
        The coerced value, or the original if no rule applies.
    """
    if isinstance(target_type, type):
        if isinstance(value, target_type) and not isinstance(value, bool):
            return value

        if is_dataclass(target_type) and isinstance(value, dict):
            nested = {f.name for f in fields(target_type)}
            return target_type(**{k: v for k, v in value.items() if k in nested})

        if issubclass(target_type, Enum):
            return _coerce_enum(target_type, value, label)

    return value


def _coerce_enum(enum_type: type[Enum], value: Any, label: str) -> Any:
    """Resolve an enum from its value, or from its member name.

    Args:
        enum_type: The enum to resolve into.
        value: A member value, or a member name such as `"DEBUG"`.
        label: Dotted field name, for log messages.

    Returns:
        The matching member, or the enum's engine default when nothing matches.
    """
    if isinstance(value, enum_type):
        return value
    try:
        return enum_type(value)
    except ValueError:
        pass
    if isinstance(value, str):
        try:
            return enum_type[value.upper()]
        except KeyError:
            pass

    fallback = next(iter(enum_type))
    logger.warning(
        f"Config value {value!r} is not a valid {enum_type.__name__} for "
        f"'{label}'; falling back to {fallback.name}."
    )
    return fallback
