"""`ColumnarWorld`: component state held in native columns.

The object ECS keeps one Python object per component and lends that state
to native code a call at a time. Here it is the other way round: the
columns live in Rust (`rust/src/world.rs`), a native system works on them
in place, and Python reaches them three ways.

```python
world = ColumnarWorld()
entity = world.spawn()
world.add(entity, Position(Vector2(1.0, 2.0)))

world.view(entity, Position).value = Vector2(3.0, 4.0)   # one entity
xs = world.arrays(Position)["value.x"]                   # every entity
world.add_scaled(Position, "value.x", Velocity, "value.x", dt)  # natively
```

**An array pins its component.** `arrays()` returns NumPy arrays over the
column memory itself, with no copy. While one is alive, anything that
would move that memory -- an `add` that has to grow the column, a `flush`
with removals pending -- raises `BufferError`. Drop the arrays before
changing the world's structure; reading and writing values is always fine.

**Removal is deferred**, as in `EntityManager`: `remove` and `despawn`
take effect at once for every lookup, and the rows leave the columns at
the next `flush`, in order.

This is a spike. It stands beside the object ECS and is not wired into
`EntityManager`, scenes or systems.
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from typing import Any, Final, cast

import numpy as np
import numpy.typing as npt

from pyguara import native
from pyguara.columnar.schema import FieldKind, Schema, schema_for
from pyguara.common.types import Vector2

TOMBSTONE: Final = 2**64 - 1
"""What a removed row reads as in a component's entity column."""


class ColumnArrays(Mapping[str, npt.NDArray[Any]]):
    """One component's columns as NumPy arrays over the native memory.

    Indexed by column name -- a `Vector2` field `position` appears as
    `position.x` and `position.y`. Holding this pins the component; see
    the module docstring.

    Attributes:
        entities: The entity id of each row, read-only. A row removed
            while the arrays were alive reads as `TOMBSTONE`.
    """

    __slots__ = ("_columns", "entities")

    def __init__(
        self, columns: dict[str, npt.NDArray[Any]], entities: npt.NDArray[np.uint64]
    ) -> None:
        """Wrap already-exported arrays.

        Args:
            columns: Column name to array.
            entities: The row-to-entity column.
        """
        self._columns = columns
        self.entities = entities

    def __getitem__(self, name: str) -> npt.NDArray[Any]:
        """Return the array for one column."""
        try:
            return self._columns[name]
        except KeyError:
            known = ", ".join(self._columns)
            raise KeyError(f"no column {name!r}; this component has {known}") from None

    def __setitem__(self, name: str, values: Any) -> None:
        """Write `values` into a column, in place.

        Exists so `arrays["x"] += step` works: Python evaluates that as an
        in-place add followed by an assignment of the result, which is the
        array already there. Assigning anything else copies it into the
        column; the array object itself is never replaced, because it is
        the only thing that points at the native memory.
        """
        column = self[name]
        if values is not column:
            column[...] = values

    def __iter__(self) -> Iterator[str]:
        """Iterate column names in declared order."""
        return iter(self._columns)

    def __len__(self) -> int:
        """Return the number of columns."""
        return len(self._columns)


