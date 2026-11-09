"""The ECS's subscriptions accept a function that returns something.

Like the network callbacks (`tests/test_net_callback_typing.py`), what an ECS
subscriber returns is thrown away. Typed `-> None`, strict mypy refuses the
obvious subscriber -- a dispatcher's `dispatch`, which returns a `bool` -- and a
game wraps it in a function to satisfy the checker. `object` is the type for a
result nobody reads.

mypy does not check `tests/`, and nothing inside `pyguara/` subscribes a
value-returning function, so this runs mypy on a caller written the way a game
writes one.
"""

from __future__ import annotations

import textwrap
from pathlib import Path

from mypy import api as mypy_api

_CALLER = textwrap.dedent(
    """
    from pyguara.ecs.component import BaseComponent, Component
    from pyguara.ecs.entity import Entity
    from pyguara.ecs.events import EntityDestroyed
    from pyguara.ecs.manager import EntityManager
    from pyguara.events.dispatcher import EventDispatcher


    class Marker(BaseComponent):
        pass


    def counted(entity: Entity, component: Component) -> int:
        return 1


    def wire(world: EntityManager, dispatcher: EventDispatcher) -> None:
        world.subscribe_entity_removed(
            lambda entity: dispatcher.dispatch(EntityDestroyed(entity=entity))
        )
        world.subscribe_component_added(Marker, counted)
        world.subscribe_component_removed(Marker, counted)
        world.subscribe_component_changed(Marker, counted)
    """
)


def test_subscriptions_take_a_function_that_returns_a_value(tmp_path: Path) -> None:
    """Strict mypy accepts `dispatcher.dispatch` and friends as ECS subscribers."""
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
