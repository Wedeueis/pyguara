"""Camera framing: shake as an offset, bounds clamping, co-op fit, lookahead."""

import pytest

from pyguara.common.types import Rect, Vector2
from pyguara.graphics.components.camera import Camera2D, CameraFollowConstraints


def _camera(width: int = 800, height: int = 600) -> Camera2D:
    return Camera2D(width, height)


def _run(camera: Camera2D, seconds: float, step: float = 1 / 60) -> None:
    for _ in range(int(seconds / step)):
        camera.update(step)


# -- Shake no longer walks the camera away --


def test_a_finished_shake_leaves_the_camera_where_it_started():
    """The offset oscillates around zero but was *added into* `position` and
    never subtracted, so every explosion left the camera somewhere else --
    a random walk across a scene with explosions in it."""
    camera = _camera()
    camera.position = Vector2(100, 100)

    camera.shake(magnitude=10.0, duration=0.5)
    _run(camera, 1.0)

    assert camera.position == Vector2(100, 100)


def test_repeated_shakes_do_not_accumulate():
    camera = _camera()
    camera.position = Vector2(500, 500)

    for _ in range(20):
        camera.shake(magnitude=25.0, duration=0.1)
        _run(camera, 0.2)

    assert camera.position == Vector2(500, 500)


def test_a_shake_still_moves_the_picture():
    camera = _camera()
    camera.position = Vector2(100, 100)
    camera.shake(magnitude=50.0, duration=1.0)

    camera.update(1 / 60)

    assert camera.view_position != camera.position
    screen = camera.world_to_screen(Vector2(100, 100))
    assert screen != Vector2(400, 300)


def test_the_view_bounds_follow_the_shake_too():
    """`get_view_bounds` is the culling rectangle; a shaken camera that
    culls against its unshaken position pops sprites at the edge."""
    camera = _camera()
    camera.position = Vector2(0, 0)
    before = camera.get_view_bounds()

    camera.shake(magnitude=100.0, duration=1.0)
    camera.update(1 / 60)

    assert camera.get_view_bounds() != before


# -- Bounds --


def test_bounds_stop_the_view_at_the_level_edge():
    camera = _camera()
    camera.set_bounds(Rect(0, 0, 2000, 1500))
    camera.position = Vector2(-500, -500)

    camera.update(1 / 60)

    assert camera.position == Vector2(400, 300)


def test_bounds_stop_the_view_at_the_far_edge_too():
    camera = _camera()
    camera.set_bounds(Rect(0, 0, 2000, 1500))
    camera.position = Vector2(9000, 9000)

    camera.update(1 / 60)

    assert camera.position == Vector2(1600, 1200)


def test_a_room_smaller_than_the_screen_is_centred():
    """Picking an edge instead would show more wall on one side than the
    other."""
    camera = _camera()
    camera.set_bounds(Rect(0, 0, 400, 300))
    camera.position = Vector2(5000, -5000)

    camera.update(1 / 60)

    assert camera.position == Vector2(200, 150)


def test_zooming_in_lets_the_camera_approach_the_edge():
    """The clamp is sized from the view, not the viewport, so it has to
    track zoom."""
    camera = _camera()
    camera.set_bounds(Rect(0, 0, 2000, 1500))
    camera.zoom = 2.0
    camera.position = Vector2(0, 0)

    camera.update(1 / 60)

    assert camera.position == Vector2(200, 150)


def test_a_split_screen_camera_clamps_against_its_declared_viewport():
    camera = _camera()
    camera.set_viewport_size(400, 600)
    camera.set_bounds(Rect(0, 0, 2000, 1500))
    camera.position = Vector2(0, 0)

    camera.update(1 / 60)

    assert camera.position == Vector2(200, 300)


def test_clearing_the_bounds_releases_the_camera():
    camera = _camera()
    camera.set_bounds(Rect(0, 0, 2000, 1500))
    camera.position = Vector2(-500, -500)
    camera.update(1 / 60)

    camera.set_bounds(None)
    camera.position = Vector2(-500, -500)
    camera.update(1 / 60)

    assert camera.position == Vector2(-500, -500)
    assert camera.bounds is None


