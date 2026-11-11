//! The renderer's native core: one instanced pipeline on wgpu.
//!
//! Everything the engine draws in 2D -- a filled rectangle, a circle, a
//! line, a sprite, a run of text -- is a quad. So there is one pipeline and
//! one instance layout, and a primitive is a row in an array: where the
//! quad is, how big, how turned, which part of which texture, what colour,
//! and whether the fragment shader should cut a circle out of it. A frame
//! is that array uploaded once and drawn in runs that share a texture and
//! a scissor rectangle.
//!
//! **Order is the caller's.** Runs are drawn in the order primitives were
//! pushed, and a run breaks only when the texture or the scissor changes.
//! This is a painter's-order 2D renderer, like the two it replaces; there
//! is no depth buffer to make order not matter.
//!
//! **Python pushes one primitive per call**, with scalar arguments. ADR
//! 0004 measured that shape as the cheap one -- 20,000 scalar pushes cost
//! 2.3 ms, less than building the lists a single bulk call would need.
//! **Except a sprite batch**: there the lists already exist (`RenderBatch`
//! is made of them), and what cost was the Python placing each sprite
//! before its push. `sprites` takes the batch's lists as they are and does
//! that placement here -- 0.5 to 1.2 us a sprite down to 0.04 to 0.13.
//!
//! **The target is offscreen.** A frame is rendered into a texture, and
//! `read_pixels` copies it out: that is what makes a frame checkable in a
//! test with no window, and it is how stage A presents (the pygame window
//! shows the copied frame). A swapchain on the window's own handle is the
//! next stage and replaces the copy, not the pipeline.
//!
//! Like `audio` and `net` this is a backend with no Python counterpart:
//! `display.backend` chooses it, not the native-acceleration switch.

use std::collections::HashMap;

use bytemuck::{Pod, Zeroable};
use pyo3::exceptions::{PyKeyError, PyRuntimeError, PyValueError};
use pyo3::prelude::*;
use pyo3::types::PyBytes;

/// The one texture every untextured primitive samples: a white pixel.
const WHITE: u32 = 0;

const KIND_QUAD: f32 = 0.0;
const KIND_CIRCLE: f32 = 1.0;
const KIND_ROUNDED: f32 = 2.0;

const TARGET_FORMAT: wgpu::TextureFormat = wgpu::TextureFormat::Rgba8Unorm;
/// A target that holds values above 1.0, for the render graph's chain.
const HDR_FORMAT: wgpu::TextureFormat = wgpu::TextureFormat::Rgba16Float;

/// The target the frame is presented from, and drawn to by default.
const MAIN: u32 = 0;

/// Stride of one draw step's globals in the uniform buffer: the minimum
/// dynamic-offset alignment every adapter accepts.
const GLOBALS_STRIDE: u64 = 256;

/// How a fullscreen pass combines with what its target already holds.
const BLEND_REPLACE: u8 = 0;
const BLEND_ADD: u8 = 1;
const BLEND_ALPHA: u8 = 2;

/// The quad pipeline's vertex stage, shared by the default fragment and
/// by every material: a material sprite is placed exactly as any other.
const QUAD_VERTEX: &str = r"
struct Globals { size: vec2<f32>, pad: vec2<f32> };
@group(0) @binding(0) var<uniform> globals: Globals;

struct Instance {
    @location(0) center: vec2<f32>,
    @location(1) half: vec2<f32>,
    @location(2) turn: vec2<f32>,
    @location(3) uv_low: vec2<f32>,
    @location(4) uv_high: vec2<f32>,
    @location(5) color: vec4<f32>,
    @location(6) params: vec4<f32>,
};

struct Varying {
    @builtin(position) position: vec4<f32>,
    @location(0) uv: vec2<f32>,
    @location(1) color: vec4<f32>,
    @location(2) local: vec2<f32>,
    @location(3) params: vec4<f32>,
    @location(4) half: vec2<f32>,
};

@vertex
fn vertex(@builtin(vertex_index) index: u32, instance: Instance) -> Varying {
    var corners = array<vec2<f32>, 6>(
        vec2<f32>(-1.0, -1.0), vec2<f32>(1.0, -1.0), vec2<f32>(1.0, 1.0),
        vec2<f32>(-1.0, -1.0), vec2<f32>(1.0, 1.0), vec2<f32>(-1.0, 1.0),
    );
    let corner = corners[index];
    let local = corner * instance.half;
    let turned = vec2<f32>(
        local.x * instance.turn.x - local.y * instance.turn.y,
        local.x * instance.turn.y + local.y * instance.turn.x,
    );
    let world = instance.center + turned;
    var out: Varying;
    out.position = vec4<f32>(
        world.x / globals.size.x * 2.0 - 1.0,
        1.0 - world.y / globals.size.y * 2.0,
        0.0,
        1.0,
    );
    out.uv = mix(instance.uv_low, instance.uv_high, corner * 0.5 + vec2<f32>(0.5, 0.5));
    out.color = instance.color;
    out.local = local;
    out.params = instance.params;
    out.half = instance.half;
    return out;
}

";

/// The sprite's own texture, as the default fragment names it.
const QUAD_IMAGE: &str = r"
@group(1) @binding(0) var image: texture_2d<f32>;
@group(1) @binding(1) var image_sampler: sampler;
";

/// The default fragment: shapes, text and plain sprites.
const QUAD_FRAGMENT: &str = r"
@fragment
fn fragment(in: Varying) -> @location(0) vec4<f32> {
    // Sampled before any branch: a texture sample may not sit inside
    // control flow that varies per fragment.
    let texel = textureSample(image, image_sampler, in.uv);
    if (in.params.x > 1.5) {
        // A rounded box, as a signed distance: negative inside. `y` is
        // the corner radius, `z` an outline's thickness or zero to fill.
        let reach = abs(in.local) - in.half + vec2<f32>(in.params.y, in.params.y);
        let distance = length(max(reach, vec2<f32>(0.0, 0.0)))
            + min(max(reach.x, reach.y), 0.0) - in.params.y;
        if (distance > 0.0 || (in.params.z > 0.0 && distance < -in.params.z)) {
            discard;
        }
        return in.color;
    }
    if (in.params.x > 0.5) {
        // A circle: keep what lies between the inner and outer radius.
        let distance = length(in.local);
        if (distance > in.params.y || distance < in.params.z) {
            discard;
        }
        return in.color;
    }
    return in.color * texel;
}
";

/// What a material's module adds between the vertex stage and the
/// author's `material` function: the sprite texture under the names the
/// author uses, and what a sprite hands the function.
const MATERIAL_PRELUDE: &str = r"
@group(1) @binding(0) var sprite_texture: texture_2d<f32>;
@group(1) @binding(1) var sprite_sampler: sampler;

struct Sprite {
    // Where in the sprite's texture this fragment is, atlas region and
    // flips applied: sample `sprite_texture` here for the plain sprite.
    uv: vec2<f32>,
    // The per-sprite tint, 0-1 RGBA. The plain sprite is texel * color.
    color: vec4<f32>,
};
";

/// Calls the author's `material` with the fragment's sprite.
const MATERIAL_FRAGMENT: &str = r"
@fragment
fn fragment(in: Varying) -> @location(0) vec4<f32> {
    var sprite: Sprite;
    sprite.uv = in.uv;
    sprite.color = in.color;
    return material(sprite);
}
";

/// Copies the offscreen target onto the window: one triangle that covers
/// the screen, sampling the frame.
const PRESENT_SHADER: &str = r"
@group(0) @binding(0) var frame: texture_2d<f32>;
@group(0) @binding(1) var frame_sampler: sampler;

struct Varying {
    @builtin(position) position: vec4<f32>,
    @location(0) uv: vec2<f32>,
};

@vertex
fn vertex(@builtin(vertex_index) index: u32) -> Varying {
    let corner = vec2<f32>(f32((index << 1u) & 2u), f32(index & 2u));
    var out: Varying;
    out.position = vec4<f32>(corner * 2.0 - vec2<f32>(1.0, 1.0), 0.0, 1.0);
    out.uv = vec2<f32>(corner.x, 1.0 - corner.y);
    return out;
}

@fragment
fn fragment(in: Varying) -> @location(0) vec4<f32> {
    return textureSample(frame, frame_sampler, in.uv);
}
";

/// A window's display connection, in the form wgpu wants at start-up.
#[derive(Debug)]
struct Display(wgpu::rwh::RawDisplayHandle);

// The handle is a pointer the windowing system owns for the life of the
// window. It is only ever read, and only from the thread that drew.
unsafe impl Send for Display {}
unsafe impl Sync for Display {}

impl wgpu::rwh::HasDisplayHandle for Display {
    fn display_handle(&self) -> Result<wgpu::rwh::DisplayHandle<'_>, wgpu::rwh::HandleError> {
        // SAFETY: the caller of `for_window` keeps the window open for as
        // long as this renderer lives.
        Ok(unsafe { wgpu::rwh::DisplayHandle::borrow_raw(self.0) })
    }
}

/// What `for_window` is told about a window: its kind, its native
/// identifiers, and whether to wait for the display's refresh.
type WindowSpec = (String, usize, usize, bool);

/// Turn a window's native identifiers into raw handles.
///
/// `window` and `display` are what the windowing library reports: an HWND
/// on Windows, an X11 window id and its display pointer, or a Wayland
/// surface pointer and its display pointer.
fn raw_handles(
    kind: &str,
    window: usize,
    display: usize,
) -> PyResult<(wgpu::rwh::RawDisplayHandle, wgpu::rwh::RawWindowHandle)> {
    use std::ptr::NonNull;
    use wgpu::rwh;

    let pointer = |value: usize, what: &str| {
        NonNull::new(value as *mut std::ffi::c_void)
            .ok_or_else(|| PyValueError::new_err(format!("the {what} handle is null")))
    };
    match kind {
        "win32" => {
            let handle = std::num::NonZeroIsize::new(window as isize)
                .ok_or_else(|| PyValueError::new_err("the window handle is null"))?;
            Ok((
                rwh::RawDisplayHandle::Windows(rwh::WindowsDisplayHandle::new()),
                rwh::RawWindowHandle::Win32(rwh::Win32WindowHandle::new(handle)),
            ))
        }
        "x11" => Ok((
            rwh::RawDisplayHandle::Xlib(rwh::XlibDisplayHandle::new(
                Some(pointer(display, "display")?),
                0,
            )),
            rwh::RawWindowHandle::Xlib(rwh::XlibWindowHandle::new(window as std::ffi::c_ulong)),
        )),
        "wayland" => Ok((
            rwh::RawDisplayHandle::Wayland(rwh::WaylandDisplayHandle::new(pointer(
                display, "display",
            )?)),
            rwh::RawWindowHandle::Wayland(rwh::WaylandWindowHandle::new(pointer(
                window, "surface",
            )?)),
        )),
        other => Err(PyValueError::new_err(format!(
            "no window surface for {other:?}; expected win32, x11 or wayland"
        ))),
    }
}

