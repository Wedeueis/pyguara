"""Every engine loader reads from a mounted pack, with no loose files left.

The game folder is baked into a pack and then deleted, so a loader that
still opens files itself fails here rather than in a player's install.
"""

from __future__ import annotations

import json
import os
import shutil
import zipfile
from pathlib import Path

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame
import pytest

from pyguara import assets
from pyguara.audio.placeholder import sine, write_wav
from pyguara.resources.blob import BlobResource, TextResource
from pyguara.resources.data import DataResource
from pyguara.resources.loaders.blob_loader import BlobLoader, TextLoader
from pyguara.resources.loaders.data_loader import JsonLoader
from pyguara.resources.manager import ResourceManager
from pyguara.resources.meta import MetaLoader, TextureMeta
from pyguara.resources.types import AudioClip, Texture
from pyguara.ui.theme import UITheme

try:
    from pyguara import pyguara_core_rs as extension
except ImportError:  # pragma: no cover
    extension = None

needs_extension = pytest.mark.skipif(extension is None, reason="extension not built")

CAVE = Path(__file__).resolve().parents[2] / "games" / "tilemap_authoring" / "assets"


@pytest.fixture(autouse=True)
def _clean():
    yield
    assets.unmount_all()
    pygame.quit()


@pytest.fixture
def packed(tmp_path: Path, monkeypatch) -> Path:
    """Bake a game folder into a pack, delete the folder, mount the pack."""
    game = tmp_path / "game"
    (game / "assets" / "sprites").mkdir(parents=True)
    (game / "assets" / "sounds").mkdir()
    (game / "assets" / "data").mkdir()

    pygame.init()
    surface = pygame.Surface((4, 2), pygame.SRCALPHA)
    surface.fill((255, 0, 0, 255))
    pygame.image.save(surface, str(game / "assets" / "sprites" / "hero.png"))
    (game / "assets" / "sprites" / "hero.png.meta").write_text(
        json.dumps({"type": "texture", "filter": "linear"}), encoding="utf-8"
    )
    write_wav(game / "assets" / "sounds" / "beep.wav", sine(440, 0.05))
    (game / "assets" / "data" / "stats.json").write_text(
        '{"hp": 7, "name": "Guará"}', encoding="utf-8"
    )
    (game / "assets" / "data" / "glow.frag").write_text("// línea", encoding="utf-8")
    (game / "assets" / "data" / "blob.bin").write_bytes(b"\x00\x01")
    (game / "assets" / "data" / "crate.prefab.json").write_text(
        json.dumps({"name": "Crate", "components": {}}), encoding="utf-8"
    )
    (game / "assets" / "sprites" / "atlas.json").write_text(
        json.dumps(
            {"image": "hero.png", "regions": {"a": {"x": 0, "y": 0, "w": 2, "h": 2}}}
        ),
        encoding="utf-8",
    )

    shutil.copytree(CAVE, game / "assets" / "maps")
    (game / "assets" / "ui.theme.json").write_text(
        UITheme().to_json(), encoding="utf-8"
    )

    pack = tmp_path / "game.pak"
    with zipfile.ZipFile(pack, "w") as archive:
        for path in sorted(game.rglob("*")):
            if path.is_file():
                archive.write(path, path.relative_to(game).as_posix())
    shutil.rmtree(game)
    game.mkdir()  # an installed game: its folder, with nothing loose in it
    assets.mount_pack(pack, root=game)
    monkeypatch.chdir(game)
    return game


def _manager(*loaders: object) -> ResourceManager:
    manager = ResourceManager(meta_loader=MetaLoader())
    for loader in loaders:
        manager.register_loader(loader)  # type: ignore[arg-type]
    return manager


def test_data_text_and_blobs(packed: Path) -> None:
    manager = _manager(JsonLoader(), TextLoader(), BlobLoader())
    assert manager.load("assets/data/stats.json", DataResource).native_handle == {
        "hp": 7,
        "name": "Guará",
    }
    assert (
        manager.load("assets/data/glow.frag", TextResource).native_handle == "// línea"
    )
    assert (
        manager.load("assets/data/blob.bin", BlobResource).native_handle == b"\x00\x01"
    )


def test_the_folder_index_lists_packed_files(packed: Path) -> None:
    manager = _manager(JsonLoader())
    manager.index_directory("assets")
    assert manager.load("stats", DataResource).native_handle["hp"] == 7


def test_a_prefab(packed: Path) -> None:
    from pyguara.prefabs.loader import PrefabLoader

    prefab = PrefabLoader().load("assets/data/crate.prefab.json")
    assert prefab.data.name == "Crate"


def test_a_meta_file_is_read_from_the_pack(packed: Path) -> None:
    meta = MetaLoader().load_meta("assets/sprites/hero.png")
    assert isinstance(meta, TextureMeta)


def test_a_pygame_image(packed: Path) -> None:
    from pyguara.graphics.backends.pygame.loaders import PygameImageLoader

    manager = _manager(PygameImageLoader())
    texture = manager.load("assets/sprites/hero.png", Texture)
    assert (texture.width, texture.height) == (4, 2)


@needs_extension
def test_a_native_image(packed: Path) -> None:
    from pyguara.graphics.backends.wgpu.textures import NativeImageLoader

    manager = _manager(NativeImageLoader())
    texture = manager.load("assets/sprites/hero.png", Texture)
    assert (texture.width, texture.height) == (4, 2)
    assert texture.smooth, "the packed .meta file's filter was applied"


def test_a_pygame_sound(packed: Path) -> None:
    from pyguara.audio.backends.pygame.loaders import PygameSoundLoader

    pygame.mixer.init()
    manager = _manager(PygameSoundLoader())
    clip = manager.load("assets/sounds/beep.wav", AudioClip)
    assert clip.duration == pytest.approx(0.05, abs=0.01)


@needs_extension
def test_a_native_sound(packed: Path) -> None:
    from pyguara.audio.backends.native.loaders import NativeSoundLoader
    from pyguara.audio.backends.native.native_audio import NativeAudioSystem

    system = NativeAudioSystem(frequency=22050, output="offline")
    try:
        manager = _manager(NativeSoundLoader(system.mixer))
        clip = manager.load("assets/sounds/beep.wav", AudioClip)
        assert clip.duration == pytest.approx(0.05, abs=0.01)
    finally:
        system.shutdown()


@needs_extension
def test_native_music_plays_from_the_pack(packed: Path) -> None:
    from pyguara.audio.backends.native.native_audio import NativeAudioSystem

    system = NativeAudioSystem(frequency=22050, output="offline")
    try:
        system.play_music("assets/sounds/beep.wav", loop=False, fade_ms=0)
        for _ in range(200):
            system.mixer.render(64)
            if system.is_music_playing():
                break
        assert system.is_music_playing()
    finally:
        system.shutdown()


def test_a_sprite_sheet(packed: Path) -> None:
    from pyguara.graphics.backends.headless_renderer import HeadlessTextureFactory
    from pyguara.graphics.spritesheet import SpriteSheet

    sheet = SpriteSheet("assets/sprites/hero.png", HeadlessTextureFactory())
    assert sheet._image.size == (4, 2)


def test_nothing_was_read_from_disk(packed: Path) -> None:
    assert list(packed.iterdir()) == []
    assert assets.in_pack("assets/data/stats.json")


def test_a_tiled_map(packed: Path) -> None:
    from pyguara.tilemap import load_tmx

    tilemap = load_tmx("assets/maps/cerrado_cave.tmx")
    assert tilemap.layers


def test_a_theme(packed: Path) -> None:
    assert isinstance(UITheme.load("assets/ui.theme.json"), UITheme)
