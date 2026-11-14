//! Image files in and out, for the wgpu backend's textures and captures.
//!
//! What `pygame.image` did on that path: decode PNG, JPEG, BMP and TGA to
//! RGBA, and write a PNG. Pure Rust (the `image` crate), so the wheel gains
//! no system library.
//!
//! **Decoding releases the GIL**, as SDL_image did under pygame-ce:
//! `resources/async_load.py` loads textures on worker threads, and its
//! measured speed-up depends on the decode not holding the interpreter.

use pyo3::exceptions::{PyOSError, PyValueError};
use pyo3::prelude::*;
use pyo3::types::PyBytes;

/// Decode an image file to RGBA, top row first.
///
/// Args:
///     path: The file. Its format is read from its contents, with the
///         extension as a hint.
///
/// Returns:
///     `(pixels, width, height)`.
///
/// Raises:
///     OSError: If the file cannot be read or is not an image this decodes.
#[pyfunction]
pub fn decode_image<'py>(py: Python<'py>, path: &str) -> PyResult<(Bound<'py, PyBytes>, u32, u32)> {
    let decoded = py
        .detach(|| image::open(path).map(|image| image.into_rgba8()))
        .map_err(|error| PyOSError::new_err(format!("{path}: {error}")))?;
    let (width, height) = decoded.dimensions();
    Ok((PyBytes::new(py, decoded.as_raw()), width, height))
}

/// Multiply each pixel's colour by its alpha.
///
/// Rounds down, as the pygame loader's `uint8` cast did.
///
/// Args:
///     pixels: RGBA bytes.
///
/// Returns:
///     The premultiplied bytes.
#[pyfunction]
pub fn premultiply_rgba<'py>(py: Python<'py>, pixels: &[u8]) -> PyResult<Bound<'py, PyBytes>> {
    if pixels.len() % 4 != 0 {
        return Err(PyValueError::new_err(format!(
            "{} bytes is not a whole number of RGBA pixels",
            pixels.len()
        )));
    }
    let mut out = pixels.to_vec();
    for pixel in out.chunks_exact_mut(4) {
        let alpha = u32::from(pixel[3]);
        for channel in &mut pixel[..3] {
            *channel = (u32::from(*channel) * alpha / 255) as u8;
        }
    }
    Ok(PyBytes::new(py, &out))
}

/// Write RGBA pixels, top row first, as a PNG.
///
/// Args:
///     path: Where to write.
///     pixels: RGBA bytes, `width * height * 4` of them.
///     width: Width in pixels.
///     height: Height in pixels.
///
/// Raises:
///     ValueError: If the byte count does not match the size.
///     OSError: If the file cannot be written.
#[pyfunction]
pub fn encode_png(py: Python<'_>, path: &str, pixels: &[u8], width: u32, height: u32) -> PyResult<()> {
    let expected = width as usize * height as usize * 4;
    if pixels.len() != expected {
        return Err(PyValueError::new_err(format!(
            "{width}x{height} RGBA is {expected} bytes, got {}",
            pixels.len()
        )));
    }
    py.detach(|| image::save_buffer(path, pixels, width, height, image::ExtendedColorType::Rgba8))
        .map_err(|error| PyOSError::new_err(format!("{path}: {error}")))
}
