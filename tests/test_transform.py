"""Behavioural tests for the Transform component.

Transform carries the most intricate logic in `pyguara/common` -- a parent
hierarchy, lazily rebuilt world caches, and local/world coordinate conversion
-- and had no dedicated tests before this file. It appeared in ten other test
modules only as an incidental fixture, so the hierarchy math itself was
exercised almost entirely by accident.
"""

import math

import pytest

from pyguara.common.components import ResourceLink, Tag, Transform
from pyguara.common.types import Vector2


def assert_vec(actual: Vector2, expected: tuple[float, float], tol: float = 1e-9):
    assert abs(actual.x - expected[0]) < tol, f"{actual} != {expected}"
    assert abs(actual.y - expected[1]) < tol, f"{actual} != {expected}"


class TestTransformDefaults:
    def test_defaults_to_origin_no_rotation_unit_scale(self) -> None:
        t = Transform()
        assert t.position == Vector2(0, 0)
        assert t.rotation == 0.0
        assert t.scale == Vector2(1, 1)
        assert t.parent is None

    def test_rotation_degrees_mirrors_rotation(self) -> None:
        t = Transform()
        t.rotation_degrees = 180
        assert abs(t.rotation - math.pi) < 1e-9
        t.rotation = math.pi / 2
        assert abs(t.rotation_degrees - 90) < 1e-9

    def test_rotate_takes_radians(self) -> None:
        """Transform.rotate() is radians while the old Vector2.rotate() was
        degrees; the unit is asserted here so the two cannot silently swap."""
        t = Transform()
        t.rotate(math.pi)
        assert abs(t.rotation_degrees - 180) < 1e-9


class TestTransformDirections:
    def test_up_is_negative_y_matching_vector2(self) -> None:
        """Transform.up returned (0, 1) -- pointing *down* on screen, and the
        exact opposite of Vector2.up(). Gravity defaults positive, so the
        engine is unambiguously Y-down."""
        assert_vec(Transform().up, (0, -1))
        assert Transform().up == Vector2.up()

    def test_all_four_directions_at_rest(self) -> None:
        t = Transform()
        assert_vec(t.right, (1, 0))
        assert_vec(t.left, (-1, 0))
        assert_vec(t.up, (0, -1))
        assert_vec(t.down, (0, 1))

    def test_directions_follow_world_rotation(self) -> None:
        t = Transform(rotation=math.pi / 2)
        assert_vec(t.right, (0, 1))
        assert_vec(t.up, (1, 0))

    def test_forward_is_right_and_look_at_agrees(self) -> None:
        t = Transform(position=Vector2(0, 0))
        t.look_at(Vector2(10, 0))
        assert_vec(t.forward, (1, 0))
        t.look_at(Vector2(0, 10))
        assert_vec(t.forward, (0, 1))


