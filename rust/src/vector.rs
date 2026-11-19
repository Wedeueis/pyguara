//! `Vector2`, the engine's 2D value type, and `Pair`, the argument type
//! native code reads a point through.
//!
//! Every formula is spelled as the Python it replaced spelled it, operation
//! for operation, so results are the same floats. Squares are `x * x`: the
//! spelling `length` already used (ADR 0004, Decision 5). Python's `x ** 2`
//! differs from it in the last bit for some inputs and cannot be reproduced
//! here, so the few methods that used it now agree with `length` instead.
//!
//! Equality and hashing match a plain `(x, y)` tuple, which is what a
//! `Vector2` was: `Vector2(1, 2) == (1, 2)` still holds, and the two hash
//! alike, so neither a comparison nor a dict lookup changes its answer.

use std::ffi::CStr;

use pyo3::basic::CompareOp;
use pyo3::ffi;
use pyo3::exceptions::{
    PyIndexError, PyOverflowError, PyTypeError, PyValueError, PyZeroDivisionError,
};
use pyo3::intern;
use pyo3::prelude::*;
use pyo3::types::{PyBool, PyFloat, PyIterator, PyList, PyTuple, PyType};

/// An immutable 2D vector for positions, velocities and directions.
///
/// Y increases downwards, so "up" is negative Y. Every method returns a new
/// vector. It unpacks, indexes and has a length of 2 like the `(x, y)`
/// tuple it equals, and its components are always floats.
///
/// The components are held twice: as `f64` for arithmetic, and as the
/// Python floats `x` and `y` return, so a read hands back an existing
/// object as reading a tuple field does, rather than allocating one.
#[pyclass(frozen, sequence, module = "pyguara.pyguara_core_rs", name = "Vector2")]
pub struct Vector2 {
    point: Point,
    x_object: Py<PyFloat>,
    y_object: Py<PyFloat>,
}

/// A vector's two components, as native code works with them. Returned to
/// Python, it becomes a `Vector2`.
#[derive(Clone, Copy, Debug, PartialEq)]
pub struct Point {
    /// The X component.
    pub x: f64,
    /// The Y component, increasing downwards.
    pub y: f64,
}

impl std::ops::Deref for Vector2 {
    type Target = Point;

    fn deref(&self) -> &Point {
        &self.point
    }
}

impl<'py> IntoPyObject<'py> for Point {
    type Target = Vector2;
    type Output = Bound<'py, Vector2>;
    type Error = PyErr;

    fn into_pyobject(self, python: Python<'py>) -> PyResult<Bound<'py, Vector2>> {
        Bound::new(
            python,
            Vector2 {
                point: self,
                x_object: PyFloat::new(python, self.x).unbind(),
                y_object: PyFloat::new(python, self.y).unbind(),
            },
        )
    }
}

/// Give `Vector2` member descriptors for `x` and `y`.
///
/// CPython reads an object member by loading the pointer at its offset, as
/// it reads a tuple field; a PyO3 getter costs a trampoline and a new float
/// on top, and reading components is most of what game code does with a
/// vector. The offsets are measured from a real instance rather than
/// assumed, and the class cannot be subclassed, so every instance has this
/// layout.
pub fn install_component_members(python: Python<'_>) -> PyResult<()> {
    let class = python.get_type::<Vector2>();
    let probe = Point::of(0.0, 0.0).into_pyobject(python)?;
    let start = probe.as_ptr() as usize;
    let fields = probe.get();
    let members: [(&'static CStr, usize, &'static CStr); 2] = [
        (c"x", std::ptr::from_ref(&fields.x_object) as usize - start, c"The X component."),
        (
            c"y",
            std::ptr::from_ref(&fields.y_object) as usize - start,
            c"The Y component, increasing downwards.",
        ),
    ];
    for (name, offset, doc) in members {
        // CPython keeps a pointer to the definition for the descriptor's
        // lifetime, which is the interpreter's, so it is leaked on purpose.
        let definition = Box::leak(Box::new(ffi::PyMemberDef {
            name: name.as_ptr(),
            type_code: ffi::Py_T_OBJECT_EX,
            offset: ffi::Py_ssize_t::try_from(offset)?,
            flags: ffi::Py_READONLY,
            doc: doc.as_ptr(),
        }));
        // SAFETY: `definition` is leaked, so it outlives the class, and its
        // name and doc are static C strings; the call returns a new reference
        // or null with an exception set, which `from_owned_ptr_or_err` takes.
        let descriptor = unsafe {
            Bound::from_owned_ptr_or_err(
                python,
                ffi::PyDescr_NewMember(class.as_type_ptr(), definition),
            )?
        };
        class.setattr(name.to_str()?, descriptor)?;
    }
    Ok(())
}

/// A point read from Python: a `Vector2`, a two-item tuple or list, or
/// anything with numeric `x` and `y` attributes.
#[derive(Clone, Copy, Debug)]
pub struct Pair(pub f64, pub f64);

impl<'py> FromPyObject<'py> for Pair {
    fn extract_bound(value: &Bound<'py, PyAny>) -> PyResult<Self> {
        if let Ok(vector) = value.downcast::<Vector2>() {
            let vector = vector.get();
            return Ok(Pair(vector.x, vector.y));
        }
        if let Ok(tuple) = value.downcast::<PyTuple>() {
            if tuple.len() == 2 {
                return Ok(Pair(tuple.get_item(0)?.extract()?, tuple.get_item(1)?.extract()?));
            }
        } else if let Ok(list) = value.downcast::<PyList>() {
            if list.len() == 2 {
                return Ok(Pair(list.get_item(0)?.extract()?, list.get_item(1)?.extract()?));
            }
        } else {
            let python = value.py();
            if let (Ok(x), Ok(y)) = (
                value.getattr(intern!(python, "x")),
                value.getattr(intern!(python, "y")),
            ) {
                return Ok(Pair(x.extract()?, y.extract()?));
            }
        }
        Err(PyTypeError::new_err(format!(
            "expected a Vector2 or an (x, y) pair, got {}",
            value.get_type().name()?
        )))
    }
}

impl Point {
    /// A vector from two components.
    pub const fn of(x: f64, y: f64) -> Self {
        Self { x, y }
    }

