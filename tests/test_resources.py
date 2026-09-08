"""Tests for pyguara.resources.manager.ResourceManager.

Lifecycle model under test (see ResourceManager docstring):
    - load() is a cache-get; the resource enters the cache unpinned (count 0).
    - acquire()/release() are the explicit pin API and must be balanced.
    - unload_unused() evicts everything at count 0.
    - reload() re-reads a cached resource and swaps it in place.
"""

import json
from pathlib import Path

import pytest

from pyguara.resources.data import DataResource
from pyguara.resources.loaders.data_loader import JsonLoader
from pyguara.resources.manager import ResourceManager
from pyguara.resources.meta import AssetMeta, TextureMeta
from pyguara.resources.types import Resource


class MockRes(Resource):
    """Minimal concrete Resource for cache/lifecycle tests."""

    @property
    def native_handle(self) -> str:
        return "mock"


class MockLoader:
    """A loader that fabricates a MockRes without touching the disk."""

    def __init__(self) -> None:
        self.load_calls = 0

    @property
    def supported_extensions(self) -> list[str]:
        return [".mock"]

    def load(self, path: str) -> MockRes:
        self.load_calls += 1
        return MockRes(path)


class MetaMockLoader(MockLoader):
    """MockLoader that also implements the meta-aware protocol."""

    def __init__(self) -> None:
        super().__init__()
        self.seen_meta: AssetMeta | None = None

    def load_with_meta(self, path: str, meta: AssetMeta | None) -> MockRes:
        self.seen_meta = meta
        self.load_calls += 1
        return MockRes(path)


def _mgr(*loaders: object) -> ResourceManager:
    manager = ResourceManager()
    for loader in loaders or (MockLoader(),):
        manager.register_loader(loader)  # type: ignore[arg-type]
    return manager


# --------------------------------------------------------------------------
# Loading, caching, type safety
# --------------------------------------------------------------------------


def test_load_caches_by_path() -> None:
    loader = MockLoader()
    manager = _mgr(loader)

    res1 = manager.load("file.mock", MockRes)
    res2 = manager.load("file.mock", MockRes)

    assert res1 is res2
    assert loader.load_calls == 1  # second call served from cache


def test_load_resolves_indexed_name(tmp_path: Path) -> None:
    (tmp_path / "hero.mock").write_text("x")
    manager = _mgr()
    manager.index_directory(str(tmp_path))

    res = manager.load("hero", MockRes)
    assert res.path == str(tmp_path / "hero.mock")


def test_load_wrong_type_raises_on_miss() -> None:
    manager = _mgr()

    class OtherRes(Resource):
        @property
        def native_handle(self) -> None:
            return None

    with pytest.raises(TypeError):
        manager.load("file.mock", OtherRes)


def test_load_wrong_type_raises_on_cache_hit() -> None:
    manager = _mgr()
    manager.load("file.mock", MockRes)

    class OtherRes(Resource):
        @property
        def native_handle(self) -> None:
            return None

    with pytest.raises(TypeError, match="cached as MockRes"):
        manager.load("file.mock", OtherRes)


def test_load_unknown_extension_raises() -> None:
    manager = _mgr()
    with pytest.raises(ValueError, match="No loader registered"):
        manager.load("file.unknown", MockRes)


def test_register_loader_warns_on_extension_clash(
    caplog: pytest.LogCaptureFixture,
) -> None:
    manager = ResourceManager()
    manager.register_loader(MockLoader())
    with caplog.at_level("WARNING"):
        manager.register_loader(MockLoader())
    assert any("Overwriting loader" in r.message for r in caplog.records)


# --------------------------------------------------------------------------
# index_directory
# --------------------------------------------------------------------------


def test_index_directory_recursive(tmp_path: Path) -> None:
    (tmp_path / "a").mkdir()
    (tmp_path / "a" / "hero.mock").write_text("x")
    (tmp_path / "sword.mock").write_text("x")
    manager = _mgr()

    manager.index_directory(str(tmp_path))

    assert manager.load("hero", MockRes).path.endswith("a/hero.mock")
    assert manager.load("sword.mock", MockRes).path.endswith("sword.mock")


def test_index_directory_non_recursive_skips_subdirs(tmp_path: Path) -> None:
    (tmp_path / "a").mkdir()
    (tmp_path / "a" / "deep.mock").write_text("x")
    manager = _mgr()

    manager.index_directory(str(tmp_path), recursive=False)

    with pytest.raises(ValueError):
        manager.load("deep", MockRes)  # never indexed -> no extension match...