def test_bounds_clamp_a_follow_target_outside_the_level():
    camera = _camera()
    camera.set_bounds(Rect(0, 0, 2000, 1500))
    camera.position = Vector2(400, 300)
    camera.follow(Vector2(-9000, 300))

    camera.update(1 / 60)

    assert camera.position == Vector2(400, 300)


def test_a_shake_at_the_wall_is_still_a_shake():
    """Suppressing it would make an explosion next to a wall read as a
    stutter, which is more visually wrong than a few pixels of overscan."""
    camera = _camera()
    camera.set_bounds(Rect(0, 0, 2000, 1500))
    camera.position = Vector2(0, 0)
    camera.shake(magnitude=40.0, duration=1.0)

    camera.update(1 / 60)

    assert camera.position == Vector2(400, 300)
    assert camera.view_position != camera.position


# -- Multi-target framing --


def test_framing_centres_the_targets():
    camera = _camera()
    camera.frame_targets([Vector2(0, 0), Vector2(800, 400)])

    camera.update(1 / 60)

    assert camera.position == Vector2(400, 200)


def test_framing_zooms_out_until_both_targets_fit():
    camera = _camera()
    camera.frame_targets([Vector2(0, 0), Vector2(1600, 0)])

    camera.update(1 / 60)

    assert camera.zoom == pytest.approx(0.5)


def test_walking_back_together_zooms_in_again():
    camera = _camera()
    camera.frame_targets([Vector2(0, 0), Vector2(1600, 0)], max_zoom=2.0)
    camera.update(1 / 60)
    spread = camera.zoom

    camera.frame_targets([Vector2(0, 0), Vector2(800, 0)], max_zoom=2.0)
    camera.update(1 / 60)

    assert spread == pytest.approx(0.5)
    assert camera.zoom == pytest.approx(1.0)


def test_padding_keeps_a_target_off_the_very_edge():
    camera = _camera()
    camera.frame_targets([Vector2(0, 0), Vector2(800, 0)], padding=100.0)

    camera.update(1 / 60)

    assert camera.zoom == pytest.approx(0.8)


def test_min_zoom_is_the_floor_the_camera_refuses_to_pass():
    camera = _camera()
    camera.frame_targets([Vector2(0, 0), Vector2(100_000, 0)], min_zoom=0.25)

    camera.update(1 / 60)

    assert camera.zoom == pytest.approx(0.25)


def test_one_target_with_no_padding_zooms_to_the_ceiling_not_to_infinity():
    camera = _camera()
    camera.frame_targets([Vector2(50, 50)], max_zoom=3.0)

    camera.update(1 / 60)

    assert camera.zoom == pytest.approx(3.0)
    assert camera.position == Vector2(50, 50)


def test_framing_can_leave_zoom_alone():
    camera = _camera()
    camera.zoom = 1.75
    camera.frame_targets([Vector2(0, 0), Vector2(5000, 0)], adjust_zoom=False)

    camera.update(1 / 60)

    assert camera.zoom == pytest.approx(1.75)
    assert camera.position == Vector2(2500, 0)


def test_smoothing_eases_toward_the_frame_rather_than_snapping():
    camera = _camera()
    camera.position = Vector2(0, 0)
    camera.frame_targets([Vector2(1000, 0)], smooth_time=1.0, max_zoom=1.0)

    camera.update(0.1)

    assert 0 < camera.position.x < 1000


def test_framing_and_follow_cancel_each_other():
    """Both decide `position`, so holding both would make the result depend
    on the order of two lines inside `update()`."""
    camera = _camera()
    camera.follow(Vector2(100, 100))
    camera.frame_targets([Vector2(900, 900)], max_zoom=1.0)
    camera.update(1 / 60)

    assert camera.position == Vector2(900, 900)

    camera.follow(Vector2(100, 100))
    camera.update(1 / 60)

    assert camera.position == Vector2(100, 100)


