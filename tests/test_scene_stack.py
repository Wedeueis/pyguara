"""Tests for scene stack system."""

from unittest.mock import Mock

import pytest

from pyguara.events.dispatcher import EventDispatcher
from pyguara.graphics.protocols import IRenderer, UIRenderer
from pyguara.scene.base import Scene
from pyguara.scene.manager import SceneManager
from pyguara.scene.transitions import FadeTransition, TransitionConfig


class MockScene(Scene):
    """Mock scene implementation for testing."""

    def __init__(self, name: str):
        """Initialize mock scene."""
        event_dispatcher = Mock(spec=EventDispatcher)
        super().__init__(name, event_dispatcher)
        self.entered = False
        self.exited = False
        self.paused = False
        self.resumed = False
        self.updated = False
        self.rendered = False

    def on_enter(self) -> None:
        """Track enter calls."""
        self.entered = True

    def on_exit(self) -> None:
        """Track exit calls."""
        self.exited = True

    def on_pause(self) -> None:
        """Track pause calls."""
        self.paused = True

    def on_resume(self) -> None:
        """Track resume calls."""
        self.resumed = True

    def update(self, dt: float) -> None:
        """Track update calls."""
        self.updated = True

    def render(self, world_renderer: IRenderer, ui_renderer: UIRenderer) -> None:
        """Track render calls."""
        self.rendered = True

    def reset_flags(self) -> None:
        """Reset all tracking flags."""
        self.updated = False
        self.rendered = False


