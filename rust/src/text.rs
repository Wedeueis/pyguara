//! Text, rasterised for the wgpu backend: what `pygame.font` did on that path.
//!
//! **Layout follows SDL_ttf**, which is what `pygame.font` is, so a string is
//! the same size on both renderers and a UI laid out on one fits on the
//! other: a size is pixels per em (SDL asks FreeType for 72 dpi, where a
//! point is a pixel), ascent and descent are rounded outwards, a string is
//! `ascent - descent` tall, and the line advance is the font's own. Pen
//! positions carry kerning.
//!
//! **Pixels do not follow it exactly.** FreeType hints glyph outlines to the
//! pixel grid and fontdue does not, so a stem may sit across two columns
//! here where FreeType snapped it to one. The tests bound the difference.
//!
//! The default faces are Liberation Sans 2.1.5 (SIL OFL), embedded from
//! `pyguara/graphics/fonts/` -- the same files the pygame renderer opens, so
//! the two backends draw one typeface.

use std::collections::HashMap;
use std::sync::{Arc, OnceLock};

use fontdue::{Font, FontSettings, Metrics};
use pyo3::exceptions::{PyOSError, PyValueError};
use pyo3::prelude::*;
use pyo3::types::PyBytes;

const REGULAR: &[u8] = include_bytes!("../../pyguara/graphics/fonts/LiberationSans-Regular.ttf");
const BOLD: &[u8] = include_bytes!("../../pyguara/graphics/fonts/LiberationSans-Bold.ttf");
const ITALIC: &[u8] = include_bytes!("../../pyguara/graphics/fonts/LiberationSans-Italic.ttf");
const BOLD_ITALIC: &[u8] = include_bytes!("../../pyguara/graphics/fonts/LiberationSans-BoldItalic.ttf");

fn parse(bytes: &[u8]) -> Result<Font, String> {
    Font::from_bytes(bytes, FontSettings::default()).map_err(str::to_owned)
}

/// The four default faces, parsed once per process.
fn defaults() -> &'static [Arc<Font>; 4] {
    static FACES: OnceLock<[Arc<Font>; 4]> = OnceLock::new();
    FACES.get_or_init(|| {
        [REGULAR, BOLD, ITALIC, BOLD_ITALIC]
            .map(|bytes| Arc::new(parse(bytes).expect("the embedded font is a valid TTF")))
    })
}

/// One glyph, rasterised at one size: its metrics and coverage.
type Glyph = (Metrics, Vec<u8>);

/// A face at one size.
///
/// Rasterised glyphs are cached, so a HUD redrawing the same digits costs a
/// lookup per character.
#[pyclass]
pub struct NativeFont {
    font: Arc<Font>,
    px: f32,
    ascent: i32,
    descent: i32,
    line: i32,
    glyphs: HashMap<char, Glyph>,
}

impl NativeFont {
    fn at(font: Arc<Font>, size: u32) -> PyResult<Self> {
        if size == 0 {
            return Err(PyValueError::new_err("a font size must be at least 1"));
        }
        let px = size as f32;
        let metrics = font
            .horizontal_line_metrics(px)
            .ok_or_else(|| PyValueError::new_err("the font has no horizontal metrics"))?;
        // SDL_ttf's FT_CEIL on both: the descent is negative, so rounding it
        // up moves it towards the baseline, as SDL does.
        let ascent = metrics.ascent.ceil() as i32;
        // The height is the whole extent rounded up once, not the two
        // halves each rounded: `ascent - descent` below is what SDL_ttf's
        // `TTF_FontHeight` returns.
        let descent = ascent - (metrics.ascent - metrics.descent).ceil() as i32;
        let line = metrics.new_line_size.ceil() as i32;
        Ok(Self { font, px, ascent, descent, line, glyphs: HashMap::new() })
    }

    fn glyph(&mut self, character: char) -> &Glyph {
        let (font, px) = (&self.font, self.px);
        self.glyphs
            .entry(character)
            .or_insert_with(|| font.rasterize(character, px))
    }

