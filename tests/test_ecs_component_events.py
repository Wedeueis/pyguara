"""Observing components being attached, detached and changed.

The polling this closes: before it, only entity *removal* was observable,
so a HUD mirroring `Health` or a system reacting to `Poisoned` being
applied had to re-query every frame and diff the answer itself.

In its own file rather than appended to `tests/test_ecs.py`, deliberately.
Every other slice of #66 added a class to the end of that file, and every
one of them conflicted with its siblings on exactly those lines.
"""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from pyguara.ecs.component import BaseComponent
from pyguara.ecs.entity import Entity
from pyguara.ecs.manager import EntityManager


@dataclass
class Health(BaseComponent):
    """Watched by most of these tests."""

    current: int = 100


@dataclass
class Poisoned(BaseComponent):
    """A second type, so "only the type subscribed to" is testable."""

    stacks: int = 1


@pytest.fixture
def world() -> EntityManager:
    """An empty world."""
    return EntityManager()


class _Recorder:
    """Collects (entity id, component) pairs in call order."""

    def __init__(self) -> None:
        self.seen: list[tuple[str, object]] = []

    def __call__(self, entity: Entity, component: object) -> None:
        self.seen.append((entity.id, component))

    @property
    def ids(self) -> list[str]:
        """Just the entity ids, for the common assertion."""
        return [entity_id for entity_id, _ in self.seen]


class TestComponentAdded:
    def test_it_fires_with_the_entity_and_the_component(
        self, world: EntityManager
    ) -> None:
        recorder = _Recorder()
        world.subscribe_component_added(Health, recorder)
        entity = world.create_entity("hero")
        health = Health(current=42)

        entity.add_component(health)

        assert recorder.seen == [("hero", health)]

    def test_the_indexes_are_already_updated(self, world: EntityManager) -> None:
        """A subscriber must be able to query for what it was just told
        about. Firing before the index would hand it a world that does not
        yet contain the thing it is reacting to.
        """
        found: list[list[str]] = []
        world.subscribe_component_added(
            Health,
            lambda e, c: found.append([x.id for x in world.get_entities_with(Health)]),
        )
        world.create_entity("hero").add_component(Health())

        assert found == [["hero"]]

    def test_only_the_subscribed_type_fires(self, world: EntityManager) -> None:
        recorder = _Recorder()
        world.subscribe_component_added(Health, recorder)
        entity = world.create_entity("hero")

        entity.add_component(Poisoned())

        assert recorder.seen == []

    def test_it_fires_for_components_an_added_entity_already_had(
        self, world: EntityManager
    ) -> None:
        """Clones, prefabs and deserialised scenes arrive fully built.

        `add_entity` indexes their existing components through the same
        hook, so an observer that missed them would see a world containing
        entities it was never told about.
        """
        recorder = _Recorder()
        world.subscribe_component_added(Health, recorder)
        entity = Entity("prefab")
        entity.add_component(Health())

        world.add_entity(entity)

        assert recorder.ids == ["prefab"]


class TestComponentRemoved:
    def test_it_fires_with_the_detached_component(self, world: EntityManager) -> None:
        """The component is handed over because it is already gone.

        By the time this fires the entity no longer carries it, so a
        subscriber that needed to read the final value -- a HUD clearing a
        bar, a pool reclaiming a resource -- could not fetch it back.
        """
        recorder = _Recorder()
        world.subscribe_component_removed(Health, recorder)
        entity = world.create_entity("hero")
        health = Health(current=7)
        entity.add_component(health)

        entity.remove_component(Health)

        assert recorder.seen == [("hero", health)]
        assert not entity.has_component(Health)

    def test_removing_a_type_that_is_not_attached_fires_nothing(
        self, world: EntityManager
    ) -> None:
        recorder = _Recorder()
        world.subscribe_component_removed(Health, recorder)
        entity = world.create_entity("hero")

        entity.remove_component(Health)

        assert recorder.seen == []

    def test_destroying_an_entity_does_not_fire_it(self, world: EntityManager) -> None:
        """Entity removal is its own event, and a richer one.

        `subscribe_entity_removed` hands over the entity with every
        component still attached. Raising a component-removed per component
        as well would make each despawn N notifications that say strictly
        less, and a subscriber watching both would react twice.
        """
        recorder = _Recorder()
        world.subscribe_component_removed(Health, recorder)
        entity = world.create_entity("hero")
        entity.add_component(Health())

        world.remove_entity("hero")
        world.flush_pending_removals()

        assert recorder.seen == []


