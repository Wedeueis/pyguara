"""Tests for the asset metadata system.

Tests MetaLoader, TextureMeta, AudioMeta, SpritesheetMeta and related functionality.
"""

import json
import pytest
from pathlib import Path

from pyguara.resources.meta import (
    TextureFilter,
    AudioLoadMode,
    TextureMeta,
    AudioMeta,
    SpritesheetMeta,
    MetaLoader,
    META_TYPES,
    EXTENSION_TO_META_TYPE,
    get_meta_loader,
)


# =============================================================================
# Enum Tests
# =============================================================================


class TestTextureFilter:
    """Tests for TextureFilter enum."""

    def test_nearest_value(self) -> None:
        assert TextureFilter.NEAREST.value == "nearest"

    def test_linear_value(self) -> None:
        assert TextureFilter.LINEAR.value == "linear"

    def test_from_string(self) -> None:
        assert TextureFilter("nearest") == TextureFilter.NEAREST
        assert TextureFilter("linear") == TextureFilter.LINEAR


class TestAudioLoadMode:
    """Tests for AudioLoadMode enum."""

    def test_load_value(self) -> None:
        assert AudioLoadMode.LOAD.value == "load"

    def test_stream_value(self) -> None:
        assert AudioLoadMode.STREAM.value == "stream"

    def test_from_string(self) -> None:
        assert AudioLoadMode("load") == AudioLoadMode.LOAD
        assert AudioLoadMode("stream") == AudioLoadMode.STREAM


# =============================================================================
# Meta Type Tests
# =============================================================================


class TestTextureMeta:
    """Tests for TextureMeta dataclass."""

    def test_default_values(self) -> None:
        meta = TextureMeta()
        assert meta.version == 1
        assert meta.filter == "nearest"
        assert meta.mipmaps is False
        assert meta.premultiply_alpha is False
        assert meta.srgb is True
        assert meta.wrap_s == "clamp"
        assert meta.wrap_t == "clamp"

    def test_custom_values(self) -> None:
        meta = TextureMeta(
            filter="linear",
            mipmaps=True,
            premultiply_alpha=True,
            srgb=False,
            wrap_s="repeat",
            wrap_t="mirror",
        )
        assert meta.filter == "linear"
        assert meta.mipmaps is True
        assert meta.premultiply_alpha is True
        assert meta.srgb is False
        assert meta.wrap_s == "repeat"
        assert meta.wrap_t == "mirror"

    def test_get_filter_mode(self) -> None:
        meta_nearest = TextureMeta(filter="nearest")
        meta_linear = TextureMeta(filter="linear")
        assert meta_nearest.get_filter_mode() == TextureFilter.NEAREST
        assert meta_linear.get_filter_mode() == TextureFilter.LINEAR

    def test_to_dict(self) -> None:
        meta = TextureMeta()
        d = meta.to_dict()
        assert d["filter"] == "nearest"
        assert d["mipmaps"] is False
        assert d["version"] == 1

    def test_get_type_name(self) -> None:
        assert TextureMeta.get_type_name() == "texture"


