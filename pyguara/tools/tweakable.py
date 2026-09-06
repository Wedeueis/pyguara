"""Shared dispatch for editing arbitrary field values in dev tools.

Used by both `EntityInspector` (editing live component fields on a selected
entity) and `ConfigInspector` (editing `GameConfig`'s dataclass tree) -- one
per-type control dispatch, written once and reused across both tools'
differing navigation models (cycle entities vs. walk a static config tree).

Introspection is automatic (walking a component's own attributes, or a
dataclass's fields), matching this codebase's existing precedent
(`persistence/serializer.py`, `ui/theme.py`, `EntityInspector`'s own prior
read-only display) rather than a decorator or manual registry.
"""

from __future__ import annotations

import dataclasses
from collections.abc import Callable, Iterator
from enum import Enum
from typing import Any

from pyguara.common.types import Color, Rect, Vector2
from pyguara.graphics.protocols import UIRenderer

# Fixed step for numeric int/float editing -- no per-field range/step
# metadata exists anywhere in these dataclasses to size a slider or a
# proportional step against, so a flat stepper is the honest fit for what
# the data actually supports.
NUMBER_STEP = 1.0


@dataclasses.dataclass
class TweakableLeaf:
    """One editable (or read-only) leaf field, reachable via `apply()`.

    `apply` takes the *new value* and writes it back to wherever this leaf
    actually lives (its immediate parent object's attribute) -- necessary
    even for a `Vector2`'s `x`/`y`, which are read-only properties on the
    underlying `pymunk.Vec2d` and can only be changed by replacing the whole
    `Vector2` on its parent attribute, not by mutating in place.
    """

    label: str
    value: Any
    kind: str  # "bool", "number", "enum", "readonly"
    apply: Callable[[Any], None]


def _iter_own_fields(obj: Any) -> Iterator[tuple[str, Any]]:
    """Yield `(name, value)` for `obj`'s own fields.

    Skips private (`_`-prefixed) attributes -- the same filter
    `EntityInspector`'s display has always used. Works uniformly for a plain
    component (has `__dict__`) and a `slots=True` dataclass (e.g.
    `Color`/`Rect`, which have none) by falling back to
    `dataclasses.fields()` when `vars()` isn't available.
    """
    try:
        items = vars(obj).items()
    except TypeError:
        if not dataclasses.is_dataclass(obj):
            return
        items = ((f.name, getattr(obj, f.name)) for f in dataclasses.fields(obj))

    for name, value in items:
        if name.startswith("_"):
            continue
        yield name, value


def collect_tweakable_leaves(obj: Any, prefix: str = "") -> list[TweakableLeaf]:
    """Recursively walk `obj`'s own fields into a flat list of leaves.

    Dispatch per field value: `bool` -> toggle; `Enum` -> cycle; `int`/
    `float` -> stepper; `Vector2` -> two numeric sub-leaves (`.x`/`.y`); a
    nested dataclass instance -> recurse, one sub-leaf per field; anything
    else -> read-only (unchanged from what was displayed before this
    dispatch existed).
    """
    leaves: list[TweakableLeaf] = []
    for name, value in _iter_own_fields(obj):
        leaves.extend(_leaves_for(obj, name, value, f"{prefix}{name}"))
    return leaves


def _leaves_for(parent: Any, name: str, value: Any, label: str) -> list[TweakableLeaf]:
    # bool before int/float: bool is an int subclass in Python.
    if isinstance(value, bool):
        return [TweakableLeaf(label, value, "bool", lambda v: setattr(parent, name, v))]
    if isinstance(value, Enum):
        return [TweakableLeaf(label, value, "enum", lambda v: setattr(parent, name, v))]
    if isinstance(value, (int, float)):
        return [
            TweakableLeaf(label, value, "number", lambda v: setattr(parent, name, v))
        ]
    if isinstance(value, Vector2):

        def _set_x(v: float) -> None:
            current = getattr(parent, name)
            setattr(parent, name, Vector2(v, current.y))

        def _set_y(v: float) -> None:
            current = getattr(parent, name)
            setattr(parent, name, Vector2(current.x, v))

        return [
            TweakableLeaf(f"{label}.x", value.x, "number", _set_x),
            TweakableLeaf(f"{label}.y", value.y, "number", _set_y),
        ]
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return collect_tweakable_leaves(value, prefix=f"{label}.")
    return [TweakableLeaf(label, value, "readonly", lambda v: None)]


def cycle_enum(current: Enum) -> Enum:
    """Return the next member of `current`'s enum class, wrapping around."""
    members = list(type(current))
    return members[(members.index(current) + 1) % len(members)]


def apply_click(leaf: TweakableLeaf, local_x: int, row_width: int) -> None:
    """Apply a click at `local_x` (relative to the row's left edge) to `leaf`.

    Dispatches per `leaf.kind`. A `number` row splits at its horizontal
    midpoint: left half decrements by `NUMBER_STEP`, right half increments.
    """
    if leaf.kind == "bool":
        leaf.apply(not leaf.value)
    elif leaf.kind == "enum":
        leaf.apply(cycle_enum(leaf.value))
    elif leaf.kind == "number":
        step = -NUMBER_STEP if local_x < row_width / 2 else NUMBER_STEP
        new_value = leaf.value + step
        if isinstance(leaf.value, int):
            new_value = int(new_value)
        leaf.apply(new_value)
    # "readonly": no-op.


def format_leaf_value(leaf: TweakableLeaf) -> str:
    """Render `leaf.value` for display.

    Formats floats consistently with how `EntityInspector` already
    formatted them before this dispatch existed.
    """
    if isinstance(leaf.value, float):
        return f"{leaf.value:.2f}"
    if isinstance(leaf.value, Enum):
        return leaf.value.name
    return str(leaf.value)


def render_tweakable_leaves(
    renderer: UIRenderer,
    leaves: list[TweakableLeaf],
    x: int,
    y: int,
    row_width: int,
    row_height: int,
    text_color: Color,
    font_size: int = 14,
) -> list[tuple[Rect, TweakableLeaf]]:
    """Draw one text row per leaf (`label: value`) starting at `(x, y)`.

    Returns each editable row's screen `Rect` paired with its
    `TweakableLeaf`, for the caller's `process_event()` to hit-test clicks
    against. Read-only leaves are drawn but never returned as clickable.
    """
    rows: list[tuple[Rect, TweakableLeaf]] = []
    for leaf in leaves:
        renderer.draw_text(
            f"{leaf.label}: {format_leaf_value(leaf)}",
            Vector2(x, y),
            text_color,
            font_size,
        )
        if leaf.kind != "readonly":
            rows.append((Rect(x, y, row_width, row_height), leaf))
        y += row_height
    return rows