/// The window's swapchain and what copies a frame onto it.
struct Presenter {
    surface: wgpu::Surface<'static>,
    config: wgpu::SurfaceConfiguration,
    pipeline: wgpu::RenderPipeline,
    group: wgpu::BindGroup,
}

/// One primitive. 18 floats, matching the shader's `Instance`.
#[repr(C)]
#[derive(Clone, Copy, Pod, Zeroable)]
struct Instance {
    center: [f32; 2],
    half: [f32; 2],
    turn: [f32; 2],
    uv_low: [f32; 2],
    uv_high: [f32; 2],
    color: [f32; 4],
    params: [f32; 4],
}

/// A run of instances sharing a texture and a scissor rectangle.
struct Run {
    texture: u32,
    scissor: Option<[u32; 4]>,
    /// Index into the frame's material bindings, or None for the default
    /// fragment.
    material: Option<usize>,
    start: u32,
    count: u32,
}

/// A texture the frame can be drawn into and then sampled from.
struct Target {
    texture: wgpu::Texture,
    view: wgpu::TextureView,
    width: u32,
    height: u32,
    format: wgpu::TextureFormat,
}

/// One thing the frame does, in the order the caller asked for it.
enum Step {
    /// Instanced quads into a target. `first` is the index of its first
    /// instance; a step's instances are contiguous, because only the last
    /// step ever receives pushes.
    Draw {
        target: u32,
        clear: Option<wgpu::Color>,
        runs: Vec<Run>,
        first: usize,
    },
    /// A shader step: a fullscreen pass (one triangle), or instanced
    /// quads read from `instances` (six vertices each).
    Shader {
        target: u32,
        pipeline: wgpu::RenderPipeline,
        group: wgpu::BindGroup,
        viewport: Option<[u32; 4]>,
        clear: Option<wgpu::Color>,
        instances: Option<(wgpu::Buffer, u32)>,
    },
}

/// A fullscreen shader and the pipelines built for it, per target format
/// and blend mode, as they are first asked for.
struct Effect {
    module: wgpu::ShaderModule,
    group_layout: wgpu::BindGroupLayout,
    layout: wgpu::PipelineLayout,
    inputs: usize,
    uniform_bytes: usize,
    /// Per-instance attributes, for an instanced effect; empty otherwise.
    attributes: Vec<wgpu::VertexAttribute>,
    stride: u64,
    pipelines: HashMap<(wgpu::TextureFormat, u8), wgpu::RenderPipeline>,
}

/// A sprite material: the quad pipeline with the author's fragment.
struct Material {
    group_layout: wgpu::BindGroupLayout,
    uniform_bytes: usize,
    has_texture: bool,
    pipelines: HashMap<wgpu::TextureFormat, wgpu::RenderPipeline>,
}

struct Image {
    // Held so the view and bind group stay valid; never read back.
    _texture: wgpu::Texture,
    /// For a material that samples this image as its second texture.
    view: wgpu::TextureView,
    smooth: bool,
    bind_group: wgpu::BindGroup,
    width: u32,
    height: u32,
}

fn runtime_error(context: &str, error: impl std::fmt::Display) -> PyErr {
    PyRuntimeError::new_err(format!("{context}: {error}"))
}

fn unit(channel: u8) -> f32 {
    f32::from(channel) / 255.0
}

/// A wgpu device, one offscreen target and the frame being built for it.
// `unsendable`: wgpu's handles are not all `Sync` on every backend, and
// the engine only ever draws from the thread that made the window.
#[pyclass(unsendable)]
pub struct NativeGpu {
    device: wgpu::Device,
    queue: wgpu::Queue,
    adapter: String,
    /// The instanced quad pipeline, per target format.
    pipelines: HashMap<wgpu::TextureFormat, wgpu::RenderPipeline>,
    image_layout: wgpu::BindGroupLayout,
    sampler: wgpu::Sampler,
    /// Bilinear, for a texture whose meta asks for `filter: linear`.
    smooth_sampler: wgpu::Sampler,
    /// Linear and wrapping, as ModernGL samples a framebuffer's texture:
    /// what a fullscreen pass reads its inputs through.
    input_sampler: wgpu::Sampler,
    globals_layout: wgpu::BindGroupLayout,
    globals: wgpu::Buffer,
    globals_group: wgpu::BindGroup,
    /// How many draw steps `globals` has room for.
    globals_capacity: usize,
    /// Every target, the main one under `MAIN`.
    targets: HashMap<u32, Target>,
    next_target: u32,
    /// Where pushes go.
    current: u32,
    effects: HashMap<u32, Effect>,
    next_effect: u32,
    materials: HashMap<u32, Material>,
    next_material: u32,
    /// This frame's material uses: which material, and its bind group of
    /// uniforms and texture. A run names one by index.
    material_bindings: Vec<(u32, wgpu::BindGroup)>,
    /// The binding pushes are made with, if any.
    current_material: Option<usize>,
    instances: Vec<Instance>,
    instance_buffer: wgpu::Buffer,
    instance_capacity: usize,
    steps: Vec<Step>,
    scissor: Option<[u32; 4]>,
    /// What the main target is cleared to at the start of a frame.
    main_clear: wgpu::Color,
    images: HashMap<u32, Image>,
    next_image: u32,
    /// Frames rendered, for callers that want to know one happened.
    frames: u64,
    /// Set when drawing to a window rather than only offscreen.
    presenter: Option<Presenter>,
    /// Frames that reached the window.
    presented: u64,
}

fn make_target(device: &wgpu::Device, width: u32, height: u32, format: wgpu::TextureFormat) -> Target {
    let texture = device.create_texture(&wgpu::TextureDescriptor {
        label: Some("pyguara target"),
        size: wgpu::Extent3d {
            width,
            height,
            depth_or_array_layers: 1,
        },
        mip_level_count: 1,
        sample_count: 1,
        dimension: wgpu::TextureDimension::D2,
        format,
        usage: wgpu::TextureUsages::RENDER_ATTACHMENT
            | wgpu::TextureUsages::COPY_SRC
            | wgpu::TextureUsages::TEXTURE_BINDING,
        view_formats: &[],
    });
    let view = texture.create_view(&wgpu::TextureViewDescriptor::default());
    Target {
        texture,
        view,
        width,
        height,
        format,
    }
}

/// The instanced quad pipeline over `module`'s `vertex` and `fragment`:
/// the default one, or a material's, which shares the vertex stage.
fn make_quad_pipeline(
    device: &wgpu::Device,
    layout: &wgpu::PipelineLayout,
    module: &wgpu::ShaderModule,
    format: wgpu::TextureFormat,
) -> wgpu::RenderPipeline {
    let attributes = wgpu::vertex_attr_array![
        0 => Float32x2, 1 => Float32x2, 2 => Float32x2, 3 => Float32x2,
        4 => Float32x2, 5 => Float32x4, 6 => Float32x4
    ];
    device.create_render_pipeline(&wgpu::RenderPipelineDescriptor {
        label: Some("pyguara quads"),
        layout: Some(layout),
        vertex: wgpu::VertexState {
            module,
            entry_point: Some("vertex"),
            compilation_options: wgpu::PipelineCompilationOptions::default(),
            buffers: &[Some(wgpu::VertexBufferLayout {
                array_stride: std::mem::size_of::<Instance>() as u64,
                step_mode: wgpu::VertexStepMode::Instance,
                attributes: &attributes,
            })],
        },
        fragment: Some(wgpu::FragmentState {
            module,
            entry_point: Some("fragment"),
            compilation_options: wgpu::PipelineCompilationOptions::default(),
            targets: &[Some(wgpu::ColorTargetState {
                format,
                // Straight alpha, which is what the textures hold: a
                // glyph is its colour with coverage in alpha.
                blend: Some(wgpu::BlendState {
                    color: wgpu::BlendComponent {
                        src_factor: wgpu::BlendFactor::SrcAlpha,
                        dst_factor: wgpu::BlendFactor::OneMinusSrcAlpha,
                        operation: wgpu::BlendOperation::Add,
                    },
                    alpha: wgpu::BlendComponent {
                        src_factor: wgpu::BlendFactor::One,
                        dst_factor: wgpu::BlendFactor::OneMinusSrcAlpha,
                        operation: wgpu::BlendOperation::Add,
                    },
                }),
                write_mask: wgpu::ColorWrites::ALL,
            })],
        }),
        primitive: wgpu::PrimitiveState::default(),
        depth_stencil: None,
        multisample: wgpu::MultisampleState::default(),
        multiview_mask: None,
        cache: None,
    })
}

fn make_globals(device: &wgpu::Device, layout: &wgpu::BindGroupLayout, steps: usize) -> (wgpu::Buffer, wgpu::BindGroup) {
    let buffer = device.create_buffer(&wgpu::BufferDescriptor {
        label: Some("pyguara globals"),
        size: GLOBALS_STRIDE * steps as u64,
        usage: wgpu::BufferUsages::UNIFORM | wgpu::BufferUsages::COPY_DST,
        mapped_at_creation: false,
    });
    let group = device.create_bind_group(&wgpu::BindGroupDescriptor {
        label: Some("pyguara globals"),
        layout,
        entries: &[wgpu::BindGroupEntry {
            binding: 0,
            resource: wgpu::BindingResource::Buffer(wgpu::BufferBinding {
                buffer: &buffer,
                offset: 0,
                size: wgpu::BufferSize::new(16),
            }),
        }],
    });
    (buffer, group)
}

fn blend_state(blend: u8) -> Option<wgpu::BlendState> {
    match blend {
        BLEND_ADD => Some(wgpu::BlendState {
            color: wgpu::BlendComponent {
                src_factor: wgpu::BlendFactor::One,
                dst_factor: wgpu::BlendFactor::One,
                operation: wgpu::BlendOperation::Add,
            },
            alpha: wgpu::BlendComponent {
                src_factor: wgpu::BlendFactor::One,
                dst_factor: wgpu::BlendFactor::One,
                operation: wgpu::BlendOperation::Add,
            },
        }),
        BLEND_ALPHA => Some(wgpu::BlendState::ALPHA_BLENDING),
        _ => None,
    }
}

