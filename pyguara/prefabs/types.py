"""Type definitions for the prefab system.

Provides data structures for defining entity templates that can be
instantiated at runtime.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from pyguara.ecs.component import BaseComponent


@dataclass
class PrefabData:
    """Data structure representing a prefab template.

    A prefab defines an entity template with components and optional children.
    Prefabs support inheritance through the `extends` field.

    Attributes:
        name: Human-readable name for this prefab.
        version: Schema version for migration support.
        components: Dictionary mapping component names to their data.
        children: List of child prefab references with positioning.
        extends: Optional path to parent prefab for inheritance.
        tags: Optional list of tags for categorization.
    """

    name: str
    version: int = 1
    components: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    children: List[PrefabChild] = field(default_factory=list)
    extends: Optional[str] = None
    tags: List[str] = field(default_factory=list)


@dataclass
class PrefabChild:
    """Reference to a child prefab with positioning.

    Attributes:
        prefab: Path to the child prefab file.
        offset: Optional position offset from parent.
        name: Optional name override for the child entity.
        overrides: Optional component data overrides.
    """

    prefab: str
    offset: Optional[Dict[str, float]] = None
    name: Optional[str] = None
    overrides: Dict[str, Dict[str, Any]] = field(default_factory=dict)


@dataclass
class PrefabReference:
    """Lightweight reference to a prefab for lazy loading.

    Used when you want to reference a prefab without loading it immediately.

    Attributes:
        path: Path to the prefab file.
        loaded: Whether the prefab data has been loaded.
        data: The loaded prefab data, or None if not loaded.
    """

    path: str
    loaded: bool = False
    data: Optional[PrefabData] = None

    def is_loaded(self) -> bool:
        """Check if the prefab data has been loaded."""
        return self.loaded and self.data is not None


@dataclass
class PrefabInstance(BaseComponent):
    """Metadata about an instantiated prefab.

    Stored on entities created from prefabs for tracking and hot-reload.

    Attributes:
        prefab_path: Path to the source prefab.
        instance_overrides: Any runtime overrides applied.
    """

    prefab_path: str = ""
    instance_overrides: Dict[str, Dict[str, Any]] = field(default_factory=dict)
