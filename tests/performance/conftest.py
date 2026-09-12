"""Shared machinery for the performance suite.

Two kinds of test live in `tests/performance/`, and they exist for
different reasons:

*Guards* (`@pytest.mark.performance`) assert a **complexity class**, never
a wall-clock time. They measure the same operation at N and at a multiple
of N in the same process and assert the ratio between them. That cancels
machine speed out entirely, which is what makes them safe to run on a
shared CI runner: a laptop, a loaded container and a CI box all agree that
a linear algorithm costs roughly 4x as much for 4x the work, even though
they disagree about every absolute number involved.

*Sweeps* (`@pytest.mark.performance` **and** `@pytest.mark.slow`) are
`pytest-benchmark` runs at sizes too large for CI. They assert nothing.
Their job is to produce the numbers in `docs/guides/performance.md`, via
`make benchmark`.

Neither kind should ever run under coverage -- tracing every line costs
more than the code being timed, and turns every measurement into noise.
"""

from __future__ import annotations

import time
from collections.abc import Callable, Iterator
from typing import Any, TypeVar

import pytest

from pyguara.ai.flocking_system import FlockingAgent, FlockingSystem
from pyguara.common.components import Transform
from pyguara.common.random import RandomStream
from pyguara.common.spatial import SpatialHash
from pyguara.common.types import Vector2
from pyguara.ecs.manager import EntityManager

T = TypeVar("T")

# Rounds for a guard measurement. The reported figure is the *minimum*,
# not the mean: a slow round means something else on the machine got the
# CPU, and averaging that in measures the neighbours rather than the code.
GUARD_ROUNDS = 5


def measure(fn: Callable[[], Any], rounds: int = GUARD_ROUNDS) -> float:
    """Time `fn` and return the fastest run, in seconds.

    Args:
        fn: Zero-argument callable to time. Any setup belongs outside it --
            building 3000 entities takes longer than ticking them.
        rounds: How many times to run it.

    Returns:
        The shortest observed duration, in seconds.
    """
    best = float("inf")
    for _ in range(rounds):
        start = time.perf_counter()
        fn()
        best = min(best, time.perf_counter() - start)
    return best


def assert_scales_no_worse_than(
    *,
    small: float,
    large: float,
    factor: float,
    limit: float,
    what: str,
) -> None:
    """Assert that `large / small` is within what the complexity class allows.

    Args:
        small: Time for the smaller workload.
        large: Time for the larger workload.
        factor: How much bigger the large workload is (e.g. 4 for 4x).
        limit: Largest acceptable time ratio. For a linear algorithm at
            `factor=4`, something like 8 leaves generous headroom for
            constant factors while still catching a quadratic, which would
            land near 16.
        what: Name of the operation, for the failure message.

    Raises:
        AssertionError: If the ratio exceeds `limit`.
    """
    # A workload too fast to time reliably tells us nothing; treat the
    # floor as the resolution rather than dividing by near-zero.
    ratio = large / max(small, 1e-9)
    assert ratio <= limit, (
        f"{what} scaled {ratio:.1f}x for {factor}x the work "
        f"(limit {limit}x). Times: {small * 1e3:.2f}ms -> {large * 1e3:.2f}ms. "
        "That is a change of complexity class, not a constant factor."
    )


# ---- world builders -------------------------------------------------


def build_flock(
    count: int, *, spread: float, seed: int = 1234
) -> tuple[EntityManager, FlockingSystem]:
    """Build a world of `count` flocking agents and a system to tick it.

    Args:
        count: How many agents.
        spread: Width and height of the square the agents are scattered
            over. This is the knob that decides density, and density is
            what the spatial hash is sensitive to -- see
            `uniform_spread_for`.
        seed: Scatter seed, so a run is reproducible.

    Returns:
        The populated manager and a `FlockingSystem` over it.
    """
    rng = RandomStream(seed)
    manager = EntityManager()
    for _ in range(count):
        entity = manager.create_entity()
        entity.add_component(
            Transform(
                position=Vector2(rng.uniform(0.0, spread), rng.uniform(0.0, spread))
            )
        )
        entity.add_component(
            FlockingAgent(
                velocity=Vector2(rng.uniform(-40, 40), rng.uniform(-40, 40)),
                seek_weight=0.0,
            )
        )
    return manager, FlockingSystem(manager)


def uniform_spread_for(
    count: int, *, per_cell: float = 1.0, cell: float = 64.0
) -> float:
    """Return the spread that keeps density constant as `count` grows.

    A guard that grows the agent count inside a *fixed* area is measuring
    two things at once: more agents, and more neighbours each. Holding
    density constant isolates the first, which is the one the complexity
    claim is about.

    Args:
        count: Number of agents.
        per_cell: Target agents per cell.
        cell: The spatial hash's cell size.

    Returns:
        The side length of the square to scatter over.
    """
    return cell * (count / per_cell) ** 0.5


def build_hash(count: int, *, spread: float, seed: int = 99) -> SpatialHash[int]:
    """Build a `SpatialHash` holding `count` keys scattered over `spread`.

    Args:
        count: How many keys.
        spread: Width and height of the square to scatter over.
        seed: Scatter seed.

    Returns:
        The populated hash, keyed by index.
    """
    rng = RandomStream(seed)
    index: SpatialHash[int] = SpatialHash()
    for key in range(count):
        index.insert(key, Vector2(rng.uniform(0.0, spread), rng.uniform(0.0, spread)))
    return index


# ---- GL -------------------------------------------------------------


@pytest.fixture(scope="session")
def gl_ctx() -> Iterator[Any]:
    """A standalone ModernGL context, or a skip if the machine has none.

    Standalone rather than SDL: this needs no window, no display, and no
    swap semantics polluting a timing loop. `tools/agent_view.py --gl`
    uses SDL's offscreen driver instead, but that exists to capture what a
    *demo* draws, which is a different job.

    Blending is enabled here because the renderer does not do it --
    `PygameGLWindow.open()` does, and there is no window in this fixture.
    Anything measuring or reading back blended output has to set it up
    itself, which is worth knowing before trusting a pixel readback.

    Yields:
        The ModernGL context.
    """
    moderngl = pytest.importorskip("moderngl")
    try:
        ctx = moderngl.create_standalone_context()
    except Exception as exc:  # pragma: no cover - depends on the machine
        pytest.skip(f"no standalone GL context available: {exc}")

    ctx.enable(moderngl.BLEND)
    ctx.blend_func = moderngl.SRC_ALPHA, moderngl.ONE_MINUS_SRC_ALPHA
    try:
        yield ctx
    finally:
        ctx.release()
