"""Entity ownership, and what happens to a subtree when its root dies.

The leak this closes, in the issue's own words: "a despawned enemy leaks
its prefab-attached child entities (health bar, weapon, aura)". Nothing
else in the engine knows those entities were only ever meaningful as part
of the enemy, so nothing else can clean them up.

The interesting cases are all about *ordering and re-entrancy*, not about
the happy path: a removal subscriber running while the subtree is being
dismantled, a cycle that would make the cascade unbounded, and a
re-parented entity that must not still be destroyed by its old parent.
"""

from __future__ import annotations

import pytest

from pyguara.ecs.entity import Entity
from pyguara.ecs.manager import EntityManager
from pyguara.ecs.relations import ChildOf


@pytest.fixture
def world() -> EntityManager:
    """An empty world."""
    return EntityManager()


def _ids(manager: EntityManager) -> set[str]:
    """Every live entity id."""
    return {entity.id for entity in manager.get_all_entities()}


class TestParenting:
    def test_set_parent_links_both_directions(self, world: EntityManager) -> None:
        world.create_entity("enemy")
        world.create_entity("health_bar")

        world.set_parent("health_bar", "enemy")

        assert world.parent_of("health_bar") == "enemy"
        assert world.children_of("enemy") == ["health_bar"]

    def test_the_relation_is_a_component(self, world: EntityManager) -> None:
        """Queryable and serialisable, which is what #51's prefabs need.

        A parent tracked only in a private dict could not be saved with a
        scene, nor inspected, nor queried for.
        """
        world.create_entity("enemy")
        child = world.create_entity("health_bar")

        world.set_parent("health_bar", "enemy")

        assert child.has_component(ChildOf)
        assert child.get_component(ChildOf).parent_id == "enemy"
        assert [e.id for e in world.get_entities_with(ChildOf)] == ["health_bar"]

    def test_re_parenting_detaches_from_the_old_parent(
        self, world: EntityManager
    ) -> None:
        """Otherwise the first parent still destroys it, long after it left."""
        world.create_entity("first")
        world.create_entity("second")
        world.create_entity("child")
        world.set_parent("child", "first")

        world.set_parent("child", "second")

        assert world.children_of("first") == []
        assert world.children_of("second") == ["child"]
        assert world.parent_of("child") == "second"

    def test_detaching_leaves_the_child_standing(self, world: EntityManager) -> None:
        world.create_entity("enemy")
        child = world.create_entity("dropped_sword")
        world.set_parent("dropped_sword", "enemy")

        world.set_parent("dropped_sword", None)
        world.remove_entity("enemy")

        assert _ids(world) == {"dropped_sword"}
        assert not child.has_component(ChildOf)

    def test_removing_the_component_detaches_it(self, world: EntityManager) -> None:
        """The index follows the component, however the component goes.

        `set_parent(None)` is the supported route, but a component can be
        detached directly, and the reverse index must not keep claiming a
        child that no longer has the relation.
        """
        world.create_entity("enemy")
        child = world.create_entity("aura")
        world.set_parent("aura", "enemy")

        child.remove_component(ChildOf)

        assert world.parent_of("aura") is None
        assert world.children_of("enemy") == []

    def test_children_of_hands_back_a_snapshot(self, world: EntityManager) -> None:
        """Callers destroy while iterating it; the live set is mutated by
        every detach, so handing that out would raise mid-cascade.
        """
        world.create_entity("enemy")
        for name in ("a", "b"):
            world.create_entity(name)
            world.set_parent(name, "enemy")

        children = world.children_of("enemy")
        world.set_parent("a", None)

        assert sorted(children) == ["a", "b"], "the returned list aliased the index"