    /// Lay a string out: each glyph's left edge on the pen, and the extent.
    ///
    /// Returns the glyphs' left edges, the leftmost pixel (negative when a
    /// glyph overhangs the start, as an italic can) and the rightmost.
    fn layout(&mut self, text: &str) -> (Vec<(char, i32)>, i32, i32) {
        let mut placed = Vec::with_capacity(text.len());
        let mut pen = 0.0f32;
        let mut previous: Option<char> = None;
        let (mut left, mut right) = (0i32, 0i32);
        for character in text.chars() {
            if let Some(before) = previous {
                pen += self.font.horizontal_kern(before, character, self.px).unwrap_or(0.0);
            }
            let origin = pen.floor() as i32;
            let (metrics, _) = *self.glyph(character);
            let x = origin + metrics.xmin;
            if metrics.width > 0 {
                left = left.min(x);
                right = right.max(x + metrics.width as i32);
            }
            placed.push((character, x));
            // A hinted advance is whole pixels, which is what FreeType hands
            // SDL_ttf; kerning stays fractional, as HarfBuzz positions it.
            pen += metrics.advance_width.round();
            previous = Some(character);
        }
        right = right.max(pen.floor() as i32);
        (placed, left, right)
    }
}

#[pymethods]
impl NativeFont {
    /// The engine's default face at a size.
    ///
    /// Args:
    ///     size: Pixels per em, as a `pygame.font` size.
    ///     bold: The bold face.
    ///     italic: The italic face.
    #[new]
    #[pyo3(signature = (size, bold=false, italic=false))]
    fn new(size: u32, bold: bool, italic: bool) -> PyResult<Self> {
        let index = usize::from(bold) | (usize::from(italic) << 1);
        Self::at(defaults()[index].clone(), size)
    }

    /// A face from a font file's bytes, at a size.
    ///
    /// Args:
    ///     data: The contents of a `.ttf` or `.otf`.
    ///     size: Pixels per em.
    ///
    /// Raises:
    ///     OSError: If the bytes are not a font.
    #[staticmethod]
    fn from_bytes(data: &[u8], size: u32) -> PyResult<Self> {
        let font = parse(data).map_err(|error| PyOSError::new_err(format!("not a font: {error}")))?;
        Self::at(Arc::new(font), size)
    }

    /// The pixel height of any string: ascent minus descent.
    #[getter]
    fn height(&self) -> i32 {
        self.ascent - self.descent
    }

    /// The distance from one baseline to the next, leading included.
    #[getter]
    fn line_height(&self) -> i32 {
        self.line
    }

    /// The baseline's distance below the top of a rendered string.
    #[getter]
    fn ascent(&self) -> i32 {
        self.ascent
    }

    /// Each character's unhinted metrics, for checking layout against
    /// another rasteriser: `(xmin, width, advance, kerning before it)`.
    fn glyph_metrics(&mut self, text: &str) -> Vec<(i32, usize, f32, f32)> {
        let mut out = Vec::new();
        let mut previous: Option<char> = None;
        for character in text.chars() {
            let kern = previous
                .and_then(|before| self.font.horizontal_kern(before, character, self.px))
                .unwrap_or(0.0);
            let (metrics, _) = *self.glyph(character);
            out.push((metrics.xmin, metrics.width, metrics.advance_width, kern));
            previous = Some(character);
        }
        out
    }

    /// The size `render` would make, without rasterising anything new.
    fn size(&mut self, text: &str) -> (i32, i32) {
        let (_, left, right) = self.layout(text);
        (right - left, self.height())
    }

    /// Rasterise a string, white, its coverage in the alpha channel.
    ///
    /// Returns:
    ///     `(pixels, width, height)`: RGBA, top row first. The width is 0
    ///     for a string with nothing to draw.
    fn render<'py>(&mut self, py: Python<'py>, text: &str) -> (Bound<'py, PyBytes>, i32, i32) {
        let (placed, left, right) = self.layout(text);
        let (width, height) = (right - left, self.height());
        if width <= 0 || height <= 0 {
            return (PyBytes::new(py, &[]), 0, height.max(0));
        }
        let (width_u, height_u) = (width as usize, height as usize);
        let mut alpha = vec![0u8; width_u * height_u];
        let ascent = self.ascent;
        for (character, x) in placed {
            let (metrics, coverage) = self.glyph(character);
            // `ymin` is the bitmap's bottom edge above the baseline.
            let top = ascent - (metrics.ymin + metrics.height as i32);
            let x = x - left;
            for row in 0..metrics.height {
                let y = top + row as i32;
                if y < 0 || y >= height {
                    continue;
                }
                for column in 0..metrics.width {
                    let at = x + column as i32;
                    if at < 0 || at >= width {
                        continue;
                    }
                    let index = y as usize * width_u + at as usize;
                    // Overlapping glyphs keep the stronger coverage, as
                    // SDL_ttf's blended renderer does.
                    alpha[index] = alpha[index].max(coverage[row * metrics.width + column]);
                }
            }
        }
        let mut pixels = Vec::with_capacity(alpha.len() * 4);
        for value in alpha {
            pixels.extend_from_slice(&[255, 255, 255, value]);
        }
        (PyBytes::new(py, &pixels), width, height)
    }
}
