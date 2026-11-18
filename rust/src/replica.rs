//! A guest's view of replicated state: snapshot records in, blended values
//! out, for the components whose every field interpolates.
//!
//! `ReplicationClient` hands over each record it accepts, as the bytes it
//! received, and asks once a frame for the values to write at the render
//! tick. Decoding, the per-entity history and the blending all happen here,
//! so a frame costs one crossing in and the component writes out, rather
//! than a Python loop over every field of every entity.
//!
//! The arithmetic is the Python codecs', in the same order and in f64, so
//! the result is bit for bit what `ComponentSchema.write_blended` produced.
//! Python's float `%` is floored, not truncated; `py_mod` reproduces it.
//!
//! Components with a field that does not interpolate -- an integer, a flag,
//! an enum, a name -- stay in Python: their values are Python objects, and
//! they change only when a snapshot does.

use std::collections::HashMap;
use std::f64::consts::{PI, TAU};

use pyo3::exceptions::PyValueError;
use pyo3::prelude::*;
use pyo3::types::PyTuple;

use crate::vector::Point;

/// Samples kept per remote, as `replication._HISTORY`.
const DEFAULT_HISTORY: usize = 16;

#[derive(Clone, Copy)]
enum Int {
    I16,
    I32,
    U8,
    U16,
}

impl Int {
    fn parse(code: &str) -> PyResult<Self> {
        match code {
            "h" => Ok(Int::I16),
            "i" => Ok(Int::I32),
            "B" => Ok(Int::U8),
            "H" => Ok(Int::U16),
            other => Err(PyValueError::new_err(format!(
                "no interpolated field is packed as {other:?}"
            ))),
        }
    }

    fn width(self) -> usize {
        match self {
            Int::U8 => 1,
            Int::I16 | Int::U16 => 2,
            Int::I32 => 4,
        }
    }

    /// Read one little-endian value. The caller has checked it fits.
    fn read(self, bytes: &[u8]) -> f64 {
        match self {
            Int::I16 => f64::from(i16::from_le_bytes([bytes[0], bytes[1]])),
            Int::I32 => f64::from(i32::from_le_bytes([bytes[0], bytes[1], bytes[2], bytes[3]])),
            Int::U8 => f64::from(bytes[0]),
            Int::U16 => f64::from(u16::from_le_bytes([bytes[0], bytes[1]])),
        }
    }
}

/// How one field decodes and blends; mirrors a codec in `pyguara/net/schema.py`.
#[derive(Clone, Copy)]
enum Field {
    /// `Quantised`: `packed * step`, blended linearly.
    Scalar { int: Int, step: f64 },
    /// `QuantisedVector`: two of `Scalar`, snapping past `snap_squared`.
    Vector { int: Int, step: f64, snap_squared: Option<f64> },
    /// `Angle`: `packed / steps * tau`, blended the short way round.
    Angle { int: Int, steps: f64 },
}

impl Field {
    fn bytes(self) -> usize {
        match self {
            Field::Scalar { int, .. } | Field::Angle { int, .. } => int.width(),
            Field::Vector { int, .. } => 2 * int.width(),
        }
    }

    fn lanes(self) -> usize {
        match self {
            Field::Vector { .. } => 2,
            _ => 1,
        }
    }
}

/// One registered component: its size on the wire, and its fields if every
/// one of them interpolates.
struct Component {
    size: usize,
    fields: Option<Vec<Field>>,
    lanes: usize,
}

/// One accepted record: its tick, its bytes, and the decoded lanes of the
/// interpolating components it carries, by component index.
struct Sample {
    tick: i64,
    record: Vec<u8>,
    values: Vec<Option<Vec<f64>>>,
}

#[derive(PartialEq, Clone, Copy)]
enum Written {
    Nothing,
    Held(i64),
    Blended,
}

struct Remote {
    history: Vec<Sample>,
    /// The interpolating components to write, once the entity exists: each
    /// one's index and the live component object.
    write: Vec<(usize, Py<PyAny>)>,
    active: bool,
    written: Written,
}

