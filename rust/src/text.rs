//! Text, rasterised for the wgpu backend: what `pygame.font` did on that path.
//!
//! **Layout follows SDL_ttf**, which is what `pygame.font` is, so a string is
//! the same size on both renderers and a UI laid out on one fits on the
//! other: a size is pixels per em (SDL asks FreeType for 72 dpi, where a
//! point is a pixel), ascent and descent are rounded outwards, a string is
//! `ascent - descent` tall, and the line advance is the font's own. Pen
//! positions carry kerning.
//!
//! **Glyphs are hinted as FreeType hints them**: skrifa runs the font's own
//! TrueType instructions (its `fpgm`/`prep` programs) in FreeType's v40
//! normal mode, which snaps stems to the pixel grid and can widen an
//! advance -- Liberation Sans bold at 27 px turns a 16.49-pixel advance into
//! 17. The hinted outline is then filled by area coverage. What remains
//! different from FreeType is the coverage rasteriser's arithmetic, a shade
//! on an edge pixel; the tests bound it.
//!
//! The default faces are Liberation Sans 2.1.5 (SIL OFL), embedded from
//! `pyguara/graphics/fonts/` -- the same files the pygame renderer opens, so
//! the two backends draw one typeface.

use std::collections::HashMap;
use std::sync::{Arc, OnceLock};

use ab_glyph_rasterizer::{Rasterizer, point};
use pyo3::exceptions::{PyOSError, PyValueError};
use pyo3::prelude::*;
use pyo3::types::PyBytes;
use skrifa::instance::{LocationRef, Size};
use skrifa::outline::{DrawSettings, HintingInstance, HintingOptions, OutlinePen};
use skrifa::raw::TableProvider;
use skrifa::raw::tables::kern::SubtableKind;
use skrifa::{FontRef, GlyphId, MetadataProvider};

const REGULAR: &[u8] = include_bytes!("../../pyguara/graphics/fonts/LiberationSans-Regular.ttf");
const BOLD: &[u8] = include_bytes!("../../pyguara/graphics/fonts/LiberationSans-Bold.ttf");
const ITALIC: &[u8] = include_bytes!("../../pyguara/graphics/fonts/LiberationSans-Italic.ttf");
const BOLD_ITALIC: &[u8] = include_bytes!("../../pyguara/graphics/fonts/LiberationSans-BoldItalic.ttf");

/// The four default faces' bytes, shared by every size made of them.
fn defaults() -> &'static [Arc<[u8]>; 4] {
    static FACES: OnceLock<[Arc<[u8]>; 4]> = OnceLock::new();
    FACES.get_or_init(|| [REGULAR, BOLD, ITALIC, BOLD_ITALIC].map(Arc::from))
}

/// One glyph at one size, hinted: where its bitmap sits and what it covers.
#[derive(Default)]
struct Glyph {
    /// The bitmap's left edge, from the pen.
    xmin: i32,
    /// The bitmap's bottom edge, above the baseline.
    ymin: i32,
    width: usize,
    height: usize,
    /// The hinted advance, whole pixels.
    advance: f32,
    coverage: Vec<u8>,
}

/// One path command, in pixels, y up.
enum Segment {
    Move(f32, f32),
    Line(f32, f32),
    Quad(f32, f32, f32, f32),
    Cubic(f32, f32, f32, f32, f32, f32),
    Close,
}

/// Collects a hinted outline, and the box around every point of it --
/// control points included, which is how FreeType sizes a glyph's bitmap.
#[derive(Default)]
struct Path {
    segments: Vec<Segment>,
    min: (f32, f32),
    max: (f32, f32),
    any: bool,
}

impl Path {
    fn see(&mut self, x: f32, y: f32) {
        if self.any {
            self.min = (self.min.0.min(x), self.min.1.min(y));
            self.max = (self.max.0.max(x), self.max.1.max(y));
        } else {
            (self.min, self.max, self.any) = ((x, y), (x, y), true);
        }
    }
}