class TestComponentChanged:
    def test_notify_fires_the_subscribers(self, world: EntityManager) -> None:
        recorder = _Recorder()
        world.subscribe_component_changed(Health, recorder)
        entity = world.create_entity("hero")
        health = Health()
        entity.add_component(health)

        health.current = 30
        world.notify_component_changed("hero", Health)

        assert recorder.seen == [("hero", health)]
        assert recorder.seen[0][1].current == 30  # type: ignore[attr-defined]

    def test_a_plain_mutation_fires_nothing(self, world: EntityManager) -> None:
        """The honest half of the contract.

        A component is a plain dataclass and `health.current -= 10` is an
        ordinary attribute write. Detecting it would mean a descriptor or
        proxy on every field of every component -- real cost on the hottest
        path in the engine, to serve the few types anything observes. The
        writer reports instead, and this test is what stops the docstring's
        promise drifting from the behaviour.
        """
        recorder = _Recorder()
        world.subscribe_component_changed(Health, recorder)
        entity = world.create_entity("hero")
        entity.add_component(Health())

        entity.get_component(Health).current = 1

        assert recorder.seen == []

    def test_one_report_covers_a_whole_edit(self, world: EntityManager) -> None:
        """Which is the upside of reporting rather than detecting.

        A system touching several fields notifies once, when the component
        is consistent again -- not once per field, through intermediate
        states no observer should ever see.
        """
        recorder = _Recorder()
        world.subscribe_component_changed(Health, recorder)
        entity = world.create_entity("hero")
        health = Health()
        entity.add_component(health)

        health.current = 50
        health.current = 25
        health.current = 10
        world.notify_component_changed("hero", Health)

        assert len(recorder.seen) == 1
        assert health.current == 10

    def test_notifying_for_an_unknown_entity_is_a_no_op(
        self, world: EntityManager
    ) -> None:
        recorder = _Recorder()
        world.subscribe_component_changed(Health, recorder)

        world.notify_component_changed("ghost", Health)

        assert recorder.seen == []

    def test_notifying_for_a_detached_component_is_a_no_op(
        self, world: EntityManager
    ) -> None:
        """A caller reporting a change to something it has since removed
        should not have to guard the call.
        """
        recorder = _Recorder()
        world.subscribe_component_changed(Health, recorder)
        world.create_entity("hero")

        world.notify_component_changed("hero", Health)

        assert recorder.seen == []


class TestSubscriptionManagement:
    def test_subscribing_twice_notifies_once(self, world: EntityManager) -> None:
        """Matching `subscribe_entity_removed`, so a scene whose
        dependencies resolve twice does not double-notify.
        """
        recorder = _Recorder()
        world.subscribe_component_added(Health, recorder)
        world.subscribe_component_added(Health, recorder)

        world.create_entity("hero").add_component(Health())

        assert len(recorder.seen) == 1

    def test_unsubscribing_stops_it(self, world: EntityManager) -> None:
        recorder = _Recorder()
        world.subscribe_component_added(Health, recorder)
        world.unsubscribe_component_added(Health, recorder)

        world.create_entity("hero").add_component(Health())

        assert recorder.seen == []

    @pytest.mark.parametrize(
        "unsubscribe",
        [
            "unsubscribe_component_added",
            "unsubscribe_component_removed",
            "unsubscribe_component_changed",
        ],
    )
    def test_unsubscribing_something_never_subscribed_is_a_no_op(
        self, world: EntityManager, unsubscribe: str
    ) -> None:
        getattr(world, unsubscribe)(Health, _Recorder())

    def test_a_subscriber_may_unsubscribe_itself_while_notified(
        self, world: EntityManager
    ) -> None:
        """A one-shot observer, or one tearing down a subsystem that
        unsubscribes on the way out. Mutating the list being iterated would
        skip whichever subscriber happened to follow it.
        """
        calls: list[str] = []

        def once(entity: Entity, component: object) -> None:
            calls.append("once")
            world.unsubscribe_component_added(Health, once)

        def after(entity: Entity, component: object) -> None:
            calls.append("after")

        world.subscribe_component_added(Health, once)
        world.subscribe_component_added(Health, after)

        world.create_entity("a").add_component(Health())
        world.create_entity("b").add_component(Health())

        assert calls == ["once", "after", "after"]
