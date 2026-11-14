//! A columnar world: entity ids and component state held natively.
//!
//! Everything else in this crate borrows state from Python for the length
//! of a call -- pack in, solve, write back -- and `flocking` measures what
//! that costs: 63% of its native tick is the crossing. This module is the
//! other arrangement, the one ADR 0004 named and never priced: the state
//! *lives* here, a native system reads and writes it in place, and Python
//! reaches it either one value at a time or as a NumPy array over the same
//! memory.
//!
//! **Layout.** One sparse set per component: dense columns indexed by row,
//! an `entities` column naming each row's owner, and a sparse array from
//! entity index to row. Not archetype tables, because query order is part
//! of the simulation (#324) and a sparse set keeps rows in insertion order
//! without any bookkeeping.
//!
//! **Removal is deferred**, as it is in `EntityManager`. Removing a
//! component tombstones its row; `flush` compacts every table, preserving
//! the order of what is left. Nothing moves in memory in between, so a
//! loop that destroys entities while iterating a view stays valid.
//!
//! **A column can be exported as a buffer, and the memory it points at is
//! then pinned.** A NumPy array over a column holds a raw pointer into a
//! `Vec`. Any change that would move that memory -- an insert that
//! reallocates, a compaction -- raises `BufferError` while an export is
//! alive, which is `bytearray`'s rule and the only safe one for a plain
//! contiguous array.
//!
//! **There is no Python counterpart**, so this loads through
//! `native.require_extension()` like `audio` and `net`, not through the
//! store switch.

use std::ffi::{c_int, c_void, CStr};
use std::sync::atomic::{AtomicUsize, Ordering};
use std::sync::Arc;

use pyo3::exceptions::{PyBufferError, PyKeyError, PyTypeError, PyValueError};
use pyo3::ffi;
use pyo3::prelude::*;

/// "No row" in a sparse array.
const NO_ROW: u32 = u32::MAX;
/// A tombstoned row's owner.
const NO_ENTITY: u64 = u64::MAX;

/// One column's storage. The variants are the dtypes a schema may name.
enum Column {
    F64(Vec<f64>),
    F32(Vec<f32>),
    I64(Vec<i64>),
    U8(Vec<u8>),
}

impl Column {
    fn new(dtype: &str) -> PyResult<Self> {
        match dtype {
            "f8" => Ok(Self::F64(Vec::new())),
            "f4" => Ok(Self::F32(Vec::new())),
            "i8" => Ok(Self::I64(Vec::new())),
            "u1" => Ok(Self::U8(Vec::new())),
            other => Err(PyValueError::new_err(format!(
                "unknown column dtype {other:?}; expected one of f8, f4, i8, u1"
            ))),
        }
    }

    fn is_full(&self) -> bool {
        match self {
            Self::F64(v) => v.len() == v.capacity(),
            Self::F32(v) => v.len() == v.capacity(),
            Self::I64(v) => v.len() == v.capacity(),
            Self::U8(v) => v.len() == v.capacity(),
        }
    }

    fn push(&mut self, value: &Bound<'_, PyAny>) -> PyResult<()> {
        match self {
            Self::F64(v) => v.push(value.extract()?),
            Self::F32(v) => v.push(value.extract()?),
            Self::I64(v) => v.push(value.extract()?),
            Self::U8(v) => v.push(u8::from(value.is_truthy()?)),
        }
        Ok(())
    }

    fn pop(&mut self) {
        match self {
            Self::F64(v) => drop(v.pop()),
            Self::F32(v) => drop(v.pop()),
            Self::I64(v) => drop(v.pop()),
            Self::U8(v) => drop(v.pop()),
        }
    }

