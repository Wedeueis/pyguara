"""Tests for spatial audio system."""

import pytest

from pyguara.common.types import Vector2
from pyguara.audio.types import (
    AudioPriority,
    AudioBusType,
    AudioBus,
    AudioBusManager,
    SpatialAudioConfig,
    PlayingSoundInfo,
)


class TestAudioPriority:
    """Test AudioPriority enum."""

    def test_priority_ordering(self) -> None:
        """Priorities have correct relative values."""
        assert AudioPriority.LOW.value < AudioPriority.NORMAL.value
        assert AudioPriority.NORMAL.value < AudioPriority.HIGH.value
        assert AudioPriority.HIGH.value < AudioPriority.CRITICAL.value

    def test_all_priorities_defined(self) -> None:
        """All expected priority levels exist."""
        priorities = [
            AudioPriority.LOW,
            AudioPriority.NORMAL,
            AudioPriority.HIGH,
            AudioPriority.CRITICAL,
        ]
        assert len(priorities) == 4


class TestAudioBusType:
    """Test AudioBusType enum."""

    def test_all_bus_types_defined(self) -> None:
        """All expected bus types exist."""
        bus_types = [
            AudioBusType.MASTER,
            AudioBusType.SFX,
            AudioBusType.MUSIC,
            AudioBusType.VOICE,
        ]
        assert len(bus_types) == 4


class TestAudioBus:
    """Test AudioBus dataclass."""

    def test_bus_creation(self) -> None:
        """AudioBus can be created with name."""
        bus = AudioBus("test_bus")
        assert bus.name == "test_bus"
        assert bus.volume == 1.0
        assert bus.muted is False
        assert bus.parent is None

    def test_bus_with_custom_values(self) -> None:
        """AudioBus accepts custom values."""
        bus = AudioBus(name="sfx", volume=0.8, muted=True, parent="master")
        assert bus.volume == 0.8
        assert bus.muted is True
        assert bus.parent == "master"

    def test_effective_volume_normal(self) -> None:
        """Effective volume equals volume when not muted."""
        bus = AudioBus("test", volume=0.5)
        assert bus.get_effective_volume() == 0.5

    def test_effective_volume_with_parent(self) -> None:
        """Effective volume considers parent volume."""
        bus = AudioBus("test", volume=0.5)
        effective = bus.get_effective_volume(parent_volume=0.8)
        assert effective == 0.4  # 0.5 * 0.8

    def test_effective_volume_muted(self) -> None:
        """Effective volume is 0 when muted."""
        bus = AudioBus("test", volume=0.5, muted=True)
        assert bus.get_effective_volume() == 0.0

    def test_effective_volume_muted_ignores_parent(self) -> None:
        """Muted bus returns 0 regardless of parent volume."""
        bus = AudioBus("test", volume=1.0, muted=True)
        assert bus.get_effective_volume(parent_volume=1.0) == 0.0


class TestSpatialAudioConfig:
    """Test SpatialAudioConfig and spatial calculations."""

    def test_default_config(self) -> None:
        """Default config has sensible values."""
        config = SpatialAudioConfig()
        assert config.max_distance == 1000.0
        assert config.reference_distance == 100.0
        assert config.rolloff_factor == 1.0
        assert config.pan_strength == 1.0

    def test_custom_config(self) -> None:
        """Custom config values are stored."""
        config = SpatialAudioConfig(
            max_distance=500.0,
            reference_distance=50.0,
            rolloff_factor=0.5,
            pan_strength=0.8,
        )
        assert config.max_distance == 500.0
        assert config.reference_distance == 50.0
        assert config.rolloff_factor == 0.5
        assert config.pan_strength == 0.8


