"""Tests for trigger volume system."""

from pyguara.common.components import Transform
from pyguara.common.types import Vector2
from pyguara.ecs.manager import EntityManager
from pyguara.events.dispatcher import EventDispatcher
from pyguara.physics.components import Collider
from pyguara.physics.events import OnTriggerEnter, OnTriggerExit
from pyguara.physics.trigger_system import TriggerSystem
from pyguara.physics.trigger_volume import EntityTags, TriggerVolume
from pyguara.physics.types import ShapeType


class TestTriggerVolumeComponent:
    """Test TriggerVolume component functionality."""

    def test_trigger_volume_creation(self):
        """TriggerVolume should be created with default values."""
        trigger = TriggerVolume()

        assert trigger.shape_type == ShapeType.BOX
        assert trigger.dimensions == [100.0, 100.0]
        assert trigger.tags == set()
        assert trigger.entities_inside == set()
        assert trigger.active is True
        assert trigger.one_shot is False

    def test_trigger_volume_with_tags(self):
        """TriggerVolume can be created with tag filter."""
        trigger = TriggerVolume(tags={"player", "enemy"})

        assert trigger.tags == {"player", "enemy"}

    def test_contains_entity(self):
        """contains_entity should check if entity is inside."""
        trigger = TriggerVolume()
        trigger.entities_inside.add("entity123")

        assert trigger.contains_entity("entity123") is True
        assert trigger.contains_entity("entity456") is False

    def test_get_entity_count(self):
        """get_entity_count should return number of entities inside."""
        trigger = TriggerVolume()
        trigger.entities_inside.add("e1")
        trigger.entities_inside.add("e2")
        trigger.entities_inside.add("e3")

        assert trigger.get_entity_count() == 3

    def test_is_empty(self):
        """is_empty should check if trigger has no entities."""
        trigger = TriggerVolume()

        assert trigger.is_empty() is True

        trigger.entities_inside.add("e1")
        assert trigger.is_empty() is False

    def test_has_any_entity(self):
        """has_any_entity should check if trigger has entities."""
        trigger = TriggerVolume()

        assert trigger.has_any_entity() is False

        trigger.entities_inside.add("e1")
        assert trigger.has_any_entity() is True

    def test_clear(self):
        """clear should remove all entities from trigger."""
        trigger = TriggerVolume()
        trigger.entities_inside.add("e1")
        trigger.entities_inside.add("e2")

        trigger.clear()

        assert trigger.is_empty() is True

    def test_matches_tags_empty_filter(self):
        """Empty tag filter should match all entities."""
        trigger = TriggerVolume(tags=set())

        assert trigger.matches_tags(None) is True
        assert trigger.matches_tags(set()) is True
        assert trigger.matches_tags({"player"}) is True

    def test_matches_tags_with_filter(self):
        """Tag filter should match entities with overlapping tags."""
        trigger = TriggerVolume(tags={"player", "npc"})

        # Match: has "player" tag
        assert trigger.matches_tags({"player"}) is True

        # Match: has "npc" tag
        assert trigger.matches_tags({"npc", "friendly"}) is True

        # No match: no overlapping tags
        assert trigger.matches_tags({"enemy", "hostile"}) is False

        # No match: entity has no tags
        assert trigger.matches_tags(None) is False
        assert trigger.matches_tags(set()) is False