/// Python's float `%`: the result takes the divisor's sign.
fn py_mod(value: f64, divisor: f64) -> f64 {
    let remainder = value % divisor;
    if remainder != 0.0 {
        if (divisor < 0.0) != (remainder < 0.0) {
            return remainder + divisor;
        }
        return remainder;
    }
    0.0f64.copysign(divisor)
}

/// Keeps every remote's recent interpolating state, and blends it.
#[pyclass]
pub struct NativeInterpolator {
    components: Vec<Component>,
    /// Per component index, `writer(component, *values)` for the
    /// interpolating ones.
    writers: Vec<Option<Py<PyAny>>>,
    remotes: HashMap<u64, Remote>,
    history_limit: usize,
}

impl NativeInterpolator {
    fn decode(&self, record: &[u8], mask: u64) -> PyResult<Vec<Option<Vec<f64>>>> {
        if mask >> self.components.len() != 0 {
            return Err(PyValueError::new_err("a record names a component that does not exist"));
        }
        let mut values = Vec::with_capacity(self.components.len());
        let mut offset = 0usize;
        for (index, component) in self.components.iter().enumerate() {
            if mask >> index & 1 == 0 {
                values.push(None);
                continue;
            }
            let end = offset + component.size;
            if end > record.len() {
                return Err(PyValueError::new_err("a record does not fit its mask"));
            }
            values.push(component.fields.as_ref().map(|fields| {
                let mut lanes = Vec::with_capacity(component.lanes);
                let mut at = offset;
                for field in fields {
                    match *field {
                        Field::Scalar { int, step } => {
                            lanes.push(int.read(&record[at..]) * step);
                        }
                        Field::Vector { int, step, .. } => {
                            lanes.push(int.read(&record[at..]) * step);
                            lanes.push(int.read(&record[at + int.width()..]) * step);
                        }
                        Field::Angle { int, steps } => {
                            lanes.push(int.read(&record[at..]) / steps * TAU);
                        }
                    }
                    at += field.bytes();
                }
                lanes
            }));
            offset = end;
        }
        if offset != record.len() {
            return Err(PyValueError::new_err("a record is longer than its mask"));
        }
        Ok(values)
    }

    /// The value of every field of one component, `amount` of the way from
    /// `older` to `newer`, as `ComponentSchema.write_blended` computes it.
    fn blend(fields: &[Field], older: &[f64], newer: &[f64], amount: f64) -> Vec<f64> {
        let mut out = Vec::with_capacity(older.len());
        let mut lane = 0usize;
        for field in fields {
            match *field {
                Field::Scalar { .. } => {
                    let (old, new) = (older[lane], newer[lane]);
                    out.push(if old == new { old } else { old + (new - old) * amount });
                }
                Field::Angle { .. } => {
                    let (old, new) = (older[lane], newer[lane]);
                    out.push(if old == new {
                        old
                    } else {
                        let difference = py_mod(new - old + PI, TAU) - PI;
                        old + difference * amount
                    });
                }
                Field::Vector { snap_squared, .. } => {
                    let (old_x, old_y) = (older[lane], older[lane + 1]);
                    let (new_x, new_y) = (newer[lane], newer[lane + 1]);
                    if old_x == new_x && old_y == new_y {
                        out.push(old_x);
                        out.push(old_y);
                    } else {
                        let delta_x = new_x - old_x;
                        let delta_y = new_y - old_y;
                        let jumped = snap_squared
                            .is_some_and(|snap| delta_x * delta_x + delta_y * delta_y > snap);
                        if jumped {
                            out.push(new_x);
                            out.push(new_y);
                        } else {
                            out.push(old_x + delta_x * amount);
                            out.push(old_y + delta_y * amount);
                        }
                    }
                }
            }
            lane += field.lanes();
        }
        out
    }