fn color(red: f64, green: f64, blue: f64, alpha: f64) -> wgpu::Color {
    wgpu::Color {
        r: red,
        g: green,
        b: blue,
        a: alpha,
    }
}

fn make_instance_buffer(device: &wgpu::Device, capacity: usize) -> wgpu::Buffer {
    device.create_buffer(&wgpu::BufferDescriptor {
        label: Some("pyguara instances"),
        size: (capacity * std::mem::size_of::<Instance>()) as u64,
        usage: wgpu::BufferUsages::VERTEX | wgpu::BufferUsages::COPY_DST,
        mapped_at_creation: false,
    })
}

impl NativeGpu {
    fn open(width: u32, height: u32, window: Option<WindowSpec>) -> PyResult<Self> {
        let handles = match &window {
            Some((kind, native, display, _)) => Some(raw_handles(kind, *native, *display)?),
            None => None,
        };
        let instance = wgpu::Instance::new(match handles {
            // The GL backend has to know the display before it can make
            // a context that is able to draw to one of its windows.
            Some((display, _)) => {
                wgpu::InstanceDescriptor::new_with_display_handle(Box::new(Display(display)))
            }
            None => wgpu::InstanceDescriptor::new_without_display_handle(),
        });
        let surface = match handles {
            Some((display, native)) => Some(
                // SAFETY: the handles name a live window, which the caller
                // keeps open for as long as this renderer lives.
                unsafe {
                    instance.create_surface_unsafe(wgpu::SurfaceTargetUnsafe::RawHandle {
                        raw_display_handle: Some(display),
                        raw_window_handle: native,
                    })
                }
                .map_err(|error| runtime_error("the window cannot be drawn to", error))?,
            ),
            None => None,
        };
        let adapter = pollster::block_on(instance.request_adapter(&wgpu::RequestAdapterOptions {
            power_preference: wgpu::PowerPreference::HighPerformance,
            compatible_surface: surface.as_ref(),
            ..Default::default()
        }))
        .map_err(|error| runtime_error("no graphics adapter is available", error))?;
        let info = adapter.get_info();
        let (device, queue) = pollster::block_on(adapter.request_device(&wgpu::DeviceDescriptor {
            label: Some("pyguara"),
            ..Default::default()
        }))
        .map_err(|error| runtime_error("the graphics device could not be opened", error))?;

        let shader = device.create_shader_module(wgpu::ShaderModuleDescriptor {
            label: Some("pyguara quads"),
            source: wgpu::ShaderSource::Wgsl(format!("{QUAD_VERTEX}{QUAD_IMAGE}{QUAD_FRAGMENT}").into()),
        });
        let globals_layout = device.create_bind_group_layout(&wgpu::BindGroupLayoutDescriptor {
            label: Some("pyguara globals"),
            entries: &[wgpu::BindGroupLayoutEntry {
                binding: 0,
                visibility: wgpu::ShaderStages::VERTEX,
                ty: wgpu::BindingType::Buffer {
                    ty: wgpu::BufferBindingType::Uniform,
                    // One slot per draw step: targets differ in size.
                    has_dynamic_offset: true,
                    min_binding_size: None,
                },
                count: None,
            }],
        });
        let image_layout = device.create_bind_group_layout(&wgpu::BindGroupLayoutDescriptor {
            label: Some("pyguara image"),
            entries: &[
                wgpu::BindGroupLayoutEntry {
                    binding: 0,
                    visibility: wgpu::ShaderStages::FRAGMENT,
                    ty: wgpu::BindingType::Texture {
                        sample_type: wgpu::TextureSampleType::Float { filterable: true },
                        view_dimension: wgpu::TextureViewDimension::D2,
                        multisampled: false,
                    },
                    count: None,
                },
                wgpu::BindGroupLayoutEntry {
                    binding: 1,
                    visibility: wgpu::ShaderStages::FRAGMENT,
                    ty: wgpu::BindingType::Sampler(wgpu::SamplerBindingType::Filtering),
                    count: None,
                },
            ],
        });
        let layout = device.create_pipeline_layout(&wgpu::PipelineLayoutDescriptor {
            label: Some("pyguara quads"),
            bind_group_layouts: &[Some(&globals_layout), Some(&image_layout)],
            ..Default::default()
        });
        let pipelines = HashMap::from([
            (TARGET_FORMAT, make_quad_pipeline(&device, &layout, &shader, TARGET_FORMAT)),
            (HDR_FORMAT, make_quad_pipeline(&device, &layout, &shader, HDR_FORMAT)),
        ]);
        // Nearest, as pygame scales: a pixel-art sprite stays pixel art,
        // and text drawn at its own size samples texel for texel.
        let sampler = device.create_sampler(&wgpu::SamplerDescriptor {
            label: Some("pyguara nearest"),
            mag_filter: wgpu::FilterMode::Nearest,
            min_filter: wgpu::FilterMode::Nearest,
            ..Default::default()
        });
        // Bilinear, as the ModernGL backend samples a texture whose meta
        // says `linear`: "linear for HD", per `TextureMeta`.
        let smooth_sampler = device.create_sampler(&wgpu::SamplerDescriptor {
            label: Some("pyguara linear"),
            mag_filter: wgpu::FilterMode::Linear,
            min_filter: wgpu::FilterMode::Linear,
            ..Default::default()
        });
        // Linear and repeating: ModernGL's defaults for a framebuffer's
        // texture, which every effect was written against. An effect that
        // offsets its UVs near an edge reads the far side, there and here.
        let input_sampler = device.create_sampler(&wgpu::SamplerDescriptor {
            label: Some("pyguara inputs"),
            address_mode_u: wgpu::AddressMode::Repeat,
            address_mode_v: wgpu::AddressMode::Repeat,
            mag_filter: wgpu::FilterMode::Linear,
            min_filter: wgpu::FilterMode::Linear,
            ..Default::default()
        });
        let globals_capacity = 16;
        let (globals, globals_group) = make_globals(&device, &globals_layout, globals_capacity);
        let main = make_target(&device, width, height, TARGET_FORMAT);
        let instance_capacity = 4096;
        let instance_buffer = make_instance_buffer(&device, instance_capacity);

        let mut gpu = Self {
            device,
            queue,
            adapter: format!("{:?}: {}", info.backend, info.name),
            pipelines,
            image_layout,
            sampler,
            smooth_sampler,
            input_sampler,
            globals_layout,
            globals,
            globals_group,
            globals_capacity,
            targets: HashMap::from([(MAIN, main)]),
            next_target: 1,
            current: MAIN,
            effects: HashMap::new(),
            next_effect: 1,
            materials: HashMap::new(),
            next_material: 1,
            material_bindings: Vec::new(),
            current_material: None,
            instances: Vec::with_capacity(instance_capacity),
            instance_buffer,
            instance_capacity,
            steps: Vec::new(),
            scissor: None,
            main_clear: wgpu::Color::BLACK,
            images: HashMap::new(),
            next_image: 1,
            frames: 0,
            presenter: None,
            presented: 0,
        };
        let white = gpu.upload_image(1, 1, &[255, 255, 255, 255], false)?;
        gpu.images.insert(WHITE, white);
        if let Some(surface) = surface {
            let vsync = window.is_some_and(|(_, _, _, vsync)| vsync);
            gpu.presenter = Some(gpu.make_presenter(surface, &adapter, vsync)?);
        }
        Ok(gpu)
    }

    fn make_presenter(
        &self,
        surface: wgpu::Surface<'static>,
        adapter: &wgpu::Adapter,
        vsync: bool,
    ) -> PyResult<Presenter> {
        let capabilities = surface.get_capabilities(adapter);
        let mut config = surface
            .get_default_config(adapter, self.main().width, self.main().height)
            .ok_or_else(|| PyRuntimeError::new_err("the adapter cannot draw to this window"))?;
        // The frame's bytes are already display-encoded, as the pygame
        // renderer's are. An sRGB swapchain would encode them a second
        // time and wash the picture out, so prefer a plain one.
        if let Some(plain) = capabilities.formats.iter().find(|format| !format.is_srgb()) {
            config.format = *plain;
        }
        config.present_mode = if vsync {
            wgpu::PresentMode::AutoVsync
        } else {
            wgpu::PresentMode::AutoNoVsync
        };
        surface.configure(&self.device, &config);

        let shader = self.device.create_shader_module(wgpu::ShaderModuleDescriptor {
            label: Some("pyguara present"),
            source: wgpu::ShaderSource::Wgsl(PRESENT_SHADER.into()),
        });
        let layout = self.device.create_pipeline_layout(&wgpu::PipelineLayoutDescriptor {
            label: Some("pyguara present"),
            bind_group_layouts: &[Some(&self.image_layout)],
            ..Default::default()
        });
        let pipeline = self.device.create_render_pipeline(&wgpu::RenderPipelineDescriptor {
            label: Some("pyguara present"),
            layout: Some(&layout),
            vertex: wgpu::VertexState {
                module: &shader,
                entry_point: Some("vertex"),
                compilation_options: wgpu::PipelineCompilationOptions::default(),
                buffers: &[],
            },
            fragment: Some(wgpu::FragmentState {
                module: &shader,
                entry_point: Some("fragment"),
                compilation_options: wgpu::PipelineCompilationOptions::default(),
                targets: &[Some(wgpu::ColorTargetState {
                    format: config.format,
                    blend: None,
                    write_mask: wgpu::ColorWrites::ALL,
                })],
            }),
            primitive: wgpu::PrimitiveState::default(),
            depth_stencil: None,
            multisample: wgpu::MultisampleState::default(),
            multiview_mask: None,
            cache: None,
        });
        let group = self.frame_group();
        Ok(Presenter {
            surface,
            config,
            pipeline,
            group,
        })
    }

    /// A bind group over the offscreen target, for the copy to the window.
    fn frame_group(&self) -> wgpu::BindGroup {
        self.device.create_bind_group(&wgpu::BindGroupDescriptor {
            label: Some("pyguara frame"),
            layout: &self.image_layout,
            entries: &[
                wgpu::BindGroupEntry {
                    binding: 0,
                    resource: wgpu::BindingResource::TextureView(&self.main().view),
                },
                wgpu::BindGroupEntry {
                    binding: 1,
                    resource: wgpu::BindingResource::Sampler(&self.sampler),
                },
            ],
        })
    }

