"""
Interfaces definitions for core game systems.

Core system interfaces for PyGuara game engine.
Defines interfaces for dependency and data management, events, configuration and logging.
"""

from typing import Any, Dict, List, Protocol


class IResourceManager(Protocol):
    """Interface for loading raw assets and data files."""

    def load_json(self, path: str) -> Dict[str, Any]:
        """Load a JSON file and returns the raw dict."""
        ...

    def load_texture(self, path: str) -> Any:
        """Load an image file (e.g., png) as a surface."""
        ...

    def load_sound(self, path: str) -> Any:
        """Load an audio file."""
        ...

    def get_files_list(self, directory: str, extensions: str) -> List[str]:
        """Return all files in a folder (useful for auto-discovery)."""
        ...


class IEventDispatcher(Protocol):
    """Interface definition for event dispatchers."""

    pass