    /// Write one component's values through its writer: a vector field as
    /// a `Vector2`, every other field as a float.
    fn call(
        &self,
        py: Python<'_>,
        index: usize,
        component: &Py<PyAny>,
        lanes: &[f64],
    ) -> PyResult<()> {
        let fields = self.components[index]
            .fields
            .as_ref()
            .expect("only interpolating components are written");
        let writer = self.writers[index]
            .as_ref()
            .expect("an interpolating component has a writer");
        let mut arguments: Vec<Py<PyAny>> = Vec::with_capacity(fields.len() + 1);
        arguments.push(component.clone_ref(py));
        let mut lane = 0usize;
        for field in fields {
            match field {
                Field::Vector { .. } => arguments.push(
                    Point::of(lanes[lane], lanes[lane + 1]).into_pyobject(py)?.into_any().unbind(),
                ),
                _ => arguments.push(lanes[lane].into_pyobject(py)?.into_any().unbind()),
            }
            lane += field.lanes();
        }
        writer.call1(py, PyTuple::new(py, arguments)?)?;
        Ok(())
    }
}

#[pymethods]
impl NativeInterpolator {
    /// Describe the schema.
    ///
    /// Args:
    ///     components: One entry per registered component, in mask order:
    ///         `(size_in_bytes, fields)`, where `fields` is None unless every
    ///         field interpolates, and otherwise a list of
    ///         `(kind, int_code, parameter, snap_squared)` with `kind` one of
    ///         "scalar" (parameter is the step), "vector" (the step) and
    ///         "angle" (the number of steps in a turn).
    ///     writers: Per component, `writer(component, *values)`, or None for
    ///         one that does not interpolate.
    ///     history: Samples kept per remote.
    #[new]
    #[pyo3(signature = (components, writers, history = DEFAULT_HISTORY))]
    fn new(
        components: Vec<(usize, Option<Vec<(String, String, f64, Option<f64>)>>)>,
        writers: Vec<Option<Py<PyAny>>>,
        history: usize,
    ) -> PyResult<Self> {
        if writers.len() != components.len() {
            return Err(PyValueError::new_err("one writer entry per component"));
        }
        if components.len() > 32 {
            return Err(PyValueError::new_err("a record mask holds at most 32 components"));
        }
        let mut parsed = Vec::with_capacity(components.len());
        for (size, fields) in components {
            let fields = match fields {
                None => None,
                Some(specs) => {
                    let mut list = Vec::with_capacity(specs.len());
                    for (kind, code, parameter, snap) in specs {
                        let int = Int::parse(&code)?;
                        let field = match kind.as_str() {
                            "scalar" => Field::Scalar { int, step: parameter },
                            "vector" => Field::Vector { int, step: parameter, snap_squared: snap },
                            "angle" => Field::Angle { int, steps: parameter },
                            other => {
                                return Err(PyValueError::new_err(format!(
                                    "no field kind {other:?}"
                                )))
                            }
                        };
                        list.push(field);
                    }
                    let bytes: usize = list.iter().map(|f| f.bytes()).sum();
                    if bytes != size {
                        return Err(PyValueError::new_err(format!(
                            "fields take {bytes} bytes but the component is {size}"
                        )));
                    }
                    Some(list)
                }
            };
            let lanes = fields
                .as_ref()
                .map_or(0, |f: &Vec<Field>| f.iter().map(|field| field.lanes()).sum());
            parsed.push(Component { size, fields, lanes });
        }
        for (index, component) in parsed.iter().enumerate() {
            if component.fields.is_some() != writers[index].is_some() {
                return Err(PyValueError::new_err(format!(
                    "component {index} needs a writer exactly when it interpolates"
                )));
            }
        }
        Ok(Self {
            components: parsed,
            writers,
            remotes: HashMap::new(),
            history_limit: history.max(1),
        })
    }