class ColumnarWorld:
    """Entities and columnar components for one world."""

    def __init__(self) -> None:
        """Create an empty world.

        Raises:
            RuntimeError: If the native extension cannot be imported. There
                is no Python implementation to fall back to.
        """
        self._native = native.require_extension("pyguara.columnar").NativeWorld()
        self._schemas: dict[type, Schema] = {}
        self._tables: dict[type, int] = {}
        self._views: dict[type, type] = {}

    # -- entities ----------------------------------------------------------

    def spawn(self) -> int:
        """Create an entity and return its id."""
        return cast(int, self._native.spawn())

    def spawn_many(self, count: int) -> list[int]:
        """Create `count` entities in one native call."""
        return cast(list[int], self._native.spawn_many(count))

    def despawn(self, entity: int) -> bool:
        """Destroy an entity and everything it holds.

        Args:
            entity: The id to destroy.

        Returns:
            Whether it was alive.
        """
        return cast(bool, self._native.despawn(entity))

    def is_alive(self, entity: int) -> bool:
        """Report whether `entity` names a live entity."""
        return cast(bool, self._native.is_alive(entity))

    @property
    def entity_count(self) -> int:
        """How many entities are alive."""
        return cast(int, self._native.entity_count)

    # -- components --------------------------------------------------------

    def register(self, component: type) -> Schema:
        """Declare a component type, deriving its columns.

        Called implicitly by everything else here; call it directly to
        fail early on a field that cannot be a column.

        Args:
            component: A dataclass of `float`, `int`, `bool` and `Vector2`.

        Returns:
            Its schema.

        Raises:
            TypeError: If the type cannot be stored in columns.
        """
        known = self._schemas.get(component)
        if known is not None:
            return known
        schema = schema_for(component)
        table = self._native.register(component.__name__, list(schema.dtypes))
        self._schemas[component] = schema
        self._tables[component] = table
        self._views[component] = _build_view_class(schema, table)
        return schema

    def add(self, entity: int, component: Any) -> None:
        """Attach a component, copying its values into the columns.

        The instance is not kept: later changes to it do not reach the
        world. Use `view()` to write.

        Args:
            entity: The owner.
            component: An instance of a columnar component type.

        Raises:
            KeyError: If `entity` is not alive.
            ValueError: If it already holds one of this type.
            BufferError: If the columns must grow while `arrays()` of this
                type are alive.
        """
        kind = type(component)
        schema = self.register(kind)
        self._native.insert(self._tables[kind], entity, schema.flatten(component))

    def remove(self, entity: int, component: type) -> bool:
        """Detach a component. Returns whether the entity held it."""
        self.register(component)
        return cast(bool, self._native.remove(self._tables[component], entity))

    def has(self, entity: int, component: type) -> bool:
        """Report whether a live `entity` holds `component`."""
        self.register(component)
        return cast(bool, self._native.has(self._tables[component], entity))

    def count(self, component: type) -> int:
        """How many entities hold `component`."""
        self.register(component)
        return cast(int, self._native.count(self._tables[component]))

    def view[C](self, entity: int, component: type[C]) -> C:
        """Return a live view of one entity's component.

        The view has the component's fields as attributes; reading one
        reads the column and assigning one writes it. It is typed as the
        component so game code and the type checker treat it as one, but
        it is not an instance of it.

        The lookup happens on each attribute access rather than here, so
        a view of a component the entity does not hold raises `KeyError`
        on first use.

        Args:
            entity: The owner.
            component: The component type.

        Returns:
            The view.
        """
        self.register(component)
        return cast(C, self._views[component](self._native, entity))

    def get[C](self, entity: int, component: type[C]) -> C:
        """Return a detached copy of one entity's component.

        Args:
            entity: The owner.
            component: The component type.

        Returns:
            A new instance holding the current values.

        Raises:
            KeyError: If the entity is dead or does not hold it.
        """
        schema = self.register(component)
        table = self._tables[component]
        values: dict[str, Any] = {}
        for spec in schema.fields:
            if spec.kind is FieldKind.VECTOR2:
                values[spec.name] = Vector2(
                    *self._native.get_pair(table, entity, spec.column)
                )
            else:
                values[spec.name] = self._native.get(table, entity, spec.column)
        return component(**values)

    # -- bulk access -------------------------------------------------------

    def arrays(self, component: type) -> ColumnArrays:
        """Return the component's columns as NumPy arrays, without copying.

        Rows are in insertion order. Pending removals are compacted first
        unless other arrays of this component are still alive, in which
        case their rows read as `TOMBSTONE` in `entities`.

        Args:
            component: The component type.

        Returns:
            The arrays. Writable, except `entities`.
        """
        schema = self.register(component)
        table = self._tables[component]
        columns = {
            name: np.asarray(self._native.column(table, index))
            for index, name in enumerate(schema.column_names)
        }
        entities = np.asarray(self._native.entities(table))
        return ColumnArrays(columns, entities)

    def version(self, component: type, column: str) -> int:
        """Return a column's write counter.

        It changes whenever the column may have: on any `add`, `remove`,
        view assignment or native write, and on every `arrays()` call,
        since an array can be written through at any time afterwards. A
        system that caches something derived from a column compares this
        instead of being told -- the automatic form of
        `EntityManager.notify_component_changed`.

        Args:
            component: The component type.
            column: A column name, as in `arrays()`.

        Returns:
            The counter.
        """
        return cast(
            int,
            self._native.version(
                self._tables[component], self._column(component, column)
            ),
        )

    def flush(self) -> None:
        """Drop removed rows from every component, keeping order.

        Call it where `EntityManager.flush_pending_removals` is called: at
        the frame boundary.

        Raises:
            BufferError: If arrays over a component with removals pending
                are still alive.
        """
        self._native.flush()

    # -- native systems ----------------------------------------------------

    def add_scaled(
        self,
        target: type,
        target_column: str,
        source: type,
        source_column: str,
        scale: float,
    ) -> int:
        """Add `source * scale` into `target`, for entities holding both.

        `position += velocity * dt` as one native loop over the columns,
        with the GIL released and nothing packed or written back.

        Args:
            target: The component written.
            target_column: An `f8` column of it.
            source: The component read.
            source_column: An `f8` column of it.
            scale: The multiplier.

        Returns:
            How many entities were updated.
        """
        return cast(
            int,
            self._native.add_scaled(
                self._tables[target],
                self._column(target, target_column),
                self._tables[source],
                self._column(source, source_column),
                scale,
            ),
        )

    def _column(self, component: type, name: str) -> int:
        """Resolve a column name to its index."""
        schema = self.register(component)
        try:
            return schema.column_names.index(name)
        except ValueError:
            known = ", ".join(schema.column_names)
            raise KeyError(
                f"{component.__name__} has no column {name!r}; it has {known}"
            ) from None


def _build_view_class(schema: Schema, table: int) -> type:
    """Build the per-entity view class for one component type.

    A subclass of the native `RowView` carrying one native `FieldAccessor`
    per field, so an attribute access goes from the interpreter's
    descriptor call straight into Rust. A Python `property` in between
    was measured at about 35 ns per access -- as much as the read itself.
    """
    extension = native.require_extension("pyguara.columnar")
    namespace: dict[str, Any] = {
        "__slots__": (),
        "__repr__": _view_repr,
        "_fields": tuple(spec.name for spec in schema.fields),
    }
    for spec in schema.fields:
        pair = Vector2 if spec.kind is FieldKind.VECTOR2 else None
        namespace[spec.name] = extension.FieldAccessor(table, spec.column, pair)
    return type(f"{schema.component.__name__}View", (extension.RowView,), namespace)


def _view_repr(self: Any) -> str:
    body = ", ".join(f"{name}={getattr(self, name)!r}" for name in self._fields)
    return f"{type(self).__name__}({body})"