class TestSceneStack:
    """Test scene stack functionality."""

    def test_push_scene_calls_lifecycle_hooks(self):
        """Pushing a scene should call appropriate lifecycle hooks."""
        manager = SceneManager()

        scene1 = MockScene("scene1")
        scene2 = MockScene("scene2")

        manager.register(scene1)
        manager.register(scene2)

        # Set initial scene
        manager.switch_to("scene1")
        assert scene1.entered

        # Push second scene
        manager.push_scene("scene2")

        # Scene1 should be paused
        assert scene1.paused

        # Scene2 should be entered
        assert scene2.entered

    def test_pop_scene_calls_lifecycle_hooks(self):
        """Popping a scene should call appropriate lifecycle hooks."""
        manager = SceneManager()

        scene1 = MockScene("scene1")
        scene2 = MockScene("scene2")

        manager.register(scene1)
        manager.register(scene2)

        # Setup stack
        manager.switch_to("scene1")
        manager.push_scene("scene2")

        # Pop scene2
        popped = manager.pop_scene()

        # Scene2 should be exited
        assert scene2.exited

        # Scene1 should be resumed
        assert scene1.resumed

        # Popped scene should be scene2
        assert popped == scene2

    def test_pop_empty_stack_returns_none(self):
        """Popping from an empty stack should return None."""
        manager = SceneManager()

        scene = MockScene("scene")
        manager.register(scene)
        manager.switch_to("scene")

        # Try to pop with no stack
        result = manager.pop_scene()

        assert result is None

    def test_switch_to_clears_stack(self):
        """Switching scenes should clear the stack."""
        manager = SceneManager()

        scene1 = MockScene("scene1")
        scene2 = MockScene("scene2")
        scene3 = MockScene("scene3")

        manager.register(scene1)
        manager.register(scene2)
        manager.register(scene3)

        # Build up a stack
        manager.switch_to("scene1")
        manager.push_scene("scene2")

        # Switch to a different scene
        manager.switch_to("scene3")

        # Stack should be cleared
        # Trying to pop should return None
        assert manager.pop_scene() is None

    def test_update_with_pause_below_true(self):
        """When pause_below=True, only top scene should update."""
        manager = SceneManager()

        scene1 = MockScene("scene1")
        scene2 = MockScene("scene2")

        manager.register(scene1)
        manager.register(scene2)

        manager.switch_to("scene1")
        manager.push_scene("scene2", pause_below=True)

        # Reset flags
        scene1.reset_flags()
        scene2.reset_flags()

        # Update
        manager.update(0.016)

        # Only scene2 should update
        assert not scene1.updated
        assert scene2.updated

    def test_update_with_pause_below_false(self):
        """When pause_below=False, both scenes should update."""
        manager = SceneManager()

        scene1 = MockScene("scene1")
        scene2 = MockScene("scene2")

        manager.register(scene1)
        manager.register(scene2)

        manager.switch_to("scene1")
        manager.push_scene("scene2", pause_below=False)

        # Reset flags
        scene1.reset_flags()
        scene2.reset_flags()

        # Update
        manager.update(0.016)

        # Both scenes should update
        assert scene1.updated
        assert scene2.updated

    def test_render_all_scenes_in_stack(self):
        """Rendering should draw all scenes from bottom to top."""
        manager = SceneManager()

        scene1 = MockScene("scene1")
        scene2 = MockScene("scene2")
        scene3 = MockScene("scene3")

        manager.register(scene1)
        manager.register(scene2)
        manager.register(scene3)

        manager.switch_to("scene1")
        manager.push_scene("scene2")
        manager.push_scene("scene3")

        # Reset flags
        scene1.reset_flags()
        scene2.reset_flags()
        scene3.reset_flags()

        # Render
        world_renderer = Mock(spec=IRenderer)
        ui_renderer = Mock(spec=UIRenderer)
        manager.render(world_renderer, ui_renderer)

        # All scenes should be rendered
        assert scene1.rendered
        assert scene2.rendered
        assert scene3.rendered

    def test_multiple_push_pop_cycles(self):
        """Test multiple push/pop cycles."""
        manager = SceneManager()

        scene1 = MockScene("scene1")
        scene2 = MockScene("scene2")
        scene3 = MockScene("scene3")

        manager.register(scene1)
        manager.register(scene2)
        manager.register(scene3)

        # Initial scene
        manager.switch_to("scene1")
        assert scene1.entered

        # Push scene2
        manager.push_scene("scene2")
        assert scene1.paused
        assert scene2.entered

        # Push scene3
        manager.push_scene("scene3")
        assert scene2.paused
        assert scene3.entered

        # Pop back to scene2
        manager.pop_scene()
        assert scene3.exited
        assert scene2.resumed

        # Pop back to scene1
        manager.pop_scene()
        assert scene2.exited
        assert scene1.resumed

    def test_push_unregistered_scene_raises_error(self):
        """Pushing an unregistered scene should raise ValueError."""
        manager = SceneManager()

        scene1 = MockScene("scene1")
        manager.register(scene1)
        manager.switch_to("scene1")

        with pytest.raises(ValueError, match="not registered"):
            manager.push_scene("nonexistent")

    def test_nested_pause_flags(self):
        """Test complex nesting with mixed pause_below flags."""
        manager = SceneManager()

        scene1 = MockScene("scene1")
        scene2 = MockScene("scene2")
        scene3 = MockScene("scene3")

        manager.register(scene1)
        manager.register(scene2)
        manager.register(scene3)

        # scene1 (base)
        manager.switch_to("scene1")

        # scene2 on top (doesn't pause below)
        manager.push_scene("scene2", pause_below=False)

        # scene3 on top (pauses below)
        manager.push_scene("scene3", pause_below=True)

        # Reset flags
        scene1.reset_flags()
        scene2.reset_flags()
        scene3.reset_flags()

        # Update
        manager.update(0.016)

        # Only scene3 should update (it pauses everything below)
        assert not scene1.updated
        assert not scene2.updated
        assert scene3.updated


