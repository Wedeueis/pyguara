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