class TestAudioMeta:
    """Tests for AudioMeta dataclass."""

    def test_default_values(self) -> None:
        meta = AudioMeta()
        assert meta.version == 1
        assert meta.load_mode == "load"
        assert meta.volume_db == 0.0
        assert meta.loop_start is None
        assert meta.loop_end is None
        assert meta.normalize is False

    def test_custom_values(self) -> None:
        meta = AudioMeta(
            load_mode="stream",
            volume_db=-6.0,
            loop_start=1.5,
            loop_end=30.0,
            normalize=True,
        )
        assert meta.load_mode == "stream"
        assert meta.volume_db == -6.0
        assert meta.loop_start == 1.5
        assert meta.loop_end == 30.0
        assert meta.normalize is True

    def test_get_load_mode(self) -> None:
        meta_load = AudioMeta(load_mode="load")
        meta_stream = AudioMeta(load_mode="stream")
        assert meta_load.get_load_mode() == AudioLoadMode.LOAD
        assert meta_stream.get_load_mode() == AudioLoadMode.STREAM

    def test_get_volume_multiplier_zero_db(self) -> None:
        meta = AudioMeta(volume_db=0.0)
        assert meta.get_volume_multiplier() == pytest.approx(1.0)

    def test_get_volume_multiplier_minus_6_db(self) -> None:
        meta = AudioMeta(volume_db=-6.0)
        # -6 dB ≈ 0.501
        assert meta.get_volume_multiplier() == pytest.approx(0.501, rel=0.01)

    def test_get_volume_multiplier_minus_20_db(self) -> None:
        meta = AudioMeta(volume_db=-20.0)
        # -20 dB = 0.1
        assert meta.get_volume_multiplier() == pytest.approx(0.1)

    def test_get_volume_multiplier_plus_6_db(self) -> None:
        meta = AudioMeta(volume_db=6.0)
        # +6 dB ≈ 1.995
        assert meta.get_volume_multiplier() == pytest.approx(1.995, rel=0.01)

    def test_to_dict(self) -> None:
        meta = AudioMeta(volume_db=-3.0)
        d = meta.to_dict()
        assert d["load_mode"] == "load"
        assert d["volume_db"] == -3.0

    def test_get_type_name(self) -> None:
        assert AudioMeta.get_type_name() == "audio"


class TestSpritesheetMeta:
    """Tests for SpritesheetMeta dataclass."""

    def test_default_values(self) -> None:
        meta = SpritesheetMeta()
        assert meta.version == 1
        assert meta.frame_width == 32
        assert meta.frame_height == 32
        assert meta.margin == 0
        assert meta.spacing == 0
        assert meta.filter == "nearest"

    def test_custom_values(self) -> None:
        meta = SpritesheetMeta(
            frame_width=64,
            frame_height=48,
            margin=2,
            spacing=1,
            filter="linear",
        )
        assert meta.frame_width == 64
        assert meta.frame_height == 48
        assert meta.margin == 2
        assert meta.spacing == 1
        assert meta.filter == "linear"

    def test_to_dict(self) -> None:
        meta = SpritesheetMeta(frame_width=16, frame_height=16)
        d = meta.to_dict()
        assert d["frame_width"] == 16
        assert d["frame_height"] == 16

    def test_get_type_name(self) -> None:
        assert SpritesheetMeta.get_type_name() == "spritesheet"


# =============================================================================
# Registry Tests
# =============================================================================


class TestMetaRegistry:
    """Tests for META_TYPES and EXTENSION_TO_META_TYPE registries."""

    def test_meta_types_registry(self) -> None:
        assert META_TYPES["texture"] == TextureMeta
        assert META_TYPES["audio"] == AudioMeta
        assert META_TYPES["spritesheet"] == SpritesheetMeta

    def test_extension_to_meta_type_textures(self) -> None:
        for ext in [".png", ".jpg", ".jpeg", ".bmp", ".tga", ".gif"]:
            assert EXTENSION_TO_META_TYPE[ext] == "texture"

    def test_extension_to_meta_type_audio(self) -> None:
        for ext in [".wav", ".ogg", ".mp3", ".flac"]:
            assert EXTENSION_TO_META_TYPE[ext] == "audio"


# =============================================================================
# MetaLoader Tests
# =============================================================================


