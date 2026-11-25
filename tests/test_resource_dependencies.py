"""A resource loaded while another loads is its dependency.

A dependency stays cached while a resource built from it does, and
reloading it rebuilds what depends on it.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from pyguara import assets
from pyguara.dev.asset_reload import AssetReloadWatcher
from pyguara.graphics.atlas import Atlas
from pyguara.resources.exceptions import ResourceLoadError
from pyguara.resources.manager import ResourceManager
from pyguara.resources.types import Resource, Texture


class _Leaf(Resource):
    """A file's text, with a size so the budget can count it."""

    def __init__(self, path: str, text: str) -> None:
        super().__init__(path)
        self.text = text

    @property
    def native_handle(self) -> Any:
        return self.text

    @property
    def size_bytes(self) -> int:
        return 100


class _LeafLoader:
    @property
    def supported_extensions(self) -> list[str]:
        return [".leaf"]

    def load(self, path: str) -> Resource:
        return _Leaf(path, assets.read_text(path))


class _Pack(Resource):
    """The resources a `.pack` file names, one per line."""

    def __init__(self, path: str, parts: list[Resource]) -> None:
        super().__init__(path)
        self.parts = parts

    @property
    def native_handle(self) -> Any:
        return self.parts


class _PackLoader:
    def __init__(self, manager: ResourceManager) -> None:
        self._manager = manager

    @property
    def supported_extensions(self) -> list[str]:
        return [".pack"]

    def load(self, path: str) -> Resource:
        folder = Path(path).parent
        names = assets.read_text(path).split()
        parts = [self._manager.load(str(folder / name), Resource) for name in names]
        return _Pack(path, parts)


def _manager() -> ResourceManager:
    manager = ResourceManager()
    manager.register_loader(_LeafLoader())
    manager.register_loader(_PackLoader(manager))
    return manager


def _write(directory: Path, name: str, text: str) -> str:
    path = directory / name
    path.write_text(text)
    return str(path)


# ===== Recording =====


def test_a_resource_loaded_during_a_load_is_a_dependency(tmp_path: Path) -> None:
    leaf = _write(tmp_path, "a.leaf", "a")
    pack = _write(tmp_path, "p.pack", "a.leaf")
    manager = _manager()

    manager.load(pack, _Pack)

    assert manager.dependencies_of(pack) == [leaf]
    assert manager.dependents_of(leaf) == [pack]


def test_a_dependency_already_cached_is_recorded_too(tmp_path: Path) -> None:
    leaf = _write(tmp_path, "a.leaf", "a")
    pack = _write(tmp_path, "p.pack", "a.leaf")
    manager = _manager()
    manager.load(leaf, _Leaf)

    manager.load(pack, _Pack)

    assert manager.dependencies_of(pack) == [leaf]


def test_a_load_outside_any_other_records_nothing(tmp_path: Path) -> None:
    leaf = _write(tmp_path, "a.leaf", "a")
    manager = _manager()

    manager.load(leaf, _Leaf)

    assert manager.dependencies_of(leaf) == []
    assert manager.dependents_of(leaf) == []


def test_a_resource_that_depends_on_itself_raises(tmp_path: Path) -> None:
    first = _write(tmp_path, "a.pack", "b.pack")
    _write(tmp_path, "b.pack", "a.pack")
    manager = _manager()

    with pytest.raises(ResourceLoadError, match="depends on itself"):
        manager.load(first, _Pack)

    assert manager.get_cache_stats()["resource_count"] == 0


def test_a_failed_load_leaves_its_dependencies_free(tmp_path: Path) -> None:
    _write(tmp_path, "a.leaf", "a")
    pack = _write(tmp_path, "p.pack", "a.leaf missing.leaf")
    manager = _manager()

    with pytest.raises(ResourceLoadError):
        manager.load(pack, _Pack)

    assert manager.unload_unused() == 1


# ===== Holding =====