    fn length_of(self) -> f64 {
        (self.x * self.x + self.y * self.y).sqrt()
    }

    fn scaled(self, factor: f64) -> Self {
        Self::of(self.x * factor, self.y * factor)
    }

    fn divided(self, divisor: f64) -> PyResult<Self> {
        if divisor == 0.0 {
            return Err(PyZeroDivisionError::new_err("float division by zero"));
        }
        Ok(Self::of(self.x / divisor, self.y / divisor))
    }

    fn rotated_by(self, angle_radians: f64) -> PyResult<Self> {
        let (sin, cos) = sin_cos(angle_radians)?;
        Ok(Self::of(self.x * cos - self.y * sin, self.x * sin + self.y * cos))
    }

    fn projection_onto(self, other: Pair) -> Self {
        let other_length_squared = other.0 * other.0 + other.1 * other.1;
        if other_length_squared == 0.0 {
            return Self::of(0.0, 0.0);
        }
        let new_length = (self.x * other.0 + self.y * other.1) / other_length_squared;
        Self::of(other.0 * new_length, other.1 * new_length)
    }

    fn angle_between(self, other: Pair) -> f64 {
        let cross = self.x * other.1 - self.y * other.0;
        let dot = self.x * other.0 + self.y * other.1;
        cross.atan2(dot)
    }
}

/// Python's float `//`: the quotient from `fmod`, corrected towards
/// negative infinity, then floored with Python's tie rule. Flooring `a / b`
/// directly differs from it near integers.
fn floor_divide(a: f64, b: f64) -> PyResult<f64> {
    if b == 0.0 {
        return Err(PyZeroDivisionError::new_err("float floor division by zero"));
    }
    let remainder = a % b;
    let mut quotient = (a - remainder) / b;
    if remainder != 0.0 && (b < 0.0) != (remainder < 0.0) {
        quotient -= 1.0;
    }
    if quotient == 0.0 {
        return Ok(0.0f64.copysign(a / b));
    }
    let mut floored = quotient.floor();
    if quotient - floored > 0.5 {
        floored += 1.0;
    }
    Ok(floored)
}

/// `math.sin` and `math.cos`, which raise for an infinite angle where the
/// C functions return NaN.
fn sin_cos(angle: f64) -> PyResult<(f64, f64)> {
    if angle.is_infinite() {
        return Err(PyValueError::new_err("math domain error"));
    }
    Ok((angle.sin(), angle.cos()))
}

/// Python's `round(value)` on a float, kept as a float: half to even, with
/// a signed zero dropped as converting to `int` drops it, and raising for a
/// non-finite value as that conversion does.
fn round_to_whole(value: f64) -> PyResult<f64> {
    if value.is_nan() {
        return Err(PyValueError::new_err("cannot convert float NaN to integer"));
    }
    if value.is_infinite() {
        return Err(PyOverflowError::new_err("cannot convert float infinity to integer"));
    }
    Ok(value.round_ties_even() + 0.0)
}

/// Python's `round(value)`: half to even, as an `int`, raising for a
/// non-finite value as Python does.
fn python_round<'py>(python: Python<'py>, value: f64) -> PyResult<Bound<'py, PyAny>> {
    python
        .import(intern!(python, "builtins"))?
        .getattr(intern!(python, "round"))?
        .call1((value,))
}

