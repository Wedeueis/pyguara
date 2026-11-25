"""Named variants build on a prefab, and work wherever a prefab path does."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest

from pyguara.common.components import Tag, Transform
from pyguara.common.random import RandomStream
from pyguara.ecs.component import BaseComponent
from pyguara.ecs.manager import EntityManager
from pyguara.prefabs import (
    ComponentRegistry,
    PrefabChild,
    PrefabData,
    PrefabFactory,
    PrefabInstance,
    PrefabVariant,
    SpawnChoice,
    SpawnTable,
    VariantLibrary,
    load_variants,
)


@dataclass
class Stats(BaseComponent):
    """Test data: one int field and one float field."""

    hp: int = 10
    speed: float = 1.0

    def __post_init__(self) -> None:
        """Initialise the BaseComponent state the dataclass `__init__` skips."""
        BaseComponent.__init__(self)


PREFABS = {
    "creature": PrefabData(
        name="creature",
        components={"Stats": {"hp": 10, "speed": 2.0}, "Tag": {"name": "creature"}},
        tags=["enemy"],
    ),
    "goblin": PrefabData(
        name="goblin",
        extends="creature",
        components={"Tag": {"name": "goblin"}, "Transform": {}},
        children=[PrefabChild(prefab="torch")],
        tags=["enemy", "goblin"],
    ),
    "torch": PrefabData(name="torch", components={"Tag": {"name": "torch"}}),
}

ELITE = PrefabVariant(
    name="elite_goblin",
    base="goblin",
    overrides={"Tag": {"name": "elite goblin"}},
    multiply={"Stats": {"hp": 1.5, "speed": 1.25}},
    tags=("elite",),
)


def _factory(library: VariantLibrary) -> tuple[PrefabFactory, EntityManager]:
    registry = ComponentRegistry()
    for component in (Stats, Tag, Transform):
        registry.register(component)
    manager = EntityManager()
    return PrefabFactory(manager, registry, library.resolver(PREFABS.get)), manager


def _resolve(library: VariantLibrary, name: str) -> PrefabData | None:
    return library.resolver(PREFABS.get)(name)


class TestResolving:
    def test_a_variant_scales_inherited_numbers_and_replaces_fields(self) -> None:
        data = _resolve(VariantLibrary({"elite_goblin": ELITE}), "elite_goblin")

        assert data is not None
        assert data.components["Stats"] == {"hp": 15, "speed": 2.5}
        assert data.components["Tag"] == {"name": "elite goblin"}
        assert data.extends is None, "the base's chain is already applied"

    def test_an_int_field_stays_an_int(self) -> None:
        odd = PrefabVariant("odd", "creature", multiply={"Stats": {"hp": 1.33}})
        data = _resolve(VariantLibrary({"odd": odd}), "odd")
        assert data is not None
        assert data.components["Stats"]["hp"] == 13
        assert isinstance(data.components["Stats"]["hp"], int)

    def test_tags_and_children_come_from_the_base(self) -> None:
        data = _resolve(VariantLibrary({"elite_goblin": ELITE}), "elite_goblin")
        assert data is not None
        assert data.tags == ["enemy", "goblin", "elite"]
        assert [child.prefab for child in data.children] == ["torch"]

    def test_a_variant_can_build_on_another(self) -> None:
        champion = PrefabVariant(
            "champion", "elite_goblin", multiply={"Stats": {"hp": 2}}
        )
        library = VariantLibrary({"elite_goblin": ELITE, "champion": champion})
        data = _resolve(library, "champion")
        assert data is not None
        assert data.components["Stats"]["hp"] == 30
        assert data.components["Tag"] == {"name": "elite goblin"}

    def test_a_path_passes_through_untouched(self) -> None:
        library = VariantLibrary({"elite_goblin": ELITE})
        assert _resolve(library, "goblin") is PREFABS["goblin"]
        assert _resolve(library, "nowhere") is None

    def test_a_variant_of_a_missing_prefab_is_missing(self) -> None:
        lost = PrefabVariant("lost", "nowhere")
        assert _resolve(VariantLibrary({"lost": lost}), "lost") is None

    def test_resolving_leaves_the_base_unchanged(self) -> None:
        before = json.dumps(PREFABS["creature"].components, sort_keys=True)
        _resolve(VariantLibrary({"elite_goblin": ELITE}), "elite_goblin")
        assert json.dumps(PREFABS["creature"].components, sort_keys=True) == before


class TestErrors:
    def test_a_cycle_of_bases_is_named(self) -> None:
        library = VariantLibrary(
            {"a": PrefabVariant("a", "b"), "b": PrefabVariant("b", "a")}
        )
        with pytest.raises(ValueError, match="variant cycle: a -> b -> a"):
            _resolve(library, "a")

    @pytest.mark.parametrize(
        ("multiply", "match"),
        [
            ({"Stats": {"armour": 2}}, "Stats.armour, which its base does not set"),
            ({"Tag": {"name": 2}}, "Tag.name, which is 'creature', not a number"),
            ({"Stats": {"hp": {"x": 2}}}, "fields of Stats.hp, which is 10"),
        ],
    )
    def test_multiplying_what_is_not_a_number_names_the_field(
        self, multiply: dict[str, Any], match: str
    ) -> None:
        bad = PrefabVariant("bad", "creature", multiply=multiply)
        with pytest.raises(ValueError, match=match):
            _resolve(VariantLibrary({"bad": bad}), "bad")

    @pytest.mark.parametrize("factor", [-1, float("inf"), float("nan"), True, "2"])
    def test_a_factor_must_be_a_finite_non_negative_number(self, factor: Any) -> None:
        with pytest.raises(ValueError, match="a factor must be"):
            PrefabVariant("bad", "creature", multiply={"Stats": {"hp": factor}})

    def test_a_field_cannot_be_both_multiplied_and_overridden(self) -> None:
        with pytest.raises(ValueError, match="both multiplies and overrides Stats.hp"):
            PrefabVariant(
                "bad",
                "creature",
                multiply={"Stats": {"hp": 2}},
                overrides={"Stats": {"hp": 3}},
            )

    @pytest.mark.parametrize("name", ["", "goblin.prefab.json", "enemies/elite"])
    def test_a_name_cannot_look_like_a_path(self, name: str) -> None:
        with pytest.raises(ValueError, match="cannot be mistaken for a path"):
            PrefabVariant(name, "goblin")

    def test_a_key_must_match_its_variant(self) -> None:
        with pytest.raises(ValueError, match="filed as 'elite'"):
            VariantLibrary({"elite": ELITE})


class TestFactory:
    def test_create_from_path_builds_a_variant_with_its_children(self) -> None:
        factory, manager = _factory(VariantLibrary({"elite_goblin": ELITE}))

        elite = factory.create_from_path("elite_goblin")

        assert elite is not None
        stats = elite.get_component(Stats)
        assert (stats.hp, stats.speed) == (15, 2.5)
        assert elite.get_component(PrefabInstance).prefab_path == "elite_goblin"
        torches = [
            entity
            for entity in manager.get_entities_with(Tag)
            if entity.get_component(Tag).name == "torch"
        ]
        assert len(torches) == 1

    def test_a_spawn_table_can_name_a_variant(self) -> None:
        factory, _ = _factory(VariantLibrary({"elite_goblin": ELITE}))
        table = SpawnTable((SpawnChoice("goblin"), SpawnChoice("elite_goblin")))

        spawned = factory.spawn(table, RandomStream(3), count=40)

        names = {entity.get_component(Tag).name for entity in spawned}
        assert names == {"goblin", "elite goblin"}

    def test_a_child_can_be_a_variant(self) -> None:
        bright = PrefabVariant(
            "bright_torch", "torch", overrides={"Tag": {"name": "bright"}}
        )
        prefabs = {
            **PREFABS,
            "chief": PrefabData(
                name="chief", children=[PrefabChild(prefab="bright_torch")]
            ),
        }
        registry = ComponentRegistry()
        registry.register(Tag)
        manager = EntityManager()
        library = VariantLibrary({"bright_torch": bright})
        factory = PrefabFactory(manager, registry, library.resolver(prefabs.get))

        factory.create_from_path("chief")

        names = [e.get_component(Tag).name for e in manager.get_entities_with(Tag)]
        assert names == ["bright"]


class TestLoading:
    def _write(self, tmp_path: Path, data: Any) -> Path:
        path = tmp_path / "enemies.variants.json"
        path.write_text(json.dumps(data))
        return path

    def test_a_file_loads_into_a_library(self, tmp_path: Path) -> None:
        path = self._write(
            tmp_path,
            {
                "variants": {
                    "elite_goblin": {
                        "base": "goblin",
                        "overrides": {"Tag": {"name": "elite goblin"}},
                        "multiply": {"Stats": {"hp": 1.5, "speed": 1.25}},
                        "tags": ["elite"],
                    }
                }
            },
        )

        library = load_variants(path)

        assert library.names() == ["elite_goblin"]
        assert _resolve(library, "elite_goblin") == _resolve(
            VariantLibrary({"elite_goblin": ELITE}), "elite_goblin"
        )

    @pytest.mark.parametrize(
        ("data", "match"),
        [
            ([], '"variants" object'),
            ({"variants": {"x": {}}}, "variant 'x' needs a \"base\""),
            ({"variants": {"x": {"base": "g", "hp": 2}}}, r"unknown keys \['hp'\]"),
            ({"variants": {"x": {"base": "g", "tags": "elite"}}}, "list of strings"),
            ({"variants": {"x": {"base": "g", "multiply": [2]}}}, "must be an object"),
        ],
    )
    def test_a_malformed_file_names_itself(
        self, tmp_path: Path, data: Any, match: str
    ) -> None:
        path = self._write(tmp_path, data)
        with pytest.raises(ValueError, match=match) as raised:
            load_variants(path)
        assert "enemies.variants.json" in str(raised.value)

    def test_a_missing_file_is_not_found(self, tmp_path: Path) -> None:
        with pytest.raises(FileNotFoundError):
            load_variants(tmp_path / "none.variants.json")
