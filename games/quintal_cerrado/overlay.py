"""What every pushed overlay scene shares: a scrim, and a safe close key.

The store, the pause menu and the evaluation are all scenes pushed over the
frozen garden with `pause_below=True`, each closed by a key. That key is the
subtle part, and it has already caused a real bug once:

An overlay binds its close key in `on_enter()` -- which runs *inside the
dispatch of the key press that opened it* whenever the opener and the closer
are the same key (`O` for the store, `Esc` for the pause menu). Without
care, that same press then closes the overlay the instant it opens, and a
mocked-action test cannot see it. So close input is ignored until the
overlay has run one frame (`_armed`), and `_close()` is a no-op unless this
overlay is the current scene, because a key bound twice fires twice and the
second `pop_scene()` would close the *garden*.

Solved once, here, rather than once per overlay.
"""

from __future__ import annotations

from games.quintal_cerrado.bootstrap import WINDOW_HEIGHT, WINDOW_WIDTH
from pyguara.common.types import Color, Rect, Vector2
from pyguara.events.dispatcher import EventDispatcher
from pyguara.graphics.protocols import IRenderer, UIRenderer
from pyguara.input.events import OnActionEvent
from pyguara.input.manager import InputManager
from pyguara.input.types import ActionType, InputDevice
from pyguara.scene.base import Scene
from pyguara.scene.manager import SceneManager
from pyguara.ui.base import UIElement
from pyguara.ui.manager import UIManager
from pyguara.ui.types import UILayer


class Scrim(UIElement):
    """A full-screen wash over the frozen garden behind an overlay."""

    def __init__(self, width: int = WINDOW_WIDTH, height: int = WINDOW_HEIGHT) -> None:
        """Initialize the scrim.

        Args:
            width: Screen width.
            height: Screen height.
        """
        super().__init__(Vector2(0, 0), Vector2(width, height))

    def render(self, renderer: UIRenderer) -> None:
        """Wash the frame in the theme's scrim colour (which carries alpha)."""
        scrim = self.theme.colors.surface_scrim
        renderer.draw_rect(
            Rect(0, 0, self.rect.width, self.rect.height),
            Color(scrim.r, scrim.g, scrim.b, scrim.a),
        )


class OverlayScene(Scene):
    """A scene pushed over the garden and closed by a key or a button."""

    def __init__(
        self,
        name: str,
        event_dispatcher: EventDispatcher,
        close_keys: tuple[int, ...],
    ) -> None:
        """Initialize the overlay.

        Args:
            name: The scene's registered name.
            event_dispatcher: The game's dispatcher.
            close_keys: Keys that close it (besides its own Close button).
        """
        super().__init__(name, event_dispatcher)
        self._close_keys = close_keys
        self._close_action = f"{name}_close"
        self._armed = False

    def on_enter(self) -> None:
        """Bind the close keys, listen for them, and build the overlay."""
        input_manager = self.container.get(InputManager)
        input_manager.register_action(self._close_action, ActionType.PRESS)
        for key in self._close_keys:
            input_manager.bind_input(InputDevice.KEYBOARD, key, self._close_action)
        self.event_dispatcher.subscribe(OnActionEvent, self._on_action)
        self._build()

    def _build(self) -> None:
        """Put this overlay's widgets on `UILayer.OVERLAY`."""
        raise NotImplementedError

    def on_exit(self) -> None:
        """Stop listening -- a reopened overlay is a new scene with its own handler."""
        self.event_dispatcher.unsubscribe(OnActionEvent, self._on_action)

    def _on_action(self, event: OnActionEvent) -> None:
        if self._armed and event.action_name == self._close_action and event.value > 0:
            self._close()

    def _close(self) -> None:
        """Hand control back to the garden. A no-op unless this is the top scene."""
        scene_manager = self.container.get(SceneManager)
        if scene_manager.current_scene is not self:
            return
        self.container.get(UIManager).clear(UILayer.OVERLAY)
        scene_manager.pop_scene()

    def update(self, dt: float) -> None:
        """Arm the close keys once the frame that opened the overlay is over."""
        self._armed = True

    def render(self, world_renderer: IRenderer, ui_renderer: UIRenderer) -> None:
        """Draw nothing: the garden underneath is still rendering."""
