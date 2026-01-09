import pytest
from unittest.mock import MagicMock, patch
from pyguara.application.application import Application
from pyguara.di.container import DIContainer
from pyguara.scene.base import Scene
from pyguara.scene.manager import SceneManager
from pyguara.events.dispatcher import EventDispatcher
from pyguara.config.manager import ConfigManager
from pyguara.input.manager import InputManager
from pyguara.ui.manager import UIManager
from pyguara.graphics.window import Window
from pyguara.graphics.protocols import UIRenderer


# --- Mocks ---
class MockScene(Scene):
    def __init__(self, name, disp):
        super().__init__(name, disp)
        self.enter_called = False
        self.update_called = False
        self.render_called = False

    def on_enter(self):
        self.enter_called = True

    def on_exit(self):
        pass

    def update(self, dt):
        self.update_called = True

    def render(self, r):
        self.render_called = True


@pytest.fixture
def app_container():
    c = DIContainer()

    # Core Services
    c.register_instance(EventDispatcher, EventDispatcher())
    c.register_instance(ConfigManager, MagicMock())
    c.register_instance(InputManager, MagicMock())
    c.register_instance(UIManager, MagicMock())
    c.register_singleton(SceneManager, SceneManager)

    # Graphics Mocks
    mock_window = MagicMock()
    mock_window.is_open = True
    # Logic to close window after 1 frame
    # We'll handle loop breaking in the test logic or via side_effect

    c.register_instance(Window, mock_window)
    c.register_instance(UIRenderer, MagicMock())

    return c


def test_app_lifecycle_run_once(app_container):
    """
    Scenario: Application Start and Single Frame Execution
    Given a configured Application with a Starting Scene
    When run() is called
    Then the scene should be entered, updated, and rendered
    And the application should shut down gracefully
    """
    app = Application(app_container)
    scene = MockScene("start", app_container.get(EventDispatcher))

    # Mock loop control: Run once then stop
    # app._window.is_open is checked in while loop.
    # We can use side_effect on poll_events to close app?
    # Or just mock the clock to throw an exception to break loop?
    # Better: Mock app._window.is_open to return True then False

    app._window.is_open = True

    # We need to break the loop.
    # Strategy: Replace the app._clock with a mock that stops execution

    app._clock = MagicMock()

    def stop_app(*args):
        app._is_running = False
        return 16  # dt

    app._clock.tick.side_effect = stop_app

    # ACT
    with patch("pygame.event.pump"):
        app.run(scene)

    # ASSERT
    assert scene.enter_called
    assert scene.update_called
    assert scene.render_called
    # App should have called shutdown
    app._window.close.assert_called_once()


def test_scene_switching_integration(app_container):
    """
    Scenario: Scene Switching
    Given an Application running Scene A
    When SceneManager.switch_to("B") is called
    Then Scene A should exit and Scene B should enter
    """
    sm = app_container.get(SceneManager)
    scene_a = MockScene("A", MagicMock())
    scene_b = MockScene("B", MagicMock())

    sm.register(scene_a)
    sm.register(scene_b)

    # Start at A
    sm.switch_to("A")
    assert sm._current_scene == scene_a
    assert scene_a.enter_called

    # Switch to B
    sm.switch_to("B")
    assert sm._current_scene == scene_b
    assert scene_b.enter_called