/// Python's `int(value)`: truncation towards zero, as an `int`.
fn python_int<'py>(python: Python<'py>, value: f64) -> PyResult<Bound<'py, PyAny>> {
    python
        .import(intern!(python, "builtins"))?
        .getattr(intern!(python, "int"))?
        .call1((value,))
}

const HASH_BITS: u32 = 61;
const HASH_MODULUS: u64 = (1 << HASH_BITS) - 1;

/// CPython's `hash(float)` for 64-bit builds: the value reduced modulo
/// 2**61 - 1, so a whole float hashes as the int it equals. A NaN, which
/// equals nothing, hashes as 0.
fn float_hash(value: f64) -> u64 {
    if value.is_nan() {
        return 0;
    }
    if value.is_infinite() {
        return if value > 0.0 { 314_159 } else { (-314_159i64) as u64 };
    }
    let (mut mantissa, mut exponent) = frexp(value);
    let mut sign = 1i64;
    if mantissa < 0.0 {
        sign = -1;
        mantissa = -mantissa;
    }
    let mut hash: u64 = 0;
    while mantissa != 0.0 {
        hash = ((hash << 28) & HASH_MODULUS) | (hash >> (HASH_BITS - 28));
        mantissa *= 268_435_456.0;
        exponent -= 28;
        let whole = mantissa as u64;
        mantissa -= whole as f64;
        hash += whole;
        if hash >= HASH_MODULUS {
            hash -= HASH_MODULUS;
        }
    }
    let bits = HASH_BITS as i32;
    let shift = if exponent >= 0 {
        exponent % bits
    } else {
        bits - 1 - ((-1 - exponent) % bits)
    } as u32;
    hash = ((hash << shift) & HASH_MODULUS) | (hash >> (HASH_BITS - shift));
    let signed = (hash as i64).wrapping_mul(sign) as u64;
    if signed == u64::MAX { u64::MAX - 1 } else { signed }
}

/// C's `frexp`: a mantissa in [0.5, 1) and an exponent, for a finite,
/// non-zero value; zero gives zero.
fn frexp(value: f64) -> (f64, i32) {
    if value == 0.0 {
        return (value, 0);
    }
    let bits = value.to_bits();
    let biased = ((bits >> 52) & 0x7ff) as i32;
    if biased == 0 {
        // Subnormal: scale into the normal range first.
        let (mantissa, exponent) = frexp(value * f64::from_bits(0x4350_0000_0000_0000));
        return (mantissa, exponent - 54);
    }
    let mantissa = f64::from_bits((bits & !(0x7ff << 52)) | (1022 << 52));
    (mantissa, biased - 1022)
}

/// CPython's hash of a tuple of two items with these hashes.
fn tuple_hash(lanes: [u64; 2]) -> isize {
    const PRIME_1: u64 = 11_400_714_785_074_694_791;
    const PRIME_2: u64 = 14_029_467_366_897_019_727;
    const PRIME_5: u64 = 2_870_177_450_012_600_261;
    let mut accumulator = PRIME_5;
    for lane in lanes {
        accumulator = accumulator.wrapping_add(lane.wrapping_mul(PRIME_2));
        accumulator = accumulator.rotate_left(31);
        accumulator = accumulator.wrapping_mul(PRIME_1);
    }
    accumulator = accumulator.wrapping_add(2 ^ (PRIME_5 ^ 3_527_539));
    if accumulator == u64::MAX {
        return 1_546_275_796;
    }
    accumulator as i64 as isize
}


/// A constructor argument as its value and the float object to hold: the
/// argument itself when it is already a float, so nothing is allocated.
fn as_float(value: &Bound<'_, PyAny>) -> PyResult<(f64, Py<PyFloat>)> {
    if let Ok(float) = value.downcast_exact::<PyFloat>() {
        return Ok((float.value(), float.clone().unbind()));
    }
    let number: f64 = value.extract()?;
    Ok((number, PyFloat::new(value.py(), number).unbind()))
}