def test_framing_bows_to_the_bounds():
    camera = _camera()
    camera.set_bounds(Rect(0, 0, 2000, 1500))
    camera.frame_targets([Vector2(-5000, 0)], max_zoom=1.0)

    camera.update(1 / 60)

    assert camera.position == Vector2(400, 300)


def test_stop_framing_leaves_the_camera_where_it_is():
    camera = _camera()
    camera.frame_targets([Vector2(600, 600)], max_zoom=1.0)
    camera.update(1 / 60)

    camera.stop_framing()
    camera.update(1 / 60)

    assert camera.position == Vector2(600, 600)


def test_framing_rejects_an_empty_target_list():
    with pytest.raises(ValueError, match="at least one target"):
        _camera().frame_targets([])


def test_framing_rejects_a_non_positive_or_inverted_zoom_range():
    camera = _camera()
    with pytest.raises(ValueError, match="must be positive"):
        camera.frame_targets([Vector2(0, 0)], min_zoom=0.0)
    with pytest.raises(ValueError, match="above max_zoom"):
        camera.frame_targets([Vector2(0, 0)], min_zoom=2.0, max_zoom=1.0)


# -- Lookahead --


def test_lookahead_leads_a_moving_target():
    """Show more of what the player is about to hit than of what they have
    already passed."""
    camera = _camera()
    constraints = CameraFollowConstraints(
        deadzone=Rect(0, 0, 0, 0), smooth_time=0.0, lookahead=0.5
    )
    x = 0.0
    for _ in range(30):
        x += 10.0
        camera.follow(Vector2(x, 0), constraints)
        camera.update(1 / 60)

    assert camera.position.x > x


def test_without_lookahead_the_camera_sits_on_the_target():
    camera = _camera()
    constraints = CameraFollowConstraints(
        deadzone=Rect(0, 0, 0, 0), smooth_time=0.0, lookahead=0.0
    )
    x = 0.0
    for _ in range(30):
        x += 10.0
        camera.follow(Vector2(x, 0), constraints)
        camera.update(1 / 60)

    assert camera.position.x == pytest.approx(x)


def test_lookahead_needs_no_caller_supplied_velocity():
    """The camera measures it from the point it was given last frame, so a
    caller already passing `player.transform.position` passes nothing more."""
    camera = _camera()
    constraints = CameraFollowConstraints(
        deadzone=Rect(0, 0, 0, 0), smooth_time=0.0, lookahead=1.0
    )

    camera.follow(Vector2(0, 0), constraints)
    camera.update(1 / 60)
    camera.follow(Vector2(6, 0), constraints)
    camera.update(1 / 60)

    # 6 px in 1/60 s is 360 px/s; one second of lead is 360 px ahead of 6.
    assert camera.position.x == pytest.approx(366.0)


def test_a_stationary_target_is_not_led_anywhere():
    camera = _camera()
    constraints = CameraFollowConstraints(
        deadzone=Rect(0, 0, 0, 0), smooth_time=0.0, lookahead=1.0
    )

    for _ in range(10):
        camera.follow(Vector2(250, 250), constraints)
        camera.update(1 / 60)

    assert camera.position == Vector2(250, 250)


def test_a_reversing_target_is_led_the_other_way():
    camera = _camera()
    constraints = CameraFollowConstraints(
        deadzone=Rect(0, 0, 0, 0), smooth_time=0.0, lookahead=0.5
    )

    x = 0.0
    for _ in range(30):
        x += 10.0
        camera.follow(Vector2(x, 0), constraints)
        camera.update(1 / 60)
    leading = camera.position.x

    for _ in range(30):
        x -= 10.0
        camera.follow(Vector2(x, 0), constraints)
        camera.update(1 / 60)

    assert camera.position.x < x
    assert camera.position.x < leading