class TestSceneStackIntegration:
    """Test scene stack integration patterns."""

    def test_pause_menu_pattern(self):
        """Common pattern: push pause menu over game scene."""
        manager = SceneManager()

        game_scene = MockScene("game")
        pause_menu = MockScene("pause_menu")

        manager.register(game_scene)
        manager.register(pause_menu)

        # Start game
        manager.switch_to("game")

        # Open pause menu (pause game)
        manager.push_scene("pause_menu", pause_below=True)

        # Reset flags
        game_scene.reset_flags()
        pause_menu.reset_flags()

        # Update and render
        manager.update(0.016)
        world_renderer = Mock(spec=IRenderer)
        ui_renderer = Mock(spec=UIRenderer)
        manager.render(world_renderer, ui_renderer)

        # Game should not update but should render (visible behind menu)
        assert not game_scene.updated
        assert game_scene.rendered

        # Pause menu should update and render
        assert pause_menu.updated
        assert pause_menu.rendered

        # Close pause menu
        manager.pop_scene()

        # Game should be resumed
        assert game_scene.resumed

    def test_dialog_over_game_pattern(self):
        """Common pattern: show dialog without pausing game."""
        manager = SceneManager()

        game_scene = MockScene("game")
        dialog = MockScene("dialog")

        manager.register(game_scene)
        manager.register(dialog)

        # Start game
        manager.switch_to("game")

        # Show dialog (don't pause game)
        manager.push_scene("dialog", pause_below=False)

        # Reset flags
        game_scene.reset_flags()
        dialog.reset_flags()

        # Update
        manager.update(0.016)

        # Both should update
        assert game_scene.updated
        assert dialog.updated

    def test_inventory_over_pause_over_game(self):
        """Complex pattern: inventory -> pause menu -> game."""
        manager = SceneManager()

        game = MockScene("game")
        pause = MockScene("pause")
        inventory = MockScene("inventory")

        manager.register(game)
        manager.register(pause)
        manager.register(inventory)

        # Start game
        manager.switch_to("game")

        # Open pause menu
        manager.push_scene("pause", pause_below=True)

        # Open inventory from pause menu
        manager.push_scene("inventory", pause_below=True)

        # Reset flags
        game.reset_flags()
        pause.reset_flags()
        inventory.reset_flags()

        # Update
        manager.update(0.016)

        # Only inventory should update
        assert not game.updated
        assert not pause.updated
        assert inventory.updated

        # Close inventory
        manager.pop_scene()
        assert pause.resumed

        # Close pause
        manager.pop_scene()
        assert game.resumed


class TestSceneLifecycleRepair:
    """Regression tests for the scene lifecycle repair (wayfinder ticket 29)."""

    def test_push_with_two_phase_transition_does_not_exit_paused_scene(self):
        """SCENE-1: pushing over a scene with a two-phase transition must not
        call on_exit() on the scene being paused underneath, at start or at
        the phase-flip midpoint."""
        manager = SceneManager()

        game = MockScene("game")
        pause_menu = MockScene("pause_menu")
        manager.register(game)
        manager.register(pause_menu)

        manager.switch_to("game")
        game.reset_flags()

        transition = FadeTransition(TransitionConfig(duration=1.0, two_phase=True))
        manager.push_scene("pause_menu", transition=transition)
        assert not game.exited

        manager.update(0.5)  # phase-flip midpoint
        assert not game.exited

        manager.update(0.5)  # transition completes
        assert not game.exited

    def test_single_phase_transition_enters_to_scene_before_render_shows_it(self):
        """SCENE-1: a single-phase transition must call on_enter() on the
        incoming scene immediately at transition start -- before render()
        ever shows it -- not deferred to transition completion."""
        manager = SceneManager()

        scene1 = MockScene("scene1")
        scene2 = MockScene("scene2")
        manager.register(scene1)
        manager.register(scene2)

        manager.switch_to("scene1")

        transition = FadeTransition(TransitionConfig(duration=1.0, two_phase=False))
        manager.switch_to("scene2", transition=transition)

        # on_enter() already ran -- before update()/render() have run at all.
        assert scene2.entered

        world_renderer = Mock(spec=IRenderer)
        ui_renderer = Mock(spec=UIRenderer)
        manager.render(world_renderer, ui_renderer)
        assert scene2.rendered

    def test_three_deep_stack_excludes_base_scene_when_middle_pauses_below(self):
        """SCENE-2: a three-deep stack (base -> paused middle -> active top)
        with the middle scene's pause_below=True must exclude the base scene
        from active updates, even though the top scene's own pause_below is
        False -- the off-by-one regression case."""
        manager = SceneManager()

        base = MockScene("base")
        middle = MockScene("middle")
        top = MockScene("top")
        manager.register(base)
        manager.register(middle)
        manager.register(top)

        manager.switch_to("base")
        manager.push_scene("middle", pause_below=True)
        manager.push_scene("top", pause_below=False)

        base.reset_flags()
        middle.reset_flags()
        top.reset_flags()

        manager.update(0.016)

        assert not base.updated
        assert middle.updated
        assert top.updated

    def test_cleanup_exits_every_scene_ever_entered_exactly_once_lifo(self):
        """cleanup() must unwind the whole stack LIFO, exiting every scene
        that was ever entered exactly once -- current scene first, then the
        stack top-to-bottom."""
        manager = SceneManager()

        base = MockScene("base")
        middle = MockScene("middle")
        top = MockScene("top")
        manager.register(base)
        manager.register(middle)
        manager.register(top)

        manager.switch_to("base")
        manager.push_scene("middle")
        manager.push_scene("top")

        exit_order = []
        base.on_exit = lambda: exit_order.append("base")
        middle.on_exit = lambda: exit_order.append("middle")
        top.on_exit = lambda: exit_order.append("top")

        manager.cleanup()

        assert exit_order == ["top", "middle", "base"]

    def test_pop_with_transition_resumes_previous_scene_not_reenters(self):
        """pop_scene() with a transition must resume the previous scene
        (on_resume()), not re-enter it, and must not exit the popped scene
        synchronously before the transition manager can render it."""
        manager = SceneManager()

        game = MockScene("game")
        pause_menu = MockScene("pause_menu")
        manager.register(game)
        manager.register(pause_menu)

        manager.switch_to("game")
        manager.push_scene("pause_menu")

        enter_calls = []
        game.on_enter = lambda: enter_calls.append(True)

        transition = FadeTransition(TransitionConfig(duration=1.0, two_phase=True))
        popped = manager.pop_scene(transition=transition)
        assert popped is pause_menu

        # Not exited synchronously -- must stay alive for the transition to render.
        assert not pause_menu.exited

        manager.update(0.5)  # phase-flip midpoint
        assert pause_menu.exited
        assert game.resumed
        assert enter_calls == []  # resumed, never re-entered


