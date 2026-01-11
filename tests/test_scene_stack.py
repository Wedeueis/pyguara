"""Tests for scene stack system."""

from unittest.mock import Mock

from pyguara.scene.manager import SceneManager
from pyguara.scene.base import Scene
from pyguara.events.dispatcher import EventDispatcher
from pyguara.graphics.protocols import IRenderer, UIRenderer


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

        try:
            manager.push_scene("nonexistent")
            assert False, "Should have raised ValueError"
        except ValueError as e:
            assert "not registered" in str(e)

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
