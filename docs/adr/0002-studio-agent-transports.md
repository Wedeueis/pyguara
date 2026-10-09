# ADR 0002: Two transports for Studio's agent surface

- **Status:** accepted
- **Date:** 2026-10-09
- **Context:** [issue #53](https://github.com/Wedeueis/pyguara/issues/53)

## Context

Studio's operations need to be reachable by a coding agent. The Model
Context Protocol is what agents speak, and its Python SDK is a real
dependency with a real API surface that has already had a major version
break (`mcp` 2.0 renamed `FastMCP` to `MCPServer` and moved the low-level
handlers from decorators to constructor callbacks).

This engine has been bitten by an optional dependency before, badly. The
first `pyguara/editor` imported pyimgui's pygame integration, which
transitively ran `import OpenGL.GL`. PyOpenGL was declared nowhere, so the
editor's `HAS_IMGUI` flag was unconditionally `False` in **every** install
configuration: every method early-returned, and 705 lines of subsystem
never executed once before being deleted. Nothing asserted on the flag,
which is how it hid for its entire life.

## Decision

**The operation surface is the contract. MCP is one transport over it.**

- `pyguara.studio.ops` — the registry, the schemas, the validation and
  every error message. Standard library only.
- `pyguara.studio.ops.stdio` — JSON lines on stdin and stdout. Standard
  library only. Works in every install, in a shell pipe, and from a test.
- `pyguara.studio.mcp` — a thin adapter presenting the same operations as
  MCP tools, behind an optional `studio` extra.

The adapter decides nothing. It does not define a schema, validate an
argument or compose an error, because the moment it did, the two front
ends would start to disagree — and the one that drifts is always the one
nobody is watching.

Two structural guards keep this honest:

- **A test blocks the `imgui_bundle` import and asserts the ops surface
  still loads.** Asserted by blocking rather than by reading source,
  because the coupling that broke it once was three modules away: a
  module-level `DockLayout` import in `studio/attach.py`, which
  `studio/__init__.py` imports, which `studio.ops` goes through.
- **`mcp` is in the `dev` extra as well as `studio`, so the availability
  test can *assert* the flag rather than skip on it.** That assertion is
  the whole lesson of the deleted editor.

## Alternatives considered

**MCP only.** Rejected: the agent surface would be unusable without the
SDK, and an optional dependency would be load-bearing for the feature it
fronts — exactly the shape that killed the first editor.

**Hand-rolled MCP, no dependency.** Rejected: we would own protocol
compatibility as MCP revisions land, for no gain over the SDK.

**`MCPServer` (the former `FastMCP`) instead of the low-level `Server`.**
Rejected: it derives a tool's schema from a Python function's type hints,
which is backwards here. The schemas are already written, emitted from the
component model, and carry enum members and field documentation no type
hint can express.

## Costs

- Two transports to keep working, mitigated by the adapter being thin
  enough that there is little to diverge.
- `mcp` is pinned to 2.x, so a 1.x install is refused rather than failing
  deeper in with an `AttributeError`.
