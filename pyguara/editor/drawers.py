"""
Editor drawers for rendering component inspectors.

This module provides a registry of strategies to render different types of
components in the ImGui inspector. It supports:
1. Dataclasses (Automatic reflection).
2. Custom Handlers (e.g. for Transform).
3. Primitive Types (Vector2, Color, Enums).
"""

import dataclasses
from enum import Enum
from typing import Any, Callable, Dict, Type

# Try importing ImGui, degrade gracefully
try:
    import imgui
except ImportError:
    imgui = None

from pyguara.common.types import Vector2, Color
from pyguara.common.components import Transform


class InspectorDrawer:
    """Registry for component drawing strategies."""

    _custom_drawers: Dict[Type, Callable[[str, Any], bool]] = {}

    @classmethod
    def register(cls, type_: Type, drawer: Callable[[str, Any], bool]) -> None:
        """Register a custom drawer for a specific type."""
        cls._custom_drawers[type_] = drawer

    @classmethod
    def draw_component(cls, component: Any) -> None:
        """Draw a component."""
        if not imgui:
            return

        # 1. Custom Class Handlers (e.g. Transform)
        if type(component) in cls._custom_drawers:
            cls._custom_drawers[type(component)]("Header", component)
            return

        # 2. Dataclasses (Reflection)
        if dataclasses.is_dataclass(component):
            cls._draw_dataclass(component)
            return

        # 3. Fallback (Public Properties/__dict__)
        cls._draw_generic(component)

    @classmethod
    def _draw_dataclass(cls, obj: Any) -> None:
        for field in dataclasses.fields(obj):
            if field.name.startswith("_"):
                continue

            val = getattr(obj, field.name)
            new_val = cls._draw_field(field.name, val, field.type)

            if new_val is not None:
                setattr(obj, field.name, new_val)

    @classmethod
    def _draw_generic(cls, obj: Any) -> None:
        # Fallback to __dict__ for standard classes
        # This is brittle but better than nothing for unknown types
        if hasattr(obj, "__dict__"):
            for name, val in obj.__dict__.items():
                if name.startswith("_"):
                    continue
                new_val = cls._draw_field(name, val, type(val))
                if new_val is not None:
                    setattr(obj, name, new_val)

    @classmethod
    def _draw_field(cls, label: str, value: Any, type_hint: Any = None) -> Any:
        """
        Draw a single field based on its type.

        Returns the new value if changed, or None.
        """
        # 1. Vector2
        if isinstance(value, Vector2):
            changed, (nx, ny) = imgui.drag_float2(label, value.x, value.y, 0.1)
            if changed:
                return Vector2(nx, ny)
            return None

        # 2. Color
        if isinstance(value, Color):
            norm = (value.r / 255.0, value.g / 255.0, value.b / 255.0, value.a / 255.0)
            changed, new_norm = imgui.color_edit4(label, *norm)
            if changed:
                return Color(
                    int(new_norm[0] * 255),
                    int(new_norm[1] * 255),
                    int(new_norm[2] * 255),
                    int(new_norm[3] * 255),
                )
            return None

        # 3. Enums
        if isinstance(value, Enum):
            # Show a combo box
            enum_type = type(value)
            options = [e.name for e in enum_type]
            try:
                current_idx = options.index(value.name)
            except ValueError:
                current_idx = 0

            clicked, new_idx = imgui.combo(label, current_idx, options)
            if clicked:
                return list(enum_type)[new_idx]
            return None

        # 4. Primitives
        if isinstance(value, bool):
            changed, new_val = imgui.checkbox(label, value)
            if changed:
                return new_val
            return None

        if isinstance(value, float):
            changed, new_val = imgui.drag_float(label, value, 0.1)
            if changed:
                return new_val
            return None

        if isinstance(value, int):
            changed, new_val = imgui.drag_int(label, value)
            if changed:
                return new_val
            return None

        if isinstance(value, str):
            changed, new_val = imgui.input_text(label, value, 256)
            if changed:
                return new_val
            return None

        # 5. Lists (Basic support)
        if isinstance(value, list):
            if imgui.tree_node(label):
                # We can't easily edit lists without more context (add/remove),
                # but we can visualize them
                for i, item in enumerate(value):
                    imgui.text(f"[{i}] {item}")
                imgui.tree_pop()
            return None

        imgui.text(f"{label}: {value} (Read Only)")
        return None


# --- Custom Drawer Implementations ---


def draw_transform(label: str, transform: Transform) -> bool:
    """Specialized drawer for Transform component."""
    # Position
    changed_p, (px, py) = imgui.drag_float2(
        "Position", transform.position.x, transform.position.y, 1.0
    )
    if changed_p:
        transform.position = Vector2(px, py)

    # Rotation (Degrees)
    changed_r, rot = imgui.drag_float("Rotation", transform.rotation_degrees, 1.0)
    if changed_r:
        transform.rotation_degrees = rot

    # Scale
    changed_s, (sx, sy) = imgui.drag_float2(
        "Scale", transform.scale.x, transform.scale.y, 0.1
    )
    if changed_s:
        transform.scale = Vector2(sx, sy)

    return False


# Register Default Drawers
InspectorDrawer.register(Transform, draw_transform)
