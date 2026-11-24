"""The swarm, held to recorded values and to its Python reference, exactly.

`tests/golden/swarm.json` was recorded from the native swarm where
`tests/reference/swarm.py` agreed with it bit for bit. Both comparisons are
exact, in `float.hex()`.
"""

from __future__ import annotations

import pytest

from pyguara.common.types import Vector2
from tests.golden.swarm import SCENARIOS, Scenario, encode, load, native
from tests.reference.swarm import ReferenceSwarm

RECORDED = load()


def _reference_rows(scenario: Scenario) -> list[list[str | int]]:
    swarm = ReferenceSwarm(cell_size=scenario.cell_size)
    scenario.play(swarm)
    return [
        [agent, x.hex(), y.hex(), vx.hex(), vy.hex()]
        for agent, x, y, vx, vy in swarm.state()
    ]


def test_every_scenario_is_recorded() -> None:
    assert set(RECORDED) == {scenario.name for scenario in SCENARIOS}


@pytest.mark.parametrize("scenario", SCENARIOS, ids=lambda s: s.name)
def test_the_scenarios_are_not_trivial(scenario: Scenario) -> None:
    """Every scenario has agents that steered by flockmates."""
    swarm = native(scenario)
    counts = swarm.neighbour_counts()
    assert swarm.count > 0
    assert sum(1 for count in counts if count > 0) >= len(counts) // 10


@pytest.mark.parametrize("scenario", SCENARIOS, ids=lambda s: s.name)
def test_the_swarm_matches_its_recording(scenario: Scenario) -> None:
    assert encode(native(scenario)) == RECORDED[scenario.name]


@pytest.mark.parametrize("scenario", SCENARIOS, ids=lambda s: s.name)
def test_the_swarm_matches_its_reference(scenario: Scenario) -> None:
    assert encode(native(scenario)) == _reference_rows(scenario)


def test_every_agent_steers_from_the_start_of_the_tick() -> None:
    """Two mirror-image agents stay mirror images.

    Were an agent to see a neighbour already moved this tick, the one
    computed second would steer differently from its twin.
    """
    from pyguara.ai.swarm import Swarm, SwarmKind

    swarm = Swarm(cell_size=64.0)
    kind = swarm.add_kind(SwarmKind(separation_radius=40.0))
    left, right = swarm.spawn(
        kind, [Vector2(90, 100), Vector2(110, 100)], [Vector2(5, 3), Vector2(-5, 3)]
    )
    for _ in range(30):
        swarm.update(1 / 60)
        (a, b), (va, vb) = (
            swarm.positions([left, right]),
            swarm.velocities([left, right]),
        )
        assert a.x - 100 == 100 - b.x and a.y == b.y
        assert va.x == -vb.x and va.y == vb.y
