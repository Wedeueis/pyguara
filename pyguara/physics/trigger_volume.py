"""Trigger volume components for zone-based gameplay mechanics.

Trigger volumes are sensor colliders that track which entities are inside them.
They're essential for implementing checkpoints, collectibles, damage zones,
teleporters, and any gameplay mechanic that activates when entities enter an area.

Usage:
    from pyguara.physics.trigger_volume import TriggerVolume

    # Create a checkpoint trigger
    checkpoint = entity_manager.create_entity()
    checkpoint.add_component(Transform(position=Vector2(400, 300)))
    checkpoint.add_component(TriggerVolume(
        shape_type=ShapeType.BOX,
        dimensions=[100, 100],
        tags={"player"}  # Only trigger for player entities
    ))

    # Check what's inside
    if checkpoint.trigger_volume.contains_entity(player.id):
        save_checkpoint()
"""

from dataclasses import dataclass, field
from typing import Optional, Set

from pyguara.ecs.component import BaseComponent
from pyguara.physics.types import ShapeType


@dataclass
class TriggerVolume(BaseComponent):
    """High-level trigger volume component that tracks entities inside it.

    TriggerVolume automatically creates a sensor Collider and subscribes to
    trigger events to maintain a list of entities currently inside the zone.
    It supports tag-based filtering to only trigger for specific entity types.

    The component state is automatically updated by TriggerSystem (if registered).
    Otherwise, you need to manually subscribe to OnTriggerEnter/Exit events.

    Attributes:
        shape_type: Geometric shape of the trigger zone.
        dimensions: Size parameters [radius] for circle, [width, height] for box.
        tags: Set of tags that can trigger this volume (empty = all entities trigger).
        entities_inside: Set of entity IDs currently inside the trigger.
        active: Whether the trigger is active (inactive triggers don't fire events).
        one_shot: If True, trigger deactivates after first entity enters.
    """

    # Shape configuration (creates sensor Collider)
    shape_type: ShapeType = ShapeType.BOX
    dimensions: list = field(default_factory=lambda: [100.0, 100.0])

    # Filtering
    tags: Set[str] = field(default_factory=set)

    # State (managed by TriggerSystem or manual event handlers)
    entities_inside: Set[str] = field(default_factory=set, repr=False)

    # Behavior
    active: bool = True
    one_shot: bool = False

    def __post_init__(self) -> None:
        """Initialize base component state."""
        super().__init__()

    def contains_entity(self, entity_id: str) -> bool:
        """Check if an entity is currently inside the trigger.

        Args:
            entity_id: Entity ID to check.

        Returns:
            True if entity is inside, False otherwise.
        """
        return entity_id in self.entities_inside

    def get_entity_count(self) -> int:
        """Get number of entities currently inside.

        Returns:
            Count of entities in the trigger.
        """
        return len(self.entities_inside)

    def is_empty(self) -> bool:
        """Check if trigger is empty.

        Returns:
            True if no entities are inside, False otherwise.
        """
        return len(self.entities_inside) == 0

    def has_any_entity(self) -> bool:
        """Check if trigger has any entities inside.

        Returns:
            True if at least one entity is inside, False otherwise.
        """
        return len(self.entities_inside) > 0

    def clear(self) -> None:
        """Remove all entities from the trigger state.

        This doesn't affect the actual physics simulation, only the
        internal tracking. Use this when resetting or cleaning up.
        """
        self.entities_inside.clear()

    def matches_tags(self, entity_tags: Optional[Set[str]]) -> bool:
        """Check if entity's tags match this trigger's filter.

        Args:
            entity_tags: Set of tags from the entity (or None).

        Returns:
            True if entity should trigger this volume, False otherwise.
        """
        # Empty filter = accept all entities
        if not self.tags:
            return True

        # No tags on entity = no match if filter is set
        if not entity_tags:
            return False

        # Check for any tag overlap
        return bool(self.tags & entity_tags)


@dataclass
class EntityTags(BaseComponent):
    """Component for tagging entities with string identifiers.

    Tags are used by TriggerVolumes for filtering which entities can
    activate them. They can also be used for general entity categorization.

    Attributes:
        tags: Set of string tags for this entity.
    """

    tags: Set[str] = field(default_factory=set)

    def __post_init__(self) -> None:
        """Initialize base component state."""
        super().__init__()

    def add_tag(self, tag: str) -> None:
        """Add a tag to this entity.

        Args:
            tag: Tag string to add.
        """
        self.tags.add(tag)

    def remove_tag(self, tag: str) -> None:
        """Remove a tag from this entity.

        Args:
            tag: Tag string to remove.
        """
        self.tags.discard(tag)

    def has_tag(self, tag: str) -> bool:
        """Check if entity has a specific tag.

        Args:
            tag: Tag string to check.

        Returns:
            True if entity has the tag, False otherwise.
        """
        return tag in self.tags

    def has_any_tag(self, *tags: str) -> bool:
        """Check if entity has any of the specified tags.

        Args:
            *tags: Tag strings to check.

        Returns:
            True if entity has at least one of the tags, False otherwise.
        """
        return bool(self.tags & set(tags))

    def has_all_tags(self, *tags: str) -> bool:
        """Check if entity has all of the specified tags.

        Args:
            *tags: Tag strings to check.

        Returns:
            True if entity has all the tags, False otherwise.
        """
        return set(tags).issubset(self.tags)