    fn get<'py>(&self, python: Python<'py>, row: usize) -> PyResult<Bound<'py, PyAny>> {
        Ok(match self {
            Self::F64(v) => v[row].into_pyobject(python)?.into_any(),
            Self::F32(v) => v[row].into_pyobject(python)?.into_any(),
            Self::I64(v) => v[row].into_pyobject(python)?.into_any(),
            Self::U8(v) => (v[row] != 0).into_pyobject(python)?.to_owned().into_any(),
        })
    }

    fn set(&mut self, row: usize, value: &Bound<'_, PyAny>) -> PyResult<()> {
        match self {
            Self::F64(v) => v[row] = value.extract()?,
            Self::F32(v) => v[row] = value.extract()?,
            Self::I64(v) => v[row] = value.extract()?,
            Self::U8(v) => v[row] = u8::from(value.is_truthy()?),
        }
        Ok(())
    }

    /// Move row `from` down to `to` and leave the tail for `truncate`.
    fn shift(&mut self, from: usize, to: usize) {
        match self {
            Self::F64(v) => v[to] = v[from],
            Self::F32(v) => v[to] = v[from],
            Self::I64(v) => v[to] = v[from],
            Self::U8(v) => v[to] = v[from],
        }
    }

    fn truncate(&mut self, len: usize) {
        match self {
            Self::F64(v) => v.truncate(len),
            Self::F32(v) => v.truncate(len),
            Self::I64(v) => v.truncate(len),
            Self::U8(v) => v.truncate(len),
        }
    }

    /// Pointer, item size and struct-format code, for a buffer export.
    fn raw(&mut self) -> (*mut c_void, usize, &'static CStr) {
        match self {
            Self::F64(v) => (v.as_mut_ptr().cast(), 8, c"d"),
            Self::F32(v) => (v.as_mut_ptr().cast(), 4, c"f"),
            Self::I64(v) => (v.as_mut_ptr().cast(), 8, c"q"),
            Self::U8(v) => (v.as_mut_ptr().cast(), 1, c"B"),
        }
    }
}

/// One component's sparse set.
struct Table {
    name: String,
    columns: Vec<Column>,
    /// Bumped by every write to the matching column.
    versions: Vec<u64>,
    /// Row -> owning entity id, or `NO_ENTITY` for a tombstone.
    entities: Vec<u64>,
    /// Entity index -> row, or `NO_ROW`.
    sparse: Vec<u32>,
    /// Tombstoned rows awaiting `compact`.
    dead: usize,
    /// Live buffer exports over this table's memory. Shared with every
    /// `ColumnView`, so releasing a buffer needs no borrow of the world.
    exports: Arc<AtomicUsize>,
}

impl Table {
    fn pinned(&self) -> bool {
        self.exports.load(Ordering::Relaxed) > 0
    }

    fn row_of(&self, index: u32) -> Option<usize> {
        match self.sparse.get(index as usize) {
            Some(&row) if row != NO_ROW => Some(row as usize),
            _ => None,
        }
    }

    fn pinned_error(&self, doing: &str) -> PyErr {
        PyBufferError::new_err(format!(
            "cannot {doing} component {:?} while an array over it is alive; \
             drop the array first",
            self.name
        ))
    }

    /// Tombstone `index`'s row. Never moves memory, so it is always legal.
    fn tombstone(&mut self, index: u32) -> bool {
        let Some(row) = self.row_of(index) else {
            return false;
        };
        self.entities[row] = NO_ENTITY;
        self.sparse[index as usize] = NO_ROW;
        self.dead += 1;
        for version in &mut self.versions {
            *version += 1;
        }
        true
    }

    /// Squeeze the tombstones out, keeping the survivors' order.
    fn compact(&mut self) -> PyResult<()> {
        if self.dead == 0 {
            return Ok(());
        }
        if self.pinned() {
            return Err(self.pinned_error("compact"));
        }
        let mut to = 0;
        for from in 0..self.entities.len() {
            let owner = self.entities[from];
            if owner == NO_ENTITY {
                continue;
            }
            if to != from {
                self.entities[to] = owner;
                for column in &mut self.columns {
                    column.shift(from, to);
                }
                self.sparse[index_of(owner) as usize] = to as u32;
            }
            to += 1;
        }
        self.entities.truncate(to);
        for column in &mut self.columns {
            column.truncate(to);
        }
        self.dead = 0;
        Ok(())
    }
}

fn index_of(entity: u64) -> u32 {
    entity as u32
}

fn generation_of(entity: u64) -> u32 {
    (entity >> 32) as u32
}

