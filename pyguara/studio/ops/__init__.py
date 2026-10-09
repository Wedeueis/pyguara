"""The operation surface: one registry, three front ends.

A human picking from the command palette, an agent calling an MCP tool,
and a script piping JSON into `pyguara studio ops` all reach the same
`Operation` objects -- because three parallel surfaces drift, and the one
that drifts is always the one the agent uses.
"""

from pyguara.studio.ops.builtin import build_registry, default_registry
from pyguara.studio.ops.registry import (
    Operation,
    OperationError,
    OperationRegistry,
    OperationResult,
    RiskClass,
)
from pyguara.studio.ops.stdio import handle_line, handle_lines, serve

__all__ = [
    "Operation",
    "OperationError",
    "OperationRegistry",
    "OperationResult",
    "RiskClass",
    "build_registry",
    "default_registry",
    "handle_line",
    "handle_lines",
    "serve",
]
