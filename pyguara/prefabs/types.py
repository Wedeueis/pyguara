"""Type definitions for the prefab system.

Provides data structures for defining entity templates that can be
instantiated at runtime.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

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
    components: dict[str, dict[str, Any]] = field(default_factory=dict)
    children: list[PrefabChild] = field(default_factory=list)
    extends: str | None = None
    tags: list[str] = field(default_factory=list)


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
    offset: dict[str, float] | None = None
    name: str | None = None
    overrides: dict[str, dict[str, Any]] = field(default_factory=dict)


@dataclass
class PrefabInstance(BaseComponent):
    """Metadata about an instantiated prefab.

    Stored on entities created from prefabs for tracking and hot-reload.

    Attributes:
        prefab_path: Path to the source prefab.
        instance_overrides: Any runtime overrides applied.
    """

    prefab_path: str = ""
    instance_overrides: dict[str, dict[str, Any]] = field(default_factory=dict)