class TestSwitchToUnwindsTheStack:
    """switch_to() replaced the stack with a bare `.clear()`.

    Every scene underneath was abandoned live -- still holding its
    EntityManager, its systems and any physics bodies -- without ever
    receiving on_exit(). cleanup() had been written specifically to avoid that
    leak, and switch_to() reintroduced it on every scene change.
    """

    def test_switch_to_exits_the_scene_beneath_an_overlay(self):
        manager = SceneManager()
        game, pause, menu = MockScene("game"), MockScene("pause"), MockScene("menu")
        for scene in (game, pause, menu):
            manager.register(scene)

        manager.switch_to("game")
        manager.push_scene("pause")
        manager.switch_to("menu")

        assert game.exited
        assert pause.exited

    def test_switch_to_cleans_up_the_system_manager_of_stacked_scenes(self):
        manager = SceneManager()
        game, menu = MockScene("game"), MockScene("menu")
        manager.register(game)
        manager.register(menu)
        game.system_manager = Mock()

        manager.switch_to("game")
        manager.push_scene("menu")
        manager.switch_to("menu")

        assert game.system_manager.cleanup.called

    def test_switch_to_exits_a_deep_stack_top_down(self):
        manager = SceneManager()
        order: list[str] = []
        scenes = [MockScene(n) for n in ("base", "mid", "top", "other")]
        for scene in scenes:
            scene.on_exit = lambda s=scene: order.append(s.name)  # type: ignore[method-assign]
            manager.register(scene)

        manager.switch_to("base")
        manager.push_scene("mid")
        manager.push_scene("top")
        manager.switch_to("other")

        assert order == ["top", "mid", "base"]

    def test_the_stack_is_empty_after_a_switch(self):
        manager = SceneManager()
        for name in ("game", "pause", "menu"):
            manager.register(MockScene(name))

        manager.switch_to("game")
        manager.push_scene("pause")
        manager.switch_to("menu")

        assert manager._stack == []
        assert manager.pop_scene() is None


