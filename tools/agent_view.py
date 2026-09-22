#!/usr/bin/env python
"""Run a PyGuara demo headlessly and save frames, so an agent can see it.

An agent working on this engine cannot look at a window. This boots a demo,
advances it a fixed number of frames, optionally feeds it input, and writes PNG
frames it can open.

    uv run python tools/agent_view.py --list
    uv run python tools/agent_view.py guara_falcao --frames 120 --shot 1 --shot 119
    uv run python tools/agent_view.py ui_scene_graph --click 400,300@30 --shot 45
    uv run python tools/agent_view.py physics_integration --every 30 --frames 120

What this proves, and what it does not:

    It reads the surface the renderer drew onto. That proves the *render path*
    works -- entities queried, sprites submitted, batches flushed, UI laid out.

    It does NOT prove a window appears on screen. Those are different
    questions, and they have already diverged once here: with `vsync` enabled
    pygame silently promoted the display to an OpenGL surface, which never
    presents software blits. Captures looked perfect; the real window was
    blank.

    To check that a window actually displays, see
    docs/guides/agent-visual-inspection.md -- it needs a channel outside WSL.

Frames are checked for being a single flat colour and flagged, because a blank
frame is the most common way this silently tells you nothing.
"""

from __future__ import annotations

import argparse
import importlib
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

# Headless by default: surface capture works identically under the dummy
# driver, needs no display, and is deterministic on CI. --windowed overrides.
#
# `dummy` has no OpenGL at all ("OpenGL support is either not configured in
# SDL or not available in current SDL video driver"), so a ModernGL-backed
# demo cannot even create its context under it. `offscreen` does provide a
# real GL context headlessly, so --gl selects that instead; capture then has
# to read the GL framebuffer rather than a pygame surface (see `_capture`).
if "--windowed" not in sys.argv:
    _headless_driver = "offscreen" if "--gl" in sys.argv else "dummy"
    os.environ.setdefault("SDL_VIDEODRIVER", _headless_driver)
    os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame  # noqa: E402  (must follow the driver selection above)

DEFAULT_OUT = REPO_ROOT / ".agent-view"

# name -> (bootstrap module, scene module, scene class). Explicit rather than
# derived, so a broken demo names itself instead of failing during discovery.
DEMOS: dict[str, tuple[str, str, str]] = {
    "asset_pipeline": (
        "games.asset_pipeline.bootstrap",
        "games.asset_pipeline.scenes",
        "AssetScene",
    ),
    "boot_process": (
        "games.boot_process.bootstrap",
        "games.boot_process.scenes",
        "BootScene",
    ),
    "ecs_mental_model": (
        "games.ecs_mental_model.bootstrap",
        "games.ecs_mental_model.scenes",
        "ECSScene",
    ),
    "guara_falcao": (
        "games.guara_falcao.bootstrap",
        "games.guara_falcao.scenes",
        "TitleScene",
    ),
    "input_events": (
        "games.input_events.bootstrap",
        "games.input_events.scenes",
        "InputScene",
    ),
    "physics_integration": (
        "games.physics_integration.bootstrap",
        "games.physics_integration.scenes",
        "PhysicsScene",
    ),
    "protocolo_bandeira": (
        "games.protocolo_bandeira.bootstrap",
        "games.protocolo_bandeira.scenes",
        "MenuScene",
    ),
    "quintal_cerrado": (
        "games.quintal_cerrado.bootstrap",
        "games.quintal_cerrado.scenes",
        "TitleScene",
    ),
    "tamandua_murundus": (
        "games.tamandua_murundus.bootstrap",
        "games.tamandua_murundus.scenes",
        "ClearingScene",
    ),
    "true_coral": (
        "games.true_coral.bootstrap",
        "games.true_coral.scenes",
        "MenuScene",
    ),
    "ui_scene_graph": (
        "games.ui_scene_graph.bootstrap",
        "games.ui_scene_graph.scenes",
        "MenuScene",
    ),
    "mourisco_ressonancia": (
        "games.mourisco_ressonancia.bootstrap",
        "games.mourisco_ressonancia.scenes",
        "CaveScene",
    ),
    "vinagre_matilha": (
        "games.vinagre_matilha.bootstrap",
        "games.vinagre_matilha.scenes",
        "MenuScene",
    ),
}


@dataclass
class Script:
    """What to do on which frame."""

    frames: int = 120
    shots: set[int] = field(default_factory=set)
    keys: list[tuple[int, int]] = field(default_factory=list)
    clicks: list[tuple[int, int, int]] = field(default_factory=list)
    moves: list[tuple[int, int, int]] = field(default_factory=list)