    fn guarded(width: u32, height: u32, window: Option<WindowSpec>) -> PyResult<Self> {
        // wgpu's GL backend unwraps EGL errors while it opens a device. The
        // one seen in practice is `BadAccess`, raised when another OpenGL
        // context is already current in this process -- a ModernGL context
        // from earlier in a test run, never a game, which has one backend.
        // A panic would surface in Python as a `BaseException`; this makes
        // it the `RuntimeError` the caller is told to expect.
        match std::panic::catch_unwind(|| Self::open(width, height, window)) {
            Ok(opened) => opened,
            Err(panic) => {
                let reason = panic
                    .downcast_ref::<String>()
                    .cloned()
                    .or_else(|| panic.downcast_ref::<&str>().map(|text| (*text).to_owned()))
                    .unwrap_or_else(|| "unknown".to_owned());
                Err(PyRuntimeError::new_err(format!(
                    "the graphics device could not be opened: {reason}. If this \
                     process already holds an OpenGL context, wgpu's GL backend \
                     cannot open a second one"
                )))
            }
        }
    }

    fn check_size(width: u32, height: u32) -> PyResult<()> {
        if width == 0 || height == 0 || width > 16_384 || height > 16_384 {
            return Err(PyValueError::new_err(format!(
                "a render target must be between 1 and 16384 pixels a side, got {width}x{height}"
            )));
        }
        Ok(())
    }

    fn upload_image(&self, width: u32, height: u32, pixels: &[u8], smooth: bool) -> PyResult<Image> {
        Self::check_size(width, height)?;
        let expected = width as usize * height as usize * 4;
        if pixels.len() != expected {
            return Err(PyValueError::new_err(format!(
                "a {width}x{height} RGBA image is {expected} bytes, got {}",
                pixels.len()
            )));
        }
        let size = wgpu::Extent3d {
            width,
            height,
            depth_or_array_layers: 1,
        };
        let texture = self.device.create_texture(&wgpu::TextureDescriptor {
            label: Some("pyguara image"),
            size,
            mip_level_count: 1,
            sample_count: 1,
            dimension: wgpu::TextureDimension::D2,
            format: wgpu::TextureFormat::Rgba8Unorm,
            usage: wgpu::TextureUsages::TEXTURE_BINDING | wgpu::TextureUsages::COPY_DST,
            view_formats: &[],
        });
        self.queue.write_texture(
            wgpu::TexelCopyTextureInfo {
                texture: &texture,
                mip_level: 0,
                origin: wgpu::Origin3d::ZERO,
                aspect: wgpu::TextureAspect::All,
            },
            pixels,
            wgpu::TexelCopyBufferLayout {
                offset: 0,
                bytes_per_row: Some(width * 4),
                rows_per_image: Some(height),
            },
            size,
        );
        let view = texture.create_view(&wgpu::TextureViewDescriptor::default());
        let bind_group = self.device.create_bind_group(&wgpu::BindGroupDescriptor {
            label: Some("pyguara image"),
            layout: &self.image_layout,
            entries: &[
                wgpu::BindGroupEntry {
                    binding: 0,
                    resource: wgpu::BindingResource::TextureView(&view),
                },
                wgpu::BindGroupEntry {
                    binding: 1,
                    resource: wgpu::BindingResource::Sampler(if smooth {
                        &self.smooth_sampler
                    } else {
                        &self.sampler
                    }),
                },
            ],
        });
        Ok(Image {
            _texture: texture,
            view,
            smooth,
            bind_group,
            width,
            height,
        })
    }

    /// Validate and queue a shader step; what `fullscreen` and `instanced`
    /// share.
    #[allow(clippy::too_many_arguments)]
    fn shader_step(
        &mut self,
        effect: u32,
        target: u32,
        inputs: &[u32],
        uniforms: &[u8],
        blend: u8,
        viewport: Option<(u32, u32, u32, u32)>,
        clear: Option<(f64, f64, f64, f64)>,
        instances: Option<(wgpu::Buffer, u32)>,
    ) -> PyResult<()> {
        let Some(format) = self.targets.get(&target).map(|found| found.format) else {
            return Err(PyKeyError::new_err(format!("no target {target}")));
        };
        let (wanted_inputs, wanted_bytes) = match self.effects.get(&effect) {
            Some(found) => (found.inputs, found.uniform_bytes),
            None => return Err(PyKeyError::new_err(format!("no effect {effect}"))),
        };
        if inputs.len() != wanted_inputs {
            return Err(PyValueError::new_err(format!(
                "the effect reads {wanted_inputs} inputs, got {}",
                inputs.len()
            )));
        }
        if uniforms.len() != wanted_bytes {
            return Err(PyValueError::new_err(format!(
                "the effect's uniforms are {wanted_bytes} bytes, got {}",
                uniforms.len()
            )));
        }
        if inputs.contains(&target) {
            return Err(PyValueError::new_err(
                "a pass cannot read the target it writes; draw into another and swap",
            ));
        }
        let mut views = Vec::with_capacity(inputs.len());
        for input in inputs {
            match self.targets.get(input) {
                Some(found) => views.push(found.view.clone()),
                None => return Err(PyKeyError::new_err(format!("no target {input}"))),
            }
        }
        let pipeline = self.effect_pipeline(effect, format, blend)?;
        let buffer = (wanted_bytes > 0).then(|| {
            let buffer = self.device.create_buffer(&wgpu::BufferDescriptor {
                label: Some("pyguara effect uniforms"),
                size: wanted_bytes.next_multiple_of(16) as u64,
                usage: wgpu::BufferUsages::UNIFORM | wgpu::BufferUsages::COPY_DST,
                mapped_at_creation: false,
            });
            let mut padded = uniforms.to_vec();
            padded.resize(wanted_bytes.next_multiple_of(16), 0);
            self.queue.write_buffer(&buffer, 0, &padded);
            buffer
        });
        let mut entries = Vec::new();
        if let Some(buffer) = &buffer {
            entries.push(wgpu::BindGroupEntry {
                binding: 0,
                resource: buffer.as_entire_binding(),
            });
        }
        entries.push(wgpu::BindGroupEntry {
            binding: 1,
            resource: wgpu::BindingResource::Sampler(&self.input_sampler),
        });
        for (index, view) in views.iter().enumerate() {
            entries.push(wgpu::BindGroupEntry {
                binding: 2 + index as u32,
                resource: wgpu::BindingResource::TextureView(view),
            });
        }
        let group = self.device.create_bind_group(&wgpu::BindGroupDescriptor {
            label: Some("pyguara effect"),
            layout: &self.effects[&effect].group_layout,
            entries: &entries,
        });
        let clear = clear.map(|(red, green, blue, alpha)| color(red, green, blue, alpha));
        if target == MAIN {
            if let Some(fill) = clear {
                self.main_clear = fill;
            }
        }
        self.steps.push(Step::Shader {
            target,
            pipeline,
            group,
            viewport: viewport.map(|(x, y, width, height)| [x, y, width, height]),
            clear,
            instances,
        });
        Ok(())
    }

    fn main(&self) -> &Target {
        &self.targets[&MAIN]
    }

    /// The runs of the draw step pushes go to, opening one if the last
    /// step is not a draw into the current target.
    fn draw_runs(&mut self) -> &mut Vec<Run> {
        let reuse = matches!(self.steps.last(), Some(Step::Draw { target, .. }) if *target == self.current);
        if !reuse {
            self.steps.push(Step::Draw {
                target: self.current,
                clear: None,
                runs: Vec::new(),
                first: self.instances.len(),
            });
        }
        match self.steps.last_mut() {
            Some(Step::Draw { runs, .. }) => runs,
            _ => unreachable!("a draw step was just ensured"),
        }
    }

    fn push(&mut self, texture: u32, instance: Instance) {
        let index = self.instances.len() as u32;
        let scissor = self.scissor;
        let material = self.current_material;
        // The step before the instance, so a step it opens starts at this
        // instance; and found once, since this runs for every primitive.
        let runs = self.draw_runs();
        match runs.last_mut() {
            Some(last) if last.texture == texture && last.scissor == scissor && last.material == material => {
                last.count += 1
            }
            _ => runs.push(Run {
                texture,
                scissor,
                material,
                start: index,
                count: 1,
            }),
        }
        self.instances.push(instance);
    }

    fn target_size(&self, id: u32) -> (u32, u32) {
        self.targets.get(&id).map_or((0, 0), |target| (target.width, target.height))
    }

    /// The fullscreen pipeline for an effect, a target format and a blend.
    fn effect_pipeline(&mut self, effect: u32, format: wgpu::TextureFormat, blend: u8) -> PyResult<wgpu::RenderPipeline> {
        let Some(found) = self.effects.get_mut(&effect) else {
            return Err(PyKeyError::new_err(format!("no effect {effect}")));
        };
        if let Some(pipeline) = found.pipelines.get(&(format, blend)) {
            return Ok(pipeline.clone());
        }
        let instance_layout = wgpu::VertexBufferLayout {
            array_stride: found.stride,
            step_mode: wgpu::VertexStepMode::Instance,
            attributes: &found.attributes,
        };
        let buffers = if found.attributes.is_empty() {
            Vec::new()
        } else {
            vec![Some(instance_layout)]
        };
        let pipeline = self.device.create_render_pipeline(&wgpu::RenderPipelineDescriptor {
            label: Some("pyguara effect"),
            layout: Some(&found.layout),
            vertex: wgpu::VertexState {
                module: &found.module,
                entry_point: Some("vertex"),
                compilation_options: wgpu::PipelineCompilationOptions::default(),
                buffers: &buffers,
            },
            fragment: Some(wgpu::FragmentState {
                module: &found.module,
                entry_point: Some("fragment"),
                compilation_options: wgpu::PipelineCompilationOptions::default(),
                targets: &[Some(wgpu::ColorTargetState {
                    format,
                    blend: blend_state(blend),
                    write_mask: wgpu::ColorWrites::ALL,
                })],
            }),
            primitive: wgpu::PrimitiveState::default(),
            depth_stencil: None,
            multisample: wgpu::MultisampleState::default(),
            multiview_mask: None,
            cache: None,
        });
        found.pipelines.insert((format, blend), pipeline.clone());
        Ok(pipeline)
    }

    #[allow(clippy::too_many_arguments)]
    fn solid(&mut self, x: f32, y: f32, width: f32, height: f32, color: [f32; 4]) {
        if width <= 0.0 || height <= 0.0 {
            return;
        }
        self.push(
            WHITE,
            Instance {
                center: [x + width * 0.5, y + height * 0.5],
                half: [width * 0.5, height * 0.5],
                turn: [1.0, 0.0],
                uv_low: [0.0, 0.0],
                uv_high: [1.0, 1.0],
                color,
                params: [KIND_QUAD, 0.0, 0.0, 0.0],
            },
        );
    }
}