/// Entity ids and component columns for one world.
///
/// An entity id is a 64-bit integer: a slot index in the low half and that
/// slot's generation in the high half. A despawned id never resolves again
/// even after its slot is reused, which is what a `uuid4` string bought the
/// object ECS at forty times the size.
#[pyclass]
pub struct NativeWorld {
    generations: Vec<u32>,
    alive: Vec<bool>,
    /// Freed slots, reused last-in first-out so allocation is a pure
    /// function of the call sequence.
    free: Vec<u32>,
    live: usize,
    tables: Vec<Table>,
}

impl NativeWorld {
    fn resolve(&self, entity: u64) -> Option<u32> {
        let index = index_of(entity);
        let slot = index as usize;
        if slot < self.alive.len()
            && self.alive[slot]
            && self.generations[slot] == generation_of(entity)
        {
            Some(index)
        } else {
            None
        }
    }

    fn require(&self, entity: u64) -> PyResult<u32> {
        self.resolve(entity)
            .ok_or_else(|| PyKeyError::new_err(format!("entity {entity} is not alive")))
    }

    fn table(&self, table: usize) -> PyResult<&Table> {
        self.tables
            .get(table)
            .ok_or_else(|| PyKeyError::new_err(format!("no component table {table}")))
    }

    fn table_mut(&mut self, table: usize) -> PyResult<&mut Table> {
        self.tables
            .get_mut(table)
            .ok_or_else(|| PyKeyError::new_err(format!("no component table {table}")))
    }

    /// The row holding `entity`'s component, or `KeyError`.
    fn locate(&self, table: usize, entity: u64) -> PyResult<usize> {
        let index = self.require(entity)?;
        let held = self.table(table)?;
        held.row_of(index).ok_or_else(|| {
            PyKeyError::new_err(format!("entity {entity} has no {:?}", held.name))
        })
    }

    fn spawn_one(&mut self) -> u64 {
        self.live += 1;
        if let Some(index) = self.free.pop() {
            self.alive[index as usize] = true;
            return (u64::from(self.generations[index as usize]) << 32) | u64::from(index);
        }
        let index = self.generations.len() as u32;
        self.generations.push(0);
        self.alive.push(true);
        u64::from(index)
    }
}

fn check_column(held: &Table, column: usize) -> PyResult<()> {
    if column < held.columns.len() {
        Ok(())
    } else {
        Err(PyKeyError::new_err(format!(
            "component {:?} has no column {column}",
            held.name
        )))
    }
}

#[pymethods]
impl NativeWorld {
    /// Create an empty world.
    #[new]
    fn new() -> Self {
        Self {
            generations: Vec::new(),
            alive: Vec::new(),
            free: Vec::new(),
            live: 0,
            tables: Vec::new(),
        }
    }

    /// Allocate an entity id.
    fn spawn(&mut self) -> u64 {
        self.spawn_one()
    }

    /// Allocate `count` entity ids in one crossing.
    fn spawn_many(&mut self, count: usize) -> Vec<u64> {
        (0..count).map(|_| self.spawn_one()).collect()
    }

    /// Kill an entity and tombstone every component it holds.
    ///
    /// Returns whether it was alive. Its id stops resolving at once; the
    /// rows go at the next `flush`.
    fn despawn(&mut self, entity: u64) -> bool {
        let Some(index) = self.resolve(entity) else {
            return false;
        };
        for held in &mut self.tables {
            held.tombstone(index);
        }
        let slot = index as usize;
        self.alive[slot] = false;
        // Wrapping: after 2**32 reuses of one slot an ancient id could
        // resolve again, which is not a failure worth a check per spawn.
        self.generations[slot] = self.generations[slot].wrapping_add(1);
        self.free.push(index);
        self.live -= 1;
        true
    }

    /// Whether `entity` names a live entity.
    fn is_alive(&self, entity: u64) -> bool {
        self.resolve(entity).is_some()
    }

    /// How many entities are alive.
    #[getter]
    fn entity_count(&self) -> usize {
        self.live
    }