    /// Record an accepted sample for a remote.
    ///
    /// The caller has already decided it is not stale. Raises ValueError,
    /// keeping nothing, if the record does not match its mask.
    fn push(&mut self, handle: u64, tick: i64, record: &[u8], mask: u64) -> PyResult<()> {
        let values = self.decode(record, mask)?;
        let limit = self.history_limit;
        let remote = self.remotes.entry(handle).or_insert_with(|| Remote {
            history: Vec::new(),
            write: Vec::new(),
            active: false,
            written: Written::Nothing,
        });
        remote.history.push(Sample { tick, record: record.to_vec(), values });
        if remote.history.len() > limit {
            remote.history.remove(0);
        }
        Ok(())
    }

    /// Start writing these interpolating components of a remote, given as
    /// `(index, component)`.
    fn activate(&mut self, handle: u64, components: Vec<(usize, Py<PyAny>)>) -> PyResult<()> {
        for (index, _) in &components {
            let index = *index;
            if self.components.get(index).and_then(|c| c.fields.as_ref()).is_none() {
                return Err(PyValueError::new_err(format!(
                    "component {index} does not interpolate"
                )));
            }
        }
        if let Some(remote) = self.remotes.get_mut(&handle) {
            remote.write = components;
            remote.active = true;
            remote.written = Written::Nothing;
        }
        Ok(())
    }

    /// Forget a remote and everything kept for it.
    fn forget(&mut self, handle: u64) {
        self.remotes.remove(&handle);
    }

    /// How many remotes are kept. For tests.
    fn __len__(&self) -> usize {
        self.remotes.len()
    }

    /// Write every active remote's components as they are at `render`.
    ///
    /// Mirrors `ReplicationClient._apply_interpolated`: hold the newest
    /// sample past it, hold the oldest before it, hold either side when the
    /// two records are the same, and otherwise blend. A held sample is
    /// written once, not every frame.
    ///
    /// Returns:
    ///     How many components were written.
    fn interpolate(&mut self, py: Python<'_>, render: f64) -> PyResult<usize> {
        enum Plan {
            Hold(usize),
            Blend(usize, f64),
        }
        let mut writes: Vec<(Py<PyAny>, usize, Vec<f64>)> = Vec::new();
        for remote in self.remotes.values_mut() {
            if !remote.active || remote.history.is_empty() || remote.write.is_empty() {
                continue;
            }
            let history = &remote.history;
            let newest = history.len() - 1;
            let plan = if render >= history[newest].tick as f64 {
                Plan::Hold(newest)
            } else {
                let index = history.partition_point(|sample| sample.tick as f64 <= render);
                if index == 0 {
                    Plan::Hold(0)
                } else if history[index - 1].record == history[index].record {
                    Plan::Hold(index - 1)
                } else {
                    let older = &history[index - 1];
                    let newer = &history[index];
                    let amount =
                        (render - older.tick as f64) / (newer.tick - older.tick) as f64;
                    Plan::Blend(index, amount)
                }
            };
            match plan {
                Plan::Hold(at) => {
                    let tick = history[at].tick;
                    if remote.written == Written::Held(tick) {
                        continue;
                    }
                    for (index, component) in &remote.write {
                        if let Some(Some(values)) = history[at].values.get(*index) {
                            writes.push((component.clone_ref(py), *index, values.clone()));
                        }
                    }
                    remote.written = Written::Held(tick);
                }
                Plan::Blend(index, amount) => {
                    let older = &history[index - 1];
                    let newer = &history[index];
                    for (index, component) in &remote.write {
                        let index = *index;
                        let (Some(Some(old)), Some(Some(new))) =
                            (older.values.get(index), newer.values.get(index))
                        else {
                            continue;
                        };
                        let fields = self.components[index]
                            .fields
                            .as_ref()
                            .expect("activate checked it interpolates");
                        writes.push((
                            component.clone_ref(py),
                            index,
                            Self::blend(fields, old, new, amount),
                        ));
                    }
                    remote.written = Written::Blended;
                    remote.history.drain(..index.saturating_sub(2));
                }
            }
        }
        for (component, index, lanes) in &writes {
            self.call(py, *index, component, lanes)?;
        }
        Ok(writes.len())
    }
}