class TestEntityTags:
    """Test EntityTags component."""

    def test_entity_tags_creation(self):
        """EntityTags should be created with empty set."""
        tags = EntityTags()

        assert tags.tags == set()

    def test_entity_tags_with_initial_tags(self):
        """EntityTags can be created with initial tags."""
        tags = EntityTags(tags={"player", "friendly"})

        assert tags.tags == {"player", "friendly"}

    def test_add_tag(self):
        """add_tag should add a tag to the set."""
        tags = EntityTags()
        tags.add_tag("player")

        assert "player" in tags.tags

    def test_remove_tag(self):
        """remove_tag should remove a tag from the set."""
        tags = EntityTags(tags={"player", "friendly"})
        tags.remove_tag("friendly")

        assert "player" in tags.tags
        assert "friendly" not in tags.tags

    def test_has_tag(self):
        """has_tag should check for specific tag."""
        tags = EntityTags(tags={"player"})

        assert tags.has_tag("player") is True
        assert tags.has_tag("enemy") is False

    def test_has_any_tag(self):
        """has_any_tag should check for any matching tag."""
        tags = EntityTags(tags={"player", "friendly"})

        assert tags.has_any_tag("player") is True
        assert tags.has_any_tag("enemy", "player") is True
        assert tags.has_any_tag("enemy", "hostile") is False

    def test_has_all_tags(self):
        """has_all_tags should check for all specified tags."""
        tags = EntityTags(tags={"player", "friendly", "alive"})

        assert tags.has_all_tags("player", "friendly") is True
        assert tags.has_all_tags("player", "enemy") is False


