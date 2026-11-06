"""The network callbacks accept a function that returns something.

Every callback the networking code takes -- and the projectile kit's `on_end` --
throws away what it returns. Typed `-> None`, strict mypy refuses the callback the
docs recommend, `on_event=dispatcher.dispatch`, because `dispatch` returns a `bool`;
a game then wraps it in a lambda to satisfy the checker. `object` is the type for a
result nobody reads.

mypy does not check `tests/`, and nothing inside `pyguara/` passes a value-returning
function to these, so this runs mypy on a caller written the way a game writes one.
"""

from __future__ import annotations

import textwrap
from pathlib import Path

from mypy import api as mypy_api

_CALLER = textwrap.dedent(
    """
    from pyguara.ecs.entity import Entity
    from pyguara.ecs.manager import EntityManager
    from pyguara.events.dispatcher import EventDispatcher
    from pyguara.kits.projectiles import EndHandler, Projectile, ProjectileEnd
    from pyguara.net.driver import ClientDriver, HostDriver
    from pyguara.net.replication import ReplicationClient, ReplicationHost
    from pyguara.net.schema import ReplicationSchema
    from pyguara.net.session import ClientSession, HostSession, SessionEvent
    from pyguara.net.simulated import SimulatedNetwork


    class Clock:
        fixed_tick = 0


    def counted(event: SessionEvent) -> int:
        return 1


    def seen(entity: Entity | None) -> bool:
        return True


    def ended(projectile: Projectile, reason: ProjectileEnd) -> bool:
        return True


    def wire(
        world: EntityManager,
        dispatcher: EventDispatcher,
        schema: ReplicationSchema,
        host_session: HostSession,
        client_session: ClientSession,
        host: ReplicationHost,
        network: SimulatedNetwork,
        clock: Clock,
    ) -> None:
        client = ReplicationClient(
            world, schema, {}, on_event=dispatcher.dispatch, on_controlled=seen
        )
        ReplicationHost(world, schema, host_session.send, on_backlog=lambda peer: 1)
        HostDriver(clock, host_session, host, on_event=counted)
        ClientDriver(client_session, client, on_event=counted)
        network.tap = lambda source, destination, data: len(data)
        handler: EndHandler = ended
    """
)


def test_callbacks_take_a_function_that_returns_a_value(tmp_path: Path) -> None:
    """Strict mypy accepts `dispatcher.dispatch` and friends as callbacks."""
    caller = tmp_path / "caller.py"
    caller.write_text(_CALLER)
    out, err, status = mypy_api.run(
        [
            "--strict",
            "--no-incremental",
            "--follow-imports=silent",
            "--python-version=3.12",
            str(caller),
        ]
    )
    assert status == 0, out + err
