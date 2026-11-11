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

const SHADER: &str = r"
struct Globals { size: vec2<f32>, pad: vec2<f32> };
@group(0) @binding(0) var<uniform> globals: Globals;
@group(1) @binding(0) var image: texture_2d<f32>;
@group(1) @binding(1) var image_sampler: sampler;

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
    start: u32,
    count: u32,
}

struct Image {
    // Held so the view and bind group stay valid; never read back.
    _texture: wgpu::Texture,
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
    pipeline: wgpu::RenderPipeline,
    image_layout: wgpu::BindGroupLayout,
    sampler: wgpu::Sampler,
    globals: wgpu::Buffer,
    globals_group: wgpu::BindGroup,
    target: wgpu::Texture,
    target_view: wgpu::TextureView,
    width: u32,
    height: u32,
    instances: Vec<Instance>,
    instance_buffer: wgpu::Buffer,
    instance_capacity: usize,
    runs: Vec<Run>,
    scissor: Option<[u32; 4]>,
    clear: wgpu::Color,
    images: HashMap<u32, Image>,
    next_image: u32,
    /// Frames rendered, for callers that want to know one happened.
    frames: u64,
    /// Set when drawing to a window rather than only offscreen.
    presenter: Option<Presenter>,
    /// Frames that reached the window.
    presented: u64,
}

