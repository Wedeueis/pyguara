"""`pyguara studio`: the authoring surface from a terminal.

Three subcommands, each the front door to something built elsewhere:

- **`instructions`** writes or checks the `AGENTS.md` family. Needs no
  engine at all, so it runs in CI.
- **`ops`** serves the operation surface as JSON lines on stdio. No
  dependency beyond the engine.
- **`mcp`** serves the same operations over the Model Context Protocol,
  which is what an agent is configured to launch.

`ops` and `mcp` speak on stdout, so **nothing else may**. This is not a
hypothetical: pygame prints a version banner to stdout the moment it is
imported, and the engine's `EngineLogger` builds its console handler
around `sys.stdout`, so a plain boot emits five lines of prose straight
into the protocol stream. A reader on the other end sees a parse error and
blames the protocol.

`_protocol_stdout()` is the fix. It hands the real stdout to the server
and points `sys.stdout` at stderr for everything else, before the engine
is imported -- so the banner, the boot logs and any stray `print` in game
code all land on stderr where they are readable and harmless.
"""

from __future__ import annotations

import os
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import IO

import click

from pyguara.studio.agent.journal import Actor, Journal
from pyguara.studio.session import ApprovalMode, StudioSession

APPROVAL_CHOICES = tuple(mode.value for mode in ApprovalMode)
"""The `--mode` values, taken from the enum so they cannot drift."""


@contextmanager
def _protocol_stdout() -> Iterator[IO[str]]:
    """Reserve stdout for the protocol, and send everything else to stderr.

    Yields the real stdout while `sys.stdout` points at stderr, so the
    only thing that reaches a client is what the server writes
    deliberately.

    Entered *before* the engine is imported, because the two worst
    offenders happen at import time: pygame prints a version banner, and
    `EngineLogger` builds its console handler around whatever `sys.stdout`
    is when the handler is constructed. Swapping afterwards would be too
    late for both.

    `PYGAME_HIDE_SUPPORT_PROMPT` is set as well. The redirect already
    catches the banner, but stderr is a log a person reads, and a version
    line nobody asked for is noise in it.

    Yields:
        The real stdout, to hand to the server.
    """
    os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")
    real_stdout = sys.stdout
    sys.stdout = sys.stderr
    try:
        yield real_stdout
    finally:
        sys.stdout = real_stdout


@click.group()
def studio() -> None:
    """Edit PyGuara content, and let coding agents do the same."""


@studio.command("instructions")
@click.argument(
    "project",
    type=click.Path(exists=True, file_okay=False, path_type=Path),
    default=".",
)
@click.option(
    "--check",
    is_flag=True,
    help="Report drift and exit non-zero instead of writing. For CI.",
)
@click.option(
    "--dry-run",
    is_flag=True,
    help="Print what would be written without writing it.",
)
@click.option(
    "--no-shims",
    is_flag=True,
    help="Write only AGENTS.md, no CLAUDE.md / GEMINI.md / Cursor rule.",
)
def instructions_command(
    project: Path, check: bool, dry_run: bool, no_shims: bool
) -> None:
    """Generate the instruction files coding agents read.

    Writes a canonical `AGENTS.md` and thin per-tool shims that import it.
    Anything outside the generated markers is preserved, so this is safe
    to run against a file full of hand-written knowledge.

    Args:
        project: The project directory. Defaults to the working directory.
        check: Report drift and exit 1 rather than writing.
        dry_run: Print the intended contents without writing.
        no_shims: Skip the per-tool shim files.

    Raises:
        SystemExit: With status 1 when `--check` finds drift.
    """
    # Imported for its side effect: the component vocabulary in the
    # generated file comes from the registry, which is empty until the
    # engine's own components are registered into it.
    from pyguara.application.bootstrap import _register_core_components
    from pyguara.prefabs.registry import get_component_registry
    from pyguara.studio.agent.instructions import (
        build_instructions,
        check_instructions,
        write_instructions,
    )

    registry = get_component_registry()
    _register_core_components(registry)

    from pyguara.studio.agent.instructions import ShimKind

    shims: tuple[ShimKind, ...] = (
        () if no_shims else (ShimKind.CLAUDE, ShimKind.GEMINI, ShimKind.CURSOR)
    )
    built = build_instructions(project, registry=registry, shims=shims)

    for warning in built.warnings:
        click.echo(click.style(f"warning: {warning}", fg="yellow"), err=True)

    if check:
        drifts = check_instructions(project, built)
        if not drifts:
            click.echo(click.style("Instruction files are up to date.", fg="green"))
            return
        for drift in drifts:
            click.echo(click.style(f"{drift.path}: {drift.reason}", fg="red"), err=True)
        click.echo("\nRun `pyguara studio instructions` to update them.", err=True)
        raise SystemExit(1)

    if dry_run:
        for file in built.files:
            click.echo(click.style(f"--- {file.path} ---", bold=True))
            click.echo(file.content)
        return

    written = write_instructions(project, built)
    if not written:
        click.echo("Already up to date.")
        return
    for path in written:
        click.echo(f"wrote {path.relative_to(project.resolve())}")


