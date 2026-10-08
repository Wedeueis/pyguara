"""Tweening entity properties: paths, the component, and the engine system."""

import pytest

from pyguara.animation.easing import EasingType
from pyguara.animation.interpolation import decompose, interpolate, recompose
from pyguara.animation.timeline import Timeline
from pyguara.animation.tweener import (
    PropertyPathError,
    Tweener,
    TweenSystem,
    bind_tween,
    resolve_property,
    stop_property,
    stop_tweens,
    tween_property,
)
from pyguara.common.components import Transform
from pyguara.common.types import Color, Vector2
from pyguara.ecs.manager import EntityManager
from pyguara.graphics.components.sprite import Sprite
from pyguara.resources.types import Texture


class FakeTexture(Texture):
    """A texture that never touches a backend."""

    def __init__(self) -> None:
        super().__init__("fake")

    @property
    def width(self) -> int:
        return 1

    @property
    def height(self) -> int:
        return 1

    @property
    def native_handle(self) -> None:
        return None


@pytest.fixture
def world():
    manager = EntityManager()
    entity = manager.create_entity()
    entity.add_component(Transform(position=Vector2(0, 0)))
    return manager, entity


# -- Property paths --


def test_a_path_resolves_to_the_current_value_and_a_writer(world):
    _manager, entity = world

    target = resolve_property(entity, "transform.position")

    assert target.current == Vector2(0, 0)
    target.apply(Vector2(10, 20))
    assert entity.get_component(Transform).position == Vector2(10, 20)


def test_a_deeper_path_walks_through_intermediate_attributes(world):
    """`sprite.color.a` and friends: the walk is general, not two levels."""
    _manager, entity = world
    entity.add_component(Sprite(texture=FakeTexture(), color=Color(10, 20, 30)))

    target = resolve_property(entity, "sprite.color")

    assert target.current == Color(10, 20, 30)


def test_a_path_with_no_attribute_part_is_refused(world):
    _manager, entity = world

    with pytest.raises(PropertyPathError, match="at least a component"):
        resolve_property(entity, "transform")


def test_a_path_naming_a_missing_component_is_refused(world):
    """Raised rather than logged: a tween that quietly does nothing is
    worse to debug than one that refuses to start."""
    _manager, entity = world

    with pytest.raises(PropertyPathError, match="no component 'rigid_body'"):
        resolve_property(entity, "rigid_body.velocity")


def test_a_path_naming_a_missing_attribute_is_refused(world):
    _manager, entity = world

    with pytest.raises(PropertyPathError, match="has no 'postition'"):
        resolve_property(entity, "transform.postition")


# -- tween_property --


def test_tweening_a_position_writes_it_every_tick(world):
    manager, entity = world
    system = TweenSystem(manager)

    tween_property(entity, "transform.position", to=Vector2(100, 0), duration=1.0)
    system.update(0.5)

    assert entity.get_component(Transform).position.x == pytest.approx(50.0)
    assert isinstance(entity.get_component(Transform).position, Vector2)


def test_the_start_point_is_read_from_the_property_itself(world):
    """Which is what makes a knockback retargeted mid-flight continuous
    rather than snapping back."""
    manager, entity = world
    system = TweenSystem(manager)

    tween_property(entity, "transform.position", to=Vector2(100, 0), duration=1.0)
    system.update(0.5)

    tween_property(entity, "transform.position", to=Vector2(0, 0), duration=1.0)
    system.update(0.0)

    assert entity.get_component(Transform).position.x == pytest.approx(50.0)


def test_the_tween_lands_exactly_on_its_destination(world):
    """A binding dropped before its last write would leave the entity one
    frame short of where it was sent."""
    manager, entity = world
    system = TweenSystem(manager)

    tween_property(entity, "transform.position", to=Vector2(100, 50), duration=1.0)
    system.update(2.0)

    assert entity.get_component(Transform).position == Vector2(100, 50)


def test_a_finished_binding_is_dropped(world):
    manager, entity = world
    system = TweenSystem(manager)
    tween_property(entity, "transform.position", to=Vector2(1, 0), duration=0.1)

    system.update(0.2)

    assert entity.get_component(Tweener).bindings == []


def test_tweening_adds_the_component_automatically(world):
    _manager, entity = world
    assert not entity.has_component(Tweener)

    tween_property(entity, "transform.rotation", to=1.0, duration=1.0)

    assert entity.has_component(Tweener)


def test_a_second_tween_on_the_same_path_replaces_the_first(world):
    """Two tweens writing one property every frame is never what anyone
    wanted: the last writer wins and the result depends on binding order."""
    _manager, entity = world

    tween_property(entity, "transform.rotation", to=1.0, duration=1.0)
    tween_property(entity, "transform.rotation", to=2.0, duration=1.0)

    assert len(entity.get_component(Tweener).bindings) == 1


def test_replace_can_be_turned_off(world):
    _manager, entity = world

    tween_property(entity, "transform.rotation", to=1.0, duration=1.0)
    tween_property(entity, "transform.rotation", to=2.0, duration=1.0, replace=False)

    assert len(entity.get_component(Tweener).bindings) == 2


