"""A prefab's children are owned by it, and a prefab that cannot be built
leaves nothing behind."""

from __future__ import annotations

import pytest

from pyguara.common.components import Tag, Transform
from pyguara.ecs.manager import EntityManager
from pyguara.prefabs import ComponentRegistry, PrefabChild, PrefabData, PrefabFactory


def _factory(prefabs: dict[str, PrefabData]) -> tuple[PrefabFactory, EntityManager]:
    registry = ComponentRegistry()
    registry.register(Tag)
    registry.register(Transform)
    manager = EntityManager()
    return PrefabFactory(manager, registry, prefabs.get), manager


def _names(manager: EntityManager) -> list[str]:
    return sorted(e.get_component(Tag).name for e in manager.get_entities_with(Tag))


TORCH = PrefabData(name="torch", components={"Tag": {"name": "torch"}, "Transform": {}})
FLAME = PrefabData(name="flame", components={"Tag": {"name": "flame"}})
LIT_TORCH = PrefabData(
    name="lit_torch",
    components={"Tag": {"name": "torch"}, "Transform": {}},
    children=[PrefabChild("flame")],
)
GOBLIN = PrefabData(
    name="goblin",
    components={"Tag": {"name": "goblin"}, "Transform": {}},
    children=[PrefabChild("lit_torch"), PrefabChild("torch")],
)
PREFABS = {"torch": TORCH, "flame": FLAME, "lit_torch": LIT_TORCH, "goblin": GOBLIN}


class TestOwnership:
    def test_each_child_is_owned_by_the_entity_that_declared_it(self) -> None:
        factory, manager = _factory(PREFABS)

        goblin = factory.create(GOBLIN)

        torches = manager.children_of(goblin.id)
        assert len(torches) == 2
        lit = next(t for t in torches if manager.children_of(t))
        (flame,) = manager.children_of(lit)
        assert manager.parent_of(flame) == lit

    def test_destroying_the_parent_destroys_every_descendant(self) -> None:
        factory, manager = _factory(PREFABS)
        goblin = factory.create(GOBLIN)
        survivor = factory.create(TORCH)

        manager.remove_entity(goblin.id)
        manager.flush_pending_removals()

        assert _names(manager) == ["torch"]
        assert manager.get_entity(survivor.id) is survivor

    def test_destroying_a_child_leaves_the_parent(self) -> None:
        factory, manager = _factory(PREFABS)
        goblin = factory.create(GOBLIN)

        for child in manager.children_of(goblin.id):
            manager.remove_entity(child)
        manager.flush_pending_removals()

        assert _names(manager) == ["goblin"]


class TestNothingLeftBehind:
    def test_a_missing_child_at_any_depth_creates_nothing(self) -> None:
        prefabs = {
            **PREFABS,
            "lit_torch": PrefabData(name="lit_torch", children=[PrefabChild("ember")]),
        }
        factory, manager = _factory(prefabs)

        with pytest.raises(ValueError, match="child 'ember', which did not load"):
            factory.create(GOBLIN)

        assert list(manager.get_all_entities()) == []

    @pytest.mark.parametrize(
        ("prefabs", "match"),
        [
            (
                {"loop": PrefabData(name="loop", children=[PrefabChild("loop")])},
                "loop -> loop",
            ),
            (
                {
                    "a": PrefabData(name="a", children=[PrefabChild("b")]),
                    "b": PrefabData(name="b", children=[PrefabChild("a")]),
                },
                "a -> b -> a",
            ),
        ],
    )
    def test_a_prefab_inside_itself_is_a_cycle(
        self, prefabs: dict[str, PrefabData], match: str
    ) -> None:
        factory, manager = _factory(prefabs)
        root = next(iter(prefabs))
        with pytest.raises(ValueError, match=f"prefab child cycle: {match}"):
            factory.create_from_path(root)
        assert list(manager.get_all_entities()) == []

    def test_the_same_child_twice_is_not_a_cycle(self) -> None:
        pair = PrefabData(
            name="pair", children=[PrefabChild("torch"), PrefabChild("torch")]
        )
        factory, manager = _factory({**PREFABS, "pair": pair})
        factory.create_from_path("pair")
        assert _names(manager) == ["torch", "torch"]

    def test_bad_data_in_a_grandchild_destroys_what_was_built(self) -> None:
        bad_flame = PrefabData(name="flame", components={"Tag": {"nmae": "flame"}})
        factory, manager = _factory({**PREFABS, "flame": bad_flame})

        with pytest.raises(ValueError, match="nmae"):
            factory.create(GOBLIN)
        manager.flush_pending_removals()

        assert list(manager.get_all_entities()) == []

    def test_a_child_id_already_in_use_is_refused(self) -> None:
        named = PrefabData(
            name="named",
            components={"Tag": {"name": "named"}},
            children=[PrefabChild("torch", name="the_torch")],
        )
        factory, manager = _factory({**PREFABS, "named": named})
        factory.create_from_path("named")

        with pytest.raises(ValueError, match=r"already in use \['the_torch'\]"):
            factory.create_from_path("named")

        assert _names(manager) == ["named", "torch"]

    def test_an_id_used_twice_in_one_prefab_is_refused(self) -> None:
        twins = PrefabData(
            name="twins",
            children=[PrefabChild("torch", name="t"), PrefabChild("torch", name="t")],
        )
        factory, manager = _factory({**PREFABS, "twins": twins})
        with pytest.raises(ValueError, match=r"used twice \['t'\]"):
            factory.create_from_path("twins")
        assert list(manager.get_all_entities()) == []
