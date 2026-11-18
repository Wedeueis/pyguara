//! Render extraction over columns: sprites drawn straight from a world.
//!
//! The object path builds a `RenderCommand` per sprite, sorts them, groups
//! them into `RenderBatch` lists and hands each list to `NativeGpu.sprites`.
//! This reads the same fields from a `NativeWorld`'s columns and pushes the
//! instances itself, so a frame crosses into native code once.
//!
//! **It reproduces `Scene.render`'s rules exactly.** A sprite's world
//! position is its offset added to its transform's position, or to
//! `lerp(previous, position, alpha)` when the transform interpolates, or
//! the offset alone with no transform. A y-sorted sprite's depth is that
//! world Y plus `sort_offset`. The order is a stable sort on `(layer,
//! sort_group, depth)`, and the per-sprite arithmetic is
//! `NativeGpu::push_sprite`, which `sprites` also uses.

use std::cmp::Ordering;

use pyo3::exceptions::PyValueError;
use pyo3::prelude::*;

use crate::gpu::NativeGpu;
use crate::world::NativeWorld;

/// The sprite columns, in the order `SpriteExtraction` takes them.
const SPRITE_COLUMNS: usize = 16;
/// The transform columns, in the order `SpriteExtraction` takes them.
const TRANSFORM_COLUMNS: usize = 5;

/// One sprite this frame, before sorting.
struct Drawn {
    layer: i64,
    group: i64,
    depth: f64,
    row: usize,
    x: f64,
    y: f64,
    texture: u32,
    color: (u8, u8, u8, u8),
}

/// Draws a world's sprites into a `NativeGpu`.
///
/// Built once with the table and column numbers, then called each frame.
/// `sprite_columns` are, in order: texture, layer, z_index, visible,
/// y_sort, sort_offset, sort_group, offset x, offset y, rotation, scale x,
/// scale y, red, green, blue, alpha. `transform` is the table and its
/// position x, position y, previous x, previous y and interpolate columns,
/// or None for sprites placed by their offset alone.
#[pyclass(module = "pyguara.pyguara_core_rs")]
pub struct SpriteExtraction {
    sprite: usize,
    sprite_columns: [usize; SPRITE_COLUMNS],
    transform: Option<(usize, [usize; TRANSFORM_COLUMNS])>,
    /// Reused across frames, so a frame allocates nothing once it has grown.
    drawn: Vec<Drawn>,
}

fn columns<const N: usize>(given: Vec<usize>, what: &str) -> PyResult<[usize; N]> {
    let count = given.len();
    given.try_into().map_err(|_| {
        PyValueError::new_err(format!("{what} takes {N} column numbers, got {count}"))
    })
}

#[pymethods]
impl SpriteExtraction {
    #[new]
    #[pyo3(signature = (sprite, sprite_columns, transform = None))]
    fn new(
        sprite: usize,
        sprite_columns: Vec<usize>,
        transform: Option<(usize, Vec<usize>)>,
    ) -> PyResult<Self> {
        Ok(Self {
            sprite,
            sprite_columns: columns(sprite_columns, "a sprite")?,
            transform: match transform {
                Some((table, given)) => Some((table, columns(given, "a transform")?)),
                None => None,
            },
            drawn: Vec::new(),
        })
    }