class TestTransformHierarchy:
    def test_child_world_position_includes_parent_offset(self) -> None:
        parent = Transform(position=Vector2(100, 50))
        child = Transform(position=Vector2(10, 5))
        child.set_parent(parent, keep_world_transform=False)
        assert_vec(child.world_position, (110, 55))

    def test_child_inherits_parent_rotation_and_scale(self) -> None:
        parent = Transform(rotation=math.pi / 2, scale=Vector2(2, 2))
        child = Transform(position=Vector2(1, 0))
        child.set_parent(parent, keep_world_transform=False)

        assert_vec(child.world_position, (0, 2))
        assert abs(child.world_rotation - math.pi / 2) < 1e-9
        assert_vec(child.world_scale, (2, 2))

    def test_keep_world_transform_preserves_world_position(self) -> None:
        parent = Transform(position=Vector2(100, 100))
        child = Transform(position=Vector2(10, 10))

        child.set_parent(parent, keep_world_transform=True)

        assert_vec(child.world_position, (10, 10))
        assert_vec(child.position, (-90, -90))

    def test_detaching_preserves_world_position(self) -> None:
        parent = Transform(position=Vector2(100, 100))
        child = Transform(position=Vector2(10, 10))
        child.set_parent(parent, keep_world_transform=False)
        assert_vec(child.world_position, (110, 110))

        child.set_parent(None, keep_world_transform=True)

        assert child.parent is None
        assert_vec(child.world_position, (110, 110))

    def test_reparenting_removes_the_child_from_the_old_parent(self) -> None:
        a, b = Transform(), Transform()
        child = Transform()
        child.set_parent(a)
        child.set_parent(b)

        assert a.children == []
        assert b.children == [child]

    def test_children_returns_a_snapshot_not_the_live_list(self) -> None:
        parent = Transform()
        Transform().set_parent(parent)
        snapshot = parent.children
        snapshot.clear()
        assert len(parent.children) == 1

    def test_setting_parent_to_the_current_parent_is_a_noop(self) -> None:
        parent, child = Transform(), Transform()
        child.set_parent(parent)
        child.set_parent(parent)
        assert parent.children == [child]

    def test_three_level_chain_composes(self) -> None:
        a = Transform(position=Vector2(100, 0))
        b = Transform(position=Vector2(10, 0))
        c = Transform(position=Vector2(1, 0))
        b.set_parent(a, keep_world_transform=False)
        c.set_parent(b, keep_world_transform=False)
        assert_vec(c.world_position, (111, 0))


class TestTransformCycles:
    """set_parent() had no cycle guard: any loop turned every later world_*
    read into unbounded recursion."""

    def test_self_parenting_is_rejected(self) -> None:
        t = Transform()
        with pytest.raises(ValueError, match="itself or to one of its own"):
            t.set_parent(t)
        assert t.parent is None
        assert t.children == []

    def test_direct_cycle_is_rejected(self) -> None:
        a, b = Transform(), Transform()
        a.set_parent(b)
        with pytest.raises(ValueError, match="descendants"):
            b.set_parent(a)

    def test_indirect_cycle_is_rejected(self) -> None:
        a, b, c = Transform(), Transform(), Transform()
        b.set_parent(a)
        c.set_parent(b)
        with pytest.raises(ValueError, match="descendants"):
            a.set_parent(c)

    def test_the_hierarchy_survives_a_rejected_cycle(self) -> None:
        a, b = Transform(), Transform()
        a.set_parent(b)
        with pytest.raises(ValueError):
            b.set_parent(a)

        assert a.parent is b
        assert b.parent is None
        assert b.children == [a]
        assert a.world_position == Vector2(0, 0)

    def test_is_ancestor_of(self) -> None:
        a, b, unrelated = Transform(), Transform(), Transform()
        b.set_parent(a)
        assert a.is_ancestor_of(b)
        assert a.is_ancestor_of(a)
        assert not b.is_ancestor_of(a)
        assert not a.is_ancestor_of(unrelated)


class TestTransformDirtyCaching:
    def test_moving_a_parent_updates_child_world_position(self) -> None:
        parent = Transform(position=Vector2(0, 0))
        child = Transform(position=Vector2(10, 0))
        child.set_parent(parent, keep_world_transform=False)
        assert_vec(child.world_position, (10, 0))

        parent.position = Vector2(100, 0)

        assert_vec(child.world_position, (110, 0))

    def test_moving_a_parent_updates_a_grandchild(self) -> None:
        a, b, c = Transform(), Transform(), Transform()
        b.set_parent(a, keep_world_transform=False)
        c.set_parent(b, keep_world_transform=False)
        c.position = Vector2(1, 0)
        assert_vec(c.world_position, (1, 0))

        a.position = Vector2(50, 0)

        assert_vec(c.world_position, (51, 0))

    def test_repeated_parent_moves_all_propagate(self) -> None:
        """A dirty node stops _mark_dirty() recursing. That is only sound
        because cleaning a node also cleans its ancestors, so a dirty node can
        never have a clean descendant -- this walks that interleaving."""
        parent, child = Transform(), Transform()
        child.set_parent(parent, keep_world_transform=False)

        for step in range(1, 4):
            parent.position = Vector2(step * 10, 0)
            assert_vec(child.world_position, (step * 10, 0))
            parent.position = Vector2(step * 10 + 1, 0)
            assert_vec(parent.world_position, (step * 10 + 1, 0))
            assert_vec(child.world_position, (step * 10 + 1, 0))

    def test_rotating_a_parent_updates_child_world_rotation(self) -> None:
        parent, child = Transform(), Transform()
        child.set_parent(parent, keep_world_transform=False)
        assert child.world_rotation == 0.0

        parent.rotation = math.pi

        assert abs(child.world_rotation - math.pi) < 1e-9