impl OutlinePen for Path {
    fn move_to(&mut self, x: f32, y: f32) {
        self.see(x, y);
        self.segments.push(Segment::Move(x, y));
    }
    fn line_to(&mut self, x: f32, y: f32) {
        self.see(x, y);
        self.segments.push(Segment::Line(x, y));
    }
    fn quad_to(&mut self, cx: f32, cy: f32, x: f32, y: f32) {
        self.see(cx, cy);
        self.see(x, y);
        self.segments.push(Segment::Quad(cx, cy, x, y));
    }
    fn curve_to(&mut self, cx0: f32, cy0: f32, cx1: f32, cy1: f32, x: f32, y: f32) {
        self.see(cx0, cy0);
        self.see(cx1, cy1);
        self.see(x, y);
        self.segments.push(Segment::Cubic(cx0, cy0, cx1, cy1, x, y));
    }
    fn close(&mut self) {
        self.segments.push(Segment::Close);
    }
}

/// Fill a path by area coverage into a `width` x `height` bitmap whose
/// bottom-left corner is at `(left, bottom)` in the path's pixels.
fn rasterise(path: &Path, left: f32, bottom: f32, width: usize, height: usize) -> Vec<u8> {
    let mut raster = Rasterizer::new(width, height);
    let at = |x: f32, y: f32| point(x - left, height as f32 - (y - bottom));
    let (mut start, mut pen) = ((0.0, 0.0), (0.0, 0.0));
    for segment in &path.segments {
        match *segment {
            Segment::Move(x, y) => {
                if pen != start {
                    raster.draw_line(at(pen.0, pen.1), at(start.0, start.1));
                }
                (start, pen) = ((x, y), (x, y));
            }
            Segment::Line(x, y) => {
                raster.draw_line(at(pen.0, pen.1), at(x, y));
                pen = (x, y);
            }
            Segment::Quad(cx, cy, x, y) => {
                raster.draw_quad(at(pen.0, pen.1), at(cx, cy), at(x, y));
                pen = (x, y);
            }
            Segment::Cubic(cx0, cy0, cx1, cy1, x, y) => {
                raster.draw_cubic(at(pen.0, pen.1), at(cx0, cy0), at(cx1, cy1), at(x, y));
                pen = (x, y);
            }
            Segment::Close => {
                if pen != start {
                    raster.draw_line(at(pen.0, pen.1), at(start.0, start.1));
                }
                pen = start;
            }
        }
    }
    if pen != start {
        raster.draw_line(at(pen.0, pen.1), at(start.0, start.1));
    }
    let mut coverage = vec![0u8; width * height];
    raster.for_each_pixel(|index, alpha| {
        coverage[index] = (alpha.clamp(0.0, 1.0) * 255.0).round() as u8;
    });
    coverage
}

/// A face at one size.
///
/// Rasterised glyphs are cached, so a HUD redrawing the same digits costs a
/// lookup per character.
#[pyclass(unsendable)]
pub struct NativeFont {
    data: Arc<[u8]>,
    hinting: HintingInstance,
    px: f32,
    /// Font units to pixels, for kerning.
    scale: f32,
    ascent: i32,
    descent: i32,
    line: i32,
    glyphs: HashMap<char, Glyph>,
}

