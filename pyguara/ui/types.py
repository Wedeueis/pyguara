"""UI domain definitions and constants."""

from __future__ import annotations

from dataclasses import dataclass, field, fields
from enum import Enum, IntEnum, auto

from pyguara.common.types import Color  # FIX: Import Color

# --- Enums ---


class UIElementState(Enum):
    """Visual state of a UI component."""

    NORMAL = auto()
    HOVERED = auto()
    PRESSED = auto()
    DISABLED = auto()
    FOCUSED = auto()


class UILayer(IntEnum):
    """Which band of the screen an element belongs to.

    The manager sorts roots by layer and then by the order they were added,
    so a HUD stays under an overlay no matter which was built first -- the
    thing a flat list cannot express. Values are spaced by 100 so a game can
    slot its own band between two of these without renumbering.
    """

    BACKDROP = 0
    """Behind everything: a menu's backing plate, a vignette."""

    CONTENT = 100
    """The default. A menu, a screen's own widgets."""

    HUD = 200
    """In-world readouts that stay up while the game runs."""

    OVERLAY = 300
    """Modals: a pause menu, an options panel, a dialog."""


class UIAnchor(Enum):
    """Positioning anchor point."""

    TOP_LEFT = auto()
    TOP_CENTER = auto()
    TOP_RIGHT = auto()
    CENTER_LEFT = auto()
    CENTER = auto()
    CENTER_RIGHT = auto()
    BOTTOM_LEFT = auto()
    BOTTOM_CENTER = auto()
    BOTTOM_RIGHT = auto()


class TextAlign(Enum):
    """Where a `Label` positions its text within its own width.

    Only meaningful when the label has an explicit `width` -- an
    auto-sizing label's rect is exactly the text's width, so there is
    nowhere for alignment to move it.
    """

    LEFT = auto()
    CENTER = auto()
    RIGHT = auto()


class LayoutDirection(Enum):
    """Direction for container stacking."""

    HORIZONTAL = auto()
    VERTICAL = auto()


class LayoutAlignment(Enum):
    """Child alignment within containers."""

    START = auto()
    CENTER = auto()
    END = auto()
    STRETCH = auto()


class UIEventType(Enum):
    """UI interaction event types.

    Type-safe enumeration for UI events to prevent typos and enable
    IDE autocomplete. Each event represents a specific user interaction
    with UI elements.

    Example:
        >>> # Type-safe event handling
        >>> if event_type == UIEventType.MOUSE_DOWN:
        ...     element.handle_click()
        >>>
        >>> # IDE provides autocomplete
        >>> element.handle_event(UIEventType.MOUSE_MOVE, position)
    """

    MOUSE_DOWN = "mouse_down"
    """Mouse button pressed within element bounds."""

    MOUSE_UP = "mouse_up"
    """Mouse button released (may be outside element)."""

    MOUSE_MOVE = "mouse_move"
    """Mouse cursor moved (used for hover detection)."""

    MOUSE_ENTER = "mouse_enter"
    """Mouse cursor entered element bounds."""

    MOUSE_LEAVE = "mouse_leave"
    """Mouse cursor left element bounds."""

    FOCUS_GAINED = "focus_gained"
    """Element received input focus (keyboard/gamepad)."""

    FOCUS_LOST = "focus_lost"
    """Element lost input focus."""

    KEY_DOWN = "key_down"
    """Keyboard key was pressed."""

    KEY_UP = "key_up"
    """Keyboard key was released."""

    TEXT_INPUT = "text_input"
    """Unicode text input (for printable characters)."""


# --- Theme Structures ---


# The five colours every other role is derived from, and the two state
# overlays. A theme that sets only these still gets a coherent full palette
# out of `ColorScheme.derive()`.
_BASE_PRIMARY = Color(70, 130, 180)
_BASE_SECONDARY = Color(100, 149, 237)
_BASE_BACKGROUND = Color(32, 32, 32)
_BASE_TEXT = Color(255, 255, 255)
_BASE_BORDER = Color(96, 96, 96)


def _relative_luminance(color: Color) -> float:
    """Perceived brightness of `color`, 0.0-255.0.

    Args:
        color: The colour to weigh.

    Returns:
        The luminance, weighting green far above blue the way an eye does.
    """
    return 0.2126 * color.r + 0.7152 * color.g + 0.0722 * color.b


def _readable_on(color: Color) -> Color:
    """Black or white, whichever stays legible on `color`.

    Args:
        color: The background the text sits on.

    Returns:
        `Color.BLACK` over a light background, `Color.WHITE` over a dark one.
    """
    return Color.BLACK if _relative_luminance(color) > 140 else Color.WHITE


def _toward_text(background: Color, text: Color, amount: float) -> Color:
    """Shift `background` towards `text` by `amount`.

    Lifting a surface means lightening it in a dark theme and darkening it
    in a light one. Interpolating towards the *text* colour does both,
    because a theme's text is always the far end of its own contrast range.

    Args:
        background: The surface colour to shift.
        text: The theme's text colour, standing in for "away from the
            background".
        amount: How far to move, 0.0-1.0.

    Returns:
        The shifted colour.
    """
    return background.lerp(text, amount)


