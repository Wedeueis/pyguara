"""Columnar component storage: world state in native, typed columns.

A spike beside the object ECS, not a replacement for it yet. See
`docs/adr/0008-the-columnar-world-spike.md`.
"""

from pyguara.columnar.schema import FieldKind, FieldSpec, Schema, schema_for
from pyguara.columnar.world import TOMBSTONE, ColumnArrays, ColumnarWorld

__all__ = [
    "TOMBSTONE",
    "ColumnArrays",
    "ColumnarWorld",
    "FieldKind",
    "FieldSpec",
    "Schema",
    "schema_for",
]
