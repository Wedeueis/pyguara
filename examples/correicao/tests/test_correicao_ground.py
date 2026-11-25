"""The ground's prefab data: a boulder is the stone at twice the size."""

from __future__ import annotations

from collections import Counter

from examples.correicao.scenes import PREFABS
from pyguara.common.random import RandomStream
from pyguara.prefabs import PrefabCache, load_spawn_table, load_variants


def test_a_boulder_is_the_stone_twice_the_size() -> None:
    resolve = load_variants(f"{PREFABS}/ground.variants.json").resolver(
        PrefabCache().load
    )

    stone = resolve(f"{PREFABS}/stone.prefab.json")
    boulder = resolve("boulder")

    assert stone is not None
    assert boulder is not None
    assert boulder.components["Sprite"]["scale"] == {"x": 2.0, "y": 2.0}
    assert (
        boulder.components["Sprite"]["texture"]
        == (stone.components["Sprite"]["texture"])
    )
    assert "boulder" in boulder.tags


def test_the_ground_table_scatters_boulders_among_the_stones() -> None:
    table = load_spawn_table(f"{PREFABS}/ground.spawn.json")
    picks = Counter(choice.prefab for choice in table.pick_many(RandomStream(1), 900))
    assert picks["boulder"] > 0
    assert picks[f"{PREFABS}/stone.prefab.json"] > picks["boulder"]


def test_every_prefab_the_scene_uses_names_a_texture_that_exists() -> None:
    from pathlib import Path

    from examples.correicao.scenes import PLAYER_PREFAB

    resolve = load_variants(f"{PREFABS}/ground.variants.json").resolver(
        PrefabCache().load
    )
    table = load_spawn_table(f"{PREFABS}/ground.spawn.json")

    for path in [PLAYER_PREFAB, *(choice.prefab for choice in table.choices)]:
        prefab = resolve(path)
        assert prefab is not None, path
        assert Path(prefab.components["Sprite"]["texture"]).is_file(), path