class TestCascadeDestroy:
    def test_destroying_a_parent_destroys_its_children(
        self, world: EntityManager
    ) -> None:
        world.create_entity("enemy")
        for part in ("health_bar", "weapon", "aura"):
            world.create_entity(part)
            world.set_parent(part, "enemy")

        world.remove_entity("enemy")

        assert _ids(world) == set()

    def test_it_reaches_the_whole_subtree(self, world: EntityManager) -> None:
        """Grandchildren too -- a weapon's own muzzle-flash emitter."""
        world.create_entity("enemy")
        world.create_entity("weapon")
        world.create_entity("muzzle_flash")
        world.set_parent("weapon", "enemy")
        world.set_parent("muzzle_flash", "weapon")

        world.remove_entity("enemy")

        assert _ids(world) == set()

    def test_destroying_a_child_leaves_the_parent(self, world: EntityManager) -> None:
        """Ownership points one way. A destroyed weapon does not kill its
        wielder.
        """
        world.create_entity("enemy")
        world.create_entity("weapon")
        world.set_parent("weapon", "enemy")

        world.remove_entity("weapon")

        assert _ids(world) == {"enemy"}
        assert world.children_of("enemy") == []

    def test_a_sibling_subtree_is_untouched(self, world: EntityManager) -> None:
        """The cascade follows the relation, not the whole world."""
        world.create_entity("enemy")
        world.create_entity("aura")
        world.set_parent("aura", "enemy")
        world.create_entity("bystander")

        world.remove_entity("enemy")

        assert _ids(world) == {"bystander"}

    def test_every_removal_notifies_subscribers(self, world: EntityManager) -> None:
        """A cascaded child is destroyed, not merely forgotten.

        `Scene` republishes this hook as `EntityDestroyed`, and physics and
        the spatial index both unregister from it. A child dropped without
        the hook would leave its body in the simulation forever -- the leak
        moved, not closed.
        """
        seen: list[str] = []
        world.subscribe_entity_removed(lambda entity: seen.append(entity.id))
        world.create_entity("enemy")
        world.create_entity("aura")
        world.set_parent("aura", "enemy")

        world.remove_entity("enemy")

        assert sorted(seen) == ["aura", "enemy"]

    def test_a_subscriber_sees_the_subtree_before_it_is_dismantled(
        self, world: EntityManager
    ) -> None:
        """Children are removed before the parent's own soft-death, so a
        subscriber reacting to the parent finds the relation already gone
        -- but one reacting to a *child* can still read its parent id from
        the component, which is what makes the hook useful for cleanup.
        """
        parents_seen: dict[str, str | None] = {}

        def record(entity: Entity) -> None:
            relation = (
                entity.get_component(ChildOf) if entity.has_component(ChildOf) else None
            )
            parents_seen[entity.id] = relation.parent_id if relation else None

        world.subscribe_entity_removed(record)
        world.create_entity("enemy")
        world.create_entity("aura")
        world.set_parent("aura", "enemy")

        world.remove_entity("enemy")

        assert parents_seen == {"aura": "enemy", "enemy": None}

    def test_a_subscriber_cannot_parent_onto_a_dying_entity(
        self, world: EntityManager
    ) -> None:
        """Attaching a child to something already being destroyed would
        leave that child orphaned *and* holding a dangling parent id: the
        parent's cascade has already been decided, so the newcomer is
        never reached.

        The subscriber fires here on a **child's** removal, which is the
        case that matters: that runs partway through the parent's teardown.
        The parent is soft-dead before any of it begins, so the attempt
        raises rather than half-succeeding. (Cascading before soft-death --
        the obvious ordering -- leaves the parent alive at exactly this
        moment, and the link is silently accepted.)
        """
        world.create_entity("enemy")
        world.create_entity("aura")
        world.set_parent("aura", "enemy")
        world.create_entity("latecomer")
        failures: list[Exception] = []

        def attach_late(entity: Entity) -> None:
            if entity.id != "aura":
                return
            try:
                world.set_parent("latecomer", "enemy")
            except KeyError as error:
                failures.append(error)

        world.subscribe_entity_removed(attach_late)
        world.remove_entity("enemy")

        assert len(failures) == 1, (
            "parenting onto a parent that is mid-teardown should raise"
        )
        assert world.parent_of("latecomer") is None
        assert _ids(world) == {"latecomer"}

    def test_removing_a_parent_twice_is_harmless(self, world: EntityManager) -> None:
        """Re-entrancy: a removal subscriber may well destroy the parent
        again on its way out.
        """
        world.create_entity("enemy")
        world.create_entity("aura")
        world.set_parent("aura", "enemy")

        world.remove_entity("enemy")
        world.remove_entity("enemy")

        assert _ids(world) == set()

    def test_the_index_does_not_outlive_the_parent(self, world: EntityManager) -> None:
        """A destroyed parent's entry must go, or an id reused later
        inherits a set of long-dead children.
        """
        world.create_entity("enemy")
        world.create_entity("aura")
        world.set_parent("aura", "enemy")
        world.remove_entity("enemy")
        world.flush_pending_removals()

        world.create_entity("enemy")

        assert world.children_of("enemy") == []


class TestRejectedLinks:
    def test_an_entity_cannot_parent_itself(self, world: EntityManager) -> None:
        world.create_entity("a")

        with pytest.raises(ValueError, match="its own parent"):
            world.set_parent("a", "a")

    def test_a_cycle_is_rejected(self, world: EntityManager) -> None:
        """The natural mistake -- re-parenting a node under its own
        descendant -- and the one that makes the cascade unbounded.
        """
        world.create_entity("a")
        world.create_entity("b")
        world.create_entity("c")
        world.set_parent("b", "a")
        world.set_parent("c", "b")

        with pytest.raises(ValueError, match="own ancestor"):
            world.set_parent("a", "c")

        assert world.parent_of("a") is None, "the rejected link was applied anyway"

    def test_an_unknown_entity_raises(self, world: EntityManager) -> None:
        """Rather than silently doing nothing.

        A caller that believes a cascade is wired up when it is not finds
        out at the leak, which is much later and somewhere else.
        """
        world.create_entity("real")

        with pytest.raises(KeyError, match="child"):
            world.set_parent("ghost", "real")
        with pytest.raises(KeyError, match="parent"):
            world.set_parent("real", "ghost")