#[pymethods]
impl Vector2 {
    #[new]
    #[pyo3(signature = (x, y))]
    fn new(x: &Bound<'_, PyAny>, y: &Bound<'_, PyAny>) -> PyResult<Self> {
        let (x_value, x_object) = as_float(x)?;
        let (y_value, y_object) = as_float(y)?;
        Ok(Self { point: Point::of(x_value, y_value), x_object, y_object })
    }

    #[classattr]
    fn __match_args__() -> (&'static str, &'static str) {
        ("x", "y")
    }

    // --- the tuple it equals -------------------------------------------

    fn __len__(&self) -> usize {
        2
    }

    fn __getitem__(&self, python: Python<'_>, index: isize) -> PyResult<Py<PyFloat>> {
        match index {
            0 | -2 => Ok(self.x_object.clone_ref(python)),
            1 | -1 => Ok(self.y_object.clone_ref(python)),
            _ => Err(PyIndexError::new_err("Vector2 index out of range")),
        }
    }

    fn __iter__<'py>(&self, python: Python<'py>) -> PyResult<Bound<'py, PyIterator>> {
        PyTuple::new(python, [self.x_object.bind(python), self.y_object.bind(python)])?.try_iter()
    }

    fn __richcmp__(
        &self,
        python: Python<'_>,
        other: &Bound<'_, PyAny>,
        op: CompareOp,
    ) -> PyResult<Py<PyAny>> {
        let equal = if let Ok(vector) = other.downcast::<Vector2>() {
            let vector = vector.get();
            self.x == vector.x && self.y == vector.y
        } else if let Ok(tuple) = other.downcast::<PyTuple>() {
            tuple.len() == 2
                && tuple.get_item(0)?.eq(self.x)?
                && tuple.get_item(1)?.eq(self.y)?
        } else {
            return Ok(python.NotImplemented());
        };
        match op {
            CompareOp::Eq => Ok(boolean(python, equal)),
            CompareOp::Ne => Ok(boolean(python, !equal)),
            _ => Ok(python.NotImplemented()),
        }
    }

    fn __hash__(&self) -> isize {
        tuple_hash([float_hash(self.x), float_hash(self.y)])
    }

    fn __bool__(&self) -> bool {
        self.x != 0.0 || self.y != 0.0
    }

    fn __repr__(&self, python: Python<'_>) -> PyResult<String> {
        Ok(format!(
            "Vector2({}, {})",
            PyFloat::new(python, self.x).repr()?,
            PyFloat::new(python, self.y).repr()?
        ))
    }

    fn __reduce__<'py>(slf: &Bound<'py, Self>) -> (Bound<'py, PyType>, (f64, f64)) {
        let vector = slf.get();
        (slf.get_type(), (vector.x, vector.y))
    }

    fn __copy__(slf: Bound<'_, Self>) -> Bound<'_, Self> {
        slf
    }

    fn __deepcopy__<'py>(slf: Bound<'py, Self>, _memo: &Bound<'py, PyAny>) -> Bound<'py, Self> {
        slf
    }

    // --- arithmetic ----------------------------------------------------

    fn __add__(&self, other: Pair) -> Point {
        Point::of(self.x + other.0, self.y + other.1)
    }

    fn __radd__(&self, other: Pair) -> Point {
        Point::of(other.0 + self.x, other.1 + self.y)
    }

    fn __sub__(&self, other: Pair) -> Point {
        Point::of(self.x - other.0, self.y - other.1)
    }

    fn __rsub__(&self, other: Pair) -> Point {
        Point::of(other.0 - self.x, other.1 - self.y)
    }

    fn __mul__(&self, other: f64) -> Point {
        self.scaled(other)
    }

    fn __rmul__(&self, other: f64) -> Point {
        self.scaled(other)
    }

    fn __truediv__(&self, other: f64) -> PyResult<Point> {
        self.divided(other)
    }

    fn __floordiv__(&self, other: f64) -> PyResult<Point> {
        Ok(Point::of(floor_divide(self.x, other)?, floor_divide(self.y, other)?))
    }

    fn __neg__(&self) -> Point {
        Point::of(-self.x, -self.y)
    }

    fn __pos__(&self) -> Point {
        self.point
    }

    fn __abs__(&self) -> f64 {
        self.length_of()
    }

    // --- length and angle ----------------------------------------------

    #[getter]
    fn length(&self) -> f64 {
        self.length_of()
    }

    #[getter]
    fn magnitude(&self) -> f64 {
        self.length_of()
    }

    #[getter]
    fn length_squared(&self) -> f64 {
        self.x * self.x + self.y * self.y
    }

    #[getter]
    fn sqr_magnitude(&self) -> f64 {
        self.x * self.x + self.y * self.y
    }

    #[getter]
    fn angle(&self) -> f64 {
        self.y.atan2(self.x)
    }

    #[getter]
    fn angle_degrees(&self) -> f64 {
        self.y.atan2(self.x).to_degrees()
    }

    #[getter]
    fn polar_tuple(&self) -> (f64, f64) {
        (self.length_of(), self.y.atan2(self.x))
    }

    #[getter]
    fn int_tuple<'py>(&self, python: Python<'py>) -> PyResult<Bound<'py, PyTuple>> {
        PyTuple::new(python, [python_round(python, self.x)?, python_round(python, self.y)?])
    }

    // --- products and distances ----------------------------------------

    fn dot(&self, other: Pair) -> f64 {
        self.x * other.0 + self.y * other.1
    }

    fn cross(&self, other: Pair) -> f64 {
        self.x * other.1 - self.y * other.0
    }

    fn get_distance(&self, other: Pair) -> f64 {
        self.get_distance_squared(other).sqrt()
    }

    fn distance_to(&self, other: Pair) -> f64 {
        self.get_distance_squared(other).sqrt()
    }

    fn get_distance_squared(&self, other: Pair) -> f64 {
        let dx = self.x - other.0;
        let dy = self.y - other.1;
        dx * dx + dy * dy
    }

    fn get_angle_between(&self, other: Pair) -> f64 {
        self.angle_between(other)
    }

    fn get_angle_degrees_between(&self, other: Pair) -> f64 {
        self.angle_between(other).to_degrees()
    }

    fn projection(&self, other: Pair) -> Point {
        self.projection_onto(other)
    }

    fn reject(&self, other: Pair) -> Point {
        let projected = self.projection_onto(other);
        Point::of(self.x - projected.x, self.y - projected.y)
    }

    fn convert_to_basis(&self, x_vector: Pair, y_vector: Pair) -> PyResult<Point> {
        let x_length_squared = x_vector.0 * x_vector.0 + x_vector.1 * x_vector.1;
        let y_length_squared = y_vector.0 * y_vector.0 + y_vector.1 * y_vector.1;
        if x_length_squared == 0.0 || y_length_squared == 0.0 {
            return Err(PyZeroDivisionError::new_err("float division by zero"));
        }
        Ok(Point::of(
            self.dot(x_vector) / x_length_squared,
            self.dot(y_vector) / y_length_squared,
        ))
    }

    fn cpvrotate(&self, other: Pair) -> Point {
        Point::of(self.x * other.0 - self.y * other.1, self.x * other.1 + self.y * other.0)
    }

    fn cpvunrotate(&self, other: Pair) -> Point {
        Point::of(self.x * other.0 + self.y * other.1, self.y * other.0 - self.x * other.1)
    }

    // --- direction -----------------------------------------------------

    fn normalize(&self) -> Point {
        let length = self.length_of();
        if length != 0.0 {
            return Point::of(self.x / length, self.y / length);
        }
        Point::of(0.0, 0.0)
    }

    fn normalized(&self) -> Point {
        self.normalize()
    }

    fn normalized_and_length(&self) -> (Point, f64) {
        let length = self.length_of();
        if length != 0.0 {
            return (Point::of(self.x / length, self.y / length), length);
        }
        (Point::of(0.0, 0.0), 0.0)
    }

    fn perpendicular(&self) -> Point {
        Point::of(-self.y, self.x)
    }

    fn perpendicular_normal(&self) -> Point {
        let length = self.length_of();
        if length != 0.0 {
            return Point::of(-self.y / length, self.x / length);
        }
        self.point
    }

    fn rotated(&self, angle_radians: f64) -> PyResult<Point> {
        self.rotated_by(angle_radians)
    }

    fn rotated_degrees(&self, angle_degrees: f64) -> PyResult<Point> {
        self.rotated_by(angle_degrees.to_radians())
    }

    fn rotate_degrees(&self, angle_degrees: f64) -> PyResult<Point> {
        self.rotated_by(angle_degrees.to_radians())
    }

    fn scale_to_length(&self, length: f64) -> PyResult<Point> {
        let old_length = self.length_of();
        if old_length == 0.0 {
            return Err(PyZeroDivisionError::new_err("float division by zero"));
        }
        Ok(Point::of(self.x * length / old_length, self.y * length / old_length))
    }

    fn clamp_magnitude(&self, max_length: f64) -> Point {
        if max_length <= 0.0 {
            return Point::of(0.0, 0.0);
        }
        let length = self.length_of();
        if length <= max_length || length == 0.0 {
            return self.point;
        }
        self.scaled(max_length / length)
    }

    fn reflect(&self, normal: Pair) -> Point {
        let length = (normal.0 * normal.0 + normal.1 * normal.1).sqrt();
        if length == 0.0 {
            return self.point;
        }
        let (nx, ny) = (normal.0 / length, normal.1 / length);
        let dot = self.x * nx + self.y * ny;
        Point::of(self.x - 2.0 * dot * nx, self.y - 2.0 * dot * ny)
    }

    // --- towards another point -----------------------------------------

    fn lerp(&self, target: Pair, t: f64) -> Point {
        Point::of(self.x + (target.0 - self.x) * t, self.y + (target.1 - self.y) * t)
    }

    fn interpolate_to(&self, other: Pair, range: f64) -> Point {
        self.lerp(other, range)
    }

    fn move_towards(&self, target: Pair, max_distance: f64) -> Point {
        if max_distance <= 0.0 {
            return self.point;
        }
        let delta = Point::of(target.0 - self.x, target.1 - self.y);
        let distance = delta.length_of();
        if distance <= max_distance || distance == 0.0 {
            return Point::of(target.0, target.1);
        }
        let scale = max_distance / distance;
        Point::of(self.x + delta.x * scale, self.y + delta.y * scale)
    }

    fn snapped(&self, grid: &Bound<'_, PyAny>) -> PyResult<Point> {
        let (step_x, step_y) = if let Ok(vector) = grid.downcast::<Vector2>() {
            let vector = vector.get();
            (vector.x, vector.y)
        } else {
            let step: f64 = grid.extract()?;
            (step, step)
        };
        let snap = |value: f64, step: f64| -> PyResult<f64> {
            if step == 0.0 {
                return Ok(value);
            }
            Ok(round_to_whole(value / step)? * step)
        };
        Ok(Point::of(snap(self.x, step_x)?, snap(self.y, step_y)?))
    }

    // --- conversions ---------------------------------------------------

    fn to_tuple(&self) -> (f64, f64) {
        (self.x, self.y)
    }

    fn to_int_tuple<'py>(&self, python: Python<'py>) -> PyResult<Bound<'py, PyTuple>> {
        PyTuple::new(python, [python_int(python, self.x)?, python_int(python, self.y)?])
    }

    // --- constructors --------------------------------------------------

    #[staticmethod]
    fn zero() -> Point {
        Point::of(0.0, 0.0)
    }

    #[staticmethod]
    fn one() -> Point {
        Point::of(1.0, 1.0)
    }

    #[staticmethod]
    fn ones() -> Point {
        Point::of(1.0, 1.0)
    }

    #[staticmethod]
    fn unit() -> Point {
        Point::of(0.0, 1.0)
    }

    #[staticmethod]
    fn up() -> Point {
        Point::of(0.0, -1.0)
    }

    #[staticmethod]
    fn down() -> Point {
        Point::of(0.0, 1.0)
    }

    #[staticmethod]
    fn left() -> Point {
        Point::of(-1.0, 0.0)
    }

    #[staticmethod]
    fn right() -> Point {
        Point::of(1.0, 0.0)
    }

    #[staticmethod]
    fn from_polar(length: f64, angle: f64) -> PyResult<Point> {
        let (sin, cos) = sin_cos(angle)?;
        Ok(Point::of(cos * length, sin * length))
    }

    #[staticmethod]
    #[pyo3(signature = (degrees, length = 1.0))]
    fn from_angle_degrees(degrees: f64, length: f64) -> PyResult<Point> {
        let (sin, cos) = sin_cos(degrees.to_radians())?;
        Ok(Point::of(cos * length, sin * length))
    }
}

/// A Python `bool`, as the object a rich comparison returns.
fn boolean(python: Python<'_>, value: bool) -> Py<PyAny> {
    PyBool::new(python, value).to_owned().into_any().unbind()
}