    /// Declare a component and return its table number.
    ///
    /// `dtypes` gives one dtype code per column: `f8`, `f4`, `i8` or `u1`.
    fn register(&mut self, name: String, dtypes: Vec<String>) -> PyResult<usize> {
        if dtypes.is_empty() {
            return Err(PyValueError::new_err(format!(
                "component {name:?} declares no columns"
            )));
        }
        let columns = dtypes
            .iter()
            .map(|dtype| Column::new(dtype))
            .collect::<PyResult<Vec<_>>>()?;
        self.tables.push(Table {
            name,
            versions: vec![0; columns.len()],
            columns,
            entities: Vec::new(),
            sparse: Vec::new(),
            dead: 0,
            exports: Arc::new(AtomicUsize::new(0)),
        });
        Ok(self.tables.len() - 1)
    }

    /// Attach a component: one value per column, in declared order.
    fn insert(&mut self, table: usize, entity: u64, values: Vec<Bound<'_, PyAny>>) -> PyResult<()> {
        let index = self.require(entity)?;
        let held = self.table_mut(table)?;
        if values.len() != held.columns.len() {
            return Err(PyValueError::new_err(format!(
                "component {:?} has {} columns, got {} values",
                held.name,
                held.columns.len(),
                values.len()
            )));
        }
        if held.row_of(index).is_some() {
            return Err(PyValueError::new_err(format!(
                "entity {entity} already has {:?}",
                held.name
            )));
        }
        let would_move = held.entities.len() == held.entities.capacity()
            || held.columns.iter().any(Column::is_full);
        if would_move && held.pinned() {
            return Err(held.pinned_error("grow"));
        }
        let row = held.entities.len();
        for (position, (column, value)) in held.columns.iter_mut().zip(&values).enumerate() {
            if let Err(error) = column.push(value) {
                // Undo the columns already pushed, so a bad value leaves
                // every column the same length.
                for earlier in &mut held.columns[..position] {
                    earlier.pop();
                }
                return Err(error);
            }
        }
        held.entities.push(entity);
        let slot = index as usize;
        if held.sparse.len() <= slot {
            held.sparse.resize(slot + 1, NO_ROW);
        }
        held.sparse[slot] = row as u32;
        for version in &mut held.versions {
            *version += 1;
        }
        Ok(())
    }

    /// Detach a component. Returns whether the entity held it.
    fn remove(&mut self, table: usize, entity: u64) -> PyResult<bool> {
        let Some(index) = self.resolve(entity) else {
            return Ok(false);
        };
        Ok(self.table_mut(table)?.tombstone(index))
    }

    /// Whether `entity` holds the component.
    fn has(&self, table: usize, entity: u64) -> PyResult<bool> {
        let held = self.table(table)?;
        Ok(self
            .resolve(entity)
            .is_some_and(|index| held.row_of(index).is_some()))
    }

