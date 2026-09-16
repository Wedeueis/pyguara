"""The pause menu and the options panel, overlaid on whatever is behind.

Both are pushed onto the scene stack with `pause_below=True`, which does
exactly the right thing: `SceneManager` gates *updates* on that flag and
keeps rendering every scene under it, so the frozen game shows through the
scrim. Neither menu has to know what it was pushed over.

Both live on `UILayer.OVERLAY`, which is what keeps them above the HUD and,
more usefully, what keeps the HUD out of the focus ring while they are up:
the ring is scoped to the topmost layer that has anything focusable, so Tab
inside the options panel cycles the options and nothing else.
"""

from __future__ import annotations

from collections.abc import Callable

from games.guara_falcao.events import DebugCollidersToggled
from pyguara.audio.audio_system import IAudioSystem
from pyguara.common.types import Color, Rect, Vector2
from pyguara.di.container import DIContainer
from pyguara.events.dispatcher import EventDispatcher
from pyguara.graphics.protocols import IRenderer, UIRenderer
from pyguara.graphics.vfx.effects.bloom import BloomEffect
from pyguara.graphics.window import Window
from pyguara.scene.base import Scene
from pyguara.scene.manager import SceneManager
from pyguara.ui.base import UIElement
from pyguara.ui.components.checkbox import Checkbox
from pyguara.ui.components.slider import Slider
from pyguara.ui.components.text import Label
from pyguara.ui.design_system import (
    BevelButton,
    BevelPanel,
    Skins,
    cerrado_day,
    cerrado_dusk,
)
from pyguara.ui.layout import BoxContainer
from pyguara.ui.manager import UIManager
from pyguara.ui.theme import set_theme
from pyguara.ui.types import LayoutAlignment, LayoutDirection, UILayer

MENU_WIDTH = 360
OPTIONS_WIDTH = 520
ROW_LABEL_WIDTH = 150


class Scrim(UIElement):
    """A full-screen wash over everything behind the menu.

    The colour is the theme's `surface_scrim`, which carries alpha -- so
    this is also the one element in the demo that proves the UI renderers
    blend rather than replace. Drawn at full screen size rather than with
    fill constraints so it covers the frame even before a layout pass.
    """

    def __init__(self, width: int, height: int, *, strength: float = 1.0) -> None:
        """Initialize the scrim.

        Args:
            width: Screen width.
            height: Screen height.
            strength: Scale on the theme's scrim alpha. A modal wants the
                full weight; a title screen wants a fraction of it, since
                there is nothing behind it the reader has to stop looking
                at -- only a backdrop to settle down.
        """
        super().__init__(Vector2(0, 0), Vector2(width, height))
        self.strength = strength

    def render(self, renderer: UIRenderer) -> None:
        """Wash the frame."""
        scrim = self.theme.colors.surface_scrim
        renderer.draw_rect(
            Rect(0, 0, self.rect.width, self.rect.height),
            Color(scrim.r, scrim.g, scrim.b, int(scrim.a * self.strength)),
        )


class Rule(UIElement):
    """A one-pixel line under an options row."""

    def __init__(self, width: int) -> None:
        """Initialize the rule.

        Args:
            width: How wide to draw.
        """
        super().__init__(Vector2(0, 0), Vector2(width, 1))

    def render(self, renderer: UIRenderer) -> None:
        """Draw the line."""
        renderer.draw_rect(self.rect, self.theme.colors.edge_subtle)


def _heading(text: str) -> Label:
    """A section heading inside a menu panel.

    Args:
        text: The heading.

    Returns:
        A label at heading size, taking its colour from the theme.
    """
    return Label(text, Vector2(0, 0), font_size=14)


def _row(label_text: str, control: UIElement, width: int) -> BoxContainer:
    """One options row: a label on the left, a control on the right.

    A horizontal `BoxContainer` rather than a grid, because the engine has
    no grid layout and two columns do not need one.

    Args:
        label_text: The row's name.
        control: The widget on the right.
        width: Row width.

    Returns:
        The row container.
    """
    row = BoxContainer(
        Vector2(0, 0),
        Vector2(width, 28),
        direction=LayoutDirection.HORIZONTAL,
        alignment=LayoutAlignment.START,
        spacing=12,
    )
    name = Label(label_text, Vector2(0, 0), font_size=12)
    row.add_child(name)
    row.add_child(control)
    return row