def parse_at(value: str, what: str) -> tuple[str, int]:
    """Split a `payload@tick` argument.

    Args:
        value: The raw argument, e.g. `"SPACE@30"` or `"400,300@45"`.
        what: Argument name, for the error message.

    Returns:
        The payload and the tick it applies to. Tick defaults to 1.

    Raises:
        SystemExit: If the tick is not an integer.
    """
    payload, _, tick = value.partition("@")
    if not tick:
        return payload, 1
    if not tick.isdigit():
        raise SystemExit(f"--{what}: '{tick}' is not a frame number in {value!r}")
    return payload, int(tick)


def resolve_key(name: str) -> int:
    """Turn a key name into a pygame key code.

    Args:
        name: A pygame key name, with or without the `K_` prefix -- `SPACE`,
            `K_SPACE` and `space` all work.

    Returns:
        The pygame key constant.

    Raises:
        SystemExit: If no such key exists.
    """
    # pygame spells letter keys lowercase (`K_s`) and named keys uppercase
    # (`K_SPACE`), so try both rather than forcing one and rejecting half
    # the keyboard.
    candidates = (
        [name] if name.startswith("K_") else [f"K_{name.lower()}", f"K_{name.upper()}"]
    )
    for candidate in candidates:
        code = getattr(pygame, candidate, None)
        if isinstance(code, int):
            return code
    tried = ", ".join(f"pygame.{c}" for c in candidates)
    raise SystemExit(f"--press: unknown key {name!r} (tried {tried})")


def _window_type() -> type:
    """Return the `Window` type, imported late to keep driver setup first."""
    from pyguara.graphics.window import Window

    return Window


def _render_graph(container: object) -> object | None:
    """Return the demo's `RenderGraph`, if it runs on the ModernGL backend.

    The graph is the handle to everything GL here: its own context (making
    one fresh fails, since `moderngl.create_context()` detects through GLX
    and SDL's offscreen driver provides EGL) and, more importantly, the
    offscreen framebuffer the final pass blits from.
    """
    try:
        from pyguara.graphics.backends.pygame.stubs import PygameRenderGraph
        from pyguara.graphics.pipeline.graph import RenderGraph

        graph = container.get(RenderGraph)  # type: ignore[attr-defined]
    except Exception:
        return None
    if isinstance(graph, PygameRenderGraph):
        return None
    return graph


def _capture_fbo(graph: object) -> object | None:
    """Return the framebuffer the final pass blits from, if it exists.

    This is the buffer that holds the composed frame, and the one a GL
    capture reads. `_redirect_ui_into(...)` also aims the UI overlay at
    it, so a capture shows the frame a player would see rather than the
    frame minus its UI.
    """
    final_pass = graph.get_pass("final")  # type: ignore[attr-defined]
    name = getattr(final_pass, "input_fbo_name", "world")
    return graph.fbo_manager.get(name)  # type: ignore[attr-defined]


def _redirect_ui_into(container: object, graph: object, active: dict) -> None:
    """Make the UI overlay land in the capture buffer, not on the screen.

    **Why this is needed at all.** `Application` composites the UI onto the
    *default* framebuffer, after the final pass has blitted to it. A
    capture cannot read that: under SDL's offscreen driver the default
    framebuffer reads back as solid zeros (verified -- the read succeeds
    and returns nothing). So for as long as this tool has existed, every
    capture has been the frame *minus its UI*, and no `UIManager` widget
    in any demo had ever been seen in one.

    The fix is to bind the capture buffer immediately before the UI
    composites, so the overlay lands there instead. `GLUIRenderer.present()`
    draws a fullscreen quad into whatever framebuffer is bound, so no
    engine change is needed -- only the target.

    The screen loses its UI on those frames, which does not matter when
    nobody is looking at it. In `--windowed` runs somebody is, so this is
    not installed and a windowed capture still omits the UI layer.

    Args:
        container: The demo's DI container.
        graph: The render graph, or None for a non-GL backend.
        active: One-key dict the caller flips on capture ticks.
    """
    from pyguara.graphics.protocols import UIRenderer

    try:
        ui_renderer = container.get(UIRenderer)  # type: ignore[attr-defined]
    except Exception:  # pragma: no cover - backend without a UI renderer
        return

    original_present = ui_renderer.present

    def present_into_capture() -> None:
        if active["on"]:
            fbo = _capture_fbo(graph)
            if fbo is not None:
                fbo.bind()
        original_present()

    ui_renderer.present = present_into_capture  # type: ignore[method-assign]