    /// Read one value.
    fn get<'py>(
        &self,
        python: Python<'py>,
        table: usize,
        entity: u64,
        column: usize,
    ) -> PyResult<Bound<'py, PyAny>> {
        let row = self.locate(table, entity)?;
        let held = &self.tables[table];
        check_column(held, column)?;
        held.columns[column].get(python, row)
    }

    /// Read two adjacent `f8` columns in one crossing -- a `Vector2`.
    fn get_pair(&self, table: usize, entity: u64, column: usize) -> PyResult<(f64, f64)> {
        let row = self.locate(table, entity)?;
        let held = &self.tables[table];
        check_column(held, column + 1)?;
        match (&held.columns[column], &held.columns[column + 1]) {
            (Column::F64(first), Column::F64(second)) => Ok((first[row], second[row])),
            _ => Err(PyTypeError::new_err("get_pair needs two f8 columns")),
        }
    }

    /// Write one value.
    fn set(
        &mut self,
        table: usize,
        entity: u64,
        column: usize,
        value: &Bound<'_, PyAny>,
    ) -> PyResult<()> {
        let row = self.locate(table, entity)?;
        let held = &mut self.tables[table];
        check_column(held, column)?;
        held.columns[column].set(row, value)?;
        held.versions[column] += 1;
        Ok(())
    }

    /// Write two adjacent `f8` columns in one crossing.
    fn set_pair(
        &mut self,
        table: usize,
        entity: u64,
        column: usize,
        first: f64,
        second: f64,
    ) -> PyResult<()> {
        let row = self.locate(table, entity)?;
        let held = &mut self.tables[table];
        check_column(held, column + 1)?;
        let (head, tail) = held.columns.split_at_mut(column + 1);
        match (&mut head[column], &mut tail[0]) {
            (Column::F64(a), Column::F64(b)) => {
                a[row] = first;
                b[row] = second;
            }
            _ => return Err(PyTypeError::new_err("set_pair needs two f8 columns")),
        }
        held.versions[column] += 1;
        held.versions[column + 1] += 1;
        Ok(())
    }

    /// How many entities hold the component.
    fn count(&self, table: usize) -> PyResult<usize> {
        let held = self.table(table)?;
        Ok(held.entities.len() - held.dead)
    }

    /// How many rows are tombstoned and waiting for `flush`.
    fn pending(&self, table: usize) -> PyResult<usize> {
        Ok(self.table(table)?.dead)
    }

    /// The column's write counter: it changes whenever the column may have.
    fn version(&self, table: usize, column: usize) -> PyResult<u64> {
        let held = self.table(table)?;
        check_column(held, column)?;
        Ok(held.versions[column])
    }

    /// Compact every table, dropping tombstoned rows in order.
    ///
    /// Raises `BufferError`, changing nothing in that table, if an array
    /// over a table with tombstones is still alive.
    fn flush(&mut self) -> PyResult<()> {
        for held in &mut self.tables {
            held.compact()?;
        }
        Ok(())
    }

    /// `target[column] += source[column] * scale`, for every entity
    /// holding both components.
    ///
    /// The whole of a movement integration, done in place: no packing, no
    /// write-back, and the GIL released for the loop. Rows are visited in
    /// `source`'s order, which matters to nothing here since each row is
    /// independent, but is stated because order is otherwise a promise.
    #[allow(clippy::too_many_arguments)]
    fn add_scaled(
        &mut self,
        python: Python<'_>,
        target: usize,
        target_column: usize,
        source: usize,
        source_column: usize,
        scale: f64,
    ) -> PyResult<usize> {
        if target == source {
            return Err(PyValueError::new_err(
                "add_scaled needs two different components",
            ));
        }
        check_column(self.table(target)?, target_column)?;
        check_column(self.table(source)?, source_column)?;
        let (low, high) = self.tables.split_at_mut(target.max(source));
        let (into, from) = if target < source {
            (&mut low[target], &high[0])
        } else {
            (&mut high[0], &low[source])
        };
        let (Column::F64(written), Column::F64(read)) =
            (&mut into.columns[target_column], &from.columns[source_column])
        else {
            return Err(PyTypeError::new_err("add_scaled needs two f8 columns"));
        };
        let owners = &from.entities;
        let sparse = &into.sparse;
        let touched = python.detach(|| {
            let mut touched = 0;
            for (row, &owner) in owners.iter().enumerate() {
                if owner == NO_ENTITY {
                    continue;
                }
                let Some(&other) = sparse.get(index_of(owner) as usize) else {
                    continue;
                };
                if other == NO_ROW {
                    continue;
                }
                written[other as usize] += read[row] * scale;
                touched += 1;
            }
            touched
        });
        into.versions[target_column] += 1;
        Ok(touched)
    }

    /// A buffer over one column, for `numpy.asarray`.
    ///
    /// Compacts the table first when nothing else is exported, so the
    /// array has no tombstoned rows in it.
    fn column(slf: &Bound<'_, Self>, table: usize, column: usize) -> PyResult<ColumnView> {
        let mut world = slf.borrow_mut();
        let held = world.table_mut(table)?;
        check_column(held, column)?;
        if !held.pinned() {
            held.compact()?;
        }
        Ok(ColumnView {
            world: slf.clone().unbind(),
            table,
            column: Some(column),
            exports: Arc::clone(&held.exports),
        })
    }

    /// A read-only buffer over the row -> entity id column.
    ///
    /// A tombstoned row reads as `2**64 - 1`.
    fn entities(slf: &Bound<'_, Self>, table: usize) -> PyResult<ColumnView> {
        let mut world = slf.borrow_mut();
        let held = world.table_mut(table)?;
        if !held.pinned() {
            held.compact()?;
        }
        Ok(ColumnView {
            world: slf.clone().unbind(),
            table,
            column: None,
            exports: Arc::clone(&held.exports),
        })
    }
}

