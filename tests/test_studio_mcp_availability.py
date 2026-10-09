"""The MCP SDK must be importable in a dev install, and say so when not.

The same guard `tests/test_editor_availability.py` provides, for the same
reason and after the same lesson. The engine's first optional dependency
was pyimgui's PyOpenGL requirement, which was declared nowhere: the
editor's `HAS_IMGUI` was unconditionally `False` in every install, every
method early-returned, and 705 lines of subsystem never executed once
before being deleted. Nothing asserted on the flag, which is how it hid
for its whole life.

So this asserts on the flag. If a dev install cannot import `mcp`, the
suite fails rather than quietly running without an MCP front end.
"""

from __future__ import annotations

import pytest

from pyguara.studio.mcp.availability import (
    MCP_AVAILABLE,
    MCP_IMPORT_ERROR,
    require_mcp,
)


def test_the_sdk_is_importable_in_a_dev_install() -> None:
    """The assertion whose absence killed the first editor.

    `mcp` is in the `dev` extra as well as the `studio` one precisely so
    this can be asserted rather than skipped.
    """
    assert MCP_AVAILABLE, (
        f"The MCP SDK could not be imported: {MCP_IMPORT_ERROR}. "
        f"Run `uv sync --all-extras`."
    )


def test_no_error_is_recorded_when_the_import_worked() -> None:
    assert MCP_IMPORT_ERROR is None


def test_require_mcp_passes_when_available() -> None:
    require_mcp()


def test_the_server_module_imports() -> None:
    """Importing it must not need a session, a world or a running engine.

    A module that can only be imported inside a configured application is
    a module nothing can test.
    """
    from pyguara.studio.mcp import server

    assert server.SERVER_NAME == "pyguara-studio"


def test_it_is_the_two_x_api_that_is_present() -> None:
    """`mcp` 2.0 renamed FastMCP to MCPServer and moved the low-level
    handlers from decorators to constructor callbacks, so a 1.x install
    cannot run the server. A version check here reads as "wrong version"
    rather than an `AttributeError` three frames into a request."""
    import inspect

    from mcp.server.lowlevel import Server

    parameters = inspect.signature(Server.__init__).parameters
    assert "on_list_tools" in parameters
    assert "on_call_tool" in parameters


def test_the_failure_message_names_both_ways_in(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A developer who hits this needs to know the extra that fixes it
    *and* that there is a dependency-free transport they can use now."""
    from pyguara.studio.mcp import availability

    monkeypatch.setattr(availability, "MCP_AVAILABLE", False)
    monkeypatch.setattr(availability, "MCP_IMPORT_ERROR", "no module named mcp")

    with pytest.raises(RuntimeError) as caught:
        availability.require_mcp()

    message = str(caught.value)
    assert "--extra studio" in message
    assert "pyguara studio ops" in message


def test_the_dependency_is_not_load_bearing() -> None:
    """The operation surface must work with no MCP SDK at all.

    This is the structural answer to how the last optional dependency
    became dead code: it was the only way in. `ops.stdio` imports nothing
    outside the standard library and the engine.
    """
    import pyguara.studio.ops.stdio as stdio

    source = stdio.__file__
    assert source is not None
    with open(source, encoding="utf-8") as handle:
        text = handle.read()
    assert "import mcp" not in text
    assert "from mcp" not in text