def _capture(graph: object | None) -> pygame.Surface | None:
    """Return the frame just rendered, from whichever backend drew it.

    The pygame backends draw into the display surface, so reading it back
    is the whole job -- and their UI draws straight onto that surface, so
    it is already included.

    A ModernGL backend does not: under an `OPENGL` display,
    `get_surface()` hands back a surface the GPU never touched. So read
    the offscreen framebuffer the final pass blits from. The default
    framebuffer is no use -- after the swap it is an undefined back
    buffer, and before it reads back as solid zeros under the offscreen
    driver. The UI is composited into this same buffer on capture ticks;
    see `_redirect_ui_into()`.
    """
    surface = pygame.display.get_surface()
    if graph is None:
        return surface

    fbo = _capture_fbo(graph)
    if fbo is None:
        return surface

    size = (fbo.width, fbo.height)
    frame = pygame.image.frombuffer(fbo.fbo.read(components=3), size, "RGB")
    # GL's origin is bottom-left, pygame's is top-left.
    return pygame.transform.flip(frame, False, True)


def is_blank(surface: pygame.Surface) -> bool:
    """Report whether a frame is a single flat colour.

    A blank frame is the usual way this tool silently tells you nothing, so it
    is worth flagging rather than leaving for the reader to notice.

    Args:
        surface: The captured frame.

    Returns:
        True if every sampled pixel is identical.
    """
    width, height = surface.get_size()
    if width == 0 or height == 0:
        return True
    step_x = max(1, width // 32)
    step_y = max(1, height // 32)
    first = surface.get_at((0, 0))
    for y in range(0, height, step_y):
        for x in range(0, width, step_x):
            if surface.get_at((x, y)) != first:
                return False
    return True


def run(demo: str, script: Script, out_dir: Path) -> int:
    """Boot a demo, drive it, and write the requested frames.

    Args:
        demo: Key from `DEMOS`.
        script: Frames to run, frames to capture, input to inject.
        out_dir: Directory for the PNGs.

    Returns:
        A process exit code: 0 if frames were captured and none were blank,
        1 if every capture was blank, 2 if the demo raised.
    """
    from pyguara.application.application import Application
    from pyguara.events.dispatcher import EventDispatcher

    bootstrap_mod, scenes_mod, scene_name = DEMOS[demo]
    configure = importlib.import_module(bootstrap_mod).configure_game_container
    scene_class = getattr(importlib.import_module(scenes_mod), scene_name)

    out_dir.mkdir(parents=True, exist_ok=True)
    container = configure()
    app = container.get(Application)
    graph = _render_graph(container)

    tick = 0
    saved: list[tuple[Path, bool]] = []
    original_render = app._render

    # Flipped on for the frames being captured, so the UI composites into
    # the buffer the capture reads instead of onto the unreadable screen.
    # Not installed for a windowed run -- see `_redirect_ui_into()`.
    capturing = {"on": False}
    if graph is not None and "--windowed" not in sys.argv:
        _redirect_ui_into(container, graph, capturing)

    def render_and_capture() -> None:
        nonlocal tick
        tick += 1
        capturing["on"] = tick in script.shots

        for at, key in script.keys:
            if at == tick:
                pygame.event.post(pygame.event.Event(pygame.KEYDOWN, key=key))
        for at, x, y in script.moves:
            if at == tick:
                pygame.event.post(
                    pygame.event.Event(pygame.MOUSEMOTION, pos=(x, y), rel=(0, 0))
                )
        for at, x, y in script.clicks:
            if at == tick:
                pygame.event.post(
                    pygame.event.Event(pygame.MOUSEBUTTONDOWN, pos=(x, y), button=1)
                )
                pygame.event.post(
                    pygame.event.Event(pygame.MOUSEBUTTONUP, pos=(x, y), button=1)
                )

        original_render()

        if tick in script.shots:
            captured = _capture(graph)
            if captured is not None:
                path = out_dir / f"{demo}_{tick:04d}.png"
                pygame.image.save(captured, str(path))
                saved.append((path, is_blank(captured)))

        if tick >= script.frames:
            app._is_running = False

    app._render = render_and_capture  # type: ignore[method-assign]

    dispatcher = (
        container.get(EventDispatcher)
        if EventDispatcher in container._services
        else app._event_dispatcher
    )

    try:
        app.run(starting_scene=scene_class(dispatcher))
    except Exception as error:  # noqa: BLE001 - the report is the product here
        print(f"\nFAILED: {demo} raised {type(error).__name__}: {error}")
        import traceback

        traceback.print_exc()
        return 2

    print(f"\n{demo}: ran {tick} frames, captured {len(saved)}")
    for path, blank in saved:
        marker = "  BLANK - nothing was drawn" if blank else ""
        print(f"    {path}{marker}")

    if saved and all(blank for _, blank in saved):
        print(
            "\nEvery captured frame is a single flat colour. The render path "
            "produced nothing; this is not a display problem."
        )
        return 1
    return 0


def main(argv: list[str] | None = None) -> int:
    """Parse arguments and run one demo.

    Args:
        argv: Argument list, defaulting to `sys.argv[1:]`.

    Returns:
        A process exit code.
    """
    parser = argparse.ArgumentParser(
        description="Run a PyGuara demo headlessly and save frames to look at.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "examples:\n"
            "  agent_view.py --list\n"
            "  agent_view.py guara_falcao --frames 120 --shot 1 --shot 119\n"
            "  agent_view.py guara_falcao --press RETURN@20 --shot 40\n"
            "  agent_view.py ui_scene_graph --click 400,300@30 --shot 45\n"
            "  agent_view.py quintal_cerrado --move 200,200@30 --shot 60\n"
            "  agent_view.py physics_integration --every 30\n"
        ),
    )
    parser.add_argument("demo", nargs="?", help="demo name; see --list")
    parser.add_argument("--list", action="store_true", help="list demo names and exit")
    parser.add_argument("--frames", type=int, default=120, help="frames to run (120)")
    parser.add_argument(
        "--shot",
        action="append",
        type=int,
        default=[],
        metavar="TICK",
        help="capture this frame; repeatable",
    )
    parser.add_argument("--every", type=int, metavar="N", help="capture every N frames")
    parser.add_argument(
        "--press",
        action="append",
        default=[],
        metavar="KEY@TICK",
        help="press a key on a frame, e.g. SPACE@30; repeatable",
    )
    parser.add_argument(
        "--click",
        action="append",
        default=[],
        metavar="X,Y@TICK",
        help="click a point on a frame, e.g. 400,300@30; repeatable",
    )
    parser.add_argument(
        "--move",
        action="append",
        default=[],
        metavar="X,Y@TICK",
        help="move the cursor to a point on a frame, e.g. 400,300@30; "
        "repeatable. What hover states and tooltips need: a click alone "
        "never tells the UI where the cursor is",
    )
    parser.add_argument(
        "--out", type=Path, default=DEFAULT_OUT, help=f"output dir ({DEFAULT_OUT.name})"
    )
    parser.add_argument(
        "--windowed",
        action="store_true",
        help="use a real window instead of the dummy driver",
    )
    parser.add_argument(
        "--gl",
        action="store_true",
        help="headless OpenGL: use SDL's offscreen driver (dummy has no GL) "
        "and capture the GL framebuffer. Required for ModernGL demos.",
    )
    args = parser.parse_args(argv)

    if args.list:
        print("demos:")
        for name, (_, _, scene) in sorted(DEMOS.items()):
            print(f"  {name:<22} starts in {scene}")
        return 0

    if not args.demo:
        parser.error("give a demo name, or --list")
    if args.demo not in DEMOS:
        parser.error(f"unknown demo {args.demo!r}. Known: {', '.join(sorted(DEMOS))}")

    script = Script(frames=args.frames, shots=set(args.shot))
    if args.every:
        script.shots.update(range(args.every, args.frames + 1, args.every))
    if not script.shots:
        # Capture something rather than nothing: the last frame is the most
        # informative single frame for a run nobody scripted.
        script.shots = {args.frames}

    for raw in args.press:
        name, at = parse_at(raw, "press")
        script.keys.append((at, resolve_key(name)))
    for flag, raw_values, target in (
        ("click", args.click, script.clicks),
        ("move", args.move, script.moves),
    ):
        for raw in raw_values:
            point, at = parse_at(raw, flag)
            try:
                x_str, y_str = point.split(",")
                target.append((at, int(x_str), int(y_str)))
            except ValueError:
                raise SystemExit(f"--{flag}: expected X,Y@TICK, got {raw!r}") from None

    return run(args.demo, script, args.out)


if __name__ == "__main__":
    raise SystemExit(main())