def _open_session(
    project: Path, scene: str | None, mode: str, journal_path: Path | None
) -> StudioSession:
    """Boot a headless engine and open a session over a world.

    Headless rather than windowed because both servers are driven by
    another process: there is nobody to look at a window, and opening one
    would fail on a machine with no display. The headless bootstrap still
    wires the resource manager, which is what lets a loaded scene resolve
    its textures -- without it every sprite would be skipped and the
    session would describe a scene that renders nothing.

    Args:
        project: The project directory, for the project map.
        scene: A scene to load, by the key `SceneSerializer` saved it
            under. None opens an empty world.
        mode: The approval mode name.
        journal_path: Where to append the journal, or None for memory only.

    Returns:
        The session.

    Raises:
        SystemExit: If the named scene could not be loaded. Starting with
            an empty world after being asked for a specific scene would
            look like an empty project.
    """
    from pyguara.application.bootstrap import create_headless_application
    from pyguara.ecs.manager import EntityManager
    from pyguara.prefabs.registry import ComponentRegistry
    from pyguara.scene.serializer import SceneSerializer

    application = create_headless_application()
    container = application.container

    world = EntityManager()
    scene_name = scene

    if scene is not None:
        from pyguara.events.dispatcher import EventDispatcher
        from pyguara.scene.base import Scene

        class _LoadedScene(Scene):
            """A bare scene to load into.

            `SceneSerializer.load_scene` touches only the entity manager,
            so it needs none of what `resolve_dependencies()` provides.
            """

            def on_enter(self) -> None: ...

            def on_exit(self) -> None: ...

            def update(self, dt: float) -> None: ...

        holder = _LoadedScene(scene, container.get(EventDispatcher))
        serializer = container.get(SceneSerializer)
        if not serializer.load_scene(holder, scene):
            raise SystemExit(
                f"Could not load the scene '{scene}'. It is a persistence "
                f"key, not a file path -- the name it was saved under."
            )
        world = holder.entity_manager

    return StudioSession(
        world,
        scene_name=scene_name,
        project_root=project.resolve(),
        component_registry=container.get(ComponentRegistry),
        journal=Journal(journal_path),
        approval_mode=ApprovalMode(mode),
    )


def _session_options(function: click.decorators.FC) -> click.decorators.FC:
    """Add the options both servers share.

    Args:
        function: The command to decorate.

    Returns:
        The decorated command.
    """
    function = click.option(
        "--project",
        type=click.Path(exists=True, file_okay=False, path_type=Path),
        default=".",
        help="The project directory, for `project_overview`.",
    )(function)
    function = click.option(
        "--scene",
        default=None,
        help="A saved scene to open, by its persistence key.",
    )(function)
    function = click.option(
        "--mode",
        type=click.Choice(APPROVAL_CHOICES),
        default=ApprovalMode.AUTO.value,
        help=(
            "auto applies edits; ask queues them for a person; plan "
            "describes them and changes nothing."
        ),
    )(function)
    return click.option(
        "--journal",
        "journal_path",
        type=click.Path(dir_okay=False, path_type=Path),
        default=None,
        help="Append the action journal to this file.",
    )(function)


@studio.command("ops")
@_session_options
def ops_command(
    project: Path, scene: str | None, mode: str, journal_path: Path | None
) -> None:
    """Serve the operation surface as JSON lines on stdin and stdout.

    One JSON object per line in, one per line out:

        {"op": "scene_summary"}
        {"op": "set_field", "args": {"entity_id": "hero", ...}}

    Needs no dependency beyond the engine itself, which is why it is the
    surface's contract and the MCP server is a second transport over it.

    Args:
        project: The project directory.
        scene: A saved scene to open, by its persistence key.
        mode: The approval mode.
        journal_path: Where to append the journal.
    """
    with _protocol_stdout() as stream:
        from pyguara.studio.ops.stdio import serve

        session = _open_session(project, scene, mode, journal_path)
        click.echo(
            f"pyguara studio ops ready ({len(session.snapshot())} entities, "
            f"mode={mode}). One JSON object per line; "
            f'{{"op": "list_operations"}} to begin.',
            err=True,
        )
        raise SystemExit(serve(session, stdout=stream))


@studio.command("mcp")
@_session_options
def mcp_command(
    project: Path, scene: str | None, mode: str, journal_path: Path | None
) -> None:
    """Serve the operation surface over the Model Context Protocol.

    What an agent is configured to launch as a stdio MCP server. Needs the
    `studio` extra; `pyguara studio ops` offers the same operations with
    no extra dependency.

    Args:
        project: The project directory.
        scene: A saved scene to open, by its persistence key.
        mode: The approval mode.
        journal_path: Where to append the journal.

    Raises:
        SystemExit: If the MCP SDK is not installed.
    """
    with _protocol_stdout() as stream:
        import anyio

        from pyguara.studio.mcp.availability import MCP_AVAILABLE, require_mcp

        if not MCP_AVAILABLE:
            try:
                require_mcp()
            except RuntimeError as exc:
                raise SystemExit(str(exc)) from exc

        from pyguara.studio.mcp.server import serve_stdio

        session = _open_session(project, scene, mode, journal_path)
        click.echo(
            f"pyguara studio mcp ready ({len(session.snapshot())} entities, "
            f"mode={mode}).",
            err=True,
        )
        anyio.run(
            lambda: serve_stdio(
                session, actor=Actor.AGENT, stdout=anyio.wrap_file(stream)
            )
        )


def main() -> int:
    """Run the studio command group standalone.

    Returns:
        A process exit code.
    """
    studio.main(standalone_mode=False)
    return 0


if __name__ == "__main__":  # pragma: no cover - manual entry point
    sys.exit(main())
