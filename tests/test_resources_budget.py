"""The cache budget, LRU eviction, and the loaders that need no backend."""

from __future__ import annotations

from pathlib import Path

import pytest

from pyguara.resources import (
    BlobLoader,
    BlobResource,
    ResourceManager,
    TextLoader,
    TextResource,
)
from pyguara.resources.types import Resource, Texture


class FakeTexture(Texture):
    """A texture that knows its dimensions and nothing else."""

    def __init__(self, path: str, width: int = 64, height: int = 64) -> None:
        super().__init__(path)
        self._width = width
        self._height = height

    @property
    def width(self) -> int:
        return self._width

    @property
    def height(self) -> int:
        return self._height

    @property
    def native_handle(self) -> None:
        return None


class Unmeasurable(Resource):
    """A resource that cannot estimate its own size."""

    @property
    def native_handle(self) -> None:
        return None


# Every `.tex` is this size unless its name says otherwise, so a test can
# write its budget as a multiple of one texture and mean it.
TEXTURE_BYTES = 64 * 64 * 4


class FakeTextureLoader:
    """Hands back a 64x64 `FakeTexture`, or one sized by a `WxH` name."""

    @property
    def supported_extensions(self) -> list[str]:
        return [".tex"]

    def load(self, path: str) -> Resource:
        stem = Path(path).stem
        width, separator, height = stem.partition("x")
        if separator and width.isdigit() and height.isdigit():
            return FakeTexture(path, int(width), int(height))
        return FakeTexture(path, 64, 64)


class UnmeasurableLoader:
    @property
    def supported_extensions(self) -> list[str]:
        return [".blank"]

    def load(self, path: str) -> Resource:
        return Unmeasurable(path)


def _manager() -> ResourceManager:
    manager = ResourceManager()
    manager.register_loader(FakeTextureLoader())
    manager.register_loader(UnmeasurableLoader())
    return manager


# -- size_bytes --


def test_a_texture_estimates_four_bytes_a_pixel():
    assert FakeTexture("a.tex", 64, 32).size_bytes == 64 * 32 * 4


def test_a_resource_that_cannot_estimate_reports_zero():
    """Zero means unknown, not free."""
    assert Unmeasurable("a.blank").size_bytes == 0


def test_a_blob_knows_exactly_how_big_it_is():
    assert BlobResource("a.bin", b"12345").size_bytes == 5


def test_text_measures_its_encoded_length_not_its_characters():
    """A multi-byte character costs more than one byte, and the budget
    counts memory rather than characters."""
    resource = TextResource("a.glsl", "héllo")

    assert len(resource.text) == 5
    assert resource.size_bytes == 6


# -- The budget --


def test_without_a_budget_nothing_is_evicted():
    manager = _manager()
    for index in range(20):
        manager.load(f"tile_{index}.tex", Texture)

    assert manager.cache_budget_bytes is None
    assert manager.get_cache_stats()["resource_count"] == 20


def test_cache_size_bytes_sums_the_estimates():
    manager = _manager()
    manager.load("a.tex", Texture)
    manager.load("32x32.tex", Texture)

    assert manager.cache_size_bytes() == TEXTURE_BYTES + (32 * 32 * 4)


def test_loading_past_the_budget_evicts_the_oldest():
    manager = _manager()
    manager.set_cache_budget(TEXTURE_BYTES * 2)

    manager.load("a.tex", Texture)
    manager.load("b.tex", Texture)
    manager.load("c.tex", Texture)

    cached = dict(manager.iter_cached())
    assert "a.tex" not in cached
    assert sorted(cached) == ["b.tex", "c.tex"]


def test_the_resource_just_loaded_is_never_the_one_evicted():
    """Returning it and evicting it in the same call would hand the caller
    an object the cache no longer has, and the next load of the same path a
    second instance of it."""
    manager = _manager()
    manager.set_cache_budget(1)

    resource = manager.load("a.tex", Texture)

    assert "a.tex" in dict(manager.iter_cached())
    assert manager.load("a.tex", Texture) is resource


def test_a_cache_hit_counts_as_use():
    """Insertion order is only use order for a cache nothing has touched
    twice; `move_to_end` is what makes LRU mean anything."""
    manager = _manager()
    manager.set_cache_budget(TEXTURE_BYTES * 2)

    manager.load("a.tex", Texture)
    manager.load("b.tex", Texture)
    manager.load("a.tex", Texture)  # touch the older one
    manager.load("c.tex", Texture)

    cached = dict(manager.iter_cached())
    assert "a.tex" in cached
    assert "b.tex" not in cached


def test_a_pinned_resource_is_never_evicted():
    """`acquire()` means "I am using this"; evicting it anyway would hand
    the next load a second instance while the first is still being drawn."""
    manager = _manager()
    manager.load("a.tex", Texture)
    manager.acquire("a.tex")
    manager.load("b.tex", Texture)

    manager.set_cache_budget(1)

    cached = dict(manager.iter_cached())
    assert "a.tex" in cached
    assert "b.tex" not in cached


