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
# A wgpu demo draws offscreen under it (no window is opened), and the capture
# reads the frame back from the GPU.
if "--windowed" not in sys.argv:
    os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
    os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
    # The wgpu window's own switch; SDL's no longer reaches it.
    os.environ.setdefault("PYGUARA_WINDOW", "offscreen")

import pygame  # noqa: E402  (must follow the driver selection above)

DEFAULT_OUT = REPO_ROOT / ".agent-view"

from tools.demo_list import DEMOS  # noqa: E402


@dataclass
class Script:
    """What to do on which frame."""

    frames: int = 120
    shots: set[int] = field(default_factory=set)
    keys: list[tuple[int, int]] = field(default_factory=list)
    clicks: list[tuple[int, int, int]] = field(default_factory=list)
    moves: list[tuple[int, int, int]] = field(default_factory=list)
    require_world: bool = False


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
    """Return the demo's `RenderGraph`, if it runs on the wgpu backend.

    The handle to the world buffer, for `--require-world`.
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


def capture_frame(window: object) -> pygame.Surface | None:
    """Return the frame just rendered, UI included.

    The pygame backend draws onto pygame's display surface, so that is
    read. The wgpu window draws into a GPU target, offscreen here, and is
    read back from it.

    Args:
        window: The application's `Window`.
    """
    read_pixels = getattr(window.backend, "read_pixels", None)  # type: ignore[attr-defined]
    if read_pixels is None:
        return pygame.display.get_surface()
    pixels, width, height = read_pixels()
    return pygame.image.frombuffer(pixels, (width, height), "RGBA").copy()


def _capture_world(graph: object | None) -> pygame.Surface | None:
    """Return the world pass's own buffer, before any UI is composited.

    `_capture` reads the *composed* frame, which on a wgpu demo also
    carries the UI overlay. That makes `is_blank` useless for the failure
    it was built to catch: a dead world render path still leaves a HUD on
    screen, so the frame is never a single flat colour. Reading "world"
    alone is what can tell whether the scene itself drew anything.

    Args:
        graph: The render graph, or None for the pygame backend.

    Returns:
        The world buffer as a surface, or None when there is no graph.
    """
    if graph is None:
        return None
    fbo = graph.fbo_manager.get("world")  # type: ignore[attr-defined]
    if fbo is None:
        return None
    return _wgpu_buffer(fbo)


def _wgpu_buffer(fbo: object) -> pygame.Surface:
    """Read a wgpu buffer back as a surface; an HDR one is clipped to 8 bits."""
    size = (fbo.width, fbo.height)  # type: ignore[attr-defined]
    raw = fbo.read_rgba()  # type: ignore[attr-defined]
    return pygame.image.frombuffer(raw, size, "RGBA").copy()


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
    from pyguara.events.input import (
        KeyDownEvent,
        MouseButtonEvent,
        MouseMotionEvent,
    )

    bootstrap_mod, scenes_mod, scene_name = DEMOS[demo]
    configure = importlib.import_module(bootstrap_mod).configure_game_container
    scene_class = getattr(importlib.import_module(scenes_mod), scene_name)

    out_dir.mkdir(parents=True, exist_ok=True)
    container = configure()
    app = container.get(Application)
    window = container.get(_window_type())
    graph = _render_graph(container)

    tick = 0
    saved: list[tuple[Path, bool]] = []
    flat_world: list[Path] = []
    original_render = app._render

    def render_and_capture() -> None:
        nonlocal tick
        tick += 1

        # Engine events, posted to the window: they take the path real
        # input takes, on either backend, with no SDL queue involved.
        for at, key in script.keys:
            if at == tick:
                window.post_event(KeyDownEvent(key_code=key))
        for at, x, y in script.moves:
            if at == tick:
                window.post_event(MouseMotionEvent(x=x, y=y, rel_x=0, rel_y=0))
        for at, x, y in script.clicks:
            if at == tick:
                window.post_event(MouseButtonEvent(button=1, x=x, y=y, is_down=True))
                window.post_event(MouseButtonEvent(button=1, x=x, y=y, is_down=False))

        original_render()

        if tick in script.shots:
            captured = capture_frame(window)
            if captured is not None:
                path = out_dir / f"{demo}_{tick:04d}.png"
                pygame.image.save(captured, str(path))
                saved.append((path, is_blank(captured)))
                if script.require_world:
                    world = _capture_world(graph)
                    if world is not None and is_blank(world):
                        flat_world.append(path)

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

    if flat_world and len(flat_world) == len(saved):
        print(
            "\nThe world pass drew nothing: its own buffer is a single flat "
            "colour on every captured frame. The frame above only looks fine "
            "because the UI overlay is composited over it, and that is drawn "
            "by a different renderer -- it proves nothing about the world."
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
        "--require-world",
        action="store_true",
        help="fail if the world pass drew nothing, even when the UI overlay "
        "keeps the composed frame from looking blank. For a run driven into "
        "gameplay -- a menu's world legitimately is a flat clear",
    )
    parser.add_argument(
        "--out", type=Path, default=DEFAULT_OUT, help=f"output dir ({DEFAULT_OUT.name})"
    )
    parser.add_argument(
        "--windowed",
        action="store_true",
        help="use a real window instead of the dummy driver",
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
    script.require_world = args.require_world
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