class TestMetaLoaderBasics:
    """Basic MetaLoader functionality tests."""

    def test_init(self) -> None:
        loader = MetaLoader()
        assert loader._cache == {}

    def test_get_meta_path(self) -> None:
        loader = MetaLoader()
        path = loader.get_meta_path("assets/hero.png")
        assert path == Path("assets/hero.png.meta")

    def test_get_meta_path_with_spaces(self) -> None:
        loader = MetaLoader()
        path = loader.get_meta_path("assets/my hero.png")
        assert path == Path("assets/my hero.png.meta")

    def test_has_meta_exists(self, tmp_path: Path) -> None:
        loader = MetaLoader()
        asset_path = tmp_path / "test.png"
        meta_path = tmp_path / "test.png.meta"
        meta_path.write_text("{}")
        assert loader.has_meta(str(asset_path)) is True

    def test_has_meta_not_exists(self, tmp_path: Path) -> None:
        loader = MetaLoader()
        asset_path = tmp_path / "test.png"
        assert loader.has_meta(str(asset_path)) is False

    def test_clear_cache(self) -> None:
        loader = MetaLoader()
        loader._cache["test"] = TextureMeta()
        loader._cache["test2"] = AudioMeta()
        assert len(loader._cache) == 2
        loader.clear_cache()
        assert len(loader._cache) == 0


class TestMetaLoaderLoadMeta:
    """Tests for MetaLoader.load_meta()."""

    def test_load_meta_no_file(self, tmp_path: Path) -> None:
        loader = MetaLoader()
        asset_path = tmp_path / "test.png"
        result = loader.load_meta(str(asset_path))
        assert result is None

    def test_load_meta_texture(self, tmp_path: Path) -> None:
        loader = MetaLoader()
        asset_path = tmp_path / "test.png"
        meta_path = tmp_path / "test.png.meta"
        meta_path.write_text(
            json.dumps({"type": "texture", "filter": "linear", "mipmaps": True})
        )

        result = loader.load_meta(str(asset_path))
        assert isinstance(result, TextureMeta)
        assert result.filter == "linear"
        assert result.mipmaps is True

    def test_load_meta_audio(self, tmp_path: Path) -> None:
        loader = MetaLoader()
        asset_path = tmp_path / "test.ogg"
        meta_path = tmp_path / "test.ogg.meta"
        meta_path.write_text(
            json.dumps({"type": "audio", "load_mode": "stream", "volume_db": -3.0})
        )

        result = loader.load_meta(str(asset_path))
        assert isinstance(result, AudioMeta)
        assert result.load_mode == "stream"
        assert result.volume_db == -3.0

    def test_load_meta_spritesheet(self, tmp_path: Path) -> None:
        loader = MetaLoader()
        asset_path = tmp_path / "sprites.png"
        meta_path = tmp_path / "sprites.png.meta"
        meta_path.write_text(
            json.dumps({"type": "spritesheet", "frame_width": 64, "frame_height": 64})
        )

        result = loader.load_meta(str(asset_path))
        assert isinstance(result, SpritesheetMeta)
        assert result.frame_width == 64
        assert result.frame_height == 64

    def test_load_meta_infers_type_from_extension(self, tmp_path: Path) -> None:
        loader = MetaLoader()
        asset_path = tmp_path / "test.png"
        meta_path = tmp_path / "test.png.meta"
        # No "type" field - should infer from .png extension
        meta_path.write_text(json.dumps({"filter": "linear"}))

        result = loader.load_meta(str(asset_path))
        assert isinstance(result, TextureMeta)
        assert result.filter == "linear"

    def test_load_meta_infers_audio_type(self, tmp_path: Path) -> None:
        loader = MetaLoader()
        asset_path = tmp_path / "test.wav"
        meta_path = tmp_path / "test.wav.meta"
        meta_path.write_text(json.dumps({"volume_db": -6.0}))

        result = loader.load_meta(str(asset_path))
        assert isinstance(result, AudioMeta)
        assert result.volume_db == -6.0

    def test_load_meta_caches_result(self, tmp_path: Path) -> None:
        loader = MetaLoader()
        asset_path = tmp_path / "test.png"
        meta_path = tmp_path / "test.png.meta"
        meta_path.write_text(json.dumps({"type": "texture"}))

        result1 = loader.load_meta(str(asset_path))
        result2 = loader.load_meta(str(asset_path))
        assert result1 is result2
        assert str(asset_path) in loader._cache

    def test_load_meta_invalid_json(self, tmp_path: Path) -> None:
        loader = MetaLoader()
        asset_path = tmp_path / "test.png"
        meta_path = tmp_path / "test.png.meta"
        meta_path.write_text("not valid json {{{")

        result = loader.load_meta(str(asset_path))
        assert result is None

    def test_load_meta_unknown_type(self, tmp_path: Path) -> None:
        loader = MetaLoader()
        asset_path = tmp_path / "test.png"
        meta_path = tmp_path / "test.png.meta"
        meta_path.write_text(json.dumps({"type": "unknown_type"}))

        result = loader.load_meta(str(asset_path))
        assert result is None

    def test_load_meta_no_type_unknown_extension(self, tmp_path: Path) -> None:
        loader = MetaLoader()
        asset_path = tmp_path / "test.xyz"
        meta_path = tmp_path / "test.xyz.meta"
        meta_path.write_text(json.dumps({"filter": "linear"}))

        result = loader.load_meta(str(asset_path))
        assert result is None

    def test_load_meta_ignores_unknown_fields(self, tmp_path: Path) -> None:
        loader = MetaLoader()
        asset_path = tmp_path / "test.png"
        meta_path = tmp_path / "test.png.meta"
        meta_path.write_text(
            json.dumps(
                {"type": "texture", "filter": "linear", "unknown_field": "ignored"}
            )
        )

        result = loader.load_meta(str(asset_path))
        assert isinstance(result, TextureMeta)
        assert result.filter == "linear"
        assert not hasattr(result, "unknown_field")

    def test_load_meta_expected_type_warning(self, tmp_path: Path) -> None:
        loader = MetaLoader()
        asset_path = tmp_path / "test.png"
        meta_path = tmp_path / "test.png.meta"
        meta_path.write_text(json.dumps({"type": "texture"}))

        # Load with wrong expected type - should log warning but still return
        result = loader.load_meta(str(asset_path), expected_type=AudioMeta)
        assert isinstance(result, TextureMeta)


