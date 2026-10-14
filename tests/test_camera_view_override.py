"""An editor can take the view from a game that drives its camera.

Studio shows the game's own framebuffer, so there is exactly one camera:
panning the viewport has to move the camera the game renders with. And a
game whose follow system writes that camera every tick wins -- measured on
a demo, a pan put the camera at (-97, 178) and forty frames later the
follow system had it at (204, 387), so the click that followed landed on
whatever had moved under the cursor. That is what "the middle button broke
selection" was.

Godot and Unity sidestep the question by rendering the editor view
themselves. With one camera, the answer is an override: the game keeps
writing where *it* wants the camera, those writes are recorded and not
displayed, and releasing hands it back wherever the game had got to.
"""

from __future__ import annotations

import pytest

from pyguara.common.types import Vector2
from pyguara.graphics.components.camera import Camera2D


@pytest.fixture
def camera() -> Camera2D:
    return Camera2D(1280, 720)


@pytest.mark.unit
class TestTakingTheView:
    def test_nothing_is_overridden_to_begin_with(self, camera: Camera2D) -> None:
        assert camera.view_overridden is False

    def test_taking_it_holds_the_current_position(self, camera: Camera2D) -> None:
        camera.position = Vector2(100, 50)

        camera.take_view()

        assert camera.view_overridden is True
        assert camera.position == Vector2(100, 50)

    def test_the_game_can_no_longer_move_the_view(self, camera: Camera2D) -> None:
        """The whole point: a follow system writing every tick used to drag
        the view back the moment the hand let go."""
        camera.position = Vector2(100, 50)
        camera.take_view(Vector2(900, 900))

        for _ in range(40):
            camera.position = Vector2(100, 50)

        assert camera.position == Vector2(900, 900)

    def test_the_transforms_follow_the_override(self, camera: Camera2D) -> None:
        """Not just `position`: everything that maps world to screen has to
        agree, or picking lands somewhere other than the picture."""
        camera.take_view(Vector2(640, 360))

        assert camera.view_position == Vector2(640, 360)
        centre = camera.world_to_screen(Vector2(640, 360))
        assert centre.x == pytest.approx(640)
        assert centre.y == pytest.approx(360)

    def test_zoom_can_be_taken_too(self, camera: Camera2D) -> None:
        camera.zoom = 1.0
        camera.take_view(zoom=2.5)

        camera.zoom = 1.0

        assert camera.zoom == 2.5

    def test_taking_it_twice_is_the_same_as_once(self, camera: Camera2D) -> None:
        """A drag calls it every frame and should not have to track
        whether it already holds the view."""
        camera.position = Vector2(10, 10)
        camera.take_view(Vector2(500, 500))
        camera.take_view(Vector2(600, 600))

        assert camera.position == Vector2(600, 600)

    def test_a_zero_zoom_is_still_refused(self, camera: Camera2D) -> None:
        with pytest.raises(ValueError, match="positive"):
            camera.take_view(zoom=0.0)


@pytest.mark.unit
class TestGivingItBack:
    def test_the_game_resumes_where_it_had_got_to(self, camera: Camera2D) -> None:
        """Not where the view was left. The follow system has been tracking
        the player all along, and snapping to that is what "follow the game
        again" means."""
        camera.position = Vector2(10, 10)
        camera.take_view(Vector2(900, 900))
        camera.position = Vector2(222, 333)

        camera.release_view()

        assert camera.view_overridden is False
        assert camera.position == Vector2(222, 333)

    def test_zoom_comes_back_too(self, camera: Camera2D) -> None:
        camera.zoom = 1.5
        camera.take_view(zoom=4.0)
        camera.zoom = 2.0

        camera.release_view()

        assert camera.zoom == 2.0

    def test_releasing_without_taking_is_harmless(self, camera: Camera2D) -> None:
        camera.position = Vector2(5, 5)

        camera.release_view()

        assert camera.position == Vector2(5, 5)


@pytest.mark.unit
class TestItDoesNotDisturbTheRest:
    def test_shake_still_moves_the_picture_not_the_camera(
        self, camera: Camera2D
    ) -> None:
        camera.take_view(Vector2(100, 100))
        camera.shake(magnitude=10.0, duration=1.0)
        camera.update(1 / 60)

        assert camera.position == Vector2(100, 100)
        assert camera.view_position != camera.position

    def test_follow_still_records_where_the_game_wants_to_be(
        self, camera: Camera2D
    ) -> None:
        camera.take_view(Vector2(0, 0))
        camera.follow(Vector2(400, 400))
        camera.update(1 / 60)

        assert camera.position == Vector2(0, 0)
        camera.release_view()
        assert camera.position != Vector2(0, 0)
