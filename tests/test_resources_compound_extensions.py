"""A loader registered for `.prefab.json` wins over one for `.json`."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from pyguara.prefabs import Prefab, PrefabLoader
from pyguara.resources.data import DataResource
from pyguara.resources.loaders.data_loader import JsonLoader
from pyguara.resources.manager import ResourceManager


def _files(directory: Path) -> tuple[str, str]:
    prefab = directory / "goblin.prefab.json"
    prefab.write_text(json.dumps({"name": "goblin", "components": {}}))
    data = directory / "stats.json"
    data.write_text(json.dumps({"health": 3}))
    return str(prefab), str(data)


@pytest.mark.parametrize("prefab_first", [True, False])
def test_the_longest_registered_extension_chooses_the_loader(
    tmp_path: Path, prefab_first: bool
) -> None:
    prefab_path, data_path = _files(tmp_path)
    manager = ResourceManager()
    loaders = [PrefabLoader(), JsonLoader()]
    for loader in loaders if prefab_first else reversed(loaders):
        manager.register_loader(loader)

    assert manager.load(prefab_path, Prefab).data.name == "goblin"
    assert manager.load(data_path, DataResource).native_handle == {"health": 3}


def test_extensions_match_whatever_their_case(tmp_path: Path) -> None:
    path = tmp_path / "GOBLIN.PREFAB.JSON"
    path.write_text(json.dumps({"name": "goblin", "components": {}}))
    manager = ResourceManager()
    manager.register_loader(JsonLoader())
    manager.register_loader(PrefabLoader())

    assert manager.load(str(path), Prefab).data.name == "goblin"


def test_a_compound_extension_is_indexed_by_name(tmp_path: Path) -> None:
    prefab_path, _ = _files(tmp_path)
    manager = ResourceManager()
    manager.register_loader(PrefabLoader())

    manager.index_directory(str(tmp_path))

    assert manager.load("goblin.prefab.json", Prefab).path == prefab_path


def test_an_asynchronous_load_chooses_the_same_loader(tmp_path: Path) -> None:
    prefab_path, _ = _files(tmp_path)
    manager = ResourceManager()
    manager.register_loader(JsonLoader())
    manager.register_loader(PrefabLoader())

    request = manager.load_async(prefab_path, Prefab)
    while manager.pending_loads:
        manager.pump(budget_ms=1000.0)

    assert isinstance(request.resource, Prefab)


def test_a_name_with_no_registered_extension_still_raises(tmp_path: Path) -> None:
    path = tmp_path / "notes.prefab.txt"
    path.write_text("hello")
    manager = ResourceManager()
    manager.register_loader(PrefabLoader())

    with pytest.raises(ValueError, match="No loader registered"):
        manager.load(str(path), Prefab)
