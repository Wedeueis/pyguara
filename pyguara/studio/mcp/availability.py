"""Whether the MCP SDK is importable, resolved once here.

The SDK is a transport, not the contract: the operation surface also
runs over `pyguara.studio.ops.stdio`, which needs only the standard
library. If this import fails, only the MCP front end is unavailable.
`mcp` is in the `dev` extra, and the test suite asserts the flag is
true there.

The check is for the 2.x shape of the SDK, which renamed `FastMCP` to
`MCPServer` and moved the low-level handlers to constructor callbacks,
so a 1.x install reads as "wrong version".
"""

from __future__ import annotations

from pyguara.log import get_logger

logger = get_logger(__name__)

MCP_AVAILABLE: bool
"""True when a usable `mcp` 2.x could be imported."""

MCP_IMPORT_ERROR: str | None
"""Why the import failed, or None when it succeeded."""

try:
    from mcp.server.lowlevel import Server as _Server  # noqa: F401
    from mcp.server.stdio import stdio_server as _stdio_server  # noqa: F401

    MCP_AVAILABLE = True
    MCP_IMPORT_ERROR = None
except ImportError as exc:  # pragma: no cover - the dev extra installs it
    MCP_AVAILABLE = False
    MCP_IMPORT_ERROR = str(exc)


def require_mcp() -> None:
    """Raise if the MCP SDK is missing, naming the install that provides it.

    Called by everything that would otherwise fail deeper in on a module
    that was never bound. Raising beats the alternative the deleted editor
    shipped -- an early-returning no-op that looked like a working server
    answering nothing.

    Raises:
        RuntimeError: If `mcp` is not importable, pointing at both the
            extra that provides it and the dependency-free transport that
            needs nothing.
    """
    if not MCP_AVAILABLE:
        raise RuntimeError(
            "The Studio MCP server needs the Model Context Protocol SDK, "
            f"which is not installed: {MCP_IMPORT_ERROR}. Install it with "
            "`uv sync --extra studio` or `pip install -e .[studio]`. The "
            "same operations are available with no extra dependency over "
            "`pyguara studio ops`, which speaks JSON lines on stdio."
        )