#[pymethods]
impl NativeGpu {
    /// Open a device and an offscreen target of the given size.
    #[new]
    fn new(width: u32, height: u32) -> PyResult<Self> {
        Self::check_size(width, height)?;
        Self::guarded(width, height, None)
    }

    /// Open a device that draws to a window as well as offscreen.
    ///
    /// `kind` is `win32`, `x11` or `wayland`; `window` and `display` are
    /// the native identifiers the windowing library reports for it. The
    /// window must stay open for as long as the returned object lives.
    #[staticmethod]
    #[pyo3(signature = (kind, window, display, width, height, vsync = true))]
    fn for_window(
        kind: String,
        window: usize,
        display: usize,
        width: u32,
        height: u32,
        vsync: bool,
    ) -> PyResult<Self> {
        Self::check_size(width, height)?;
        Self::guarded(width, height, Some((kind, window, display, vsync)))
    }

    /// Whether frames can be presented to a window.
    #[getter]
    fn has_surface(&self) -> bool {
        self.presenter.is_some()
    }

    /// How many frames have reached the window.
    #[getter]
    fn presented(&self) -> u64 {
        self.presented
    }

    /// Copy the last rendered frame to the window and show it.
    ///
    /// Returns False when there was nothing to show it on this time -- no
    /// window, a minimised one, or a swapchain that had to be rebuilt --
    /// which is a frame skipped, not an error.
    fn present(&mut self) -> bool {
        let Some(presenter) = &self.presenter else {
            return false;
        };
        let frame = match presenter.surface.get_current_texture() {
            wgpu::CurrentSurfaceTexture::Success(frame)
            | wgpu::CurrentSurfaceTexture::Suboptimal(frame) => frame,
            wgpu::CurrentSurfaceTexture::Outdated | wgpu::CurrentSurfaceTexture::Lost => {
                presenter.surface.configure(&self.device, &presenter.config);
                return false;
            }
            _ => return false,
        };
        let view = frame.texture.create_view(&wgpu::TextureViewDescriptor::default());
        let mut encoder = self
            .device
            .create_command_encoder(&wgpu::CommandEncoderDescriptor { label: Some("pyguara present") });
        {
            let mut pass = encoder.begin_render_pass(&wgpu::RenderPassDescriptor {
                label: Some("pyguara present"),
                color_attachments: &[Some(wgpu::RenderPassColorAttachment {
                    view: &view,
                    depth_slice: None,
                    resolve_target: None,
                    ops: wgpu::Operations {
                        load: wgpu::LoadOp::Clear(wgpu::Color::BLACK),
                        store: wgpu::StoreOp::Store,
                    },
                })],
                ..Default::default()
            });
            pass.set_pipeline(&presenter.pipeline);
            pass.set_bind_group(0, &presenter.group, &[]);
            pass.draw(0..3, 0..1);
        }
        self.queue.submit([encoder.finish()]);
        self.queue.present(frame);
        self.presented += 1;
        true
    }

    /// Which backend and adapter the device is on, for the boot log.
    #[getter]
    fn adapter(&self) -> &str {
        &self.adapter
    }

    #[getter]
    fn width(&self) -> u32 {
        self.main().width
    }

    #[getter]
    fn height(&self) -> u32 {
        self.main().height
    }

    /// How many frames `end_frame` has rendered.
    #[getter]
    fn frames(&self) -> u64 {
        self.frames
    }

    /// How many primitives the frame being built holds.
    #[getter]
    fn pending(&self) -> usize {
        self.instances.len()
    }

    /// How many draw calls the frame being built would issue.
    #[getter]
    fn pending_runs(&self) -> usize {
        self.steps
            .iter()
            .map(|step| match step {
                Step::Draw { runs, .. } => runs.len(),
                Step::Shader { .. } => 1,
            })
            .sum()
    }

    /// How many steps -- draws into a target, fullscreen passes -- the
    /// frame being built holds.
    #[getter]
    fn pending_steps(&self) -> usize {
        self.steps.len()
    }

    /// Replace the target with one of a new size. Drops the frame in progress.
    fn resize(&mut self, width: u32, height: u32) -> PyResult<()> {
        Self::check_size(width, height)?;
        self.targets.insert(MAIN, make_target(&self.device, width, height, TARGET_FORMAT));
        if self.presenter.is_some() {
            let group = self.frame_group();
            if let Some(presenter) = &mut self.presenter {
                presenter.group = group;
                presenter.config.width = width;
                presenter.config.height = height;
                presenter.surface.configure(&self.device, &presenter.config);
            }
        }
        self.instances.clear();
        self.steps.clear();
        self.current = MAIN;
        self.scissor = None;
        Ok(())
    }

    /// Upload an RGBA image and return its id.
    ///
    /// `smooth` samples it bilinearly when it is drawn scaled or turned;
    /// otherwise texel for texel, as pygame scales.
    #[pyo3(signature = (width, height, pixels, smooth = false))]
    fn create_texture(&mut self, width: u32, height: u32, pixels: &[u8], smooth: bool) -> PyResult<u32> {
        let image = self.upload_image(width, height, pixels, smooth)?;
        let id = self.next_image;
        self.next_image += 1;
        self.images.insert(id, image);
        Ok(id)
    }

    /// Free a texture. Unknown ids are ignored, so a cache can evict freely.
    ///
    /// Primitives already pushed with it this frame are dropped with it:
    /// a run naming a missing texture is skipped at draw time.
    fn destroy_texture(&mut self, id: u32) {
        if id != WHITE {
            self.images.remove(&id);
        }
    }

    /// How many textures are held, the white pixel included.
    #[getter]
    fn texture_count(&self) -> usize {
        self.images.len()
    }

    /// Clear the target to a colour.
    ///
    /// With no scissor set this discards everything pushed so far, since
    /// it would all be painted over. With one set it clears only that
    /// rectangle, which is what `IRenderer.clear` means inside a viewport.
    fn clear(&mut self, red: u8, green: u8, blue: u8, alpha: u8) {
        match self.scissor {
            None => self.clear_target(
                f64::from(red) / 255.0,
                f64::from(green) / 255.0,
                f64::from(blue) / 255.0,
                f64::from(alpha) / 255.0,
            ),
            Some([x, y, width, height]) => {
                // Opaque by construction: a clear replaces, it does not blend.
                self.solid(
                    x as f32,
                    y as f32,
                    width as f32,
                    height as f32,
                    [unit(red), unit(green), unit(blue), 1.0],
                );
            }
        }
    }

    /// Restrict what follows to a rectangle, clamped to the target.
    fn set_scissor(&mut self, x: i64, y: i64, width: i64, height: i64) {
        let (target_width, target_height) = self.target_size(self.current);
        let left = x.clamp(0, i64::from(target_width));
        let top = y.clamp(0, i64::from(target_height));
        let right = (x + width).clamp(left, i64::from(target_width));
        let bottom = (y + height).clamp(top, i64::from(target_height));
        self.scissor = Some([
            left as u32,
            top as u32,
            (right - left) as u32,
            (bottom - top) as u32,
        ]);
    }

    /// Draw to the whole target again.
    fn clear_scissor(&mut self) {
        self.scissor = None;
    }

    /// Clear the current target, whatever the scissor, to a colour given
    /// in 0-1 floats.
    ///
    /// What was pushed into this target since the last step that did
    /// something else is dropped, since it would all be painted over.
    /// The main target keeps the colour: it is cleared to it at the start
    /// of every frame, until told otherwise, as it always was.
    fn clear_target(&mut self, red: f64, green: f64, blue: f64, alpha: f64) {
        let fill = color(red, green, blue, alpha);
        if self.current == MAIN {
            self.main_clear = fill;
        }
        if let Some(Step::Draw { target, clear, runs, first }) = self.steps.last_mut() {
            if *target == self.current {
                self.instances.truncate(*first);
                runs.clear();
                *clear = Some(fill);
                return;
            }
        }
        self.steps.push(Step::Draw {
            target: self.current,
            clear: Some(fill),
            runs: Vec::new(),
            first: self.instances.len(),
        });
    }

    /// Make an offscreen target and return its id.
    ///
    /// `hdr` makes it 16-bit float, so values above 1.0 survive -- the
    /// render graph's chain is declared that way. Otherwise 8-bit, like
    /// the main target.
    #[pyo3(signature = (width, height, hdr = false))]
    fn create_target(&mut self, width: u32, height: u32, hdr: bool) -> PyResult<u32> {
        Self::check_size(width, height)?;
        let format = if hdr { HDR_FORMAT } else { TARGET_FORMAT };
        let id = self.next_target;
        self.next_target += 1;
        self.targets.insert(id, make_target(&self.device, width, height, format));
        Ok(id)
    }

    /// Give an offscreen target a new size. Its contents are lost.
    fn resize_target(&mut self, id: u32, width: u32, height: u32) -> PyResult<()> {
        Self::check_size(width, height)?;
        if id == MAIN {
            return Err(PyValueError::new_err("resize the main target with resize()"));
        }
        let Some(format) = self.targets.get(&id).map(|target| target.format) else {
            return Err(PyKeyError::new_err(format!("no target {id}")));
        };
        self.targets.insert(id, make_target(&self.device, width, height, format));
        Ok(())
    }

    /// Free an offscreen target. Unknown ids, and the main one, are ignored.
    ///
    /// A step already queued into it, or reading it, is skipped.
    fn destroy_target(&mut self, id: u32) {
        if id != MAIN {
            self.targets.remove(&id);
        }
        if self.current == id {
            self.current = MAIN;
        }
    }

    /// Send what is pushed from now on to a target; 0 is the main one.
    ///
    /// The scissor is dropped: it was a rectangle on the other target.
    fn set_target(&mut self, id: u32) -> PyResult<()> {
        if !self.targets.contains_key(&id) {
            return Err(PyKeyError::new_err(format!("no target {id}")));
        }
        self.current = id;
        self.scissor = None;
        Ok(())
    }

    /// Which target pushes go to.
    #[getter]
    fn current_target(&self) -> u32 {
        self.current
    }

    /// The size of the target pushes go to, in pixels.
    #[getter]
    fn current_size(&self) -> (u32, u32) {
        self.target_size(self.current)
    }

    /// How many targets exist, the main one included.
    #[getter]
    fn target_count(&self) -> usize {
        self.targets.len()
    }

