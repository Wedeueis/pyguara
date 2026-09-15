"""The components the Cerrado look needs beyond what a theme can say.

Deliberately two classes, not a parallel widget tree. A checkbox, slider,
progress bar or text field styled by this design system is the *stock*
component reading Cerrado colours out of the theme -- `set_theme
(cerrado_dusk())` and they are skinned, with their layout, focus traversal
and both backends intact. Only the bevel needed code, because a raised
edge is geometry rather than a colour.

`ButtonSkin` exists for the same reason: the brand has button colourways --
the sage and wood variants -- that are not "the theme's primary action" and
so have nowhere to live in a theme that describes one action colour.
"""

from __future__ import annotations

from dataclasses import dataclass

from pyguara.common.types import Color, Rect, Vector2
from pyguara.graphics.protocols import UIRenderer
from pyguara.ui.components.button import Button
from pyguara.ui.components.panel import Panel
from pyguara.ui.design_system.skin import draw_bevel, draw_stamp_shadow
from pyguara.ui.design_system.tokens import Guara, Rock, Sand, Verdant, Wood
from pyguara.ui.types import UIElementState


@dataclass(frozen=True)
class ButtonSkin:
    """A button colourway that is not the theme's primary action.

    Attributes:
        fill: Resting background.
        hover: Background under the cursor.
        press: Background while held. Per-skin on purpose -- a shared
            press colour turns a green button orange on click.
        edge: Border colour.
        text: Label colour.
    """

    fill: Color
    hover: Color
    press: Color
    edge: Color
    text: Color


class Skins:
    """The brand's button colourways."""

    SAGE = ButtonSkin(
        fill=Verdant.COLONIAL_500,
        hover=Color.from_hex("#4c835c"),
        press=Verdant.COLONIAL_700,
        edge=Verdant.COLONIAL_700,
        text=Verdant.SAGE_100,
    )

    WOOD = ButtonSkin(
        fill=Wood.C500,
        hover=Wood.C400,
        press=Wood.C700,
        edge=Rock.C600,
        text=Sand.C100,
    )

    GUARA = ButtonSkin(
        fill=Guara.C500,
        hover=Guara.C400,
        press=Guara.C600,
        edge=Guara.C700,
        text=Wood.INK_900,
    )


class BevelButton(Button):
    """A button with a raised edge that inverts when pressed.

    Everything else -- sizing, focus, hit testing, the click callback --
    is the stock `Button`. Without a `skin` it wears the active theme's
    action colours, so it stays correct under any theme rather than only
    the Cerrado ones.

    Attributes:
        skin: A brand colourway, or None to follow the theme.
        uppercase: Render the label upper-cased. Applied at render time,
            so `self.text` keeps what the caller passed.
        press_offset: Pixels the face drops when held.
    """

    def __init__(
        self,
        text: str,
        position: Vector2,
        size: Vector2 = Vector2(120, 40),
        *,
        skin: ButtonSkin | None = None,
        uppercase: bool = True,
        press_offset: int = 1,
    ) -> None:
        """Initialize the button.

        Args:
            text: The label.
            position: Top-left corner.
            size: Width and height.
            skin: A brand colourway, or None to read the theme.
            uppercase: Whether to upper-case the label when drawing.
            press_offset: Pixels the face drops while held.
        """
        super().__init__(text, position, size)
        self.skin = skin
        self.uppercase = uppercase
        self.press_offset = press_offset

    def fill_color(self) -> Color:
        """The background for the current state, honouring `skin`.

        Returns:
            The fill colour.
        """
        if self.skin is None or self.state == UIElementState.DISABLED:
            return super().fill_color()
        if self.state == UIElementState.PRESSED:
            return self.skin.press
        if self.state == UIElementState.HOVERED:
            return self.skin.hover
        return self.skin.fill

    def text_color(self) -> Color:
        """The label colour, honouring `skin`.

        Returns:
            The text colour.
        """
        if self.skin is None or self.state == UIElementState.DISABLED:
            return super().text_color()
        return self.skin.text

    def border_color(self) -> Color:
        """The edge colour, honouring `skin` unless focused.

        Returns:
            The focus ring when focused, otherwise the skin's or theme's
            edge.
        """
        if self.state == UIElementState.FOCUSED:
            return self.theme.colors.focus_ring
        if self.skin is None:
            return super().border_color()
        return self.skin.edge

    def render(self, renderer: UIRenderer) -> None:
        """Render the button: shadow, face, bevel, then label."""
        pressed = self.state == UIElementState.PRESSED
        face = self.rect
        if pressed and self.press_offset:
            face = Rect(
                self.rect.x,
                self.rect.y + self.press_offset,
                self.rect.width,
                self.rect.height,
            )

        # Raised, and therefore casting, only while it is actually
        # pressable and not already pushed in. A disabled button that
        # still threw a shadow would be claiming a depth it does not have.
        raised = not pressed and self.state != UIElementState.DISABLED
        shadows = self.theme.shadows
        if raised and shadows.enabled:
            draw_stamp_shadow(
                renderer, face, shadows.color, offset=max(1, shadows.offset_y)
            )

        fill = self.fill_color()
        renderer.draw_rect(face, fill, width=0)
        renderer.draw_rect(face, self.border_color(), width=self.theme.borders.width)

        if self.state != UIElementState.DISABLED:
            draw_bevel(renderer, face, fill, pressed=pressed)

        self._render_label_in(renderer, face)

    def _render_label_in(self, renderer: UIRenderer, face: Rect) -> None:
        """Draw the label centred in `face` rather than in `self.rect`.

        Args:
            renderer: The UI renderer to draw through.
            face: The (possibly offset) rectangle actually drawn.
        """
        label = self.text.upper() if self.uppercase else self.text
        size = self.theme.fonts.size_normal
        w, h = renderer.get_text_size(label, size)

        renderer.draw_text(
            label,
            Vector2(
                face.x + (face.width - w) // 2,
                face.y + (face.height - h) // 2,
            ),
            self.text_color(),
        )


class BevelPanel(Panel):
    """A panel with a raised edge, and optionally a stamp shadow.

    Attributes:
        bevel: Whether to draw the raised edge.
        shadow: Whether to draw the stamp shadow. Off by default -- a
            panel is usually the thing other elements sit on, and a
            shadow under every one of them reads as noise.
    """

    def __init__(
        self,
        position: Vector2,
        size: Vector2,
        color: Color | None = None,
        border_width: int = 1,
        *,
        bevel: bool = True,
        shadow: bool = False,
    ) -> None:
        """Initialize the panel.

        Args:
            position: Top-left corner.
            size: Width and height.
            color: Fill colour, or None for the theme's card surface.
            border_width: Edge thickness.
            bevel: Draw the raised edge.
            shadow: Draw the stamp shadow behind the panel.
        """
        super().__init__(position, size, color, border_width)
        self.bevel = bevel
        self.shadow = shadow

    def render(self, renderer: UIRenderer) -> None:
        """Render the panel, with its shadow and bevel."""
        shadows = self.theme.shadows
        if self.shadow and shadows.enabled:
            draw_stamp_shadow(
                renderer, self.rect, shadows.color, offset=max(1, shadows.offset_y)
            )

        super().render(renderer)

        if self.bevel:
            fill = self._color or self.theme.colors.surface_card
            draw_bevel(renderer, self.rect, fill)