class TestTransformCoordinateConversion:
    def test_local_to_world_round_trips(self) -> None:
        t = Transform(position=Vector2(10, 20), rotation=0.7, scale=Vector2(2, 3))
        point = Vector2(5, -4)
        assert_vec(t.world_to_local(t.local_to_world(point)), (5, -4), tol=1e-6)

    def test_local_to_world_applies_scale_rotation_then_translation(self) -> None:
        t = Transform(
            position=Vector2(10, 0), rotation=math.pi / 2, scale=Vector2(2, 2)
        )
        assert_vec(t.local_to_world(Vector2(1, 0)), (10, 2))

    def test_world_to_local_of_a_zero_scaled_transform_returns_origin(self) -> None:
        """A zero scale is not invertible; the origin is returned rather than
        raising ZeroDivisionError mid-frame."""
        t = Transform(scale=Vector2(0, 0))
        assert t.world_to_local(Vector2(5, 5)) == Vector2(0, 0)

    def test_world_position_setter_accounts_for_the_parent(self) -> None:
        parent = Transform(position=Vector2(100, 100))
        child = Transform()
        child.set_parent(parent, keep_world_transform=False)

        child.world_position = Vector2(150, 150)

        assert_vec(child.position, (50, 50))
        assert_vec(child.world_position, (150, 150))

    def test_world_rotation_setter_accounts_for_the_parent(self) -> None:
        parent = Transform(rotation=math.pi / 2)
        child = Transform()
        child.set_parent(parent, keep_world_transform=False)

        child.world_rotation = math.pi

        assert abs(child.rotation - math.pi / 2) < 1e-9
        assert abs(child.world_rotation - math.pi) < 1e-9

    def test_distance_to_uses_world_space(self) -> None:
        parent = Transform(position=Vector2(100, 0))
        child = Transform()
        child.set_parent(parent, keep_world_transform=False)
        other = Transform(position=Vector2(103, 4))
        assert child.distance_to(other) == 5.0


class TestSharedComponents:
    def test_tag_and_resource_link_have_no_instance_dict(self) -> None:
        """slots=True keeps these off a per-instance __dict__, as the ECS docs
        require of dataclass components."""
        assert not hasattr(Tag("player"), "__dict__")
        assert not hasattr(ResourceLink("a/b.json"), "__dict__")

    def test_slotted_components_still_initialise_base_state(self) -> None:
        """dataclass(slots=True) rebuilds the class, which breaks a zero-arg
        super() in __post_init__; entity must still be initialised."""
        assert Tag("player").entity is None
        assert ResourceLink("a/b.json").entity is None

    def test_tag_defaults_and_equality(self) -> None:
        assert Tag().name == "Entity"
        assert Tag("a") == Tag("a")
        assert Tag("a") != Tag("b")


class TestTransformFalsyDefaults:
    """`position or default` is wrong for Vector2: pymunk's Vec2d is falsy at
    (0, 0), so an explicitly requested zero was silently replaced."""

    def test_explicit_zero_scale_is_honoured(self) -> None:
        assert Transform(scale=Vector2(0, 0)).scale == Vector2(0, 0)

    def test_explicit_zero_position_is_honoured(self) -> None:
        assert Transform(position=Vector2(0, 0)).position == Vector2(0, 0)

    def test_omitted_arguments_still_default(self) -> None:
        t = Transform()
        assert t.position == Vector2(0, 0)
        assert t.scale == Vector2(1, 1)
