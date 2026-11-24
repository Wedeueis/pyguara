"""The demos the capture tools and tests can boot, by name, and where they are.

The demos are `examples/` in this checkout unless `PYGUARA_EXAMPLES` names
another folder, such as a checkout of a separate examples repository. The
folder's name is the package the demos import as, and its parent is the
directory their relative asset paths start from: run a demo with that as
the working directory.

Standard library only, so a check that runs a demo with pygame made
unimportable (`tests/integration/_without_pygame.py`) can read it without
`agent_view` loading pygame first.
"""

from __future__ import annotations

import importlib
import os
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

EXAMPLES_DIR = Path(
    os.environ.get("PYGUARA_EXAMPLES")
    or Path(__file__).resolve().parent.parent / "examples"
).resolve()
"""The folder holding one package per demo."""

DEMO_ROOT = EXAMPLES_DIR.parent
"""The working directory a demo expects: its asset paths are relative to it."""

PACKAGE = EXAMPLES_DIR.name

# name -> starting scene class. Explicit rather than derived, so a broken demo
# names itself instead of failing during discovery.
_SCENES: dict[str, str] = {
    "asset_pipeline": "AssetScene",
    "boot_process": "BootScene",
    "correicao": "HordeScene",
    "ecs_mental_model": "ECSScene",
    "net_horde": "SideBySideScene",
    "guara_falcao": "TitleScene",
    "input_events": "InputScene",
    "physics_integration": "PhysicsScene",
    "protocolo_bandeira": "MenuScene",
    "quintal_cerrado": "TitleScene",
    "tilemap_authoring": "TilemapScene",
    "tamandua_murundus": "ClearingScene",
    "true_coral": "MenuScene",
    "ui_scene_graph": "MenuScene",
    "mourisco_ressonancia": "CaveScene",
    "vinagre_matilha": "MenuScene",
}

# name -> (bootstrap module, scene module, scene class).
DEMOS: dict[str, tuple[str, str, str]] = {
    name: (f"{PACKAGE}.{name}.bootstrap", f"{PACKAGE}.{name}.scenes", scene)
    for name, scene in _SCENES.items()
}


def demo_module(demo: str, module: str) -> ModuleType:
    """Import one module of a demo, putting the demos on the import path.

    Args:
        demo: A key of `DEMOS`.
        module: The module inside the demo's package, such as `"scenes"`.

    Returns:
        The imported module.

    Raises:
        KeyError: If `demo` is not a known demo.
        ImportError: If a package of the same name was already imported
            from another folder.
    """
    if demo not in DEMOS:
        raise KeyError(f"unknown demo {demo!r}. Known: {', '.join(sorted(DEMOS))}")
    root = str(DEMO_ROOT)
    if root in sys.path:
        sys.path.remove(root)
    sys.path.insert(0, root)
    imported = importlib.import_module(f"{PACKAGE}.{demo}.{module}")
    # A package of the same name imported earlier from elsewhere wins over
    # the path; booting it would test the wrong demos without saying so.
    if not Path(imported.__file__ or "").resolve().is_relative_to(EXAMPLES_DIR):
        raise ImportError(
            f"{imported.__name__} was imported from {imported.__file__}, "
            f"not from {EXAMPLES_DIR}: a package named {PACKAGE!r} was "
            "already loaded from another folder"
        )
    return imported


def load_demo(demo: str) -> tuple[Any, type]:
    """Import a demo and return what boots it.

    Args:
        demo: A key of `DEMOS`.

    Returns:
        The demo's `configure_game_container` and its starting scene class.
    """
    configure = demo_module(demo, "bootstrap").configure_game_container
    scene_class = getattr(demo_module(demo, "scenes"), DEMOS[demo][2])
    return configure, scene_class