/// A buffer exporter over one column of a `NativeWorld`.
///
/// Holding one of these pins nothing. Taking a buffer from it -- which is
/// what `numpy.asarray` does -- pins the table until that buffer is
/// released, which for an array is when the array is collected.
#[pyclass]
pub struct ColumnView {
    world: Py<NativeWorld>,
    table: usize,
    /// `None` is the entity id column.
    column: Option<usize>,
    exports: Arc<AtomicUsize>,
}

/// What `__getbuffer__` allocates and `__releasebuffer__` frees.
struct Shape {
    extent: ffi::Py_ssize_t,
    stride: ffi::Py_ssize_t,
}

#[pymethods]
impl ColumnView {
    /// Fill a PEP 3118 buffer over the column's memory.
    ///
    /// # Safety
    ///
    /// Called by CPython with a valid `view`. The pointer handed out stays
    /// valid until `__releasebuffer__` because `exports` is non-zero until
    /// then, and every operation that could move the memory checks it.
    unsafe fn __getbuffer__(
        slf: Bound<'_, Self>,
        view: *mut ffi::Py_buffer,
        flags: c_int,
    ) -> PyResult<()> {
        if view.is_null() {
            return Err(PyBufferError::new_err("null buffer view"));
        }
        let this = slf.borrow();
        let mut world = this.world.bind(slf.py()).borrow_mut();
        let held = &mut world.tables[this.table];
        let rows = held.entities.len();
        let (pointer, item_size, format, read_only) = match this.column {
            Some(column) => {
                // A writable export may be written through at any time, so
                // the column counts as changed from here on.
                held.versions[column] += 1;
                let (pointer, item_size, format) = held.columns[column].raw();
                (pointer, item_size, format, false)
            }
            None => (held.entities.as_mut_ptr().cast::<c_void>(), 8, c"Q", true),
        };
        if read_only && (flags & ffi::PyBUF_WRITABLE) == ffi::PyBUF_WRITABLE {
            return Err(PyBufferError::new_err("the entity column is read-only"));
        }
        let shape = Box::into_raw(Box::new(Shape {
            extent: rows as ffi::Py_ssize_t,
            stride: item_size as ffi::Py_ssize_t,
        }));
        this.exports.fetch_add(1, Ordering::Relaxed);
        drop(world);
        drop(this);
        unsafe {
            (*view).buf = pointer;
            (*view).len = (rows * item_size) as ffi::Py_ssize_t;
            (*view).readonly = c_int::from(read_only);
            (*view).itemsize = item_size as ffi::Py_ssize_t;
            (*view).format = if (flags & ffi::PyBUF_FORMAT) == ffi::PyBUF_FORMAT {
                format.as_ptr().cast_mut()
            } else {
                std::ptr::null_mut()
            };
            (*view).ndim = 1;
            (*view).shape = &raw mut (*shape).extent;
            (*view).strides = &raw mut (*shape).stride;
            (*view).suboffsets = std::ptr::null_mut();
            (*view).internal = shape.cast();
            (*view).obj = slf.into_ptr();
        }
        Ok(())
    }

    /// Unpin the table and free the shape allocated above.
    ///
    /// # Safety
    ///
    /// Called by CPython once per successful `__getbuffer__`, with the
    /// same `view`.
    unsafe fn __releasebuffer__(&self, view: *mut ffi::Py_buffer) {
        unsafe {
            drop(Box::from_raw((*view).internal.cast::<Shape>()));
        }
        self.exports.fetch_sub(1, Ordering::Relaxed);
    }
}

/// One entity's handle, and the base of every generated view class.
///
/// `pyguara.columnar` subclasses this once per component type and hangs a
/// `FieldAccessor` on the subclass for each field, so `view.health` is a
/// descriptor call straight into this module with no Python frame in
/// between. That matters because the access is the unit cost of every
/// line of game code that touches an entity: measured, a Python
/// `property` doing the same work costs about 35 ns before it has read
/// anything.
#[pyclass(subclass)]
pub struct RowView {
    world: Py<NativeWorld>,
    entity: u64,
}

