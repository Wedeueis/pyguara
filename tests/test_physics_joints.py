"""Tests for physics joint system."""

from pyguara.common.components import Transform
from pyguara.common.types import Vector2
from pyguara.ecs.manager import EntityManager
from pyguara.physics.backends.pymunk_impl import PymunkEngine
from pyguara.physics.components import Collider, RigidBody
from pyguara.physics.joints import (
    Joint,
    create_distance_joint,
    create_pin_joint,
    create_slider_joint,
    create_spring_joint,
)
from pyguara.physics.types import BodyType, JointType, ShapeType


class TestJointComponent:
    """Test Joint component creation and factory functions."""

    def test_joint_creation(self):
        """Joint component should be created with default values."""
        joint = Joint()

        assert joint.joint_type == JointType.PIN
        assert joint.target_entity_id == ""
        assert joint.anchor_a == Vector2.zero()
        assert joint.anchor_b == Vector2.zero()
        assert joint._joint_handle is None

    def test_create_pin_joint(self):
        """create_pin_joint should create PIN joint with correct parameters."""
        joint = create_pin_joint(
            target_entity_id="target123",
            anchor_a=Vector2(10, 20),
            anchor_b=Vector2(30, 40),
            max_force=1000.0,
            collide_connected=True,
        )

        assert joint.joint_type == JointType.PIN
        assert joint.target_entity_id == "target123"
        assert joint.anchor_a == Vector2(10, 20)
        assert joint.anchor_b == Vector2(30, 40)
        assert joint.max_force == 1000.0
        assert joint.collide_connected is True

    def test_create_distance_joint(self):
        """create_distance_joint should create DISTANCE joint."""
        joint = create_distance_joint(
            target_entity_id="target456", distance=100.0, max_force=500.0
        )

        assert joint.joint_type == JointType.DISTANCE
        assert joint.target_entity_id == "target456"
        assert joint.min_distance == 100.0
        assert joint.max_distance == 100.0
        assert joint.max_force == 500.0

    def test_create_spring_joint(self):
        """create_spring_joint should create SPRING joint with stiffness/damping."""
        joint = create_spring_joint(
            target_entity_id="target789",
            rest_length=50.0,
            stiffness=200.0,
            damping=15.0,
        )

        assert joint.joint_type == JointType.SPRING
        assert joint.target_entity_id == "target789"
        assert joint.min_distance == 50.0
        assert joint.max_distance == 50.0
        assert joint.stiffness == 200.0
        assert joint.damping == 15.0

    def test_create_slider_joint(self):
        """create_slider_joint should create SLIDER joint with distance limits."""
        joint = create_slider_joint(
            target_entity_id="targetABC", min_distance=10.0, max_distance=100.0
        )

        assert joint.joint_type == JointType.SLIDER
        assert joint.target_entity_id == "targetABC"
        assert joint.min_distance == 10.0
        assert joint.max_distance == 100.0

    def test_joint_factory_defaults(self):
        """Joint factory functions should use default anchors."""
        joint = create_pin_joint(target_entity_id="test")

        assert joint.anchor_a == Vector2.zero()
        assert joint.anchor_b == Vector2.zero()