class TestTriggerSystem:
    """Test TriggerSystem integration."""

    def setup_method(self):
        """Set up test environment."""
        self.manager = EntityManager()
        self.dispatcher = EventDispatcher()
        self.trigger_system = TriggerSystem(self.manager, self.dispatcher)

    def test_trigger_system_creation(self):
        """TriggerSystem should be created successfully."""
        assert self.trigger_system is not None

    def test_trigger_enter_updates_volume(self):
        """OnTriggerEnter event should update TriggerVolume state."""
        # Create trigger entity
        trigger_entity = self.manager.create_entity()
        trigger_entity.add_component(Transform(position=Vector2(100, 100)))
        trigger_entity.add_component(TriggerVolume())

        # Create entering entity
        player = self.manager.create_entity()

        # Simulate trigger enter event
        event = OnTriggerEnter(
            trigger_entity=trigger_entity.id, other_entity=player.id, timestamp=0.0
        )
        self.dispatcher.dispatch(event)

        # Check trigger was updated
        trigger_volume = trigger_entity.get_component(TriggerVolume)
        assert trigger_volume.contains_entity(player.id)

    def test_trigger_exit_updates_volume(self):
        """OnTriggerExit event should update TriggerVolume state."""
        # Create trigger entity
        trigger_entity = self.manager.create_entity()
        trigger_entity.add_component(TriggerVolume())

        # Create entity
        player = self.manager.create_entity()

        # Entity enters
        event_enter = OnTriggerEnter(
            trigger_entity=trigger_entity.id, other_entity=player.id, timestamp=0.0
        )
        self.dispatcher.dispatch(event_enter)

        # Entity exits
        event_exit = OnTriggerExit(
            trigger_entity=trigger_entity.id, other_entity=player.id, timestamp=0.0
        )
        self.dispatcher.dispatch(event_exit)

        # Check trigger was updated
        trigger_volume = trigger_entity.get_component(TriggerVolume)
        assert not trigger_volume.contains_entity(player.id)

    def test_trigger_with_tag_filter(self):
        """Trigger with tags should only accept matching entities."""
        # Create trigger that only accepts "player" tag
        trigger_entity = self.manager.create_entity()
        trigger_entity.add_component(TriggerVolume(tags={"player"}))

        # Create player with tag
        player = self.manager.create_entity()
        player.add_component(EntityTags(tags={"player"}))

        # Create enemy without tag
        enemy = self.manager.create_entity()
        enemy.add_component(EntityTags(tags={"enemy"}))

        # Player enters - should be accepted
        event_player = OnTriggerEnter(
            trigger_entity=trigger_entity.id, other_entity=player.id, timestamp=0.0
        )
        self.dispatcher.dispatch(event_player)

        # Enemy enters - should be rejected
        event_enemy = OnTriggerEnter(
            trigger_entity=trigger_entity.id, other_entity=enemy.id, timestamp=0.0
        )
        self.dispatcher.dispatch(event_enemy)

        # Check only player is in trigger
        trigger_volume = trigger_entity.get_component(TriggerVolume)
        assert trigger_volume.contains_entity(player.id)
        assert not trigger_volume.contains_entity(enemy.id)

    def test_one_shot_trigger(self):
        """One-shot trigger should deactivate after first entity enters."""
        # Create one-shot trigger
        trigger_entity = self.manager.create_entity()
        trigger_entity.add_component(TriggerVolume(one_shot=True))

        # Create entities
        player1 = self.manager.create_entity()
        player2 = self.manager.create_entity()

        # First entity enters - should work
        event1 = OnTriggerEnter(
            trigger_entity=trigger_entity.id, other_entity=player1.id, timestamp=0.0
        )
        self.dispatcher.dispatch(event1)

        trigger_volume = trigger_entity.get_component(TriggerVolume)
        assert trigger_volume.contains_entity(player1.id)
        assert trigger_volume.active is False

        # Second entity enters - should be rejected (trigger inactive)
        event2 = OnTriggerEnter(
            trigger_entity=trigger_entity.id, other_entity=player2.id, timestamp=0.0
        )
        self.dispatcher.dispatch(event2)

        assert not trigger_volume.contains_entity(player2.id)

    def test_inactive_trigger(self):
        """Inactive trigger should not accept entities."""
        # Create inactive trigger
        trigger_entity = self.manager.create_entity()
        trigger_entity.add_component(TriggerVolume(active=False))

        # Create entity
        player = self.manager.create_entity()

        # Entity tries to enter
        event = OnTriggerEnter(
            trigger_entity=trigger_entity.id, other_entity=player.id, timestamp=0.0
        )
        self.dispatcher.dispatch(event)

        # Should not be added
        trigger_volume = trigger_entity.get_component(TriggerVolume)
        assert not trigger_volume.contains_entity(player.id)

    def test_update_creates_sensor_collider(self):
        """TriggerSystem.update should create sensor Colliders."""
        # Create trigger without collider
        trigger_entity = self.manager.create_entity()
        trigger_entity.add_component(Transform(position=Vector2(200, 200)))
        trigger_entity.add_component(
            TriggerVolume(shape_type=ShapeType.CIRCLE, dimensions=[50.0])
        )

        # Update system
        self.trigger_system.update(0.0)

        # Check collider was created
        assert trigger_entity.has_component(Collider)
        collider = trigger_entity.get_component(Collider)
        assert collider.is_sensor is True
        assert collider.shape_type == ShapeType.CIRCLE
        assert collider.dimensions == [50.0]

    def test_clear_all_triggers(self):
        """clear_all_triggers should clear all trigger volumes."""
        # Create triggers with entities inside
        trigger1 = self.manager.create_entity()
        trigger1.add_component(TriggerVolume())
        trigger1.get_component(TriggerVolume).entities_inside.add("e1")

        trigger2 = self.manager.create_entity()
        trigger2.add_component(TriggerVolume())
        trigger2.get_component(TriggerVolume).entities_inside.add("e2")

        # Clear all
        self.trigger_system.clear_all_triggers()

        # Check all are empty
        assert trigger1.get_component(TriggerVolume).is_empty()
        assert trigger2.get_component(TriggerVolume).is_empty()

    def test_get_triggers_containing(self):
        """get_triggers_containing should find all triggers with entity."""
        player = self.manager.create_entity()

        # Create multiple triggers
        trigger1 = self.manager.create_entity()
        trigger1.add_component(TriggerVolume())
        trigger1.get_component(TriggerVolume).entities_inside.add(player.id)

        trigger2 = self.manager.create_entity()
        trigger2.add_component(TriggerVolume())
        trigger2.get_component(TriggerVolume).entities_inside.add(player.id)

        trigger3 = self.manager.create_entity()
        trigger3.add_component(TriggerVolume())

        # Find triggers containing player
        triggers = self.trigger_system.get_triggers_containing(player.id)

        assert len(triggers) == 2
        assert trigger1 in triggers
        assert trigger2 in triggers
        assert trigger3 not in triggers