def test_tweens_on_different_paths_coexist(world):
    manager, entity = world
    system = TweenSystem(manager)

    tween_property(entity, "transform.position", to=Vector2(100, 0), duration=1.0)
    tween_property(entity, "transform.rotation", to=2.0, duration=1.0)
    system.update(0.5)

    transform = entity.get_component(Transform)
    assert transform.position.x == pytest.approx(50.0)
    assert transform.rotation == pytest.approx(1.0)


def test_easing_and_delay_reach_the_tween(world):
    manager, entity = world
    system = TweenSystem(manager)

    tween_property(
        entity,
        "transform.rotation",
        to=100.0,
        duration=1.0,
        easing=EasingType.EASE_IN_QUAD,
        delay=0.5,
    )

    system.update(0.4)
    assert entity.get_component(Transform).rotation == pytest.approx(0.0)

    # 0.5 s into a 1 s tween is halfway; EASE_IN_QUAD squares that, so
    # a quarter of the way to 100.
    system.update(0.6)
    assert entity.get_component(Transform).rotation == pytest.approx(25.0)


def test_on_complete_fires_once(world):
    manager, entity = world
    system = TweenSystem(manager)
    calls: list[int] = []

    tween_property(
        entity,
        "transform.rotation",
        to=1.0,
        duration=0.1,
        on_complete=lambda: calls.append(1),
    )
    for _ in range(5):
        system.update(0.1)

    assert calls == [1]


def test_a_colour_property_tweens_channelwise(world):
    """#37's P2 row, through the ECS path."""
    manager, entity = world
    entity.add_component(Sprite(texture=FakeTexture(), color=Color(0, 0, 0, 255)))
    system = TweenSystem(manager)

    tween_property(entity, "sprite.color", to=Color(255, 255, 255, 0), duration=1.0)
    system.update(0.5)

    colour = entity.get_component(Sprite).color
    assert isinstance(colour, Color)
    assert colour == Color(128, 128, 128, 128)


# -- Stopping --


def test_stop_property_leaves_the_value_where_it_got_to(world):
    manager, entity = world
    system = TweenSystem(manager)
    tween_property(entity, "transform.position", to=Vector2(100, 0), duration=1.0)
    system.update(0.5)

    assert stop_property(entity, "transform.position") == 1
    system.update(0.5)

    assert entity.get_component(Transform).position.x == pytest.approx(50.0)


def test_stop_tweens_clears_every_binding(world):
    _manager, entity = world
    tween_property(entity, "transform.position", to=Vector2(1, 0), duration=1.0)
    tween_property(entity, "transform.rotation", to=1.0, duration=1.0)

    assert stop_tweens(entity) == 2
    assert entity.get_component(Tweener).bindings == []


def test_stopping_an_entity_with_no_tweener_is_not_an_error(world):
    _manager, entity = world

    assert stop_tweens(entity) == 0
    assert stop_property(entity, "transform.position") == 0


# -- bind_tween --


def test_a_timeline_can_be_bound_to_drive_callbacks(world):
    manager, entity = world
    system = TweenSystem(manager)
    calls: list[int] = []
    timeline = Timeline().wait(0.1).call(lambda: calls.append(1)).start()

    bind_tween(entity, "transform.rotation", timeline)
    system.update(0.2)

    assert calls == [1]
    assert entity.get_component(Transform).rotation == 0.0


def test_a_binding_whose_write_raises_is_dropped_not_logged_forever(world, caplog):
    """A 60 Hz log firehose is a worse outcome than a dropped effect."""
    import logging

    manager, entity = world
    system = TweenSystem(manager)
    binding = bind_tween(
        entity,
        "transform.rotation",
        Timeline().wait(10.0).start(),
    )

    def explode(_value):
        raise RuntimeError("bad destination")

    binding.apply = explode
    binding.animatable = __import__(
        "pyguara.animation.tween", fromlist=["Tween"]
    ).Tween(start_value=0.0, end_value=1.0, duration=10.0)
    binding.animatable.start()

    with caplog.at_level(logging.ERROR):
        system.update(0.1)
        system.update(0.1)

    assert entity.get_component(Tweener).bindings == []
    assert caplog.text.count("could not") == 1


# -- Interpolation helpers --


def test_decompose_and_recompose_round_trip_a_colour():
    raw = decompose(Color(1, 2, 3, 4))

    assert raw == (1.0, 2.0, 3.0, 4.0)
    assert recompose(Color(0, 0, 0), raw) == Color(1, 2, 3, 4)


def test_decompose_refuses_what_it_cannot_take_apart():
    with pytest.raises(TypeError, match="Cannot interpolate a dict"):
        decompose({"r": 1})


def test_interpolating_mismatched_shapes_is_refused():
    with pytest.raises(ValueError, match="one is a number"):
        interpolate(1.0, Vector2(1, 1), 0.5)

    with pytest.raises(ValueError, match="different length"):
        interpolate((0.0, 0.0), (1.0, 1.0, 1.0), 0.5)


def test_interpolation_is_not_clamped_so_elastic_easings_still_overshoot():
    """Clamping here would flatten exactly the part of the curve that makes
    those easings worth having."""
    assert interpolate(0.0, 100.0, 1.2) == pytest.approx(120.0)