def test_a_dependency_outlives_unload_unused_while_its_dependent_is_cached(
    tmp_path: Path,
) -> None:
    leaf = _write(tmp_path, "a.leaf", "a")
    pack = _write(tmp_path, "p.pack", "a.leaf")
    manager = _manager()
    manager.load(pack, _Pack)
    manager.acquire(pack)

    assert manager.unload_unused() == 0

    manager.release(pack)
    manager.unload_unused()
    assert [key for key, _ in manager.iter_cached()] == []
    assert manager.dependents_of(leaf) == []


def test_the_budget_does_not_evict_a_dependency_in_use(tmp_path: Path) -> None:
    leaf = _write(tmp_path, "a.leaf", "a")
    pack = _write(tmp_path, "p.pack", "a.leaf")
    manager = _manager()
    manager.load(pack, _Pack)

    manager.set_cache_budget(0)

    assert leaf in dict(manager.iter_cached())


def test_releasing_a_dependency_to_zero_keeps_it_for_its_dependent(
    tmp_path: Path,
) -> None:
    leaf = _write(tmp_path, "a.leaf", "a")
    pack = _write(tmp_path, "p.pack", "a.leaf")
    manager = _manager()
    manager.load(pack, _Pack)
    manager.acquire(leaf)

    manager.release(leaf)
    manager.unload(leaf)

    assert leaf in dict(manager.iter_cached())


def test_a_forced_unload_evicts_a_dependency_anyway(tmp_path: Path) -> None:
    leaf = _write(tmp_path, "a.leaf", "a")
    pack = _write(tmp_path, "p.pack", "a.leaf")
    manager = _manager()
    manager.load(pack, _Pack)

    manager.unload(leaf, force=True)

    assert leaf not in dict(manager.iter_cached())


# ===== Reloading =====


def test_reloading_a_dependency_rebuilds_what_depends_on_it(tmp_path: Path) -> None:
    leaf = _write(tmp_path, "a.leaf", "old")
    pack = _write(tmp_path, "p.pack", "a.leaf")
    manager = _manager()
    manager.load(pack, _Pack)

    Path(leaf).write_text("new", encoding="utf-8")
    manager.reload(leaf)

    rebuilt = manager.load(pack, _Pack)
    assert [part.native_handle for part in rebuilt.parts] == ["new"]
    assert rebuilt.parts[0] is manager.load(leaf, _Leaf)


def test_dependents_reload_after_everything_they_depend_on(tmp_path: Path) -> None:
    leaf = _write(tmp_path, "a.leaf", "a")
    inner = _write(tmp_path, "inner.pack", "a.leaf")
    outer = _write(tmp_path, "outer.pack", "inner.pack a.leaf")
    manager = _manager()
    manager.load(outer, _Pack)

    assert manager.dependents_of(leaf) == [inner, outer]

    manager.reload(leaf)
    rebuilt = manager.load(outer, _Pack)
    assert rebuilt.parts[0] is manager.load(inner, _Pack)


def test_a_reloaded_resource_records_what_it_depends_on_now(tmp_path: Path) -> None:
    _write(tmp_path, "a.leaf", "a")
    second = _write(tmp_path, "b.leaf", "b")
    pack = _write(tmp_path, "p.pack", "a.leaf")
    manager = _manager()
    manager.load(pack, _Pack)

    Path(pack).write_text("b.leaf", encoding="utf-8")
    manager.reload(pack)

    assert manager.dependencies_of(pack) == [second]


def test_a_reload_that_fails_keeps_what_it_depended_on(tmp_path: Path) -> None:
    leaf = _write(tmp_path, "a.leaf", "a")
    pack = _write(tmp_path, "p.pack", "a.leaf")
    manager = _manager()
    manager.load(pack, _Pack)

    Path(pack).write_text("missing.leaf", encoding="utf-8")
    with pytest.raises(ResourceLoadError):
        manager.reload(pack)

    assert manager.dependencies_of(pack) == [leaf]


def test_the_reload_watcher_reports_the_dependents_it_rebuilt(tmp_path: Path) -> None:
    leaf = _write(tmp_path, "a.leaf", "a")
    pack = _write(tmp_path, "p.pack", "a.leaf")
    manager = _manager()
    manager.load(pack, _Pack)
    watcher = AssetReloadWatcher(manager)
    watcher.refresh()

    watcher._on_file_changed(str(Path(leaf).resolve()))

    assert watcher.drain() == [leaf, pack]