# Conventional status colours. Unlike every other role these are *not*
# derivable from a theme's five base colours -- "danger" is red because of
# what red means, not because of what the theme's primary is -- so they have
# fixed defaults that a theme overrides when its palette has its own.
_BASE_STATE_OK = Color.from_hex("#4caf50")
_BASE_STATE_WARN = Color.from_hex("#ff9800")
_BASE_STATE_DANGER = Color.from_hex("#f44336")

SCRIM_ALPHA = 190
"""How opaque a scrim is: enough to push a frozen scene back, not hide it."""

OVERLAY_ALPHA = 240
"""A modal surface is nearly solid -- a hint of the scene, not a view of it."""


def _scrim_from(background: Color) -> Color:
    """The translucent ink a modal is laid over.

    Args:
        background: The theme's canvas colour.

    Returns:
        A darkened, part-transparent version of it.
    """
    dark = background.lerp(Color.BLACK, 0.3)
    return Color(dark.r, dark.g, dark.b, SCRIM_ALPHA)


@dataclass
class ColorScheme:
    """Standardized color palette using Color objects.

    Two layers. The **base** five plus two overlays are the shorthand a
    theme has always been written in. The **semantic roles** below them --
    surfaces, a text hierarchy, edges, action states -- are what components
    actually read, so a design system can say "this is the pressed colour
    of a primary action" rather than overloading `secondary` to mean it.

    Every semantic role has a default derived from the base colours, so a
    theme that sets only the base five is still coherent: see `derive()`,
    which is how the presets and `pyguara.ui.design_system` build theirs.
    """

    # --- Base ---
    primary: Color = field(default_factory=lambda: _BASE_PRIMARY)
    secondary: Color = field(default_factory=lambda: _BASE_SECONDARY)
    background: Color = field(default_factory=lambda: _BASE_BACKGROUND)
    text: Color = field(default_factory=lambda: _BASE_TEXT)
    border: Color = field(default_factory=lambda: _BASE_BORDER)

    # State overlays
    hover_overlay: Color = field(default_factory=lambda: Color(255, 255, 255))
    press_overlay: Color = field(default_factory=lambda: Color(0, 0, 0))

    # --- Surfaces, in depth order: the page, a card on it, something
    # raised off the card, and something cut into it. ---
    surface_canvas: Color = field(default_factory=lambda: _BASE_BACKGROUND)
    surface_card: Color = field(
        default_factory=lambda: _toward_text(_BASE_BACKGROUND, _BASE_TEXT, 0.06)
    )
    surface_raised: Color = field(
        default_factory=lambda: _toward_text(_BASE_BACKGROUND, _BASE_TEXT, 0.12)
    )
    surface_inset: Color = field(
        default_factory=lambda: _BASE_BACKGROUND.lerp(Color.BLACK, 0.12)
    )

    # --- Text, in descending emphasis. ---
    text_heading: Color = field(default_factory=lambda: _BASE_TEXT)
    text_body: Color = field(default_factory=lambda: _BASE_TEXT)
    text_muted: Color = field(
        default_factory=lambda: _BASE_TEXT.lerp(_BASE_BACKGROUND, 0.35)
    )
    text_faint: Color = field(
        default_factory=lambda: _BASE_TEXT.lerp(_BASE_BACKGROUND, 0.55)
    )
    text_on_primary: Color = field(default_factory=lambda: _readable_on(_BASE_PRIMARY))
    text_on_disabled: Color = field(
        default_factory=lambda: _BASE_TEXT.lerp(_BASE_BACKGROUND, 0.55)
    )

    # --- Edges. ---
    edge: Color = field(default_factory=lambda: _BASE_BORDER)
    edge_strong: Color = field(
        default_factory=lambda: _BASE_BORDER.lerp(_BASE_TEXT, 0.3)
    )
    focus_ring: Color = field(default_factory=lambda: _BASE_SECONDARY)

    # --- Actions, by state. ---
    action_primary: Color = field(default_factory=lambda: _BASE_PRIMARY)
    action_primary_hover: Color = field(
        default_factory=lambda: _BASE_PRIMARY.lerp(Color.WHITE, 0.15)
    )
    action_primary_press: Color = field(
        default_factory=lambda: _BASE_PRIMARY.lerp(Color.BLACK, 0.15)
    )
    action_secondary: Color = field(default_factory=lambda: _BASE_SECONDARY)
    action_disabled: Color = field(
        default_factory=lambda: _toward_text(_BASE_BACKGROUND, _BASE_TEXT, 0.1)
    )

    # --- Modal surfaces. Both carry alpha, so both need a renderer that
    # blends rather than replaces -- see the UI renderers' draw_rect. ---
    surface_scrim: Color = field(default_factory=lambda: _scrim_from(_BASE_BACKGROUND))
    surface_overlay: Color = field(
        default_factory=lambda: Color(
            _BASE_BACKGROUND.lerp(Color.BLACK, 0.12).r,
            _BASE_BACKGROUND.lerp(Color.BLACK, 0.12).g,
            _BASE_BACKGROUND.lerp(Color.BLACK, 0.12).b,
            OVERLAY_ALPHA,
        )
    )
    edge_subtle: Color = field(
        default_factory=lambda: _BASE_BACKGROUND.lerp(_BASE_BORDER, 0.5)
    )

    # --- Status. What a meter means, not what the brand looks like. ---
    state_ok: Color = field(default_factory=lambda: _BASE_STATE_OK)
    state_warn: Color = field(default_factory=lambda: _BASE_STATE_WARN)
    state_danger: Color = field(default_factory=lambda: _BASE_STATE_DANGER)

    @classmethod
    def derive(
        cls,
        *,
        primary: Color | None = None,
        secondary: Color | None = None,
        background: Color | None = None,
        text: Color | None = None,
        border: Color | None = None,
        **overrides: Color,
    ) -> ColorScheme:
        """Build a full scheme from the base colours, then apply `overrides`.

        This is the difference between a preset that only names five
        colours and one whose surfaces, edges and action states all belong
        to the same palette. Pass a role in `overrides` to state it
        outright -- which is what a design system does, having chosen every
        value deliberately rather than by rule.

        Args:
            primary: The brand/action colour.
            secondary: The supporting accent, also the default focus ring.
            background: The canvas the UI sits on.
            text: The body text colour, and the far end of the contrast
                range every surface is lifted towards.
            border: The default edge colour.
            **overrides: Any role named here wins over the derived value.

        Returns:
            A scheme with every role populated.

        Raises:
            TypeError: If `overrides` names something that is not a role.
        """
        base_primary = primary if primary is not None else _BASE_PRIMARY
        base_secondary = secondary if secondary is not None else _BASE_SECONDARY
        base_background = background if background is not None else _BASE_BACKGROUND
        base_text = text if text is not None else _BASE_TEXT
        base_border = border if border is not None else _BASE_BORDER

        derived: dict[str, Color] = {
            "primary": base_primary,
            "secondary": base_secondary,
            "background": base_background,
            "text": base_text,
            "border": base_border,
            "surface_canvas": base_background,
            "surface_card": _toward_text(base_background, base_text, 0.06),
            "surface_raised": _toward_text(base_background, base_text, 0.12),
            "surface_inset": base_background.lerp(Color.BLACK, 0.12),
            "text_heading": base_text,
            "text_body": base_text,
            "text_muted": base_text.lerp(base_background, 0.35),
            "text_faint": base_text.lerp(base_background, 0.55),
            "text_on_primary": _readable_on(base_primary),
            "text_on_disabled": base_text.lerp(base_background, 0.55),
            "edge": base_border,
            "edge_strong": base_border.lerp(base_text, 0.3),
            "focus_ring": base_secondary,
            "action_primary": base_primary,
            "action_primary_hover": base_primary.lerp(Color.WHITE, 0.15),
            "action_primary_press": base_primary.lerp(Color.BLACK, 0.15),
            "action_secondary": base_secondary,
            "action_disabled": _toward_text(base_background, base_text, 0.1),
            "surface_scrim": _scrim_from(base_background),
            "surface_overlay": Color(
                base_background.lerp(Color.BLACK, 0.12).r,
                base_background.lerp(Color.BLACK, 0.12).g,
                base_background.lerp(Color.BLACK, 0.12).b,
                OVERLAY_ALPHA,
            ),
            "edge_subtle": base_background.lerp(base_border, 0.5),
            "state_ok": _BASE_STATE_OK,
            "state_warn": _BASE_STATE_WARN,
            "state_danger": _BASE_STATE_DANGER,
        }

        known = {f.name for f in fields(cls)}
        unknown = set(overrides) - known
        if unknown:
            raise TypeError(
                f"ColorScheme has no role(s) {sorted(unknown)}. "
                f"Known roles: {sorted(known)}"
            )

        derived.update(overrides)
        return cls(**derived)


@dataclass
class SpacingScheme:
    """Standardized layout spacing."""

    padding: int = 8
    margin: int = 4
    gap: int = 8


@dataclass
class FontScheme:
    """Font configuration for UI elements."""

    family: str = "Arial"
    size_small: int = 12
    size_normal: int = 16
    size_large: int = 24
    size_title: int = 32


@dataclass
class BorderScheme:
    """Border styling configuration."""

    width: int = 2
    radius: int = 0
    color: Color = field(default_factory=lambda: Color(96, 96, 96))


@dataclass
class ShadowScheme:
    """Shadow effect configuration."""

    enabled: bool = False
    offset_x: int = 2
    offset_y: int = 2
    blur: int = 4
    color: Color = field(default_factory=lambda: Color(0, 0, 0, 128))