class TestSpatialAudioAttenuation:
    """Test distance-based attenuation calculations."""

    @pytest.fixture
    def config(self) -> SpatialAudioConfig:
        """Create a standard config for testing."""
        return SpatialAudioConfig(
            max_distance=1000.0, reference_distance=100.0, rolloff_factor=1.0
        )

    def test_attenuation_at_reference_distance(
        self, config: SpatialAudioConfig
    ) -> None:
        """Full volume at reference distance."""
        attenuation = config.calculate_attenuation(100.0)
        assert attenuation == 1.0

    def test_attenuation_closer_than_reference(
        self, config: SpatialAudioConfig
    ) -> None:
        """Full volume when closer than reference distance."""
        attenuation = config.calculate_attenuation(50.0)
        assert attenuation == 1.0

    def test_attenuation_at_zero_distance(self, config: SpatialAudioConfig) -> None:
        """Full volume at zero distance."""
        attenuation = config.calculate_attenuation(0.0)
        assert attenuation == 1.0

    def test_attenuation_at_max_distance(self, config: SpatialAudioConfig) -> None:
        """Zero volume at max distance."""
        attenuation = config.calculate_attenuation(1000.0)
        assert attenuation == 0.0

    def test_attenuation_beyond_max_distance(self, config: SpatialAudioConfig) -> None:
        """Zero volume beyond max distance."""
        attenuation = config.calculate_attenuation(1500.0)
        assert attenuation == 0.0

    def test_attenuation_decreases_with_distance(
        self, config: SpatialAudioConfig
    ) -> None:
        """Attenuation decreases as distance increases."""
        att_200 = config.calculate_attenuation(200.0)
        att_400 = config.calculate_attenuation(400.0)
        att_600 = config.calculate_attenuation(600.0)

        assert att_200 > att_400 > att_600 > 0.0
        assert att_200 < 1.0

    def test_attenuation_clamped_to_valid_range(
        self, config: SpatialAudioConfig
    ) -> None:
        """Attenuation is always between 0 and 1."""
        for distance in [0, 50, 100, 200, 500, 800, 1000, 2000]:
            attenuation = config.calculate_attenuation(float(distance))
            assert 0.0 <= attenuation <= 1.0

    def test_rolloff_factor_affects_attenuation(self) -> None:
        """Higher rolloff factor = faster attenuation."""
        config_fast = SpatialAudioConfig(rolloff_factor=2.0)
        config_slow = SpatialAudioConfig(rolloff_factor=0.5)

        distance = 300.0
        att_fast = config_fast.calculate_attenuation(distance)
        att_slow = config_slow.calculate_attenuation(distance)

        assert att_fast < att_slow


class TestSpatialAudioPanning:
    """Test stereo panning calculations."""

    @pytest.fixture
    def config(self) -> SpatialAudioConfig:
        """Create a standard config for testing."""
        return SpatialAudioConfig(max_distance=1000.0, pan_strength=1.0)

    def test_pan_centered_when_same_position(self, config: SpatialAudioConfig) -> None:
        """Pan is centered when source and listener at same position."""
        listener = Vector2(100, 100)
        source = Vector2(100, 100)
        pan = config.calculate_pan(source, listener)
        assert pan == 0.0

    def test_pan_centered_when_very_close(self, config: SpatialAudioConfig) -> None:
        """Pan is centered when source is very close."""
        listener = Vector2(100, 100)
        source = Vector2(100.5, 100)
        pan = config.calculate_pan(source, listener)
        assert pan == 0.0

    def test_pan_right_when_source_to_right(self, config: SpatialAudioConfig) -> None:
        """Positive pan when source is to the right of listener."""
        listener = Vector2(0, 0)
        source = Vector2(500, 0)
        pan = config.calculate_pan(source, listener)
        assert pan > 0.0

    def test_pan_left_when_source_to_left(self, config: SpatialAudioConfig) -> None:
        """Negative pan when source is to the left of listener."""
        listener = Vector2(0, 0)
        source = Vector2(-500, 0)
        pan = config.calculate_pan(source, listener)
        assert pan < 0.0

    def test_pan_symmetry(self, config: SpatialAudioConfig) -> None:
        """Pan is symmetric for left and right."""
        listener = Vector2(0, 0)
        source_right = Vector2(300, 0)
        source_left = Vector2(-300, 0)

        pan_right = config.calculate_pan(source_right, listener)
        pan_left = config.calculate_pan(source_left, listener)

        assert abs(pan_right) == abs(pan_left)
        assert pan_right == -pan_left

    def test_pan_clamped_to_valid_range(self, config: SpatialAudioConfig) -> None:
        """Pan is always between -1 and 1."""
        listener = Vector2(0, 0)
        for x in [-2000, -1000, -500, 0, 500, 1000, 2000]:
            source = Vector2(x, 0)
            pan = config.calculate_pan(source, listener)
            assert -1.0 <= pan <= 1.0

    def test_pan_strength_affects_panning(self) -> None:
        """Pan strength scales the panning amount."""
        config_full = SpatialAudioConfig(pan_strength=1.0)
        config_half = SpatialAudioConfig(pan_strength=0.5)

        listener = Vector2(0, 0)
        source = Vector2(500, 0)

        pan_full = config_full.calculate_pan(source, listener)
        pan_half = config_half.calculate_pan(source, listener)

        assert abs(pan_full) > abs(pan_half)

    def test_pan_ignores_y_axis(self, config: SpatialAudioConfig) -> None:
        """Panning only considers horizontal position."""
        listener = Vector2(0, 0)
        source_high = Vector2(300, 500)
        source_low = Vector2(300, -500)

        pan_high = config.calculate_pan(source_high, listener)
        pan_low = config.calculate_pan(source_low, listener)

        # Same X distance means same pan
        assert pan_high == pan_low