impl NativeFont {
    fn font(&self) -> FontRef<'_> {
        FontRef::new(&self.data).expect("checked when the face was made")
    }

    fn at(data: Arc<[u8]>, size: u32) -> PyResult<Self> {
        if size == 0 {
            return Err(PyValueError::new_err("a font size must be at least 1"));
        }
        let px = size as f32;
        let font = FontRef::new(&data).map_err(|error| PyOSError::new_err(format!("not a font: {error}")))?;
        let metrics = font.metrics(Size::new(px), LocationRef::default());
        let hinting = HintingInstance::new(
            &font.outline_glyphs(),
            Size::new(px),
            LocationRef::default(),
            HintingOptions::default(),
        )
        .map_err(|error| PyOSError::new_err(format!("the font cannot be hinted: {error}")))?;
        // SDL_ttf's FT_CEIL on the ascent; the height is the whole extent
        // rounded up once, not the two halves each rounded: `ascent -
        // descent` below is what `TTF_FontHeight` returns.
        let ascent = metrics.ascent.ceil() as i32;
        let descent = ascent - (metrics.ascent - metrics.descent).ceil() as i32;
        let line = (metrics.ascent - metrics.descent + metrics.leading).ceil() as i32;
        let scale = px / f32::from(metrics.units_per_em.max(1));
        drop(font);
        Ok(Self { data, hinting, px, scale, ascent, descent, line, glyphs: HashMap::new() })
    }

    fn glyph_id(&self, character: char) -> GlyphId {
        self.font().charmap().map(character).unwrap_or_default()
    }

    fn rasterise_glyph(&self, character: char) -> Glyph {
        let font = self.font();
        let id = font.charmap().map(character).unwrap_or_default();
        let advance_unhinted = font
            .glyph_metrics(Size::new(self.px), LocationRef::default())
            .advance_width(id)
            .unwrap_or(0.0);
        let Some(outline) = font.outline_glyphs().get(id) else {
            return Glyph { advance: advance_unhinted.round(), ..Glyph::default() };
        };
        let mut path = Path::default();
        let adjusted = outline.draw(DrawSettings::hinted(&self.hinting, false), &mut path).ok();
        let advance = adjusted
            .and_then(|metrics| metrics.advance_width)
            .unwrap_or(advance_unhinted)
            .round();
        if !path.any {
            return Glyph { advance, ..Glyph::default() };
        }
        let (left, bottom) = (path.min.0.floor(), path.min.1.floor());
        let (right, top) = (path.max.0.ceil(), path.max.1.ceil());
        let (width, height) = ((right - left) as usize, (top - bottom) as usize);
        if width == 0 || height == 0 {
            return Glyph { advance, ..Glyph::default() };
        }
        Glyph {
            xmin: left as i32,
            ymin: bottom as i32,
            width,
            height,
            advance,
            coverage: rasterise(&path, left, bottom, width, height),
        }
    }

    fn glyph(&mut self, character: char) -> &Glyph {
        if !self.glyphs.contains_key(&character) {
            let made = self.rasterise_glyph(character);
            self.glyphs.insert(character, made);
        }
        &self.glyphs[&character]
    }

    /// Kerning between two characters, in pixels, from the `kern` table.
    fn kerning(&self, left: char, right: char) -> f32 {
        let (left, right) = (self.glyph_id(left), self.glyph_id(right));
        let font = self.font();
        let Ok(kern) = font.kern() else {
            return 0.0;
        };
        let mut total = 0;
        for subtable in kern.subtables().flatten() {
            if !subtable.is_horizontal() {
                continue;
            }
            if let Ok(SubtableKind::Format0(pairs)) = subtable.kind() {
                total += pairs.kerning(left, right).unwrap_or(0);
            }
        }
        total as f32 * self.scale
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
                pen += self.kerning(before, character);
            }
            let origin = pen.floor() as i32;
            let glyph = self.glyph(character);
            let (xmin, width, advance) = (glyph.xmin, glyph.width, glyph.advance);
            let x = origin + xmin;
            if width > 0 {
                left = left.min(x);
                right = right.max(x + width as i32);
            }
            placed.push((character, x));
            // A hinted advance is whole pixels; kerning stays fractional,
            // as HarfBuzz positions it.
            pen += advance;
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
        Self::at(Arc::from(data), size)
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

    /// Each character's hinted metrics, for checking layout against
    /// another rasteriser: `(xmin, width, advance, kerning before it)`.
    fn glyph_metrics(&mut self, text: &str) -> Vec<(i32, usize, f32, f32)> {
        let mut out = Vec::new();
        let mut previous: Option<char> = None;
        for character in text.chars() {
            let kern = previous.map_or(0.0, |before| self.kerning(before, character));
            let glyph = self.glyph(character);
            out.push((glyph.xmin, glyph.width, glyph.advance, kern));
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
            let glyph = self.glyph(character);
            // `ymin` is the bitmap's bottom edge above the baseline.
            let top = ascent - (glyph.ymin + glyph.height as i32);
            let x = x - left;
            for row in 0..glyph.height {
                let y = top + row as i32;
                if y < 0 || y >= height {
                    continue;
                }
                for column in 0..glyph.width {
                    let at = x + column as i32;
                    if at < 0 || at >= width {
                        continue;
                    }
                    let index = y as usize * width_u + at as usize;
                    // Overlapping glyphs keep the stronger coverage, as
                    // SDL_ttf's blended renderer does.
                    alpha[index] = alpha[index].max(glyph.coverage[row * glyph.width + column]);
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
