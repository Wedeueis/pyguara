"""The Model Context Protocol front end over Studio's operations.

An optional adapter, not the contract. The operation surface itself runs
over `pyguara.studio.ops.stdio` with nothing but the standard library;
this exposes the same operations as MCP tools for clients that speak it.

See `availability.py` for why the dependency is optional and what stops
it becoming dead code the way the engine's first optional dependency did.
"""

from pyguara.studio.mcp.availability import (
    MCP_AVAILABLE,
    MCP_IMPORT_ERROR,
    require_mcp,
)

__all__ = ["MCP_AVAILABLE", "MCP_IMPORT_ERROR", "require_mcp"]