class TestAudioBusManager:
    """Test AudioBusManager hierarchy."""

    def test_default_buses_created(self) -> None:
        """Default buses are created on initialization."""
        manager = AudioBusManager()

        assert "master" in manager.buses
        assert "sfx" in manager.buses
        assert "music" in manager.buses
        assert "voice" in manager.buses

    def test_default_hierarchy(self) -> None:
        """Default buses have correct parent relationships."""
        manager = AudioBusManager()

        assert manager.buses["master"].parent is None
        assert manager.buses["sfx"].parent == "master"
        assert manager.buses["music"].parent == "master"
        assert manager.buses["voice"].parent == "master"

    def test_get_bus(self) -> None:
        """Can retrieve bus by name."""
        manager = AudioBusManager()
        bus = manager.get_bus("sfx")
        assert bus is not None
        assert bus.name == "sfx"

    def test_get_nonexistent_bus(self) -> None:
        """Getting nonexistent bus returns None."""
        manager = AudioBusManager()
        bus = manager.get_bus("does_not_exist")
        assert bus is None

    def test_set_bus_volume(self) -> None:
        """Can set bus volume."""
        manager = AudioBusManager()
        manager.set_bus_volume("sfx", 0.5)
        assert manager.buses["sfx"].volume == 0.5

    def test_set_bus_volume_clamped(self) -> None:
        """Bus volume is clamped to 0-1."""
        manager = AudioBusManager()

        manager.set_bus_volume("sfx", 1.5)
        assert manager.buses["sfx"].volume == 1.0

        manager.set_bus_volume("sfx", -0.5)
        assert manager.buses["sfx"].volume == 0.0

    def test_set_bus_muted(self) -> None:
        """Can mute and unmute bus."""
        manager = AudioBusManager()

        manager.set_bus_muted("sfx", True)
        assert manager.buses["sfx"].muted is True

        manager.set_bus_muted("sfx", False)
        assert manager.buses["sfx"].muted is False

    def test_effective_volume_single_bus(self) -> None:
        """Effective volume for master bus equals its volume."""
        manager = AudioBusManager()
        manager.set_bus_volume("master", 0.8)
        assert manager.get_effective_volume("master") == 0.8

    def test_effective_volume_child_bus(self) -> None:
        """Child bus effective volume includes parent."""
        manager = AudioBusManager()
        manager.set_bus_volume("master", 0.8)
        manager.set_bus_volume("sfx", 0.5)

        effective = manager.get_effective_volume("sfx")
        assert effective == pytest.approx(0.4)  # 0.8 * 0.5

    def test_effective_volume_muted_parent(self) -> None:
        """Muted parent mutes all children."""
        manager = AudioBusManager()
        manager.set_bus_muted("master", True)

        assert manager.get_effective_volume("sfx") == 0.0
        assert manager.get_effective_volume("music") == 0.0

    def test_effective_volume_muted_child(self) -> None:
        """Muted child has zero volume."""
        manager = AudioBusManager()
        manager.set_bus_muted("sfx", True)

        assert manager.get_effective_volume("sfx") == 0.0
        assert manager.get_effective_volume("music") == 1.0  # Sibling unaffected

    def test_effective_volume_nonexistent_bus(self) -> None:
        """Nonexistent bus returns 1.0."""
        manager = AudioBusManager()
        assert manager.get_effective_volume("does_not_exist") == 1.0

    def test_get_bus_for_type(self) -> None:
        """Bus type enum maps to bus name."""
        manager = AudioBusManager()

        assert manager.get_bus_for_type(AudioBusType.MASTER) == "master"
        assert manager.get_bus_for_type(AudioBusType.SFX) == "sfx"
        assert manager.get_bus_for_type(AudioBusType.MUSIC) == "music"
        assert manager.get_bus_for_type(AudioBusType.VOICE) == "voice"


class TestPlayingSoundInfo:
    """Test PlayingSoundInfo dataclass."""

    def test_playing_sound_info_creation(self) -> None:
        """PlayingSoundInfo can be created."""
        info = PlayingSoundInfo(
            channel_id=0,
            clip_path="sounds/test.wav",
            priority=AudioPriority.NORMAL,
            bus=AudioBusType.SFX,
            base_volume=0.8,
        )
        assert info.channel_id == 0
        assert info.clip_path == "sounds/test.wav"
        assert info.priority == AudioPriority.NORMAL
        assert info.bus == AudioBusType.SFX
        assert info.base_volume == 0.8
        assert info.position is None
        assert info.is_spatial is False

    def test_spatial_sound_info(self) -> None:
        """PlayingSoundInfo for spatial sound."""
        pos = Vector2(100, 200)
        info = PlayingSoundInfo(
            channel_id=1,
            clip_path="sounds/explosion.wav",
            priority=AudioPriority.HIGH,
            bus=AudioBusType.SFX,
            base_volume=1.0,
            position=pos,
            is_spatial=True,
        )
        assert info.position == pos
        assert info.is_spatial is True