def test_index_directory_ambiguous_stem_is_dropped_with_warning(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    (tmp_path / "enemies").mkdir()
    (tmp_path / "npcs").mkdir()
    (tmp_path / "enemies" / "goblin.mock").write_text("enemy")
    (tmp_path / "npcs" / "goblin.mock").write_text("npc")
    manager = _mgr()

    with caplog.at_level("WARNING"):
        manager.index_directory(str(tmp_path))

    assert any("Ambiguous asset name 'goblin'" in r.message for r in caplog.records)
    # The bare stem is refused...
    assert "goblin" not in manager._path_index
    # ...but each unambiguous full name still resolves to its own file.
    g1 = manager.load(str(tmp_path / "enemies" / "goblin.mock"), MockRes)
    assert Path(g1.path).read_text() == "enemy"


def test_index_directory_same_file_twice_is_not_ambiguous(tmp_path: Path) -> None:
    (tmp_path / "hero.mock").write_text("x")
    manager = _mgr()

    manager.index_directory(str(tmp_path))
    manager.index_directory(str(tmp_path))  # re-scan must not self-collide

    assert "hero" in manager._path_index


# --------------------------------------------------------------------------
# Reference counting: load does NOT pin
# --------------------------------------------------------------------------


def test_load_leaves_resource_unpinned() -> None:
    manager = _mgr()
    manager.load("a.mock", MockRes)
    manager.load("a.mock", MockRes)  # repeated load must not accumulate

    stats = manager.get_cache_stats()
    assert stats["resources"]["a.mock"]["ref_count"] == 0


def test_acquire_and_release_balance() -> None:
    manager = _mgr()
    manager.load("a.mock", MockRes)

    manager.acquire("a.mock")
    manager.acquire("a.mock")
    assert manager.get_cache_stats()["resources"]["a.mock"]["ref_count"] == 2

    manager.release("a.mock")
    assert "a.mock" in manager.get_cache_stats()["resources"]

    manager.release("a.mock")  # back to 0 -> evicted
    assert "a.mock" not in manager.get_cache_stats()["resources"]


def test_release_without_acquire_raises() -> None:
    manager = _mgr()
    manager.load("a.mock", MockRes)
    with pytest.raises(ValueError, match="already zero"):
        manager.release("a.mock")


def test_acquire_unloaded_raises() -> None:
    manager = _mgr()
    with pytest.raises(KeyError, match="Cannot acquire"):
        manager.acquire("ghost.mock")


def test_release_unloaded_raises() -> None:
    manager = _mgr()
    with pytest.raises(KeyError, match="Cannot release"):
        manager.release("ghost.mock")


# --------------------------------------------------------------------------
# unload / unload_unused
# --------------------------------------------------------------------------


def test_unload_unused_sweeps_everything_not_acquired() -> None:
    manager = _mgr()
    manager.load("a.mock", MockRes)
    manager.load("b.mock", MockRes)
    manager.load("c.mock", MockRes)
    manager.acquire("b.mock")  # pin one

    freed = manager.unload_unused()

    assert freed == 2
    remaining = manager.get_cache_stats()["resources"]
    assert set(remaining) == {"b.mock"}


def test_unload_force_evicts_pinned_resource() -> None:
    manager = _mgr()
    manager.load("a.mock", MockRes)
    manager.acquire("a.mock")

    manager.unload("a.mock", force=True)

    assert "a.mock" not in manager.get_cache_stats()["resources"]


def test_unload_without_force_decrements_a_pinned_resource() -> None:
    manager = _mgr()
    manager.load("a.mock", MockRes)
    manager.acquire("a.mock")
    manager.acquire("a.mock")

    manager.unload("a.mock")  # 2 -> 1, still cached
    assert manager.get_cache_stats()["resources"]["a.mock"]["ref_count"] == 1

    manager.unload("a.mock")  # 1 -> 0 -> evicted
    assert "a.mock" not in manager.get_cache_stats()["resources"]


def test_unload_missing_resource_is_a_noop() -> None:
    manager = _mgr()
    manager.unload("ghost.mock")  # must not raise


# --------------------------------------------------------------------------
# reload
# --------------------------------------------------------------------------


def test_reload_swaps_the_cached_instance_and_keeps_refcount(tmp_path: Path) -> None:
    path = tmp_path / "data.json"
    path.write_text(json.dumps({"hp": 10}))
    manager = ResourceManager()
    manager.register_loader(JsonLoader())

    first = manager.load(str(path), DataResource)
    manager.acquire(str(path))
    assert first.native_handle == {"hp": 10}

    path.write_text(json.dumps({"hp": 99}))
    second = manager.reload(str(path))

    assert second is not first
    assert second.native_handle == {"hp": 99}
    assert manager.load(str(path), DataResource) is second  # cache updated
    assert manager.get_cache_stats()["resources"][str(path)]["ref_count"] == 1


def test_reload_uncached_raises() -> None:
    manager = _mgr()
    with pytest.raises(KeyError, match="not loaded"):
        manager.reload("never.mock")


def test_reload_picks_up_changed_meta(tmp_path: Path) -> None:
    img = tmp_path / "hero.mock"
    img.write_text("x")
    meta = tmp_path / "hero.mock.meta"
    meta.write_text(json.dumps({"type": "texture", "filter": "linear"}))
    loader = MetaMockLoader()
    manager = _mgr(loader)

    manager.load(str(img), MockRes)
    assert isinstance(loader.seen_meta, TextureMeta)
    assert loader.seen_meta.filter == "linear"

    meta.write_text(json.dumps({"type": "texture", "filter": "nearest"}))
    manager.reload(str(img))

    assert isinstance(loader.seen_meta, TextureMeta)
    assert loader.seen_meta.filter == "nearest"


# --------------------------------------------------------------------------
# Meta-aware loading through the manager
# --------------------------------------------------------------------------


def test_meta_aware_loader_receives_and_attaches_meta(tmp_path: Path) -> None:
    img = tmp_path / "hero.mock"
    img.write_text("x")
    (tmp_path / "hero.mock.meta").write_text(
        json.dumps({"type": "texture", "filter": "linear"})
    )
    loader = MetaMockLoader()
    manager = _mgr(loader)

    res = manager.load(str(img), MockRes)

    assert isinstance(loader.seen_meta, TextureMeta)
    assert isinstance(res.import_meta, TextureMeta)
    assert res.import_meta.filter == "linear"


def test_meta_aware_loader_without_sidecar_gets_none(tmp_path: Path) -> None:
    img = tmp_path / "hero.mock"
    img.write_text("x")
    loader = MetaMockLoader()
    manager = _mgr(loader)

    res = manager.load(str(img), MockRes)

    assert loader.seen_meta is None
    assert res.import_meta is None


# --------------------------------------------------------------------------
# get_cache_stats
# --------------------------------------------------------------------------


def test_cache_stats_shape() -> None:
    manager = _mgr()
    manager.load("a.mock", MockRes)
    manager.load("b.mock", MockRes)
    manager.acquire("a.mock")

    stats = manager.get_cache_stats()

    assert stats["resource_count"] == 2
    assert stats["total_references"] == 1
    assert stats["resources"]["a.mock"] == {"type": "MockRes", "ref_count": 1}
    assert stats["resources"]["b.mock"]["ref_count"] == 0


# --------------------------------------------------------------------------
# Read-only browse accessors
# --------------------------------------------------------------------------


def test_iter_indexed_yields_name_path_pairs(tmp_path: Path) -> None:
    (tmp_path / "hero.mock").write_text("x")
    manager = _mgr()
    manager.index_directory(str(tmp_path))

    indexed = dict(manager.iter_indexed())

    assert indexed["hero"] == str(tmp_path / "hero.mock")
    assert indexed["hero.mock"] == str(tmp_path / "hero.mock")


def test_iter_indexed_is_empty_before_indexing() -> None:
    assert list(_mgr().iter_indexed()) == []


def test_iter_cached_yields_live_resource_objects() -> None:
    manager = _mgr()
    res = manager.load("a.mock", MockRes)

    cached = dict(manager.iter_cached())

    assert cached == {"a.mock": res}
    assert cached["a.mock"] is res


def test_iter_cached_snapshot_survives_unload_during_iteration() -> None:
    manager = _mgr()
    manager.load("a.mock", MockRes)
    manager.load("b.mock", MockRes)

    seen = []
    for path, _res in manager.iter_cached():
        seen.append(path)
        manager.unload(path, force=True)

    assert sorted(seen) == ["a.mock", "b.mock"]
    assert list(manager.iter_cached()) == []
