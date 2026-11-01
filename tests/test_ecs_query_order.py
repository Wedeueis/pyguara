"""Queries come back in a reproducible order (#324).

Order is part of the simulation: a Gauss-Seidel system's result depends on who
goes first. A `set` of uuid4 strings iterates differently in every process, so a
seeded flock did not simulate the same way twice, and no replay containing one
could reproduce. The subprocess tests are the ones that matter, since a single
process cannot see a difference between two runs of itself.
"""

from __future__ import annotations

import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

import pytest

from pyguara.ecs.component import BaseComponent
from pyguara.ecs.manager import EntityManager

REPO = Path(__file__).parent.parent


@dataclass
class A(BaseComponent):
    pass


@dataclass
class B(BaseComponent):
    pass


@dataclass
class C(BaseComponent):
    pass


def _world(count: int = 50) -> tuple[EntityManager, list[str]]:
    manager = EntityManager()
    ids = []
    for _ in range(count):
        entity = manager.create_entity()
        entity.add_component(A())
        entity.add_component(B())
        ids.append(entity.id)
    return manager, ids


def _ids(entities) -> list[str]:  # type: ignore[no-untyped-def]
    return [entity.id for entity in entities]


class TestQueriesKeepInsertionOrder:
    def test_a_single_type(self) -> None:
        manager, ids = _world()

        assert _ids(manager.get_entities_with(A)) == ids

    def test_two_types(self) -> None:
        manager, ids = _world()

        assert _ids(manager.get_entities_with(A, B)) == ids

    def test_two_types_of_different_sizes_keep_the_smaller_ones_order(self) -> None:
        manager, ids = _world()
        chosen = ids[10:20]
        for entity_id in reversed(chosen):
            manager.get_entity(entity_id).add_component(C())

        assert _ids(manager.get_entities_with(A, C)) == list(reversed(chosen))

    def test_without_keeps_the_order_of_what_is_left(self) -> None:
        manager, ids = _world()
        manager.get_entity(ids[3]).add_component(C())

        assert _ids(manager.get_entities_with(A, without=(C,))) == (ids[:3] + ids[4:])

    def test_any_of_alone(self) -> None:
        manager, ids = _world()

        assert _ids(manager.get_entities_with(any_of=(A, C))) == ids

    def test_any_of_narrowing(self) -> None:
        manager, ids = _world()
        manager.get_entity(ids[7]).add_component(C())
        manager.get_entity(ids[2]).add_component(C())

        assert _ids(manager.get_entities_with(A, any_of=(C,))) == [ids[2], ids[7]]

    def test_the_whole_world_scan(self) -> None:
        manager, ids = _world()
        manager.get_entity(ids[0]).add_component(C())

        assert _ids(manager.get_entities_with(without=(C,))) == ids[1:]

    def test_a_cached_query(self) -> None:
        manager, ids = _world()
        manager.register_cached_query(A, B)

        assert _ids(manager.get_entities_with_cached(A, B)) == ids

    def test_a_cached_query_keeps_its_order_through_a_change(self) -> None:
        manager, ids = _world()
        manager.register_cached_query(A, B)
        manager.get_entity(ids[5]).remove_component(B)
        added = manager.create_entity()
        added.add_component(A())
        added.add_component(B())

        expected = ids[:5] + ids[6:] + [added.id]
        assert _ids(manager.get_entities_with_cached(A, B)) == expected

    def test_children_keep_the_order_they_were_attached(self) -> None:
        manager = EntityManager()
        parent = manager.create_entity()
        children = [manager.create_entity() for _ in range(30)]
        for child in children:
            manager.set_parent(child.id, parent.id)

        assert manager.children_of(parent.id) == [c.id for c in children]


class TestWhatTheOrderMustNotBreak:
    def test_a_multi_term_query_may_add_components_while_iterating(self) -> None:
        """It was a fresh set before, so this has always been allowed."""
        manager, _ids_ = _world()

        for entity in manager.get_entities_with(A, B):
            entity.add_component(C())

        assert len(list(manager.get_entities_with(C))) == 50

    def test_a_query_result_does_not_alias_the_index_once_narrowed(self) -> None:
        manager, ids = _world()

        list(manager.get_entities_with(A, B))

        assert ids[0] in manager._component_index[A]


_FLOCK_SCRIPT = """
import hashlib, sys
sys.path.insert(0, ".")
from tests.performance.conftest import build_flock
from pyguara.common.components import Transform

manager, system = build_flock(120, spread=500.0, accelerate={accelerate})
for _ in range(20):
    system.update(1 / 60)
positions = [e.get_component(Transform).position
             for e in manager.get_entities_with(Transform)]
ordered = repr([(p.x, p.y) for p in positions]).encode()
print(hashlib.sha1(ordered).hexdigest())
"""


def _run_flock(accelerate: bool, hash_seed: int) -> str:
    env = {**os.environ, "PYTHONHASHSEED": str(hash_seed), "PYTHONPATH": str(REPO)}
    done = subprocess.run(
        [sys.executable, "-c", _FLOCK_SCRIPT.format(accelerate=accelerate)],
        capture_output=True,
        text=True,
        cwd=REPO,
        env=env,
        check=True,
    )
    return done.stdout.strip().splitlines()[-1]


class TestASeededFlockReproduces:
    """Exact: every coordinate of every agent, in query order, bit for bit."""

    @pytest.mark.parametrize("accelerate", [False, True], ids=["python", "native"])
    def test_across_processes_and_hash_seeds(self, accelerate: bool) -> None:
        if accelerate:
            from pyguara.ai.flocking_system import FlockingSystem

            if not FlockingSystem(EntityManager()).accelerated:
                pytest.skip("extension not built")

        digests = {_run_flock(accelerate, seed) for seed in (1, 2, 3)}

        assert len(digests) == 1, digests