# ===== Built resources =====


def test_build_caches_what_it_builds(tmp_path: Path) -> None:
    leaf = _write(tmp_path, "a.leaf", "a")
    manager = _manager()
    calls = []

    def build() -> Resource:
        calls.append(1)
        return _Pack("level", [manager.load(leaf, _Leaf)])

    first = manager.build("level", _Pack, build)
    second = manager.build("level", _Pack, build)

    assert first is second
    assert calls == [1]
    assert manager.dependencies_of("level") == [leaf]


def test_a_built_resource_is_rebuilt_when_a_dependency_reloads(tmp_path: Path) -> None:
    leaf = _write(tmp_path, "a.leaf", "old")
    manager = _manager()
    manager.build("level", _Pack, lambda: _Pack("level", [manager.load(leaf, _Leaf)]))

    Path(leaf).write_text("new", encoding="utf-8")
    manager.reload(leaf)

    level = manager.build("level", _Pack, lambda: pytest.fail("cached"))
    assert level.parts[0].native_handle == "new"


def test_build_refuses_a_result_of_the_wrong_type(tmp_path: Path) -> None:
    manager = _manager()

    with pytest.raises(TypeError, match="_Leaf"):
        manager.build("level", _Pack, lambda: _Leaf("level", "x"))

    assert manager.get_cache_stats()["resource_count"] == 0


# ===== Atlases =====


class _Image(Texture):
    def __init__(self, path: str, text: str) -> None:
        super().__init__(path)
        self.text = text

    @property
    def native_handle(self) -> Any:
        return self.text

    @property
    def width(self) -> int:
        return 16

    @property
    def height(self) -> int:
        return 16


class _ImageLoader:
    @property
    def supported_extensions(self) -> list[str]:
        return [".png"]

    def load(self, path: str) -> Resource:
        return _Image(path, assets.read_text(path))


def _atlas(directory: Path) -> tuple[str, str, ResourceManager]:
    image = _write(directory, "sheet.png", "v1")
    metadata = _write(
        directory,
        "sheet.json",
        json.dumps(
            {
                "regions": {
                    "hero": {
                        "x": 0,
                        "y": 0,
                        "width": 8,
                        "height": 8,
                        "original_size": [8, 8],
                    }
                }
            }
        ),
    )
    manager = ResourceManager()
    manager.register_loader(_ImageLoader())
    return image, metadata, manager


def test_an_atlas_is_cached_and_holds_its_pages(tmp_path: Path) -> None:
    image, metadata, manager = _atlas(tmp_path)

    atlas = manager.load_atlas(image, metadata)

    assert manager.load_atlas(image, metadata) is atlas
    assert manager.dependencies_of(metadata) == [image]
    manager.unload_unused()
    assert image in dict(manager.iter_cached())

    manager.unload(metadata)
    manager.unload_unused()
    assert image in dict(manager.iter_cached()), "still pinned by the second call"

    manager.unload(metadata)
    manager.unload_unused()
    assert dict(manager.iter_cached()) == {}


def test_reloading_an_atlas_page_rebuilds_the_atlas(tmp_path: Path) -> None:
    image, metadata, manager = _atlas(tmp_path)
    before = manager.load_atlas(image, metadata)

    Path(image).write_text("v2", encoding="utf-8")
    manager.reload(image)

    after = manager.load_atlas(image, metadata)
    assert after is not before
    assert after.texture.native_handle == "v2"
    assert isinstance(after, Atlas)


def test_the_reload_watcher_survives_a_file_that_no_longer_loads(
    tmp_path: Path,
) -> None:
    _write(tmp_path, "a.leaf", "a")
    pack = _write(tmp_path, "p.pack", "a.leaf")
    manager = _manager()
    manager.load(pack, _Pack)
    watcher = AssetReloadWatcher(manager)
    watcher.refresh()

    Path(pack).write_text("missing.leaf", encoding="utf-8")
    watcher._on_file_changed(str(Path(pack).resolve()))

    assert watcher.drain() == []
