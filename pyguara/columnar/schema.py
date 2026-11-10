"""Derive a column layout from a component dataclass.

A columnar component is declared exactly like any other: a dataclass with
typed fields. What makes it columnar is that every field has a fixed-width
numeric type, so its values can live in native columns rather than in one
Python object per entity.

| Field type | Columns |
| --- | --- |
| `float` | one `f8` |
| `int` | one `i8` |
| `bool` | one `u1` |
| `Vector2` | two `f8`, named `<field>.x` and `<field>.y` |

A Python `float` maps to `f8` and not `f4` on purpose: a column has to hold
exactly the value that was written, or a system reading it diverges from
the same arithmetic done on objects in its last bits.

Anything else -- a string, a list, another object -- raises, naming the
field. Such a component stays in the object ECS; that is the hybrid the
design calls for, not a gap in this module.
"""

from __future__ import annotations

import dataclasses
import typing
from dataclasses import dataclass
from enum import Enum
from typing import Any

from pyguara.common.types import Vector2


class FieldKind(Enum):
    """How one dataclass field is stored."""

    FLOAT = "float"
    INT = "int"
    BOOL = "bool"
    VECTOR2 = "vector2"


_DTYPES: dict[FieldKind, tuple[str, ...]] = {
    FieldKind.FLOAT: ("f8",),
    FieldKind.INT: ("i8",),
    FieldKind.BOOL: ("u1",),
    FieldKind.VECTOR2: ("f8", "f8"),
}

# `bool` before `int`: bool is a subclass of int, and a flag stored as an
# eight-byte integer would read back as 1 rather than True.
_KINDS: tuple[tuple[type, FieldKind], ...] = (
    (bool, FieldKind.BOOL),
    (int, FieldKind.INT),
    (float, FieldKind.FLOAT),
    (Vector2, FieldKind.VECTOR2),
)


@dataclass(frozen=True, slots=True)
class FieldSpec:
    """One field's place in its component's columns.

    Attributes:
        name: The dataclass field name.
        kind: How it is stored.
        column: Index of its first column.
    """

    name: str
    kind: FieldKind
    column: int

    @property
    def width(self) -> int:
        """How many columns the field occupies."""
        return len(_DTYPES[self.kind])


@dataclass(frozen=True, slots=True)
class Schema:
    """A component type's column layout.

    Attributes:
        component: The dataclass it was derived from.
        fields: One spec per field, in declaration order.
        dtypes: One dtype code per column.
        column_names: One name per column; a `Vector2` contributes two.
    """

    component: type
    fields: tuple[FieldSpec, ...]
    dtypes: tuple[str, ...]
    column_names: tuple[str, ...]

    def flatten(self, instance: Any) -> list[Any]:
        """Turn a component instance into one value per column.

        Args:
            instance: An instance of `component`.

        Returns:
            The values in column order.
        """
        values: list[Any] = []
        for spec in self.fields:
            value = getattr(instance, spec.name)
            if spec.kind is FieldKind.VECTOR2:
                values.append(float(value[0]))
                values.append(float(value[1]))
            else:
                values.append(value)
        return values


def schema_for(component: type) -> Schema:
    """Derive the column layout of a component dataclass.

    Args:
        component: A dataclass whose fields are all `float`, `int`, `bool`
            or `Vector2`.

    Returns:
        Its schema.

    Raises:
        TypeError: If `component` is not a dataclass, has no fields, or has
            a field of a type that cannot be a column.
    """
    if not dataclasses.is_dataclass(component):
        raise TypeError(
            f"{component.__name__} is not a dataclass; a columnar component "
            f"is declared as one"
        )
    hints = typing.get_type_hints(component)
    specs: list[FieldSpec] = []
    dtypes: list[str] = []
    names: list[str] = []
    for field in dataclasses.fields(component):
        kind = _kind_of(hints[field.name])
        if kind is None:
            supported = ", ".join(annotation.__name__ for annotation, _ in _KINDS)
            raise TypeError(
                f"{component.__name__}.{field.name} is {hints[field.name]!r}, "
                f"which cannot be a column. Columnar fields are {supported}; "
                f"keep this component in the object ECS, or move the field "
                f"to a component of its own."
            )
        specs.append(FieldSpec(field.name, kind, len(dtypes)))
        dtypes.extend(_DTYPES[kind])
        if kind is FieldKind.VECTOR2:
            names.extend((f"{field.name}.x", f"{field.name}.y"))
        else:
            names.append(field.name)
    if not specs:
        raise TypeError(f"{component.__name__} has no fields to store")
    return Schema(component, tuple(specs), tuple(dtypes), tuple(names))


def _kind_of(annotation: Any) -> FieldKind | None:
    """Map a resolved annotation to a storage kind, if it has one."""
    for candidate, kind in _KINDS:
        if annotation is candidate:
            return kind
    return None