class TestMetaLoaderGetOrDefault:
    """Tests for MetaLoader.get_or_default()."""

    def test_get_or_default_returns_loaded(self, tmp_path: Path) -> None:
        loader = MetaLoader()
        asset_path = tmp_path / "test.png"
        meta_path = tmp_path / "test.png.meta"
        meta_path.write_text(json.dumps({"type": "texture", "filter": "linear"}))

        result = loader.get_or_default(str(asset_path), TextureMeta)
        assert result.filter == "linear"

    def test_get_or_default_returns_default_when_no_file(self, tmp_path: Path) -> None:
        loader = MetaLoader()
        asset_path = tmp_path / "test.png"

        result = loader.get_or_default(str(asset_path), TextureMeta)
        assert result.filter == "nearest"  # Default value

    def test_get_or_default_returns_default_on_type_mismatch(
        self, tmp_path: Path
    ) -> None:
        loader = MetaLoader()
        asset_path = tmp_path / "test.png"
        meta_path = tmp_path / "test.png.meta"
        meta_path.write_text(json.dumps({"type": "audio"}))

        result = loader.get_or_default(str(asset_path), TextureMeta)
        # Should return default TextureMeta since loaded AudioMeta doesn't match
        assert isinstance(result, TextureMeta)
        assert result.filter == "nearest"


