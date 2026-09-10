"""Tests for `RandomStream` and `RandomService` (pyguara/common/random.py,
pyguara/random/service.py)."""

from __future__ import annotations

import json
import os
import subprocess
import sys

from pyguara.common.random import RandomStream
from pyguara.random.service import RandomService

# ========== RandomStream ==========


def test_stream_is_deterministic_given_seed() -> None:
    a = RandomStream(42)
    b = RandomStream(42)

    sequence_a = [a.random() for _ in range(10)]
    sequence_b = [b.random() for _ in range(10)]

    assert sequence_a == sequence_b


def test_stream_get_state_restore_state_resumes_mid_sequence() -> None:
    original = RandomStream(7)
    for _ in range(5):
        original.random()

    snapshot = original.get_state()
    expected_tail = [original.randint(0, 1000) for _ in range(5)]

    resumed = RandomStream()
    resumed.restore_state(snapshot)
    actual_tail = [resumed.randint(0, 1000) for _ in range(5)]

    assert actual_tail == expected_tail


def test_stream_restore_state_accepts_json_round_tripped_state() -> None:
    original = RandomStream(7)
    for _ in range(3):
        original.uniform(0, 1)

    round_tripped = json.loads(json.dumps(original.get_state()))
    expected_tail = [original.uniform(0, 1) for _ in range(5)]

    resumed = RandomStream()
    resumed.restore_state(round_tripped)
    actual_tail = [resumed.uniform(0, 1) for _ in range(5)]

    assert actual_tail == expected_tail


# ========== RandomService ==========


def test_service_derives_stable_named_streams_across_instances() -> None:
    a = RandomService(root_seed=123)
    b = RandomService(root_seed=123)

    sequence_a = [a.stream("enemy_ai").random() for _ in range(5)]
    sequence_b = [b.stream("enemy_ai").random() for _ in range(5)]

    assert sequence_a == sequence_b


def test_service_named_stream_derivation_ignores_string_hash_salting() -> None:
    """Guards against a `hash(name)`-based derivation: `str` hashing is
    salted per process via `PYTHONHASHSEED` unless disabled, which would
    make the same named stream diverge across runs."""
    script = (
        "from pyguara.random.service import RandomService; "
        "s = RandomService(root_seed=123).stream('enemy_ai'); "
        "print([s.random() for _ in range(5)])"
    )

    def run_with_hash_seed(hash_seed: str) -> str:
        result = subprocess.run(
            [sys.executable, "-c", script],
            capture_output=True,
            text=True,
            env={"PYTHONHASHSEED": hash_seed, "PATH": os.environ["PATH"]},
            check=True,
        )
        return result.stdout.strip()

    assert run_with_hash_seed("0") == run_with_hash_seed("1")


def test_service_distinct_names_produce_distinct_streams() -> None:
    service = RandomService(root_seed=1)

    sequence_a = [service.stream("a").random() for _ in range(5)]
    sequence_b = [service.stream("b").random() for _ in range(5)]

    assert sequence_a != sequence_b


def test_service_get_state_restore_state_round_trip() -> None:
    original = RandomService(root_seed=99)
    original.stream("a").random()
    original.stream("b").random()

    snapshot = json.loads(json.dumps(original.get_state()))
    expected_a = [original.stream("a").random() for _ in range(3)]
    expected_b = [original.stream("b").random() for _ in range(3)]

    restored = RandomService(root_seed=0)
    restored.restore_state(snapshot)
    actual_a = [restored.stream("a").random() for _ in range(3)]
    actual_b = [restored.stream("b").random() for _ in range(3)]

    assert actual_a == expected_a
    assert actual_b == expected_b

    # A name never touched before the snapshot is still lazily re-derivable,
    # and matches a fresh same-seed service exactly.
    fresh = RandomService(root_seed=99)
    assert restored.stream("c").random() == fresh.stream("c").random()


def test_service_default_root_seed_is_present_and_int() -> None:
    service = RandomService()

    assert isinstance(service.root_seed, int)
