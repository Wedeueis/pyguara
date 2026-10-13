#!/usr/bin/env python
"""Open a demo with PyGuara Studio attached, in a real window.

    uv run python tools/studio_demo.py
    uv run python tools/studio_demo.py tamandua_murundus
    uv run python tools/studio_demo.py guara_falcao --mode ask

Studio is ModernGL-only: it draws through the GL context the render graph
owns, and the Pygame backend's window is a software surface with none.
Every demo listed below already uses ModernGL; `main.py` and the other
demos do not, and Studio declines on them rather than half-installing.

The scene each demo starts on is its *gameplay* scene, not its title
screen -- there is nothing to author on a menu.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

# name -> (bootstrap module, scenes module, scene class). Explicit
# rather than discovered, and the class names are checked against
# `games/*/scenes.py`: four of them are not `GameScene`.
DEMOS: dict[str, tuple[str, str, str]] = {
    "guara_falcao": (
        "games.guara_falcao.bootstrap",
        "games.guara_falcao.scenes",
        "GameScene",
    ),
    "tamandua_murundus": (
        "games.tamandua_murundus.bootstrap",
        "games.tamandua_murundus.scenes",
        "ClearingScene",
    ),
    "quintal_cerrado": (
        "games.quintal_cerrado.bootstrap",
        "games.quintal_cerrado.scenes",
        "GardenScene",
    ),
    "true_coral": (
        "games.true_coral.bootstrap",
        "games.true_coral.scenes",
        "GameScene",
    ),
    "protocolo_bandeira": (
        "games.protocolo_bandeira.bootstrap",
        "games.protocolo_bandeira.scenes",
        "ArenaScene",
    ),
    "mourisco_ressonancia": (
        "games.mourisco_ressonancia.bootstrap",
        "games.mourisco_ressonancia.scenes",
        "CaveScene",
    ),
}


def _make_demos_resizable(*, borderless: bool = False) -> None:
    """Chain `display.resizable = True` onto every demo's configure hook.

    Demos call `create_container(_configure)` with their own hook, and the
    flags have to be set before the window exists. Wrapping the factory is
    how a tool adds one step to a hook it does not own; a game sets the
    fields in its own hook instead.

    Args:
        borderless: Also drop the OS title bar, so the editor draws its
            own. Opt-in: a borderless window relies on the editor's own
            buttons working, and the OS bar is the safe default.
    """
    from pyguara.application import bootstrap

    original = bootstrap.create_container

    def create_resizable(configure=None, register_sections=None):  # type: ignore[no-untyped-def]
        def chained(config):  # type: ignore[no-untyped-def]
            if configure is not None:
                configure(config)
            config.display.resizable = True
            if borderless:
                config.display.borderless = True

        return original(chained, register_sections)

    bootstrap.create_container = create_resizable  # type: ignore[assignment]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "demo", nargs="?", default="guara_falcao", choices=sorted(DEMOS)
    )
    parser.add_argument(
        "--mode",
        default="auto",
        choices=["auto", "ask", "plan"],
        help=(
            "how edits requested by an agent are handled: auto applies "
            "them, ask queues them for approval, plan only describes them"
        ),
    )
    parser.add_argument(
        "--borderless",
        action="store_true",
        help=(
            "drop the OS title bar and let the editor draw its own, the "
            "way Godot and VS Code do"
        ),
    )
    parser.add_argument(
        "--journal",
        default=None,
        help="append the action journal to this JSON Lines file",
    )
    args = parser.parse_args(argv)

    import importlib

    from pyguara.application.application import Application
    from pyguara.events.dispatcher import EventDispatcher
    from pyguara.studio import ApprovalMode, attach_studio

    bootstrap_mod, scenes_mod, scene_name = DEMOS[args.demo]

    # A demo's window is fixed-size, and SDL sends no resize event at all
    # for one -- a window manager may still let the frame be maximised,
    # and the editor would then draw at the starting resolution in a
    # corner of a much larger window. The flag is only honoured at
    # creation, so it is chained onto the demo's own `configure` hook
    # here rather than set afterwards.
    _make_demos_resizable(borderless=args.borderless)

    container = importlib.import_module(bootstrap_mod).configure_game_container()
    app = container.get(Application)

    attachment = attach_studio(
        container,
        project_root=REPO_ROOT,
        approval_mode=ApprovalMode(args.mode),
        journal_path=Path(args.journal) if args.journal else None,
    )
    if attachment is None:
        print(
            "Studio declined to attach. Almost always the backend: it needs "
            "ModernGL, and the Pygame window has no GL context. The log "
            "line above says which.",
            file=sys.stderr,
        )
        return 1

    scene_class = getattr(importlib.import_module(scenes_mod), scene_name)
    app.run(scene_class(container.get(EventDispatcher)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