class TestPymunkJointCreation:
    """Test joint creation in pymunk backend."""

    def setup_method(self):
        """Set up physics engine and entities for testing."""
        self.engine = PymunkEngine()
        self.engine.initialize(Vector2(0, 0))  # No gravity for simpler tests

        self.manager = EntityManager()

        # Create two entities with physics bodies
        self.entity_a = self.manager.create_entity()
        self.entity_a.add_component(Transform(position=Vector2(100, 100)))
        self.entity_a.add_component(RigidBody(mass=1.0, body_type=BodyType.DYNAMIC))
        self.entity_a.add_component(
            Collider(shape_type=ShapeType.CIRCLE, dimensions=[10])
        )

        self.entity_b = self.manager.create_entity()
        self.entity_b.add_component(Transform(position=Vector2(200, 100)))
        self.entity_b.add_component(RigidBody(mass=1.0, body_type=BodyType.DYNAMIC))
        self.entity_b.add_component(
            Collider(shape_type=ShapeType.CIRCLE, dimensions=[10])
        )

        # Create physics bodies
        self.body_a = self.engine.create_body(
            self.entity_a.id, BodyType.DYNAMIC, Vector2(100, 100)
        )
        self.body_b = self.engine.create_body(
            self.entity_b.id, BodyType.DYNAMIC, Vector2(200, 100)
        )

    def test_create_pin_joint_pymunk(self):
        """Pymunk backend should create pin joints."""
        joint_handle = self.engine.create_joint(
            body_a=self.body_a,
            body_b=self.body_b,
            joint_type=JointType.PIN,
            anchor_a=Vector2.zero(),
            anchor_b=Vector2.zero(),
            min_distance=0.0,
            max_distance=0.0,
            stiffness=0.0,
            damping=0.0,
            max_force=0.0,
            collide_connected=False,
        )

        assert joint_handle is not None

    def test_create_distance_joint_pymunk(self):
        """Pymunk backend should create distance joints."""
        joint_handle = self.engine.create_joint(
            body_a=self.body_a,
            body_b=self.body_b,
            joint_type=JointType.DISTANCE,
            anchor_a=Vector2.zero(),
            anchor_b=Vector2.zero(),
            min_distance=100.0,
            max_distance=100.0,
            stiffness=0.0,
            damping=0.0,
            max_force=0.0,
            collide_connected=False,
        )

        assert joint_handle is not None

    def test_create_spring_joint_pymunk(self):
        """Pymunk backend should create spring joints."""
        joint_handle = self.engine.create_joint(
            body_a=self.body_a,
            body_b=self.body_b,
            joint_type=JointType.SPRING,
            anchor_a=Vector2.zero(),
            anchor_b=Vector2.zero(),
            min_distance=100.0,
            max_distance=100.0,
            stiffness=200.0,
            damping=10.0,
            max_force=0.0,
            collide_connected=False,
        )

        assert joint_handle is not None

    def test_create_slider_joint_pymunk(self):
        """Pymunk backend should create slider joints."""
        joint_handle = self.engine.create_joint(
            body_a=self.body_a,
            body_b=self.body_b,
            joint_type=JointType.SLIDER,
            anchor_a=Vector2.zero(),
            anchor_b=Vector2.zero(),
            min_distance=50.0,
            max_distance=150.0,
            stiffness=0.0,
            damping=0.0,
            max_force=0.0,
            collide_connected=False,
        )

        assert joint_handle is not None

    def test_create_gear_joint_pymunk(self):
        """Pymunk backend should create gear joints."""
        joint_handle = self.engine.create_joint(
            body_a=self.body_a,
            body_b=self.body_b,
            joint_type=JointType.GEAR,
            anchor_a=Vector2.zero(),
            anchor_b=Vector2.zero(),
            min_distance=0.0,
            max_distance=0.0,
            stiffness=0.0,
            damping=0.0,
            max_force=0.0,
            collide_connected=False,
        )

        assert joint_handle is not None

    def test_create_motor_joint_pymunk(self):
        """Pymunk backend should create motor joints."""
        joint_handle = self.engine.create_joint(
            body_a=self.body_a,
            body_b=self.body_b,
            joint_type=JointType.MOTOR,
            anchor_a=Vector2.zero(),
            anchor_b=Vector2.zero(),
            min_distance=0.0,
            max_distance=0.0,
            stiffness=0.0,
            damping=0.0,
            max_force=0.0,
            collide_connected=False,
        )

        assert joint_handle is not None

    def test_joint_with_max_force(self):
        """Joints should support max force limits."""
        joint_handle = self.engine.create_joint(
            body_a=self.body_a,
            body_b=self.body_b,
            joint_type=JointType.PIN,
            anchor_a=Vector2.zero(),
            anchor_b=Vector2.zero(),
            min_distance=0.0,
            max_distance=0.0,
            stiffness=0.0,
            damping=0.0,
            max_force=1000.0,
            collide_connected=False,
        )

        assert joint_handle is not None
        assert joint_handle.max_force == 1000.0

    def test_joint_collide_connected(self):
        """Joints should support collide_connected flag."""
        joint_handle = self.engine.create_joint(
            body_a=self.body_a,
            body_b=self.body_b,
            joint_type=JointType.PIN,
            anchor_a=Vector2.zero(),
            anchor_b=Vector2.zero(),
            min_distance=0.0,
            max_distance=0.0,
            stiffness=0.0,
            damping=0.0,
            max_force=0.0,
            collide_connected=True,
        )

        assert joint_handle is not None
        # Pymunk uses 1/0 instead of True/False
        assert joint_handle.collide_bodies == 1

    def test_destroy_joint(self):
        """Engine should destroy joints."""
        joint_handle = self.engine.create_joint(
            body_a=self.body_a,
            body_b=self.body_b,
            joint_type=JointType.PIN,
            anchor_a=Vector2.zero(),
            anchor_b=Vector2.zero(),
            min_distance=0.0,
            max_distance=0.0,
            stiffness=0.0,
            damping=0.0,
            max_force=0.0,
            collide_connected=False,
        )

        # Should not raise
        self.engine.destroy_joint(joint_handle)

    def test_destroy_none_joint(self):
        """destroy_joint should handle None gracefully."""
        # Should not raise
        self.engine.destroy_joint(None)