    /// Push every visible sprite's instance into `gpu`, in draw order.
    ///
    /// Screen position is `world * zoom + offset`, as the batcher computes
    /// it. Returns how many sprites were pushed.
    ///
    /// Raises:
    ///     ValueError: For a NaN depth, which has no place in the order, or
    ///         a colour channel or texture id out of range.
    ///     KeyError: For a texture id `gpu` has not uploaded.
    #[allow(clippy::too_many_arguments)]
    fn draw(
        &mut self,
        world: PyRef<'_, NativeWorld>,
        mut gpu: PyRefMut<'_, NativeGpu>,
        zoom: f64,
        offset_x: f64,
        offset_y: f64,
        alpha: f64,
    ) -> PyResult<usize> {
        let sprites = world.read(self.sprite)?;
        let [texture, layer, z_index, visible, y_sort, sort_offset, sort_group, offset_x_col, offset_y_col, rotation, scale_x, scale_y, red, green, blue, alpha_col] =
            self.sprite_columns;
        let (layer, z_index, sort_group) = (sprites.i64(layer)?, sprites.i64(z_index)?, sprites.i64(sort_group)?);
        let (visible, y_sort) = (sprites.u8(visible)?, sprites.u8(y_sort)?);
        let sort_offset = sprites.f64(sort_offset)?;
        let (sprite_x, sprite_y) = (sprites.f64(offset_x_col)?, sprites.f64(offset_y_col)?);

        let placed = match self.transform {
            Some((table, [x, y, previous_x, previous_y, interpolate])) => {
                let read = world.read(table)?;
                Some((
                    read.f64(x)?,
                    read.f64(y)?,
                    read.f64(previous_x)?,
                    read.f64(previous_y)?,
                    read.u8(interpolate)?,
                    read,
                ))
            }
            None => None,
        };

        let textures = sprites.i64(texture)?;
                let channels = [sprites.i64(red)?, sprites.i64(green)?, sprites.i64(blue)?, sprites.i64(alpha_col)?];
        let channel = |values: &[i64], row: usize| {
            u8::try_from(values[row]).map_err(|_| {
                PyValueError::new_err(format!("a colour channel of {} is outside 0-255", values[row]))
            })
        };

        self.drawn.clear();
        for (row, &owner) in sprites.entities.iter().enumerate() {
            if owner == u64::MAX || visible[row] == 0 {
                continue;
            }
            let (offset_x_value, offset_y_value) = (sprite_x[row], sprite_y[row]);
            let (x, y) = match &placed {
                Some((xs, ys, previous_xs, previous_ys, interpolates, read)) => match read.row_of(owner) {
                    Some(at) => {
                        let (base_x, base_y) = if interpolates[at] != 0 {
                            // `Vector2.lerp`, term for term.
                            let (from_x, from_y) = (previous_xs[at], previous_ys[at]);
                            (from_x + (xs[at] - from_x) * alpha, from_y + (ys[at] - from_y) * alpha)
                        } else {
                            (xs[at], ys[at])
                        };
                        (base_x + offset_x_value, base_y + offset_y_value)
                    }
                    None => (offset_x_value, offset_y_value),
                },
                None => (offset_x_value, offset_y_value),
            };
            let depth = if y_sort[row] != 0 {
                y + sort_offset[row]
            } else {
                z_index[row] as f64
            };
            if depth.is_nan() {
                return Err(PyValueError::new_err(format!(
                    "entity {owner}'s sprite has a NaN depth, which cannot be ordered"
                )));
            }
            let texture = u32::try_from(textures[row])
                .map_err(|_| PyValueError::new_err(format!("{} is not a texture id", textures[row])))?;
            let color = (
                channel(channels[0], row)?,
                channel(channels[1], row)?,
                channel(channels[2], row)?,
                channel(channels[3], row)?,
            );
            self.drawn.push(Drawn {
                layer: layer[row],
                group: sort_group[row],
                depth,
                row,
                x,
                y,
                texture,
                color,
            });
        }

        // Stable, as `list.sort` is: equal keys keep insertion order.
        self.drawn.sort_by(|a, b| {
            a.layer
                .cmp(&b.layer)
                .then(a.group.cmp(&b.group))
                .then(a.depth.partial_cmp(&b.depth).unwrap_or(Ordering::Equal))
        });

        let (rotations, scale_xs, scale_ys) = (sprites.f64(rotation)?, sprites.f64(scale_x)?, sprites.f64(scale_y)?);
        // Every texture is looked up before anything is pushed, so a
        // missing one leaves the frame as it was.
        let mut sizes = Vec::with_capacity(self.drawn.len());
        let mut current: Option<(u32, (u32, u32))> = None;
        for drawn in &self.drawn {
            let size = match current {
                Some((held, size)) if held == drawn.texture => size,
                _ => {
                    let size = gpu.image_size(drawn.texture)?;
                    current = Some((drawn.texture, size));
                    size
                }
            };
            sizes.push(size);
        }
        for (drawn, &size) in self.drawn.iter().zip(&sizes) {
            let row = drawn.row;
            gpu.push_sprite(
                drawn.texture,
                size,
                (drawn.x * zoom + offset_x, drawn.y * zoom + offset_y),
                None,
                rotations[row],
                Some((scale_xs[row], scale_ys[row])),
                drawn.color,
            );
        }
        Ok(self.drawn.len())
    }
}