class TestTriggerUsagePatterns:
    """Test practical trigger volume usage patterns."""

    def test_checkpoint_pattern(self):
        """Trigger volume can be used for checkpoints."""
        manager = EntityManager()
        dispatcher = EventDispatcher()
        trigger_system = TriggerSystem(manager, dispatcher)  # noqa: F841

        # Create checkpoint
        checkpoint = manager.create_entity()
        checkpoint.add_component(Transform(position=Vector2(500, 300)))
        checkpoint.add_component(
            TriggerVolume(
                tags={"player"},
                one_shot=True,  # Only for player  # Checkpoint can only be activated once
            )
        )

        # Create player
        player = manager.create_entity()
        player.add_component(EntityTags(tags={"player"}))

        # Player reaches checkpoint
        event = OnTriggerEnter(
            trigger_entity=checkpoint.id, other_entity=player.id, timestamp=0.0
        )
        dispatcher.dispatch(event)

        # Verify checkpoint activated
        trigger_volume = checkpoint.get_component(TriggerVolume)
        assert trigger_volume.contains_entity(player.id)
        assert trigger_volume.active is False  # One-shot deactivated

    def test_damage_zone_pattern(self):
        """Trigger volume can be used for damage zones."""
        manager = EntityManager()
        dispatcher = EventDispatcher()
        trigger_system = TriggerSystem(manager, dispatcher)  # noqa: F841

        # Create damage zone
        lava_zone = manager.create_entity()
        lava_zone.add_component(
            TriggerVolume(
                shape_type=ShapeType.BOX,
                dimensions=[200, 100],
                tags={"player", "enemy"},  # Damages both players and enemies
            )
        )

        # Create player
        player = manager.create_entity()
        player.add_component(EntityTags(tags={"player"}))

        # Player enters damage zone
        event = OnTriggerEnter(
            trigger_entity=lava_zone.id, other_entity=player.id, timestamp=0.0
        )
        dispatcher.dispatch(event)

        # Can check if player is in damage zone each frame
        trigger_volume = lava_zone.get_component(TriggerVolume)
        assert trigger_volume.contains_entity(player.id)

    def test_collectible_pattern(self):
        """Trigger volume can be used for collectibles."""
        manager = EntityManager()
        dispatcher = EventDispatcher()
        trigger_system = TriggerSystem(manager, dispatcher)  # noqa: F841

        # Create coin
        coin = manager.create_entity()
        coin.add_component(
            TriggerVolume(
                shape_type=ShapeType.CIRCLE,
                dimensions=[20],
                tags={"player"},
                one_shot=True,  # Can only be collected once
            )
        )

        # Create player
        player = manager.create_entity()
        player.add_component(EntityTags(tags={"player"}))

        # Player collects coin
        event = OnTriggerEnter(
            trigger_entity=coin.id, other_entity=player.id, timestamp=0.0
        )
        dispatcher.dispatch(event)

        # Verify coin was collected
        trigger_volume = coin.get_component(TriggerVolume)
        assert trigger_volume.has_any_entity()
        assert not trigger_volume.active

    def test_multi_entity_tracking(self):
        """Trigger can track multiple entities simultaneously."""
        manager = EntityManager()
        dispatcher = EventDispatcher()
        trigger_system = TriggerSystem(manager, dispatcher)  # noqa: F841

        # Create zone
        zone = manager.create_entity()
        zone.add_component(TriggerVolume())

        # Create multiple entities
        entities = [manager.create_entity() for _ in range(5)]

        # All enter the zone
        for entity in entities:
            event = OnTriggerEnter(
                trigger_entity=zone.id, other_entity=entity.id, timestamp=0.0
            )
            dispatcher.dispatch(event)

        # Check all are tracked
        trigger_volume = zone.get_component(TriggerVolume)
        assert trigger_volume.get_entity_count() == 5

        # Some leave
        for entity in entities[:2]:
            event = OnTriggerExit(
                trigger_entity=zone.id, other_entity=entity.id, timestamp=0.0
            )
            dispatcher.dispatch(event)

        # Check count updated
        assert trigger_volume.get_entity_count() == 3