fn make_target(device: &wgpu::Device, width: u32, height: u32) -> (wgpu::Texture, wgpu::TextureView) {
    let target = device.create_texture(&wgpu::TextureDescriptor {
        label: Some("pyguara target"),
        size: wgpu::Extent3d {
            width,
            height,
            depth_or_array_layers: 1,
        },
        mip_level_count: 1,
        sample_count: 1,
        dimension: wgpu::TextureDimension::D2,
        format: TARGET_FORMAT,
        usage: wgpu::TextureUsages::RENDER_ATTACHMENT
            | wgpu::TextureUsages::COPY_SRC
            | wgpu::TextureUsages::TEXTURE_BINDING,
        view_formats: &[],
    });
    let view = target.create_view(&wgpu::TextureViewDescriptor::default());
    (target, view)
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
            source: wgpu::ShaderSource::Wgsl(SHADER.into()),
        });
        let globals_layout = device.create_bind_group_layout(&wgpu::BindGroupLayoutDescriptor {
            label: Some("pyguara globals"),
            entries: &[wgpu::BindGroupLayoutEntry {
                binding: 0,
                visibility: wgpu::ShaderStages::VERTEX,
                ty: wgpu::BindingType::Buffer {
                    ty: wgpu::BufferBindingType::Uniform,
                    has_dynamic_offset: false,
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
        let attributes = wgpu::vertex_attr_array![
            0 => Float32x2, 1 => Float32x2, 2 => Float32x2, 3 => Float32x2,
            4 => Float32x2, 5 => Float32x4, 6 => Float32x4
        ];
        let pipeline = device.create_render_pipeline(&wgpu::RenderPipelineDescriptor {
            label: Some("pyguara quads"),
            layout: Some(&layout),
            vertex: wgpu::VertexState {
                module: &shader,
                entry_point: Some("vertex"),
                compilation_options: wgpu::PipelineCompilationOptions::default(),
                buffers: &[Some(wgpu::VertexBufferLayout {
                    array_stride: std::mem::size_of::<Instance>() as u64,
                    step_mode: wgpu::VertexStepMode::Instance,
                    attributes: &attributes,
                })],
            },
            fragment: Some(wgpu::FragmentState {
                module: &shader,
                entry_point: Some("fragment"),
                compilation_options: wgpu::PipelineCompilationOptions::default(),
                targets: &[Some(wgpu::ColorTargetState {
                    format: TARGET_FORMAT,
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
        });
        // Nearest, as pygame scales: a pixel-art sprite stays pixel art,
        // and text drawn at its own size samples texel for texel.
        let sampler = device.create_sampler(&wgpu::SamplerDescriptor {
            label: Some("pyguara nearest"),
            mag_filter: wgpu::FilterMode::Nearest,
            min_filter: wgpu::FilterMode::Nearest,
            ..Default::default()
        });
        let globals = device.create_buffer(&wgpu::BufferDescriptor {
            label: Some("pyguara globals"),
            size: 16,
            usage: wgpu::BufferUsages::UNIFORM | wgpu::BufferUsages::COPY_DST,
            mapped_at_creation: false,
        });
        let globals_group = device.create_bind_group(&wgpu::BindGroupDescriptor {
            label: Some("pyguara globals"),
            layout: &globals_layout,
            entries: &[wgpu::BindGroupEntry {
                binding: 0,
                resource: globals.as_entire_binding(),
            }],
        });
        let (target, target_view) = make_target(&device, width, height);
        let instance_capacity = 4096;
        let instance_buffer = make_instance_buffer(&device, instance_capacity);

        let mut gpu = Self {
            device,
            queue,
            adapter: format!("{:?}: {}", info.backend, info.name),
            pipeline,
            image_layout,
            sampler,
            globals,
            globals_group,
            target,
            target_view,
            width,
            height,
            instances: Vec::with_capacity(instance_capacity),
            instance_buffer,
            instance_capacity,
            runs: Vec::new(),
            scissor: None,
            clear: wgpu::Color::BLACK,
            images: HashMap::new(),
            next_image: 1,
            frames: 0,
            presenter: None,
            presented: 0,
        };
        let white = gpu.upload_image(1, 1, &[255, 255, 255, 255])?;
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
            .get_default_config(adapter, self.width, self.height)
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
                    resource: wgpu::BindingResource::TextureView(&self.target_view),
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

    fn upload_image(&self, width: u32, height: u32, pixels: &[u8]) -> PyResult<Image> {
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
                    resource: wgpu::BindingResource::Sampler(&self.sampler),
                },
            ],
        });
        Ok(Image {
            _texture: texture,
            bind_group,
            width,
            height,
        })
    }

    fn push(&mut self, texture: u32, instance: Instance) {
        let index = self.instances.len() as u32;
        self.instances.push(instance);
        if let Some(last) = self.runs.last_mut() {
            if last.texture == texture && last.scissor == self.scissor {
                last.count += 1;
                return;
            }
        }
        self.runs.push(Run {
            texture,
            scissor: self.scissor,
            start: index,
            count: 1,
        });
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
        self.width
    }

    #[getter]
    fn height(&self) -> u32 {
        self.height
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
        self.runs.len()
    }

    /// Replace the target with one of a new size. Drops the frame in progress.
    fn resize(&mut self, width: u32, height: u32) -> PyResult<()> {
        Self::check_size(width, height)?;
        let (target, view) = make_target(&self.device, width, height);
        self.target = target;
        self.target_view = view;
        self.width = width;
        self.height = height;
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
        self.runs.clear();
        self.scissor = None;
        Ok(())
    }

    /// Upload an RGBA image and return its id.
    fn create_texture(&mut self, width: u32, height: u32, pixels: &[u8]) -> PyResult<u32> {
        let image = self.upload_image(width, height, pixels)?;
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
            None => {
                self.instances.clear();
                self.runs.clear();
                self.clear = wgpu::Color {
                    r: f64::from(red) / 255.0,
                    g: f64::from(green) / 255.0,
                    b: f64::from(blue) / 255.0,
                    a: f64::from(alpha) / 255.0,
                };
            }
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
        let left = x.clamp(0, i64::from(self.width));
        let top = y.clamp(0, i64::from(self.height));
        let right = (x + width).clamp(left, i64::from(self.width));
        let bottom = (y + height).clamp(top, i64::from(self.height));
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

    /// Render everything pushed since the last clear, and start a new frame.
    fn end_frame(&mut self) {
        self.queue.write_buffer(
            &self.globals,
            0,
            bytemuck::cast_slice(&[self.width as f32, self.height as f32, 0.0, 0.0]),
        );
        if self.instances.len() > self.instance_capacity {
            self.instance_capacity = self.instances.len().next_power_of_two();
            self.instance_buffer = make_instance_buffer(&self.device, self.instance_capacity);
        }
        if !self.instances.is_empty() {
            self.queue
                .write_buffer(&self.instance_buffer, 0, bytemuck::cast_slice(&self.instances));
        }
        let mut encoder = self
            .device
            .create_command_encoder(&wgpu::CommandEncoderDescriptor { label: Some("pyguara frame") });
        {
            let mut pass = encoder.begin_render_pass(&wgpu::RenderPassDescriptor {
                label: Some("pyguara frame"),
                color_attachments: &[Some(wgpu::RenderPassColorAttachment {
                    view: &self.target_view,
                    depth_slice: None,
                    resolve_target: None,
                    ops: wgpu::Operations {
                        load: wgpu::LoadOp::Clear(self.clear),
                        store: wgpu::StoreOp::Store,
                    },
                })],
                ..Default::default()
            });
            pass.set_pipeline(&self.pipeline);
            pass.set_bind_group(0, &self.globals_group, &[]);
            pass.set_vertex_buffer(0, self.instance_buffer.slice(..));
            for run in &self.runs {
                let Some(image) = self.images.get(&run.texture) else {
                    continue;
                };
                match run.scissor {
                    Some([_, _, 0, _] | [_, _, _, 0]) => continue,
                    Some([x, y, width, height]) => pass.set_scissor_rect(x, y, width, height),
                    None => pass.set_scissor_rect(0, 0, self.width, self.height),
                }
                pass.set_bind_group(1, &image.bind_group, &[]);
                pass.draw(0..6, run.start..run.start + run.count);
            }
        }
        self.queue.submit([encoder.finish()]);
        self.instances.clear();
        self.runs.clear();
        self.scissor = None;
        self.frames += 1;
    }

    /// Copy the last rendered frame out as tightly packed RGBA rows.
    fn read_pixels<'py>(&self, python: Python<'py>) -> PyResult<Bound<'py, PyBytes>> {
        // A copy's rows must be padded to a multiple of 256 bytes.
        let row = self.width as usize * 4;
        let padded = row.div_ceil(256) * 256;
        let buffer = self.device.create_buffer(&wgpu::BufferDescriptor {
            label: Some("pyguara readback"),
            size: (padded * self.height as usize) as u64,
            usage: wgpu::BufferUsages::COPY_DST | wgpu::BufferUsages::MAP_READ,
            mapped_at_creation: false,
        });
        let mut encoder = self
            .device
            .create_command_encoder(&wgpu::CommandEncoderDescriptor { label: Some("pyguara readback") });
        encoder.copy_texture_to_buffer(
            wgpu::TexelCopyTextureInfo {
                texture: &self.target,
                mip_level: 0,
                origin: wgpu::Origin3d::ZERO,
                aspect: wgpu::TextureAspect::All,
            },
            wgpu::TexelCopyBufferInfo {
                buffer: &buffer,
                layout: wgpu::TexelCopyBufferLayout {
                    offset: 0,
                    bytes_per_row: Some(padded as u32),
                    rows_per_image: Some(self.height),
                },
            },
            wgpu::Extent3d {
                width: self.width,
                height: self.height,
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
        let height = self.height as usize;
        PyBytes::new_with(python, row * height, |out| {
            for line in 0..height {
                out[line * row..(line + 1) * row]
                    .copy_from_slice(&mapped[line * padded..line * padded + row]);
            }
            Ok(())
        })
    }
}
