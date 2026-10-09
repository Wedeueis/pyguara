"""Directional animation: facing from a vector, clip sets, and the system."""

import pytest

from pyguara.common.components import Transform
from pyguara.common.types import Vector2
from pyguara.ecs.manager import EntityManager
from pyguara.graphics.components.animation import (
    AnimationClip,
    Animator,
    add_clip,
)
from pyguara.graphics.components.sprite import Sprite
from pyguara.kits.topdown_movement import (
    DirectionalAnimationSystem,
    DirectionalAnimator,
    DirectionalClipSet,
    Facing,
    TopDownBody,
    facing_from_vector,
)
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


# -- facing_from_vector --


def test_screen_y_grows_downward_so_negative_y_is_up():
    """The detail that makes a hand-written version face backwards for a
    week before anyone notices."""
    assert facing_from_vector(Vector2(0, -1)) is Facing.UP
    assert facing_from_vector(Vector2(0, 1)) is Facing.DOWN


def test_the_four_cardinals_resolve():
    assert facing_from_vector(Vector2(1, 0)) is Facing.RIGHT
    assert facing_from_vector(Vector2(-1, 0)) is Facing.LEFT
    assert facing_from_vector(Vector2(0, 1)) is Facing.DOWN
    assert facing_from_vector(Vector2(0, -1)) is Facing.UP


def test_the_four_diagonals_resolve():
    assert facing_from_vector(Vector2(1, 1)) is Facing.DOWN_RIGHT
    assert facing_from_vector(Vector2(-1, 1)) is Facing.DOWN_LEFT
    assert facing_from_vector(Vector2(1, -1)) is Facing.UP_RIGHT
    assert facing_from_vector(Vector2(-1, -1)) is Facing.UP_LEFT


def test_length_is_ignored():
    assert facing_from_vector(Vector2(0.01, 0)) is Facing.RIGHT
    assert facing_from_vector(Vector2(9999, 0)) is Facing.RIGHT


def test_four_way_snaps_a_diagonal_to_a_cardinal():
    assert facing_from_vector(Vector2(1, 1), ways=4) in (
        Facing.RIGHT,
        Facing.DOWN,
    )
    assert facing_from_vector(Vector2(3, 1), ways=4) is Facing.RIGHT
    assert facing_from_vector(Vector2(1, 3), ways=4) is Facing.DOWN


def test_a_zero_vector_gives_none_not_a_default():
    """A stopped character must keep facing where it last faced; snapping
    to DOWN on every halt is the other classic bug."""
    assert facing_from_vector(Vector2(0, 0)) is None


def test_an_unsupported_direction_count_is_refused():
    with pytest.raises(ValueError, match="must be 4 or 8"):
        facing_from_vector(Vector2(1, 0), ways=6)


def test_sector_boundaries_land_on_the_nearer_facing():
    """22.5 degrees is the seam between RIGHT and DOWN_RIGHT."""
    import math

    just_under = math.radians(22.0)
    just_over = math.radians(23.0)

    assert (
        facing_from_vector(Vector2(math.cos(just_under), math.sin(just_under)))
        is Facing.RIGHT
    )
    assert (
        facing_from_vector(Vector2(math.cos(just_over), math.sin(just_over)))
        is Facing.DOWN_RIGHT
    )


# -- DirectionalClipSet --


def test_a_name_follows_the_usual_convention():
    clips = DirectionalClipSet(actions=("walk",))

    assert clips.clip_name("walk", Facing.DOWN) == "walk_down"
    assert clips.clip_name("walk", Facing.UP_LEFT) == "walk_up_left"


def test_a_four_way_set_maps_a_diagonal_onto_left_or_right():
    """A profile view reads as a three-quarter view far better than a back
    view does."""
    clips = DirectionalClipSet(actions=("walk",), ways=4)

    assert clips.clip_name("walk", Facing.UP_LEFT) == "walk_left"
    assert clips.clip_name("walk", Facing.DOWN_RIGHT) == "walk_right"
    assert clips.clip_name("walk", Facing.UP) == "walk_up"


def test_an_override_wins_over_the_convention():
    clips = DirectionalClipSet(
        actions=("idle",),
        overrides={("idle", Facing.UP): "idle_back"},
    )

    assert clips.clip_name("idle", Facing.UP) == "idle_back"
    assert clips.clip_name("idle", Facing.DOWN) == "idle_down"


def test_the_separator_is_configurable():
    clips = DirectionalClipSet(actions=("walk",), separator="-")

    assert clips.clip_name("walk", Facing.DOWN) == "walk-down"