class TestJointTypes:
    """Test specific joint type behaviors."""

    def test_all_joint_types_in_enum(self):
        """JointType enum should have all expected types."""
        expected_types = {
            JointType.PIN,
            JointType.DISTANCE,
            JointType.SPRING,
            JointType.SLIDER,
            JointType.GEAR,
            JointType.MOTOR,
        }

        actual_types = set(JointType)

        assert actual_types == expected_types

    def test_joint_type_enum_values(self):
        """JointType enum values should be distinct."""
        types = list(JointType)
        assert len(types) == len(set(types))


class TestJointUsagePatterns:
    """Test practical joint usage patterns."""

    def test_rope_segment_pattern(self):
        """Joint components can form rope-like structures."""
        manager = EntityManager()

        # Create rope segments
        segments = []
        for i in range(3):
            segment = manager.create_entity()
            segment.add_component(Transform(position=Vector2(100, 100 + i * 20)))
            segment.add_component(RigidBody(mass=0.5, body_type=BodyType.DYNAMIC))
            segment.add_component(Collider(shape_type=ShapeType.CIRCLE, dimensions=[5]))
            segments.append(segment)

        # Connect segments with distance joints
        for i in range(len(segments) - 1):
            joint = create_distance_joint(
                target_entity_id=segments[i + 1].id, distance=20.0
            )
            segments[i].add_component(joint)

        # Verify all segments have joints except the last
        assert segments[0].has_component(Joint)
        assert segments[1].has_component(Joint)
        assert not segments[2].has_component(Joint)

    def test_hinge_pattern(self):
        """Pin joints can create hinges."""
        manager = EntityManager()

        door = manager.create_entity()
        door.add_component(Transform(position=Vector2(200, 200)))
        door.add_component(RigidBody(mass=5.0, body_type=BodyType.DYNAMIC))

        wall = manager.create_entity()
        wall.add_component(Transform(position=Vector2(150, 200)))
        wall.add_component(RigidBody(body_type=BodyType.STATIC))

        # Create hinge joint
        hinge = create_pin_joint(
            target_entity_id=wall.id,
            anchor_a=Vector2(-25, 0),  # Left edge of door
            anchor_b=Vector2(0, 0),  # Wall attachment
        )
        door.add_component(hinge)

        assert door.has_component(Joint)
        joint = door.get_component(Joint)
        assert joint.joint_type == JointType.PIN

    def test_spring_suspension_pattern(self):
        """Spring joints can create suspension systems."""
        manager = EntityManager()

        chassis = manager.create_entity()
        chassis.add_component(Transform(position=Vector2(300, 200)))
        chassis.add_component(RigidBody(mass=10.0, body_type=BodyType.DYNAMIC))

        wheel = manager.create_entity()
        wheel.add_component(Transform(position=Vector2(300, 250)))
        wheel.add_component(RigidBody(mass=1.0, body_type=BodyType.DYNAMIC))

        # Create spring suspension
        suspension = create_spring_joint(
            target_entity_id=chassis.id,
            rest_length=50.0,
            stiffness=300.0,
            damping=25.0,
        )
        wheel.add_component(suspension)

        assert wheel.has_component(Joint)
        joint = wheel.get_component(Joint)
        assert joint.joint_type == JointType.SPRING
        assert joint.stiffness == 300.0
        assert joint.damping == 25.0
