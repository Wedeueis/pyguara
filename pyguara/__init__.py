"""PyGuara -- a modular, ECS-based 2D game engine for Python 3.12+."""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version
from typing import TYPE_CHECKING

try:
    __version__ = version("pyguara")
except PackageNotFoundError:  # pragma: no cover - source tree without an install
    __version__ = "0.0.0"

if TYPE_CHECKING:
    from pyguara.application.bootstrap import Configure, RegisterSections, Setup
    from pyguara.scene.base import Scene

__all__ = ["__version__", "run"]


def run(
    scene: Scene | type[Scene],
    *,
    configure: Configure | None = None,
    register_sections: RegisterSections | None = None,
    setup: Setup | None = None,
) -> None:
    """Build the engine, run `scene` until the window closes, and shut down.

    `pyguara.application.bootstrap.run` under its short name. The engine is
    imported when this is called, so `import pyguara` alone stays cheap.

    Args:
        scene: The first scene: an instance, or a `Scene` subclass that is
            built with no arguments.
        configure: Optional hook to adjust configuration before the window
            and backends are built from it.
        register_sections: Optional hook to register game-defined config
            sections before the configuration loads.
        setup: Optional hook to add to the container before the
            application is built from it.
    """
    from pyguara.application import bootstrap

    bootstrap.run(
        scene,
        configure=configure,
        register_sections=register_sections,
        setup=setup,
    )
