"""The 1-of-3 pick: three cards, chosen with the keyboard.

**This is E8's focus ring driving a real menu**, which is what that
feature was built for. The cards are genuine `UIElement`s in a
`BoxContainer`, added to `UIManager`, so Tab/Shift-Tab and the arrow keys
traverse them and the ring's ordering rules apply unchanged.

They draw nothing of their own, though, and that is deliberate rather
than lazy. `UIRenderer` composites *after* the final blit, and
`tools/agent_view.py` captures the buffer the final blit reads -- so
anything a widget draws itself is invisible to every capture this
repository can take (#162). A card the player picks a run-defining
upgrade from is the last thing to ship unlooked-at. So the elements own
layout and focus, and `scenes.py` draws them onto the finished frame in
the clearing's own palette, the same place the HUD goes.

If #162 is fixed, `CardElement.render()` is where the widget's own
drawing would go, and the scene's hand-drawing is what would come out.
"""

from __future__ import annotations

from dataclasses import dataclass

from games.tamandua_murundus.upgrades import Card
from pyguara.common.types import Rect, Vector2
from pyguara.graphics.protocols import UIRenderer
from pyguara.ui.base import UIElement

CARD_WIDTH = 230
CARD_HEIGHT = 150
CARD_SPACING = 26


class CardElement(UIElement):
    """One upgrade card: a focusable box that draws nothing itself."""

    def __init__(self, card: Card, position: Vector2) -> None:
        """Create a focusable card at a fixed position.

        Args:
            card: The upgrade this card offers.
            position: Top-left corner, in screen space.
        """
        super().__init__(position, Vector2(CARD_WIDTH, CARD_HEIGHT))
        self.focusable = True
        self.card = card

    def render(self, renderer: UIRenderer) -> None:
        """Draw nothing -- see the module docstring.

        `scenes.py` draws these onto the finished frame, where a capture
        can see them.
        """
        return


@dataclass(slots=True)
class CardView:
    """What the scene needs to draw one card.

    A plain value so the drawing code takes no `UIElement` and no
    `UIManager` -- which is what lets the card layout be tested without
    either.
    """

    title: str
    blurb: str
    bounds: Rect
    focused: bool
    card_key: str


def layout_cards(
    cards: list[Card], screen_width: int, screen_height: int
) -> list[Vector2]:
    """Position `cards` in a centred row.

    A row, not a grid: three across is what a `BoxContainer` already
    does, and #151 was explicit about not building a grid container
    speculatively.

    Args:
        cards: The offered upgrades. Fewer than three is normal late in a
            run, when the pool is nearly exhausted.
        screen_width: Window width.
        screen_height: Window height.

    Returns:
        One top-left corner per card, in the same order.
    """
    count = len(cards)
    if count == 0:
        return []

    span = count * CARD_WIDTH + (count - 1) * CARD_SPACING
    left = (screen_width - span) / 2.0
    top = (screen_height - CARD_HEIGHT) / 2.0
    return [
        Vector2(left + index * (CARD_WIDTH + CARD_SPACING), top)
        for index in range(count)
    ]


def card_views(
    elements: list[CardElement], focused: UIElement | None
) -> list[CardView]:
    """Resolve the live elements into plain values for drawing.

    Args:
        elements: The card elements currently on screen.
        focused: Whatever `UIManager` currently has focus on.

    Returns:
        One view per element, in order.
    """
    return [
        CardView(
            title=element.card.title,
            blurb=element.card.blurb,
            bounds=Rect(
                element.rect.x, element.rect.y, element.rect.width, element.rect.height
            ),
            focused=element is focused,
            card_key=element.card.upgrade.key,
        )
        for element in elements
    ]
