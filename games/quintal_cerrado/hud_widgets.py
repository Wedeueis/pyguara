"""The garden HUD's own widgets: rounded cards, and the icon tool dock.

The design system's `BevelPanel`/`BevelButton` are square, opaque and
text-first. This screen wants the opposite -- soft translucent cards, and
tools a player recognises by shape before reading a word -- so these are
thin subclasses of the *stock* `Panel` and `Button`: layout, hit testing,
focus and `on_click` stay the engine's, and only `render` is new.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from games.quintal_cerrado import layout
from games.quintal_cerrado.icons import DIM_TARGET, draw_icon
from pyguara.common.types import Color, Rect, Vector2
from pyguara.graphics.protocols import UIRenderer
from pyguara.ui.components.button import Button
from pyguara.ui.components.panel import Panel
from pyguara.ui.design_system.skin import bevel_edges
from pyguara.ui.design_system.tokens import Sand, Wood
from pyguara.ui.types import UIElementState

CARD_FILL = Color(35, 28, 38, 224)
CARD_EDGE = Wood.C400.lerp(DIM_TARGET, 0.35)
CARD_SHADOW = Color(0, 0, 0, 90)
CARD_RADIUS = 8
TITLE_COLOR = Sand.C200
TEXT_COLOR = Sand.C100
MUTED_TEXT = Sand.C100.lerp(DIM_TARGET, 0.45)

SLOT_FILL = Color(58, 44, 50)
SLOT_HOVER = Color(74, 56, 58)
SLOT_ACTIVE = Wood.C700.lerp(Sand.C500, 0.2)
SLOT_EDGE = Wood.C400.lerp(DIM_TARGET, 0.5)
SLOT_RADIUS = 6
GLOW = Sand.C500
BADGE_FILL = Color(24, 18, 26)
UNAFFORDABLE_DIM = 0.6
"""How far an unaffordable slot's icon and label fade into the card."""


def draw_card(renderer: UIRenderer, rect: Rect, *, radius: int = CARD_RADIUS) -> None:
    """Draw a HUD card: a soft drop shadow, a translucent face, a warm edge.

    Args:
        renderer: The UI renderer to draw through.
        rect: The card's bounds.
        radius: Corner radius.
    """
    renderer.draw_rect(
        Rect(rect.x + 2, rect.y + 3, rect.width, rect.height),
        CARD_SHADOW,
        border_radius=radius,
    )
    renderer.draw_rect(rect, CARD_FILL, border_radius=radius)
    renderer.draw_rect(rect, CARD_EDGE, width=1, border_radius=radius)


def draw_badge(
    renderer: UIRenderer,
    text: str,
    position: Vector2,
    *,
    icon_id: str | None = None,
    color: Color = MUTED_TEXT,
    size: int = 10,
) -> Rect:
    """Draw a small dark pill holding `text`, and an icon before it.

    Args:
        renderer: The UI renderer to draw through.
        text: The badge text.
        position: Top-left corner.
        icon_id: An `icons.ICONS` key to lead with, or None.
        color: The text colour.
        size: The font size.

    Returns:
        The badge's rect, so a caller can right-align it after the fact.
    """
    text_w, text_h = renderer.get_text_size(text, size)
    icon_w = text_h if icon_id else 0
    gap = 3 if icon_id else 0
    rect = Rect(int(position.x), int(position.y), text_w + icon_w + gap + 8, text_h + 2)
    renderer.draw_rect(rect, BADGE_FILL, border_radius=3)
    if icon_id:
        draw_icon(renderer, icon_id, Rect(rect.x + 3, rect.y + 1, icon_w, text_h))
    renderer.draw_text(
        text, Vector2(rect.x + 4 + icon_w + gap, rect.y + 1), color, size
    )
    return rect


class CardPanel(Panel):
    """A `Panel` drawn as a HUD card, with an optional icon-and-title header.

    Children keep the absolute positions they were given, exactly as they
    would in a stock `Panel`.
    """

    def __init__(
        self,
        position: Vector2,
        size: Vector2,
        *,
        title: str = "",
        icon_id: str | None = None,
    ) -> None:
        """Initialize the card.

        Args:
            position: Top-left corner.
            size: Width and height.
            title: A header drawn along the top edge, or "" for none.
            icon_id: An icon drawn before the title.
        """
        super().__init__(position, size)
        self.title = title
        self.icon_id = icon_id

    def render(self, renderer: UIRenderer) -> None:
        """Draw the card, its header, then its children."""
        draw_card(renderer, self.rect)
        x = self.rect.x + 10
        if self.icon_id:
            draw_icon(renderer, self.icon_id, Rect(x, self.rect.y + 5, 15, 15))
            x += 19
        if self.title:
            renderer.draw_text(self.title, Vector2(x, self.rect.y + 6), TITLE_COLOR, 12)
        for child in self.children:
            if child.visible:
                child.render(renderer)


