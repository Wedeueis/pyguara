"""Whether the MCP SDK is importable, resolved once here.

This module exists for the same reason `pyguara/editor/availability.py`
does, and the history behind it is worth restating because this is the
second optional dependency the engine has taken on.

The first `pyguara/editor` imported pyimgui's pygame integration, which
transitively ran `import OpenGL.GL`. PyOpenGL was a dependency nowhere,
so the editor's `HAS_IMGUI` was unconditionally `False` in **every**
install configuration, every method early-returned, and 705 lines of
subsystem never executed once before being deleted. Nothing asserted on
that flag, which is how it hid.

Two things stop that happening here:

1. **The MCP SDK is a transport, not the contract.** The operation surface
   runs over `pyguara.studio.ops.stdio`, which needs nothing but the
   standard library. If this import fails, Studio's agent integration
   still works -- only the MCP front end is unavailable, and it says so.
   That is the structural answer: an optional dependency should not be
   load-bearing for the feature it fronts.
2. **A test asserts this flag is `True`.** `mcp` is in the `dev` extra, so
   a dev install that cannot import it fails the suite rather than
   quietly dropping the MCP server.

The SDK's major version matters. `mcp` 2.x renamed `FastMCP` to
`MCPServer` and moved the low-level API's handlers from decorators to
constructor callbacks, so a 1.x install cannot run this module. The check
below is for the 2.x shape specifically, rather than for the package
name, so a stale pin reads as "wrong version" instead of a confusing
`AttributeError` three frames into a request.
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