class TestTransitionReentrancy:
    """A second stack change during a transition replaced the pending scene.

    The first target was skipped without ever receiving on_enter(), while the
    scene it was replacing had already been exited.
    """

    def test_a_second_switch_during_a_transition_is_ignored(self):
        manager = SceneManager()
        manager.set_screen_size(800, 600)
        for name in ("a", "b", "c"):
            manager.register(MockScene(name))
        manager.switch_to("a")

        manager.switch_to("b", FadeTransition())
        manager.switch_to("c", FadeTransition())

        assert manager._pending_scene == "b"

    def test_a_push_during_a_transition_is_ignored(self):
        manager = SceneManager()
        manager.set_screen_size(800, 600)
        for name in ("a", "b", "c"):
            manager.register(MockScene(name))
        manager.switch_to("a")
        manager.switch_to("b", FadeTransition())

        manager.push_scene("c")

        assert manager._stack == []

    def test_a_pop_during_a_transition_is_ignored(self):
        manager = SceneManager()
        manager.set_screen_size(800, 600)
        base, top, other = MockScene("base"), MockScene("top"), MockScene("other")
        for scene in (base, top, other):
            manager.register(scene)
        manager.switch_to("base")
        manager.push_scene("top")
        manager.switch_to("other", FadeTransition())

        assert manager.pop_scene() is None

    def test_the_rejected_request_is_logged(self, caplog):
        import logging

        manager = SceneManager()
        manager.set_screen_size(800, 600)
        for name in ("a", "b", "c"):
            manager.register(MockScene(name))
        manager.switch_to("a")
        manager.switch_to("b", FadeTransition())

        with caplog.at_level(logging.WARNING):
            manager.switch_to("c", FadeTransition())

        assert "transition is already in progress" in caplog.text


class TestPopDuringTransition:
    def test_the_stack_entry_survives_until_the_transition_completes(self):
        """Popping the entry up front left the previous scene both off the
        stack and not yet current, so cleanup() could not find it."""
        manager = SceneManager()
        manager.set_screen_size(800, 600)
        base, top = MockScene("base"), MockScene("top")
        manager.register(base)
        manager.register(top)
        manager.switch_to("base")
        manager.push_scene("top")

        manager.pop_scene(FadeTransition())

        assert len(manager._stack) == 1

    def test_cleanup_mid_pop_still_exits_the_scene_being_returned_to(self):
        manager = SceneManager()
        manager.set_screen_size(800, 600)
        base, top = MockScene("base"), MockScene("top")
        manager.register(base)
        manager.register(top)
        manager.switch_to("base")
        manager.push_scene("top")
        manager.pop_scene(FadeTransition())

        manager.cleanup()

        assert base.exited
        assert top.exited

    def test_cleanup_mid_switch_exits_the_incoming_scene(self):
        """A transition that has entered its target but not yet made it
        current still leaves that scene holding its world."""
        manager = SceneManager()
        manager.set_screen_size(800, 600)
        a, b = MockScene("a"), MockScene("b")
        manager.register(a)
        manager.register(b)
        manager.switch_to("a")
        manager.switch_to("b", FadeTransition(TransitionConfig(duration=1.0)))

        manager.cleanup()

        assert b.exited

    def test_no_scene_is_exited_twice_by_cleanup(self):
        manager = SceneManager()
        manager.set_screen_size(800, 600)
        counts: dict[str, int] = {}
        for name in ("base", "top"):
            scene = MockScene(name)
            scene.on_exit = lambda s=scene: counts.__setitem__(  # type: ignore[method-assign]
                s.name, counts.get(s.name, 0) + 1
            )
            manager.register(scene)
        manager.switch_to("base")
        manager.push_scene("top")
        manager.pop_scene(FadeTransition())

        manager.cleanup()

        assert counts == {"base": 1, "top": 1}


class TestRegistration:
    def test_a_scene_registered_before_the_container_is_wired_later(self):
        """register() silently skipped resolve_dependencies() with no
        container, leaving the scene live but with no camera or render system
        -- surfacing much later as an assertion inside render()."""
        from unittest.mock import MagicMock

        from pyguara.di.container import DIContainer

        manager = SceneManager()
        scene = MockScene("early")
        manager.register(scene)
        assert scene.container is None

        container = MagicMock(spec=DIContainer)
        manager.set_container(container)

        assert scene.container is container

    def test_replacing_a_registered_name_is_logged(self, caplog):
        import logging

        manager = SceneManager()
        manager.register(MockScene("a"))

        with caplog.at_level(logging.WARNING):
            manager.register(MockScene("a"))

        assert "already registered as 'a'" in caplog.text

    def test_re_registering_the_same_object_is_not_flagged(self, caplog):
        import logging

        manager = SceneManager()
        scene = MockScene("a")
        manager.register(scene)

        with caplog.at_level(logging.WARNING):
            manager.register(scene)

        assert caplog.text == ""