    /// Compile a sprite material and return its id.
    ///
    /// `source` is the author's part of the module: their uniforms as a
    /// `Params` struct at `@group(2) @binding(0)` when `uniform_bytes` is
    /// above zero, `material_texture` and `material_sampler` at bindings 1
    /// and 2 when `has_texture`, and `fn material(sprite: Sprite) ->
    /// vec4<f32>`. The engine's vertex stage, the sprite texture and the
    /// fragment entry point that calls `material` are added here, so a
    /// material sprite is placed exactly as any other sprite.
    ///
    /// A material that does not compile is a `ValueError`, with the
    /// compiler's message.
    #[pyo3(signature = (source, uniform_bytes, has_texture = false))]
    fn create_material(&mut self, source: &str, uniform_bytes: usize, has_texture: bool) -> PyResult<u32> {
        let scope = self.device.push_error_scope(wgpu::ErrorFilter::Validation);
        let module = self.device.create_shader_module(wgpu::ShaderModuleDescriptor {
            label: Some("pyguara material"),
            source: wgpu::ShaderSource::Wgsl(
                format!("{QUAD_VERTEX}{MATERIAL_PRELUDE}{source}{MATERIAL_FRAGMENT}").into(),
            ),
        });
        let mut entries = Vec::new();
        if uniform_bytes > 0 {
            entries.push(wgpu::BindGroupLayoutEntry {
                binding: 0,
                visibility: wgpu::ShaderStages::FRAGMENT,
                ty: wgpu::BindingType::Buffer {
                    ty: wgpu::BufferBindingType::Uniform,
                    has_dynamic_offset: false,
                    min_binding_size: None,
                },
                count: None,
            });
        }
        if has_texture {
            entries.push(wgpu::BindGroupLayoutEntry {
                binding: 1,
                visibility: wgpu::ShaderStages::FRAGMENT,
                ty: wgpu::BindingType::Texture {
                    sample_type: wgpu::TextureSampleType::Float { filterable: true },
                    view_dimension: wgpu::TextureViewDimension::D2,
                    multisampled: false,
                },
                count: None,
            });
            entries.push(wgpu::BindGroupLayoutEntry {
                binding: 2,
                visibility: wgpu::ShaderStages::FRAGMENT,
                ty: wgpu::BindingType::Sampler(wgpu::SamplerBindingType::Filtering),
                count: None,
            });
        }
        let group_layout = self.device.create_bind_group_layout(&wgpu::BindGroupLayoutDescriptor {
            label: Some("pyguara material"),
            entries: &entries,
        });
        let layout = self.device.create_pipeline_layout(&wgpu::PipelineLayoutDescriptor {
            label: Some("pyguara material"),
            bind_group_layouts: &[Some(&self.globals_layout), Some(&self.image_layout), Some(&group_layout)],
            ..Default::default()
        });
        let pipelines = HashMap::from([
            (TARGET_FORMAT, make_quad_pipeline(&self.device, &layout, &module, TARGET_FORMAT)),
            (HDR_FORMAT, make_quad_pipeline(&self.device, &layout, &module, HDR_FORMAT)),
        ]);
        if let Some(error) = pollster::block_on(scope.pop()) {
            return Err(PyValueError::new_err(format!("the material does not compile: {error}")));
        }
        let id = self.next_material;
        self.next_material += 1;
        self.materials.insert(
            id,
            Material {
                group_layout,
                uniform_bytes,
                has_texture,
                pipelines,
            },
        );
        Ok(id)
    }

    /// Draw what is pushed from now on with a material, these uniforms and,
    /// if it takes one, this second texture -- until `clear_material`.
    #[pyo3(signature = (material, uniforms, texture = None))]
    fn set_material(&mut self, material: u32, uniforms: &[u8], texture: Option<u32>) -> PyResult<()> {
        let Some(found) = self.materials.get(&material) else {
            return Err(PyKeyError::new_err(format!("no material {material}")));
        };
        if uniforms.len() != found.uniform_bytes {
            return Err(PyValueError::new_err(format!(
                "the material's uniforms are {} bytes, got {}",
                found.uniform_bytes,
                uniforms.len()
            )));
        }
        let image = match (found.has_texture, texture) {
            (true, Some(id)) => match self.images.get(&id) {
                Some(image) => Some(image),
                None => return Err(PyKeyError::new_err(format!("no texture {id}"))),
            },
            (true, None) => return Err(PyValueError::new_err("the material samples a texture; none given")),
            (false, _) => None,
        };
        let buffer = (found.uniform_bytes > 0).then(|| {
            let size = found.uniform_bytes.next_multiple_of(16);
            let buffer = self.device.create_buffer(&wgpu::BufferDescriptor {
                label: Some("pyguara material uniforms"),
                size: size as u64,
                usage: wgpu::BufferUsages::UNIFORM | wgpu::BufferUsages::COPY_DST,
                mapped_at_creation: false,
            });
            let mut padded = uniforms.to_vec();
            padded.resize(size, 0);
            self.queue.write_buffer(&buffer, 0, &padded);
            buffer
        });
        let mut entries = Vec::new();
        if let Some(buffer) = &buffer {
            entries.push(wgpu::BindGroupEntry {
                binding: 0,
                resource: buffer.as_entire_binding(),
            });
        }
        if let Some(image) = image {
            entries.push(wgpu::BindGroupEntry {
                binding: 1,
                resource: wgpu::BindingResource::TextureView(&image.view),
            });
            entries.push(wgpu::BindGroupEntry {
                binding: 2,
                resource: wgpu::BindingResource::Sampler(if image.smooth {
                    &self.smooth_sampler
                } else {
                    &self.sampler
                }),
            });
        }
        let group = self.device.create_bind_group(&wgpu::BindGroupDescriptor {
            label: Some("pyguara material"),
            layout: &found.group_layout,
            entries: &entries,
        });
        self.material_bindings.push((material, group));
        self.current_material = Some(self.material_bindings.len() - 1);
        Ok(())
    }

    /// Draw what is pushed from now on with the default fragment again.
    fn clear_material(&mut self) {
        self.current_material = None;
    }

    /// Compile a fullscreen shader and return its id.
    ///
    /// `source` is complete WGSL with a `vertex` and a `fragment` entry
    /// point, binding at group 0: the uniforms at 0 when `uniform_bytes`
    /// is above zero, a sampler at 1, and one texture per input from 2.
    /// `pyguara.graphics.pipeline.device` writes that preamble; this only
    /// compiles it. A shader that does not compile is a `ValueError`
    /// here, with the compiler's message, rather than an abort mid-frame.
    ///
    /// `attributes`, when given, makes it an instanced effect: one float
    /// count (1 to 4) per per-instance attribute, at `@location(0)` on,
    /// tightly packed. Draw it with `instanced`, not `fullscreen`.
    #[pyo3(signature = (source, inputs, uniform_bytes, attributes = None))]
    fn create_effect(
        &mut self,
        source: &str,
        inputs: usize,
        uniform_bytes: usize,
        attributes: Option<Vec<u32>>,
    ) -> PyResult<u32> {
        let mut layout_attributes = Vec::new();
        let mut stride = 0u64;
        for (location, count) in attributes.unwrap_or_default().into_iter().enumerate() {
            let format = match count {
                1 => wgpu::VertexFormat::Float32,
                2 => wgpu::VertexFormat::Float32x2,
                3 => wgpu::VertexFormat::Float32x3,
                4 => wgpu::VertexFormat::Float32x4,
                _ => return Err(PyValueError::new_err(format!("an attribute is 1 to 4 floats, not {count}"))),
            };
            layout_attributes.push(wgpu::VertexAttribute {
                format,
                offset: stride,
                shader_location: location as u32,
            });
            stride += u64::from(count) * 4;
        }
        let scope = self.device.push_error_scope(wgpu::ErrorFilter::Validation);
        let module = self.device.create_shader_module(wgpu::ShaderModuleDescriptor {
            label: Some("pyguara effect"),
            source: wgpu::ShaderSource::Wgsl(source.into()),
        });
        let mut entries = Vec::new();
        if uniform_bytes > 0 {
            entries.push(wgpu::BindGroupLayoutEntry {
                binding: 0,
                visibility: wgpu::ShaderStages::FRAGMENT | wgpu::ShaderStages::VERTEX,
                ty: wgpu::BindingType::Buffer {
                    ty: wgpu::BufferBindingType::Uniform,
                    has_dynamic_offset: false,
                    min_binding_size: None,
                },
                count: None,
            });
        }
        entries.push(wgpu::BindGroupLayoutEntry {
            binding: 1,
            visibility: wgpu::ShaderStages::FRAGMENT,
            ty: wgpu::BindingType::Sampler(wgpu::SamplerBindingType::Filtering),
            count: None,
        });
        for index in 0..inputs {
            entries.push(wgpu::BindGroupLayoutEntry {
                binding: 2 + index as u32,
                visibility: wgpu::ShaderStages::FRAGMENT,
                ty: wgpu::BindingType::Texture {
                    sample_type: wgpu::TextureSampleType::Float { filterable: true },
                    view_dimension: wgpu::TextureViewDimension::D2,
                    multisampled: false,
                },
                count: None,
            });
        }
        let group_layout = self.device.create_bind_group_layout(&wgpu::BindGroupLayoutDescriptor {
            label: Some("pyguara effect"),
            entries: &entries,
        });
        let layout = self.device.create_pipeline_layout(&wgpu::PipelineLayoutDescriptor {
            label: Some("pyguara effect"),
            bind_group_layouts: &[Some(&group_layout)],
            ..Default::default()
        });
        let id = self.next_effect;
        self.next_effect += 1;
        self.effects.insert(
            id,
            Effect {
                module,
                group_layout,
                layout,
                inputs,
                uniform_bytes,
                attributes: layout_attributes,
                stride,
                pipelines: HashMap::new(),
            },
        );
        // Built now, inside the scope, so a wrong entry point or binding
        // is reported with the compile errors rather than at first use.
        let built = self.effect_pipeline(id, TARGET_FORMAT, BLEND_REPLACE);
        if let Some(error) = pollster::block_on(scope.pop()) {
            self.effects.remove(&id);
            return Err(PyValueError::new_err(format!("the effect does not compile: {error}")));
        }
        built?;
        Ok(id)
    }

    /// Queue a fullscreen pass: `effect` reads `inputs` (target ids) and
    /// writes `target`.
    ///
    /// `uniforms` are the bytes of the shader's uniform struct, already
    /// laid out. `blend` is 0 to replace, 1 to add, 2 to alpha-blend.
    /// `viewport` restricts it to a rectangle of the target; `clear`
    /// clears the whole target first, which is how a letterbox's bars are
    /// filled.
    #[pyo3(signature = (effect, target, inputs, uniforms, blend = 0, viewport = None, clear = None))]
    #[allow(clippy::too_many_arguments)]
    fn fullscreen(
        &mut self,
        effect: u32,
        target: u32,
        inputs: Vec<u32>,
        uniforms: &[u8],
        blend: u8,
        viewport: Option<(u32, u32, u32, u32)>,
        clear: Option<(f64, f64, f64, f64)>,
    ) -> PyResult<()> {
        if self.effects.get(&effect).is_some_and(|found| found.stride > 0) {
            return Err(PyValueError::new_err("an instanced effect is drawn with instanced()"));
        }
        self.shader_step(effect, target, &inputs, uniforms, blend, viewport, clear, None)
    }