class ToolSlot(Button):
    """One dock slot: an icon, a name, a hotkey badge, and maybe a cost.

    Attributes:
        tool_id: The scene's id for the tool this slot selects.
        icon_id: The `icons.ICONS` key drawn on the face.
        key_label: The hotkey, shown in a corner badge.
        active: The selected tool -- drawn with an ochre glow.
        affordable: False fades the slot, when its cost cannot be paid.
        badge: Cost or stock text for the top-left corner, or "" for none.
    """

    def __init__(
        self,
        tool_id: str,
        label: str,
        key_label: str,
        *,
        icon_id: str | None = None,
        position: Vector2 = Vector2(0, 0),
        size: Vector2 = layout.SLOT_SIZE,
    ) -> None:
        """Initialize the slot.

        Args:
            tool_id: The tool this slot selects.
            label: The name under the icon.
            key_label: The hotkey's name, e.g. "T" or "Esc".
            icon_id: The icon; defaults to `tool_id`, which is what every
                tool in `icons.ICONS` is keyed by.
            position: Top-left corner.
            size: Width and height.
        """
        super().__init__(label, position, size)
        self.tool_id = tool_id
        self.icon_id = icon_id or tool_id
        self.key_label = key_label
        self.active = False
        self.affordable = True
        self.badge = ""

    def render(self, renderer: UIRenderer) -> None:
        """Draw the slot for its current state."""
        pressed = self.state == UIElementState.PRESSED
        face = Rect(
            self.rect.x,
            self.rect.y + (1 if pressed else 0),
            self.rect.width,
            self.rect.height,
        )
        if self.active:
            fill = SLOT_ACTIVE
        elif self.state == UIElementState.HOVERED:
            fill = SLOT_HOVER
        else:
            fill = SLOT_FILL

        if self.active:
            renderer.draw_rect(
                Rect(face.x - 3, face.y - 3, face.width + 6, face.height + 6),
                GLOW,
                width=2,
                border_radius=SLOT_RADIUS + 3,
            )
        renderer.draw_rect(face, fill, border_radius=SLOT_RADIUS)
        lit, _ = bevel_edges(fill, pressed=pressed)
        renderer.draw_line(
            Vector2(face.x + SLOT_RADIUS, face.y + 1),
            Vector2(face.right - SLOT_RADIUS, face.y + 1),
            lit,
        )
        renderer.draw_rect(face, self._edge_color(), width=1, border_radius=SLOT_RADIUS)

        dim = 0.0 if self.affordable else UNAFFORDABLE_DIM
        draw_icon(
            renderer,
            self.icon_id,
            Rect(face.x + 12, face.y + 18, face.width - 24, face.height - 38),
            dim=dim,
        )
        text_color = TEXT_COLOR.lerp(DIM_TARGET, dim)
        text_w, _ = renderer.get_text_size(self.text, 11)
        renderer.draw_text(
            self.text,
            Vector2(face.x + (face.width - text_w) // 2, face.bottom - 18),
            text_color,
            11,
        )

        key_w, _ = renderer.get_text_size(self.key_label, 10)
        draw_badge(
            renderer, self.key_label, Vector2(face.right - key_w - 9, face.y + 3)
        )
        if self.badge:
            draw_badge(
                renderer,
                self.badge,
                Vector2(face.x + 3, face.y + 3),
                icon_id="seed",
                color=Sand.C200.lerp(DIM_TARGET, dim),
            )

    def _edge_color(self) -> Color:
        if self.state == UIElementState.FOCUSED and self.focus_visible:
            return self.theme.colors.focus_ring
        return GLOW if self.active else SLOT_EDGE


@dataclass(frozen=True)
class SlotSpec:
    """What one dock slot shows: its tool, its name and its hotkey."""

    tool_id: str
    label: str
    key_label: str


@dataclass(frozen=True)
class DockGroup:
    """One titled card of slots in the dock."""

    title: str
    icon_id: str
    slots: Sequence[SlotSpec]


class ToolDock:
    """The bottom dock: titled card groups of `ToolSlot`s, centred in a row.

    Attributes:
        groups: One `CardPanel` per group, in left-to-right order -- add
            each to a `UIManager` layer.
        slots: Every slot, by tool id.
    """

    def __init__(self, groups: Sequence[DockGroup], screen_width: int) -> None:
        """Lay the groups out along `layout.DOCK_Y`.

        Args:
            groups: The groups, left to right.
            screen_width: The width to centre the dock across.
        """
        widths = [layout.group_width(len(group.slots)) for group in groups]
        total = sum(widths) + layout.GAP * (len(groups) - 1)
        x = (screen_width - total) // 2
        y = layout.DOCK_Y

        self.groups: list[CardPanel] = []
        self.slots: dict[str, ToolSlot] = {}
        for group, width in zip(groups, widths, strict=True):
            card = CardPanel(
                Vector2(x, y),
                Vector2(width, layout.DOCK_HEIGHT),
                title=group.title,
                icon_id=group.icon_id,
            )
            slot_x = x + layout.DOCK_PADDING
            slot_y = y + layout.DOCK_HEADER + layout.DOCK_PADDING // 2
            for spec in group.slots:
                slot = ToolSlot(
                    spec.tool_id,
                    spec.label,
                    spec.key_label,
                    position=Vector2(slot_x, slot_y),
                )
                card.add_child(slot)
                self.slots[spec.tool_id] = slot
                slot_x += int(layout.SLOT_SIZE.x) + layout.SLOT_SPACING
            self.groups.append(card)
            x += width + layout.GAP