def test_a_budget_it_cannot_meet_is_reported_once(caplog):
    import logging

    manager = _manager()
    manager.load("pinned.tex", Texture)
    manager.acquire("pinned.tex")

    with caplog.at_level(logging.WARNING):
        manager.set_cache_budget(1)
        for index in range(5):
            manager.load(f"tile_{index}.tex", Texture)

    assert caplog.text.count("cannot shrink further") == 1


def test_an_unmeasurable_resource_is_left_alone():
    """Evicting something of unknown size frees an unknown amount, which is
    not a step towards a target."""
    manager = _manager()
    manager.load("a.blank", Resource)
    manager.load("a.tex", Texture)

    manager.set_cache_budget(1)

    assert "a.blank" in dict(manager.iter_cached())
    assert "a.tex" not in dict(manager.iter_cached())


def test_setting_a_budget_evicts_immediately_and_reports_how_many():
    manager = _manager()
    for index in range(4):
        manager.load(f"tile_{index}.tex", Texture)

    evicted = manager.set_cache_budget(TEXTURE_BYTES)

    assert evicted == 3
    assert manager.get_cache_stats()["resource_count"] == 1


def test_a_budget_of_zero_keeps_nothing_unpinned():
    """A real thing to want between levels."""
    manager = _manager()
    manager.load("a.tex", Texture)
    manager.load("b.tex", Texture)

    manager.set_cache_budget(0)

    assert manager.get_cache_stats()["resource_count"] == 0


def test_clearing_the_budget_stops_evicting():
    manager = _manager()
    manager.set_cache_budget(1)
    manager.set_cache_budget(None)

    for index in range(5):
        manager.load(f"tile_{index}.tex", Texture)

    assert manager.get_cache_stats()["resource_count"] == 5


def test_a_negative_budget_is_refused():
    with pytest.raises(ValueError, match="must not be negative"):
        _manager().set_cache_budget(-1)


def test_cache_stats_report_the_budget_and_the_total():
    manager = _manager()
    manager.load("a.tex", Texture)
    manager.set_cache_budget(10_000_000)

    stats = manager.get_cache_stats()

    assert stats["total_bytes"] == TEXTURE_BYTES
    assert stats["budget_bytes"] == 10_000_000
    assert stats["resources"]["a.tex"]["size_bytes"] == TEXTURE_BYTES


# -- The loaders --


def test_the_blob_loader_reads_bytes_verbatim(tmp_path: Path):
    path = tmp_path / "table.bin"
    path.write_bytes(bytes(range(256)))
    manager = ResourceManager()
    manager.register_loader(BlobLoader())

    resource = manager.load(str(path), BlobResource)

    assert resource.data == bytes(range(256))
    assert resource.native_handle is resource.data


def test_the_text_loader_decodes(tmp_path: Path):
    path = tmp_path / "sprite.vert"
    path.write_text("#version 330\nvoid main() {}\n")
    manager = ResourceManager()
    manager.register_loader(TextLoader())

    resource = manager.load(str(path), TextResource)

    assert resource.text.startswith("#version 330")
    assert resource.encoding == "utf-8"


def test_the_text_loader_claims_the_shader_stages():
    claimed = set(TextLoader().supported_extensions)

    assert {".vert", ".frag", ".glsl"} <= claimed


def test_neither_loader_claims_an_extension_a_real_loader_owns():
    """A blob loader claiming `.png` would quietly win the registration race
    and hand a texture request a pile of bytes."""
    claimed = set(BlobLoader().supported_extensions) | set(
        TextLoader().supported_extensions
    )

    assert not claimed & {".png", ".jpg", ".wav", ".ogg", ".json", ".tmx"}


def test_a_loader_can_be_given_its_own_extensions(tmp_path: Path):
    """A game that wants `.txt` registers this loader itself; claiming it
    engine-wide would make that choice for every game."""
    path = tmp_path / "intro.txt"
    path.write_text("once upon a time")
    manager = ResourceManager()
    manager.register_loader(TextLoader(extensions=(".txt",)))

    assert manager.load(str(path), TextResource).text == "once upon a time"


def test_a_blob_goes_through_the_whole_lifecycle(tmp_path: Path):
    """The point of putting these in the resource system at all: the index,
    the cache, the reference counting and the reload come with it."""
    path = tmp_path / "font.ttf"
    path.write_bytes(b"not really a font")
    manager = ResourceManager()
    manager.register_loader(BlobLoader())
    manager.index_directory(str(tmp_path))

    first = manager.load("font.ttf", BlobResource)
    manager.acquire("font.ttf")
    assert manager.load("font.ttf", BlobResource) is first

    path.write_bytes(b"a different font")
    reloaded = manager.reload("font.ttf")

    assert isinstance(reloaded, BlobResource)
    assert reloaded.data == b"a different font"
    manager.release("font.ttf")