class TestMetaLoaderSaveMeta:
    """Tests for MetaLoader.save_meta()."""

    def test_save_meta_creates_file(self, tmp_path: Path) -> None:
        loader = MetaLoader()
        asset_path = tmp_path / "test.png"
        meta = TextureMeta(filter="linear", mipmaps=True)

        result = loader.save_meta(str(asset_path), meta)
        assert result is True

        meta_path = tmp_path / "test.png.meta"
        assert meta_path.exists()

        data = json.loads(meta_path.read_text())
        assert data["type"] == "texture"
        assert data["filter"] == "linear"
        assert data["mipmaps"] is True

    def test_save_meta_updates_cache(self, tmp_path: Path) -> None:
        loader = MetaLoader()
        asset_path = tmp_path / "test.png"
        meta = TextureMeta(filter="linear")

        loader.save_meta(str(asset_path), meta)
        assert str(asset_path) in loader._cache
        assert loader._cache[str(asset_path)] is meta

    def test_save_meta_audio(self, tmp_path: Path) -> None:
        loader = MetaLoader()
        asset_path = tmp_path / "test.ogg"
        meta = AudioMeta(load_mode="stream", volume_db=-6.0)

        result = loader.save_meta(str(asset_path), meta)
        assert result is True

        meta_path = tmp_path / "test.ogg.meta"
        data = json.loads(meta_path.read_text())
        assert data["type"] == "audio"
        assert data["load_mode"] == "stream"
        assert data["volume_db"] == -6.0

    def test_save_meta_overwrites_existing(self, tmp_path: Path) -> None:
        loader = MetaLoader()
        asset_path = tmp_path / "test.png"
        meta_path = tmp_path / "test.png.meta"

        # Create existing meta
        meta_path.write_text(json.dumps({"type": "texture", "filter": "nearest"}))

        # Save new meta
        new_meta = TextureMeta(filter="linear")
        loader.save_meta(str(asset_path), new_meta)

        data = json.loads(meta_path.read_text())
        assert data["filter"] == "linear"


class TestMetaLoaderRoundtrip:
    """Tests for save/load roundtrip integrity."""

    def test_roundtrip_texture_meta(self, tmp_path: Path) -> None:
        loader = MetaLoader()
        asset_path = tmp_path / "test.png"
        original = TextureMeta(
            filter="linear",
            mipmaps=True,
            premultiply_alpha=True,
            srgb=False,
            wrap_s="repeat",
            wrap_t="mirror",
        )

        loader.save_meta(str(asset_path), original)
        loader.clear_cache()  # Force reload from disk
        loaded = loader.load_meta(str(asset_path))

        assert isinstance(loaded, TextureMeta)
        assert loaded.filter == original.filter
        assert loaded.mipmaps == original.mipmaps
        assert loaded.premultiply_alpha == original.premultiply_alpha
        assert loaded.srgb == original.srgb
        assert loaded.wrap_s == original.wrap_s
        assert loaded.wrap_t == original.wrap_t

    def test_roundtrip_audio_meta(self, tmp_path: Path) -> None:
        loader = MetaLoader()
        asset_path = tmp_path / "test.ogg"
        original = AudioMeta(
            load_mode="stream",
            volume_db=-12.0,
            loop_start=5.0,
            loop_end=120.0,
            normalize=True,
        )

        loader.save_meta(str(asset_path), original)
        loader.clear_cache()
        loaded = loader.load_meta(str(asset_path))

        assert isinstance(loaded, AudioMeta)
        assert loaded.load_mode == original.load_mode
        assert loaded.volume_db == original.volume_db
        assert loaded.loop_start == original.loop_start
        assert loaded.loop_end == original.loop_end
        assert loaded.normalize == original.normalize

    def test_roundtrip_spritesheet_meta(self, tmp_path: Path) -> None:
        loader = MetaLoader()
        asset_path = tmp_path / "sprites.png"
        original = SpritesheetMeta(
            frame_width=64,
            frame_height=48,
            margin=2,
            spacing=1,
            filter="linear",
        )

        loader.save_meta(str(asset_path), original)
        loader.clear_cache()
        loaded = loader.load_meta(str(asset_path))

        assert isinstance(loaded, SpritesheetMeta)
        assert loaded.frame_width == original.frame_width
        assert loaded.frame_height == original.frame_height
        assert loaded.margin == original.margin
        assert loaded.spacing == original.spacing
        assert loaded.filter == original.filter


# =============================================================================
# Singleton Tests
# =============================================================================


class TestGetMetaLoader:
    """Tests for get_meta_loader() singleton."""

    def test_returns_meta_loader(self) -> None:
        loader = get_meta_loader()
        assert isinstance(loader, MetaLoader)

    def test_returns_same_instance(self) -> None:
        loader1 = get_meta_loader()
        loader2 = get_meta_loader()
        assert loader1 is loader2
