"""The operations Studio ships with, gathered into one registry.

Each group lives beside its handlers: `project`, `query`, `edit`,
`scenes`, `config`, `resources`, `run` and `history`. Rarer work goes
behind `scene`, `config`, `resources`, `history` and `approvals`, which
take an `operation` argument.

- An entity is named by id. Ids survive undo, redo and reload.
- An error names the alternative: "No entity 'playr'. Did you mean
  'player'?"
- Every edit returns its diff.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from pyguara.studio.ops import (
    config,
    edit,
    history,
    project,
    query,
    resources,
    run,
    scenes,
)
from pyguara.studio.ops._args import schema
from pyguara.studio.ops.registry import Operation, OperationRegistry, RiskClass

if TYPE_CHECKING:
    from pyguara.studio.session import StudioSession


def _list_operations(session: StudioSession, arguments: dict[str, Any]) -> Any:
    """Return every operation, so a client can discover the surface."""
    registry = default_registry()
    return {
        "operations": [
            {
                "name": operation.name,
                "summary": operation.summary,
                "risk": operation.risk.value,
            }
            for operation in registry
        ]
    }


def build_registry() -> OperationRegistry:
    """Build a registry holding every built-in operation.

    Returns:
        A fresh registry.
    """
    registry = OperationRegistry()
    for operation in _OPERATIONS:
        registry.register(operation)
    return registry


_DEFAULT_REGISTRY: OperationRegistry | None = None


def default_registry() -> OperationRegistry:
    """Return the shared registry, building it once.

    Returns:
        The process-wide registry. A caller that wants an isolated one --
        a test, or a game adding its own operations -- uses
        `build_registry()` instead.
    """
    global _DEFAULT_REGISTRY
    if _DEFAULT_REGISTRY is None:
        _DEFAULT_REGISTRY = build_registry()
    return _DEFAULT_REGISTRY


# The order is the order clients list the operations in.
_OPERATIONS: tuple[Operation, ...] = (
    Operation(
        name="list_operations",
        summary="List every Studio operation with its risk class.",
        risk=RiskClass.READ,
        parameters=schema({}),
        handler=_list_operations,
    ),
    *project.OPERATIONS,
    *query.OPERATIONS,
    *edit.ENTITY_OPERATIONS,
    *config.OPERATIONS,
    *resources.OPERATIONS,
    *scenes.OPERATIONS,
    *edit.COMPONENT_OPERATIONS,
    *run.OPERATIONS,
    *history.OPERATIONS,
)