#[pymethods]
impl RowView {
    /// Bind a view to one entity of one world.
    #[new]
    fn new(world: Py<NativeWorld>, entity: u64) -> Self {
        Self { world, entity }
    }

    /// The entity this view reads and writes.
    #[getter]
    fn entity(&self) -> u64 {
        self.entity
    }
}

/// A descriptor reading and writing one field of a `RowView`.
#[pyclass]
pub struct FieldAccessor {
    table: usize,
    column: usize,
    /// For a two-column field, the tuple subclass a read returns.
    pair: Option<Py<pyo3::types::PyType>>,
}

/// Build `class(first, second)` for a tuple subclass, through `tuple`'s
/// own constructor rather than the subclass's.
///
/// `Vector2` subclasses `pymunk.Vec2d`, a `NamedTuple` whose `__new__` is
/// Python: constructing one costs about 210 ns, which would be most of a
/// read. This is `tuple.__new__(Vector2, (x, y))`, the spelling
/// `FlockingSystem` already uses for the same reason, reached without a
/// Python call. It runs `tuple`'s real allocator, so whatever a given
/// CPython keeps in a tuple header is initialised by the code that owns
/// it.
fn build_pair<'py>(
    class: &Bound<'py, pyo3::types::PyType>,
    first: f64,
    second: f64,
) -> PyResult<Bound<'py, PyAny>> {
    let python = class.py();
    let arguments = ((first, second),).into_pyobject(python)?;
    unsafe {
        let slot = ffi::PyType_GetSlot(&raw mut ffi::PyTuple_Type, ffi::Py_tp_new);
        let construct: ffi::newfunc = std::mem::transmute(slot);
        let raw = construct(class.as_type_ptr(), arguments.as_ptr(), std::ptr::null_mut());
        Bound::from_owned_ptr_or_err(python, raw)
    }
}

#[pymethods]
impl FieldAccessor {
    /// Bind to one field. `pair` is the class a two-column field reads as.
    #[new]
    #[pyo3(signature = (table, column, pair = None))]
    fn new(
        table: usize,
        column: usize,
        pair: Option<Bound<'_, pyo3::types::PyType>>,
    ) -> PyResult<Self> {
        if let Some(class) = &pair {
            if !class.is_subclass_of::<pyo3::types::PyTuple>()? {
                return Err(PyTypeError::new_err(
                    "a two-column field must read as a tuple subclass",
                ));
            }
        }
        Ok(Self {
            table,
            column,
            pair: pair.map(Bound::unbind),
        })
    }

    fn __get__<'py>(
        slf: &Bound<'py, Self>,
        instance: &Bound<'py, PyAny>,
        _owner: &Bound<'py, PyAny>,
    ) -> PyResult<Bound<'py, PyAny>> {
        if instance.is_none() {
            // Reached through the class, not an instance.
            return Ok(slf.clone().into_any());
        }
        let python = slf.py();
        let this = slf.borrow();
        let view = instance.downcast::<RowView>()?.borrow();
        let world = view.world.bind(python).borrow();
        let row = world.locate(this.table, view.entity)?;
        let held = &world.tables[this.table];
        match &this.pair {
            None => held.columns[this.column].get(python, row),
            Some(class) => match (&held.columns[this.column], &held.columns[this.column + 1]) {
                (Column::F64(first), Column::F64(second)) => {
                    build_pair(class.bind(python), first[row], second[row])
                }
                _ => Err(PyTypeError::new_err("a pair field needs two f8 columns")),
            },
        }
    }

    fn __set__(&self, instance: &Bound<'_, PyAny>, value: &Bound<'_, PyAny>) -> PyResult<()> {
        let python = instance.py();
        let view = instance.downcast::<RowView>()?.borrow();
        let mut world = view.world.bind(python).borrow_mut();
        match &self.pair {
            None => world.set(self.table, view.entity, self.column, value),
            Some(_) => {
                let first: f64 = value.get_item(0)?.extract()?;
                let second: f64 = value.get_item(1)?.extract()?;
                world.set_pair(self.table, view.entity, self.column, first, second)
            }
        }
    }
}