    /// Queue instanced quads: `effect` draws `count` instances read from
    /// `data`, tightly packed rows of its attributes, into `target`.
    ///
    /// Six vertices an instance; the effect's vertex stage places them.
    #[pyo3(signature = (effect, target, data, count, uniforms, blend = 0))]
    fn instanced(
        &mut self,
        effect: u32,
        target: u32,
        data: &[u8],
        count: u32,
        uniforms: &[u8],
        blend: u8,
    ) -> PyResult<()> {
        let stride = match self.effects.get(&effect) {
            Some(found) if found.stride > 0 => found.stride,
            Some(_) => return Err(PyValueError::new_err("a fullscreen effect is drawn with fullscreen()")),
            None => return Err(PyKeyError::new_err(format!("no effect {effect}"))),
        };
        if data.len() as u64 != stride * u64::from(count) {
            return Err(PyValueError::new_err(format!(
                "{count} instances of {stride} bytes are {} bytes, got {}",
                stride * u64::from(count),
                data.len()
            )));
        }
        if count == 0 {
            // Nothing to draw, but the target still becomes current, as
            // binding a framebuffer does whether or not anything follows.
            return if self.targets.contains_key(&target) {
                Ok(())
            } else {
                Err(PyKeyError::new_err(format!("no target {target}")))
            };
        }
        let buffer = self.device.create_buffer(&wgpu::BufferDescriptor {
            label: Some("pyguara effect instances"),
            size: data.len() as u64,
            usage: wgpu::BufferUsages::VERTEX | wgpu::BufferUsages::COPY_DST,
            mapped_at_creation: false,
        });
        self.queue.write_buffer(&buffer, 0, data);
        self.shader_step(effect, target, &[], uniforms, blend, None, None, Some((buffer, count)))
    }

    /// A filled rectangle with its top-left corner at `(x, y)`.
    #[allow(clippy::too_many_arguments)]
    fn rect(&mut self, x: f32, y: f32, width: f32, height: f32, red: u8, green: u8, blue: u8, alpha: u8) {
        self.solid(x, y, width, height, [unit(red), unit(green), unit(blue), unit(alpha)]);
    }

    /// A rectangle's outline, `thickness` pixels wide, drawn inside it.
    #[allow(clippy::too_many_arguments)]
    fn rect_outline(
        &mut self,
        x: f32,
        y: f32,
        width: f32,
        height: f32,
        thickness: f32,
        red: u8,
        green: u8,
        blue: u8,
        alpha: u8,
    ) {
        let color = [unit(red), unit(green), unit(blue), unit(alpha)];
        let edge = thickness.min(width * 0.5).min(height * 0.5);
        if edge <= 0.0 {
            return;
        }
        // Top and bottom span the width; the sides fill what is between,
        // so no pixel is drawn twice and a translucent outline stays even.
        self.solid(x, y, width, edge, color);
        self.solid(x, y + height - edge, width, edge, color);
        self.solid(x, y + edge, edge, height - 2.0 * edge, color);
        self.solid(x + width - edge, y + edge, edge, height - 2.0 * edge, color);
    }

    /// A rectangle with rounded corners; `thickness` above zero outlines it.
    #[allow(clippy::too_many_arguments)]
    fn rounded_rect(
        &mut self,
        x: f32,
        y: f32,
        width: f32,
        height: f32,
        radius: f32,
        thickness: f32,
        red: u8,
        green: u8,
        blue: u8,
        alpha: u8,
    ) {
        if width <= 0.0 || height <= 0.0 {
            return;
        }
        let half = [width * 0.5, height * 0.5];
        self.push(
            WHITE,
            Instance {
                center: [x + half[0], y + half[1]],
                half,
                turn: [1.0, 0.0],
                uv_low: [0.0, 0.0],
                uv_high: [1.0, 1.0],
                color: [unit(red), unit(green), unit(blue), unit(alpha)],
                params: [
                    KIND_ROUNDED,
                    radius.clamp(0.0, half[0].min(half[1])),
                    thickness.max(0.0),
                    0.0,
                ],
            },
        );
    }

    /// A circle of `radius` about `(x, y)`; `inner` above zero makes a ring.
    #[allow(clippy::too_many_arguments)]
    fn circle(&mut self, x: f32, y: f32, radius: f32, inner: f32, red: u8, green: u8, blue: u8, alpha: u8) {
        if radius <= 0.0 {
            return;
        }
        self.push(
            WHITE,
            Instance {
                center: [x, y],
                half: [radius, radius],
                turn: [1.0, 0.0],
                uv_low: [0.0, 0.0],
                uv_high: [1.0, 1.0],
                color: [unit(red), unit(green), unit(blue), unit(alpha)],
                params: [KIND_CIRCLE, radius, inner.max(0.0), 0.0],
            },
        );
    }

    /// A line from one point to another, `thickness` pixels wide.
    #[allow(clippy::too_many_arguments)]
    fn line(
        &mut self,
        from_x: f32,
        from_y: f32,
        to_x: f32,
        to_y: f32,
        thickness: f32,
        red: u8,
        green: u8,
        blue: u8,
        alpha: u8,
    ) {
        let along_x = to_x - from_x;
        let along_y = to_y - from_y;
        let length = (along_x * along_x + along_y * along_y).sqrt();
        if thickness <= 0.0 {
            return;
        }
        let (cos, sin) = if length > 0.0 {
            (along_x / length, along_y / length)
        } else {
            (1.0, 0.0)
        };
        self.push(
            WHITE,
            Instance {
                center: [(from_x + to_x) * 0.5, (from_y + to_y) * 0.5],
                half: [length * 0.5, thickness * 0.5],
                turn: [cos, sin],
                uv_low: [0.0, 0.0],
                uv_high: [1.0, 1.0],
                color: [unit(red), unit(green), unit(blue), unit(alpha)],
                params: [KIND_QUAD, 0.0, 0.0, 0.0],
            },
        );
    }

    /// A textured quad centred on `(x, y)`.
    ///
    /// `half_width`/`half_height` are in pixels; a negative one flips.
    /// The source rectangle is in texels. `turn` is in degrees, clockwise
    /// on a y-down screen, as the engine's other renderers turn.
    #[pyo3(signature = (texture, x, y, half_width, half_height, source_x, source_y, source_width, source_height, turn, red, green, blue, alpha))]
    #[allow(clippy::too_many_arguments)]
    fn quad(
        &mut self,
        texture: u32,
        x: f32,
        y: f32,
        half_width: f32,
        half_height: f32,
        source_x: f32,
        source_y: f32,
        source_width: f32,
        source_height: f32,
        turn: f32,
        red: u8,
        green: u8,
        blue: u8,
        alpha: u8,
    ) -> PyResult<()> {
        let Some(image) = self.images.get(&texture) else {
            return Err(PyKeyError::new_err(format!("no texture {texture}")));
        };
        let (width, height) = (image.width as f32, image.height as f32);
        let mut uv_low = [source_x / width, source_y / height];
        let mut uv_high = [(source_x + source_width) / width, (source_y + source_height) / height];
        if half_width < 0.0 {
            std::mem::swap(&mut uv_low[0], &mut uv_high[0]);
        }
        if half_height < 0.0 {
            std::mem::swap(&mut uv_low[1], &mut uv_high[1]);
        }
        let radians = turn.to_radians();
        self.push(
            texture,
            Instance {
                center: [x, y],
                half: [half_width.abs(), half_height.abs()],
                turn: [radians.cos(), radians.sin()],
                uv_low,
                uv_high,
                color: [unit(red), unit(green), unit(blue), unit(alpha)],
                params: [KIND_QUAD, 0.0, 0.0, 0.0],
            },
        );
        Ok(())
    }

    /// Many sprites of one texture, placed as the pygame backend places them.
    ///
    /// `WgpuRenderer.render_batch`'s per-sprite loop, moved here so a batch
    /// is one call: `destinations` is each sprite's top-left corner, and
    /// the other lists are optional and per sprite, applied to sprite `i`
    /// only when the list reaches index `i` -- the guard the pygame
    /// backend uses. A region is `(x, y, width, height)` in texels, or
    /// None for the whole texture; `rotations` are degrees, `scales` are
    /// factors, `colors` are 0-255 tints.
    ///
    /// **The arithmetic is the Python loop's, in `f64`, in the same
    /// order**, and the result is narrowed to `f32` exactly where `quad`'s
    /// arguments were. `f64::cos` is the platform's libm, as `math.cos`
    /// is, so a batch drawn here and one drawn a sprite at a time through
    /// `quad` produce the same instances; `tests/integration/test_wgpu_pixels.py`
    /// compares the two.
    #[pyo3(signature = (texture, destinations, regions = None, rotations = None, scales = None, colors = None))]
    #[allow(clippy::too_many_arguments)]
    fn sprites(
        &mut self,
        texture: u32,
        destinations: Vec<(f64, f64)>,
        regions: Option<Vec<Option<(f64, f64, f64, f64)>>>,
        rotations: Option<Vec<f64>>,
        scales: Option<Vec<(f64, f64)>>,
        colors: Option<Vec<(u8, u8, u8, u8)>>,
    ) -> PyResult<()> {
        let Some(image) = self.images.get(&texture) else {
            return Err(PyKeyError::new_err(format!("no texture {texture}")));
        };
        let (full_width, full_height) = (image.width, image.height);
        let (texture_width, texture_height) = (full_width as f32, full_height as f32);
        let regions = regions.unwrap_or_default();
        let rotations = rotations.unwrap_or_default();
        let scales = scales.unwrap_or_default();
        let colors = colors.unwrap_or_default();
        self.instances.reserve(destinations.len());

        for (index, (x, y)) in destinations.into_iter().enumerate() {
            // Python's `int(region.x)`: truncation toward zero.
            let (source_x, source_y, width, height) = match regions.get(index).copied().flatten() {
                Some((rx, ry, rw, rh)) => (rx.trunc(), ry.trunc(), rw.trunc(), rh.trunc()),
                None => (0.0, 0.0, f64::from(full_width), f64::from(full_height)),
            };
            let turn = rotations.get(index).copied().unwrap_or(0.0);
            let (mut drawn_width, mut drawn_height) = (width, height);
            if let Some(&(scale_x, scale_y)) = scales.get(index) {
                drawn_width = (width * scale_x).trunc();
                drawn_height = (height * scale_y).trunc();
            }
            let (box_width, box_height) = if turn != 0.0 {
                let radians = turn.to_radians();
                let (cos, sin) = (radians.cos().abs(), radians.sin().abs());
                (
                    (width * cos + height * sin) * (drawn_width / width),
                    (width * sin + height * cos) * (drawn_height / height),
                )
            } else {
                (drawn_width, drawn_height)
            };
            let (red, green, blue, alpha) = colors.get(index).copied().unwrap_or((255, 255, 255, 255));

            // From here on, `quad` with the arguments the loop passed it.
            let half_width = (drawn_width / 2.0) as f32;
            let half_height = (drawn_height / 2.0) as f32;
            let (source_x, source_y) = (source_x as f32, source_y as f32);
            let (source_width, source_height) = (width as f32, height as f32);
            let mut uv_low = [source_x / texture_width, source_y / texture_height];
            let mut uv_high = [
                (source_x + source_width) / texture_width,
                (source_y + source_height) / texture_height,
            ];
            if half_width < 0.0 {
                std::mem::swap(&mut uv_low[0], &mut uv_high[0]);
            }
            if half_height < 0.0 {
                std::mem::swap(&mut uv_low[1], &mut uv_high[1]);
            }
            let radians = (turn as f32).to_radians();
            self.push(
                texture,
                Instance {
                    center: [(x + box_width / 2.0) as f32, (y + box_height / 2.0) as f32],
                    half: [half_width.abs(), half_height.abs()],
                    turn: [radians.cos(), radians.sin()],
                    uv_low,
                    uv_high,
                    color: [unit(red), unit(green), unit(blue), unit(alpha)],
                    params: [KIND_QUAD, 0.0, 0.0, 0.0],
                },
            );
        }
        Ok(())
    }

