"""PyGuara -- a modular, ECS-based 2D game engine for Python 3.12+."""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("pyguara")
except PackageNotFoundError:  # pragma: no cover - source tree without an install
    __version__ = "0.0.0"

__all__ = ["__version__"]