def test_every_clip_name_lists_what_to_register():
    clips = DirectionalClipSet(actions=("idle", "walk"), ways=4)

    names = clips.every_clip_name()

    assert len(names) == 8
    assert "idle_down" in names
    assert "walk_right" in names


def test_every_clip_name_deduplicates_collapsed_overrides():
    """Registering a clip twice is a waste rather than an error, but the
    list is what a loop iterates."""
    clips = DirectionalClipSet(
        actions=("idle",),
        ways=4,
        overrides={
            ("idle", facing): "idle_any"
            for facing in (Facing.UP, Facing.DOWN, Facing.LEFT, Facing.RIGHT)
        },
    )

    assert clips.every_clip_name() == ["idle_any"]


def test_an_unsupported_way_count_is_refused_at_construction():
    with pytest.raises(ValueError, match="must be 4 or 8"):
        DirectionalClipSet(actions=("walk",), ways=6)


# -- DirectionalAnimationSystem --


def _entity_with_animator(manager: EntityManager, clips: DirectionalClipSet):
    entity = manager.create_entity()
    entity.add_component(Transform(position=Vector2(0, 0)))
    sprite = Sprite(texture=FakeTexture())
    entity.add_component(sprite)
    animator = Animator(sprite)
    for name in clips.every_clip_name():
        add_clip(animator, AnimationClip(name=name, frames=[FakeTexture()]))
    entity.add_component(animator)
    entity.add_component(DirectionalAnimator(clips, action="walk"))
    return entity, animator


def test_the_system_plays_the_clip_for_the_bodys_direction():
    manager = EntityManager()
    clips = DirectionalClipSet(actions=("walk",))
    entity, animator = _entity_with_animator(manager, clips)
    entity.add_component(TopDownBody(velocity=Vector2(0, -50)))

    DirectionalAnimationSystem(manager).update(1 / 60)

    assert animator.current_clip_name == "walk_up"


def test_a_stopped_character_keeps_facing_where_it_last_faced():
    manager = EntityManager()
    clips = DirectionalClipSet(actions=("walk",))
    entity, animator = _entity_with_animator(manager, clips)
    body = TopDownBody(velocity=Vector2(-50, 0))
    entity.add_component(body)
    system = DirectionalAnimationSystem(manager)
    system.update(1 / 60)
    assert animator.current_clip_name == "walk_left"

    body.velocity = Vector2(0, 0)
    system.update(1 / 60)

    assert entity.get_component(DirectionalAnimator).facing is Facing.LEFT
    assert animator.current_clip_name == "walk_left"


def test_walking_in_a_straight_line_does_not_restart_the_cycle():
    """`play_clip()` ignores a re-request for the clip already playing,
    which is what makes asking every frame safe."""
    manager = EntityManager()
    clips = DirectionalClipSet(actions=("walk",))
    entity, animator = _entity_with_animator(manager, clips)
    entity.add_component(TopDownBody(velocity=Vector2(50, 0)))
    system = DirectionalAnimationSystem(manager)

    system.update(1 / 60)
    animator._current_frame_index = 3
    system.update(1 / 60)

    assert animator._current_frame_index == 3


def test_a_transform_driven_character_still_faces_the_right_way():
    """A character moved by a tween, a pathfinder or a script has no body."""
    manager = EntityManager()
    clips = DirectionalClipSet(actions=("walk",))
    entity, animator = _entity_with_animator(manager, clips)
    system = DirectionalAnimationSystem(manager)

    system.update(1 / 60)  # seeds the previous position
    entity.get_component(Transform).position = Vector2(0, 40)
    system.update(1 / 60)

    assert animator.current_clip_name == "walk_down"


def test_the_action_is_the_games_business_not_the_systems():
    manager = EntityManager()
    clips = DirectionalClipSet(actions=("walk", "attack"))
    entity, animator = _entity_with_animator(manager, clips)
    entity.add_component(TopDownBody(velocity=Vector2(50, 0)))
    system = DirectionalAnimationSystem(manager)

    entity.get_component(DirectionalAnimator).action = "attack"
    system.update(1 / 60)

    assert animator.current_clip_name == "attack_right"


def test_an_entity_without_an_animator_is_skipped_not_an_error():
    """A game may well attach the facing to something it draws itself."""
    manager = EntityManager()
    entity = manager.create_entity()
    entity.add_component(Transform(position=Vector2(0, 0)))
    entity.add_component(TopDownBody(velocity=Vector2(50, 0)))
    directional = DirectionalAnimator(DirectionalClipSet(actions=("walk",)))
    entity.add_component(directional)

    DirectionalAnimationSystem(manager).update(1 / 60)

    assert directional.facing is Facing.RIGHT
