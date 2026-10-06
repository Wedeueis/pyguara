"""Base Widget class for interactive components."""

from pyguara.common.types import Color, Rect
from pyguara.graphics.protocols import UIRenderer
from pyguara.ui.base import UIElement
from pyguara.ui.types import UIElementState


class Widget(UIElement):
    """Base class for styled UI components.

    Adds helper methods to resolve theme colors based on state.
    """

    casts_shadow: bool = True
    """Whether `draw_shadow()` does anything for this class.

    Set `False` by a widget that draws its own shadow, so it does not get a
    second one from the base implementation. `design_system.BevelPanel` is
    the case that forced this: it draws a stamp shadow and *then* calls
    `Panel.render()`, so it rendered two -- and the generic one ignored its
    own per-instance `shadow` flag, breaking the opt-out.
    """

    def draw_shadow(self, renderer: UIRenderer, rect: Rect | None = None) -> None:
        """Draw this widget's drop shadow, if the theme asks for one.

        A no-op unless `theme.shadows.enabled`, which every preset leaves
        off -- so a widget calling this costs nothing until a theme opts in.
        Call it *before* drawing the widget's own face, since the shadow
        sits underneath.

        Hard-edged, matching `design_system.skin.draw_stamp_shadow`: a
        blurred shadow is not reachable through the UI renderer's
        primitives, so `ShadowScheme.blur` is **not** honoured here. That is
        recorded on the field itself rather than quietly ignored.

        Args:
            renderer: The UI renderer to draw through.
            rect: Bounds to cast from. Defaults to this widget's own rect,
                which is what a widget whose face fills its bounds wants.
        """
        shadows = self.theme.shadows
        if not (self.casts_shadow and shadows.enabled):
            return
        bounds = self.rect if rect is None else rect
        renderer.draw_rect(
            Rect(
                bounds.x + shadows.offset_x,
                bounds.y + shadows.offset_y,
                bounds.width,
                bounds.height,
            ),
            shadows.color,
            border_radius=self.theme.borders.radius,
        )

    def get_state_color(self, base_color: Color) -> Color:
        """Calculate the final color based on the current state (Hover/Press)."""
        if self.state == UIElementState.DISABLED:
            # Simple dimming for disabled state
            return Color(
                base_color.r // 2, base_color.g // 2, base_color.b // 2, base_color.a
            )

        # In a real engine, you might blend colors here.
        # For now, we return specific theme overrides if defined,
        # or just the base color.
        return base_color