    /// Render the frame's steps in order, and start a new frame.
    ///
    /// Each step is one render pass: a draw step loads its target (or
    /// clears it, if it was cleared) and draws its runs; a fullscreen step
    /// runs its shader over the target. The main target is cleared to its
    /// colour by whichever step reaches it first, or on its own if none
    /// does, so a frame that draws nothing still shows the clear colour.
    fn end_frame(&mut self) {
        if self.instances.len() > self.instance_capacity {
            self.instance_capacity = self.instances.len().next_power_of_two();
            self.instance_buffer = make_instance_buffer(&self.device, self.instance_capacity);
        }
        if !self.instances.is_empty() {
            self.queue
                .write_buffer(&self.instance_buffer, 0, bytemuck::cast_slice(&self.instances));
        }
        // One slot of globals per draw step: the size of what it draws into.
        let draws = self.steps.iter().filter(|step| matches!(step, Step::Draw { .. })).count();
        if draws > self.globals_capacity {
            self.globals_capacity = draws.next_power_of_two();
            let (buffer, group) = make_globals(&self.device, &self.globals_layout, self.globals_capacity);
            self.globals = buffer;
            self.globals_group = group;
        }
        let mut slots = vec![0u8; GLOBALS_STRIDE as usize * draws.max(1)];
        let mut slot = 0;
        for step in &self.steps {
            if let Step::Draw { target, .. } = step {
                let (width, height) = self.target_size(*target);
                let size: [f32; 4] = [width as f32, height as f32, 0.0, 0.0];
                let at = slot * GLOBALS_STRIDE as usize;
                slots[at..at + 16].copy_from_slice(bytemuck::cast_slice(&size));
                slot += 1;
            }
        }
        self.queue.write_buffer(&self.globals, 0, &slots);

        let mut encoder = self
            .device
            .create_command_encoder(&wgpu::CommandEncoderDescriptor { label: Some("pyguara frame") });
        let mut main_cleared = false;
        let mut slot = 0u32;
        for step in &self.steps {
            let (target_id, own_clear) = match step {
                Step::Draw { target, clear, .. } | Step::Shader { target, clear, .. } => (*target, *clear),
            };
            let globals_offset = slot * GLOBALS_STRIDE as u32;
            if matches!(step, Step::Draw { .. }) {
                slot += 1;
            }
            let Some(target) = self.targets.get(&target_id) else {
                continue;
            };
            let load = match own_clear {
                Some(fill) => wgpu::LoadOp::Clear(fill),
                None if target_id == MAIN && !main_cleared => wgpu::LoadOp::Clear(self.main_clear),
                None => wgpu::LoadOp::Load,
            };
            if target_id == MAIN {
                main_cleared = true;
            }
            let mut pass = encoder.begin_render_pass(&wgpu::RenderPassDescriptor {
                label: Some("pyguara step"),
                color_attachments: &[Some(wgpu::RenderPassColorAttachment {
                    view: &target.view,
                    depth_slice: None,
                    resolve_target: None,
                    ops: wgpu::Operations {
                        load,
                        store: wgpu::StoreOp::Store,
                    },
                })],
                ..Default::default()
            });
            match step {
                Step::Draw { runs, .. } => {
                    if runs.is_empty() {
                        continue;
                    }
                    pass.set_vertex_buffer(0, self.instance_buffer.slice(..));
                    // The pipeline changes only where a run's material does.
                    let mut drawing: Option<Option<usize>> = None;
                    for run in runs {
                        let Some(image) = self.images.get(&run.texture) else {
                            continue;
                        };
                        if drawing != Some(run.material) {
                            match run.material {
                                None => pass.set_pipeline(&self.pipelines[&target.format]),
                                Some(binding) => {
                                    let (material, group) = &self.material_bindings[binding];
                                    let Some(found) = self.materials.get(material) else {
                                        continue;
                                    };
                                    pass.set_pipeline(&found.pipelines[&target.format]);
                                    pass.set_bind_group(2, group, &[]);
                                }
                            }
                            pass.set_bind_group(0, &self.globals_group, &[globals_offset]);
                            drawing = Some(run.material);
                        }
                        match run.scissor {
                            Some([_, _, 0, _] | [_, _, _, 0]) => continue,
                            Some([x, y, width, height]) => pass.set_scissor_rect(x, y, width, height),
                            None => pass.set_scissor_rect(0, 0, target.width, target.height),
                        }
                        pass.set_bind_group(1, &image.bind_group, &[]);
                        pass.draw(0..6, run.start..run.start + run.count);
                    }
                }
                Step::Shader {
                    pipeline,
                    group,
                    viewport,
                    instances,
                    ..
                } => {
                    if let Some([x, y, width, height]) = *viewport {
                        let right = (x + width).min(target.width);
                        let bottom = (y + height).min(target.height);
                        if right <= x || bottom <= y {
                            continue;
                        }
                        pass.set_viewport(x as f32, y as f32, width as f32, height as f32, 0.0, 1.0);
                        pass.set_scissor_rect(x, y, right - x, bottom - y);
                    }
                    pass.set_pipeline(pipeline);
                    pass.set_bind_group(0, group, &[]);
                    match instances {
                        Some((buffer, count)) => {
                            pass.set_vertex_buffer(0, buffer.slice(..));
                            pass.draw(0..6, 0..*count);
                        }
                        None => pass.draw(0..3, 0..1),
                    }
                }
            }
        }
        if !main_cleared {
            let main = self.main();
            encoder.begin_render_pass(&wgpu::RenderPassDescriptor {
                label: Some("pyguara clear"),
                color_attachments: &[Some(wgpu::RenderPassColorAttachment {
                    view: &main.view,
                    depth_slice: None,
                    resolve_target: None,
                    ops: wgpu::Operations {
                        load: wgpu::LoadOp::Clear(self.main_clear),
                        store: wgpu::StoreOp::Store,
                    },
                })],
                ..Default::default()
            });
        }
        self.queue.submit([encoder.finish()]);
        self.instances.clear();
        self.steps.clear();
        self.material_bindings.clear();
        self.current_material = None;
        self.current = MAIN;
        self.scissor = None;
        self.frames += 1;
    }

    /// Copy a target out as tightly packed rows: the main one by default.
    ///
    /// Four bytes a pixel, RGBA, for an 8-bit target; eight for an HDR
    /// one, RGBA as little-endian 16-bit floats.
    #[pyo3(signature = (target = MAIN))]
    fn read_pixels<'py>(&self, python: Python<'py>, target: u32) -> PyResult<Bound<'py, PyBytes>> {
        let Some(found) = self.targets.get(&target) else {
            return Err(PyKeyError::new_err(format!("no target {target}")));
        };
        let (width, height) = (found.width, found.height);
        let texel = if found.format == HDR_FORMAT { 8 } else { 4 };
        // A copy's rows must be padded to a multiple of 256 bytes.
        let row = width as usize * texel;
        let padded = row.div_ceil(256) * 256;
        let buffer = self.device.create_buffer(&wgpu::BufferDescriptor {
            label: Some("pyguara readback"),
            size: (padded * height as usize) as u64,
            usage: wgpu::BufferUsages::COPY_DST | wgpu::BufferUsages::MAP_READ,
            mapped_at_creation: false,
        });
        let mut encoder = self
            .device
            .create_command_encoder(&wgpu::CommandEncoderDescriptor { label: Some("pyguara readback") });
        encoder.copy_texture_to_buffer(
            wgpu::TexelCopyTextureInfo {
                texture: &found.texture,
                mip_level: 0,
                origin: wgpu::Origin3d::ZERO,
                aspect: wgpu::TextureAspect::All,
            },
            wgpu::TexelCopyBufferInfo {
                buffer: &buffer,
                layout: wgpu::TexelCopyBufferLayout {
                    offset: 0,
                    bytes_per_row: Some(padded as u32),
                    rows_per_image: Some(height),
                },
            },
            wgpu::Extent3d {
                width,
                height,
                depth_or_array_layers: 1,
            },
        );
        self.queue.submit([encoder.finish()]);
        let slice = buffer.slice(..);
        slice.map_async(wgpu::MapMode::Read, |_| {});
        self.device
            .poll(wgpu::PollType::wait_indefinitely())
            .map_err(|error| runtime_error("waiting for the frame to be copied out failed", error))?;
        let mapped = slice
            .get_mapped_range()
            .map_err(|error| runtime_error("the copied frame could not be read", error))?;
        let height = height as usize;
        PyBytes::new_with(python, row * height, |out| {
            for line in 0..height {
                out[line * row..(line + 1) * row]
                    .copy_from_slice(&mapped[line * padded..line * padded + row]);
            }
            Ok(())
        })
    }
}