class PauseScene(Scene):
    """The pause menu, over a frozen game."""

    def __init__(
        self, event_dispatcher: EventDispatcher, width: int, height: int
    ) -> None:
        """Initialize the scene.

        Args:
            event_dispatcher: The engine's dispatcher.
            width: Screen width.
            height: Screen height.
        """
        super().__init__("PauseScene", event_dispatcher)
        self._width = width
        self._height = height

    def on_enter(self) -> None:
        """Build the menu."""
        self._build()

    def on_resume(self) -> None:
        """Rebuild after the options panel above it closes."""
        self._build()

    def _build(self) -> None:
        """Put the scrim, the panel and the buttons on the overlay layer."""
        ui_manager = self.container.get(UIManager)
        ui_manager.clear(UILayer.OVERLAY)
        ui_manager.add_element(Scrim(self._width, self._height), UILayer.OVERLAY)

        panel = BevelPanel(
            Vector2((self._width - MENU_WIDTH) // 2, self._height // 2 - 160),
            Vector2(MENU_WIDTH, 300),
            border_width=3,
            shadow=True,
        )
        ui_manager.add_element(panel, UILayer.OVERLAY)

        title = Label(
            "PAUSED", Vector2(panel.rect.x + 28, panel.rect.y + 24), font_size=24
        )
        ui_manager.add_element(title, UILayer.OVERLAY)

        column = BoxContainer(
            Vector2(panel.rect.x + 40, panel.rect.y + 80),
            Vector2(MENU_WIDTH - 80, 200),
            spacing=12,
        )
        for text, skin, handler in (
            ("Resume", Skins.SAGE, self._resume),
            ("Options", Skins.WOOD, self._options),
            ("Quit to Title", Skins.WOOD, self._quit_to_title),
        ):
            button = BevelButton(
                text, Vector2(0, 0), Vector2(MENU_WIDTH - 80, 44), skin=skin
            )
            button.on_click = handler
            column.add_child(button)
        ui_manager.add_element(column, UILayer.OVERLAY)

        # Start the ring somewhere, so the menu is usable without a mouse.
        ui_manager.set_focus(column.children[0])

    def _resume(self, _element: UIElement) -> None:
        """Close the menu and hand control back to the game."""
        self.container.get(UIManager).clear(UILayer.OVERLAY)
        self.container.get(SceneManager).pop_scene()

    def _options(self, _element: UIElement) -> None:
        """Open the options panel over this menu."""
        scene_manager = self.container.get(SceneManager)
        scene_manager.register(
            OptionsScene(self.event_dispatcher, self._width, self._height)
        )
        scene_manager.push_scene("OptionsScene")

    def _quit_to_title(self, _element: UIElement) -> None:
        """Unwind back to the title screen."""
        ui_manager = self.container.get(UIManager)
        ui_manager.clear()
        scene_manager = self.container.get(SceneManager)
        scene_manager.pop_scene()  # this menu
        scene_manager.pop_scene()  # the game under it

    def on_exit(self) -> None:
        """Take the menu off the overlay layer."""
        self.container.get(UIManager).clear(UILayer.OVERLAY)

    def update(self, dt: float) -> None:
        """Nothing ticks in a pause menu."""

    def render(self, world_renderer: IRenderer, ui_renderer: UIRenderer) -> None:
        """Draw nothing: the scene under this one is still rendering."""


class OptionsScene(Scene):
    """The options panel, over the title screen or the pause menu."""

    def __init__(
        self, event_dispatcher: EventDispatcher, width: int, height: int
    ) -> None:
        """Initialize the scene.

        Args:
            event_dispatcher: The engine's dispatcher.
            width: Screen width.
            height: Screen height.
        """
        super().__init__("OptionsScene", event_dispatcher)
        self._width = width
        self._height = height
        self._rows: list[UIElement] = []
        self._on_close: Callable[[], None] | None = None

    def on_enter(self) -> None:
        """Build the panel."""
        self._build()

    def on_resume(self) -> None:
        """Rebuild if something was pushed over this and then closed."""
        self._build()

    def _build(self) -> None:
        """Assemble every section, row and control."""
        ui_manager = self.container.get(UIManager)
        ui_manager.clear(UILayer.OVERLAY)
        ui_manager.add_element(Scrim(self._width, self._height), UILayer.OVERLAY)

        panel_x = (self._width - OPTIONS_WIDTH) // 2
        panel_y = max(24, self._height // 2 - 230)
        panel = BevelPanel(
            Vector2(panel_x, panel_y),
            Vector2(OPTIONS_WIDTH, 460),
            border_width=3,
            shadow=True,
        )
        ui_manager.add_element(panel, UILayer.OVERLAY)

        title = Label("OPTIONS", Vector2(panel_x + 28, panel_y + 22), font_size=20)
        ui_manager.add_element(title, UILayer.OVERLAY)

        # STRETCH, so every heading, row and rule spans the panel and its
        # contents start at the left edge. A BoxContainer centres a child
        # that does not stretch, which floats a section heading into the
        # middle of the panel and reads as a title rather than a label.
        column = BoxContainer(
            Vector2(panel_x + 28, panel_y + 62),
            Vector2(OPTIONS_WIDTH - 56, 340),
            alignment=LayoutAlignment.STRETCH,
            spacing=6,
        )

        audio = self.container.get(IAudioSystem)

        column.add_child(_heading("AUDIO"))
        for name, getter, setter in (
            ("Master", audio.get_master_volume, audio.set_master_volume),
            ("Music", audio.get_music_volume, audio.set_music_volume),
            ("Effects", audio.get_sfx_volume, audio.set_sfx_volume),
        ):
            slider = Slider(Vector2(0, 0), width=250, show_value=True)
            slider.value = float(getter())
            slider.on_change = setter
            column.add_child(_row(name, slider, OPTIONS_WIDTH - 56))
            column.add_child(Rule(OPTIONS_WIDTH - 56))

        # Every row below changes something you can see. A settings screen
        # full of toggles that set a flag nothing reads is the easiest
        # thing in the world to mock up and the least worth shipping.
        column.add_child(_heading("DISPLAY"))
        theme_box = Checkbox("Day", Vector2(0, 0))
        theme_box.on_change = self._on_theme_changed
        column.add_child(_row("Cerrado theme", theme_box, OPTIONS_WIDTH - 56))
        column.add_child(Rule(OPTIONS_WIDTH - 56))

        bloom_box = Checkbox("On", Vector2(0, 0), checked=self._bloom_enabled())
        bloom_box.on_change = self._on_bloom_changed
        column.add_child(_row("Bloom", bloom_box, OPTIONS_WIDTH - 56))
        column.add_child(Rule(OPTIONS_WIDTH - 56))

        column.add_child(_heading("DEVELOPER"))
        collider_box = Checkbox("Off", Vector2(0, 0))
        collider_box.on_change = self._on_colliders_changed
        column.add_child(_row("Show colliders", collider_box, OPTIONS_WIDTH - 56))

        ui_manager.add_element(column, UILayer.OVERLAY)

        buttons = BoxContainer(
            Vector2(panel_x + 28, panel_y + 400),
            Vector2(OPTIONS_WIDTH - 56, 48),
            direction=LayoutDirection.HORIZONTAL,
            spacing=12,
        )
        back = BevelButton("Back", Vector2(0, 0), Vector2(150, 40), skin=Skins.SAGE)
        back.on_click = self._close
        defaults = BevelButton(
            "Defaults", Vector2(0, 0), Vector2(150, 40), skin=Skins.GHOST
        )
        defaults.on_click = self._restore_defaults
        buttons.add_child(back)
        buttons.add_child(defaults)
        ui_manager.add_element(buttons, UILayer.OVERLAY)

        self._back_button = back
        ui_manager.set_focus(back)

    def _on_theme_changed(self, day: bool) -> None:
        """Swap the whole UI between the two Cerrado themes.

        Live re-skinning is the design system demonstrating itself: every
        element reads `get_theme()` at render time, so one call re-colours
        the panel the checkbox is sitting in.

        Args:
            day: Whether the light theme was chosen.
        """
        set_theme(cerrado_day() if day else cerrado_dusk())

    def _bloom_enabled(self) -> bool:
        """Whether the bloom pass is currently on.

        Returns:
            True when bloom is enabled, and when there is no bloom effect
            to ask -- a headless build of this scene has no GL pipeline.
        """
        try:
            return bool(self.container.get(BloomEffect).enabled)
        except Exception:
            return True

    def _on_bloom_changed(self, enabled: bool) -> None:
        """Switch the bloom pass, which changes the frame immediately.

        Args:
            enabled: Whether to bloom.
        """
        try:
            self.container.get(BloomEffect).enabled = enabled
        except Exception:
            return

    def _on_colliders_changed(self, shown: bool) -> None:
        """Ask whatever is playing to draw its collider outlines.

        Dispatched rather than called: this panel is pushed over the game
        and holds no reference to it, and walking the scene stack to find
        one would couple a menu to what it was opened from.

        Args:
            shown: Whether to draw collider outlines.
        """
        self.event_dispatcher.dispatch(DebugCollidersToggled(shown=shown))

    def _restore_defaults(self, _element: UIElement) -> None:
        """Put the audio mix and the theme back, then rebuild the panel."""
        audio = self.container.get(IAudioSystem)
        audio.set_master_volume(1.0)
        audio.set_music_volume(1.0)
        audio.set_sfx_volume(1.0)
        set_theme(cerrado_dusk())
        self.event_dispatcher.dispatch(DebugCollidersToggled(shown=False))
        self._build()

    def _close(self, _element: UIElement) -> None:
        """Return to whichever scene pushed this one."""
        self.container.get(UIManager).clear(UILayer.OVERLAY)
        self.container.get(SceneManager).pop_scene()

    def on_exit(self) -> None:
        """Take the panel off the overlay layer."""
        self.container.get(UIManager).clear(UILayer.OVERLAY)

    def update(self, dt: float) -> None:
        """Nothing ticks in an options panel."""

    def render(self, world_renderer: IRenderer, ui_renderer: UIRenderer) -> None:
        """Draw nothing: the scene under this one is still rendering."""


def quit_game(container: DIContainer) -> None:
    """Leave the demo.

    Closes the window rather than `sys.exit()`, so `Application.run()`
    falls out of its loop and runs its normal shutdown/teardown.
    """
    container.get(Window).close()
