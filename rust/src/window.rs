//! The platform window and its input, on winit.
//!
//! What SDL did through pygame for the wgpu backend: open a window, deliver
//! its keyboard, mouse and window events, and hand wgpu the native handle to
//! present to. Gamepads are `gamepad`, beside this.
//!
//! **One event loop per thread, for the life of the process.** winit refuses
//! to create a second `EventLoop`, and a test suite opens and closes windows
//! many times. So the loop is made on first use and kept in a thread-local,
//! and a `NativeWindow` is one window on it. `pump` runs the loop once with
//! no wait and collects what arrived, which is the shape a frame loop driven
//! from Python wants; winit's own `run` never returns.
//!
//! **Events cross as tuples**, `("key_down", code, mods)` and so on, and
//! `pyguara/graphics/backends/wgpu/window.py` turns them into the engine's
//! event classes. Key codes are **SDL keycodes**, because `pyguara.input.keys`
//! and every saved key binding are written in them: a printable key is its
//! unshifted character, anything else is its SDL scancode with bit 30 set.
//! Modifiers are SDL's `KMOD_*` masks for the same reason.
//!
//! **Sizes are physical pixels.** winit is DPI-aware where SDL as pygame
//! opened it was not, so a 1280x720 window is 1280x720 pixels, as before --
//! on a 150% display it looks smaller than the pygame window did, which the
//! OS used to stretch.

use std::cell::RefCell;
use std::collections::HashMap;
use std::rc::Rc;
use std::time::Duration;

use pyo3::exceptions::{PyRuntimeError, PyValueError};
use pyo3::prelude::*;
use pyo3::types::PyList;
use winit::application::ApplicationHandler;
use winit::dpi::{PhysicalPosition, PhysicalSize};
use winit::event::{ElementState, MouseButton, MouseScrollDelta, WindowEvent};
use winit::event_loop::{ActiveEventLoop, EventLoop};
use winit::keyboard::{Key, KeyCode, ModifiersState, NamedKey, PhysicalKey};
use winit::platform::modifier_supplement::KeyEventExtModifierSupplement;
use winit::platform::pump_events::EventLoopExtPumpEvents;
use winit::raw_window_handle::{HasDisplayHandle, HasWindowHandle, RawDisplayHandle, RawWindowHandle};
use winit::window::{Fullscreen, Window, WindowAttributes, WindowId};

/// SDL's `KMOD_SHIFT`, `KMOD_CTRL` and `KMOD_ALT`.
const KMOD_SHIFT: u32 = 0x0003;
const KMOD_CTRL: u32 = 0x00c0;
const KMOD_ALT: u32 = 0x0300;

/// How far one notch of a pixel-precise wheel (a trackpad) scrolls, in the
/// wheel's own unit. SDL reports such deltas in lines too.
const PIXELS_PER_LINE: f64 = 20.0;

/// One event, as it is handed to Python.
enum Event {
    Quit,
    KeyDown(i64, u32),
    KeyUp(i64, u32),
    Text(String),
    MouseButton(u8, i32, i32, bool, u32),
    MouseMotion(i32, i32, i32, i32),
    Wheel(f64, f64),
    Resize(u32, u32),
    Focus(bool),
}

/// What one window has received since it was last pumped.
#[derive(Default)]
struct Inbox {
    events: Vec<Event>,
    cursor: Option<(i32, i32)>,
    modifiers: ModifiersState,
}

/// The loop's handler: creates the window it is asked for, files events.
#[derive(Default)]
struct App {
    request: Option<WindowAttributes>,
    created: Option<Result<Window, String>>,
    inboxes: HashMap<WindowId, Inbox>,
}

impl App {
    fn create_requested(&mut self, event_loop: &ActiveEventLoop) {
        if let Some(attributes) = self.request.take() {
            self.created = Some(
                event_loop
                    .create_window(attributes)
                    .map_err(|error| error.to_string()),
            );
        }
    }
}

fn kmod(state: ModifiersState) -> u32 {
    let mut mods = 0;
    if state.shift_key() {
        mods |= KMOD_SHIFT;
    }
    if state.control_key() {
        mods |= KMOD_CTRL;
    }
    if state.alt_key() {
        mods |= KMOD_ALT;
    }
    mods
}

/// An SDL keycode from a scancode: SDL's `SDL_SCANCODE_TO_KEYCODE`.
const fn scancode(code: i64) -> i64 {
    code | (1 << 30)
}

/// Keys that are not characters, by position: winit's name, SDL's keycode.
///
/// `keycode_table()` hands this to Python, where
/// `tests/test_wgpu_window.py` holds it to `pyguara.input.keys`.
const NAMED_KEYS: &[(KeyCode, &str, i64)] = &[
    (KeyCode::Enter, "Enter", 13),
    (KeyCode::Escape, "Escape", 27),
    (KeyCode::Backspace, "Backspace", 8),
    (KeyCode::Tab, "Tab", 9),
    (KeyCode::Space, "Space", 32),
    (KeyCode::Delete, "Delete", 127),
    (KeyCode::CapsLock, "CapsLock", scancode(57)),
    (KeyCode::F1, "F1", scancode(58)),
    (KeyCode::F2, "F2", scancode(59)),
    (KeyCode::F3, "F3", scancode(60)),
    (KeyCode::F4, "F4", scancode(61)),
    (KeyCode::F5, "F5", scancode(62)),
    (KeyCode::F6, "F6", scancode(63)),
    (KeyCode::F7, "F7", scancode(64)),
    (KeyCode::F8, "F8", scancode(65)),
    (KeyCode::F9, "F9", scancode(66)),
    (KeyCode::F10, "F10", scancode(67)),
    (KeyCode::F11, "F11", scancode(68)),
    (KeyCode::F12, "F12", scancode(69)),
    (KeyCode::PrintScreen, "PrintScreen", scancode(70)),
    (KeyCode::ScrollLock, "ScrollLock", scancode(71)),
    (KeyCode::Pause, "Pause", scancode(72)),
    (KeyCode::Insert, "Insert", scancode(73)),
    (KeyCode::Home, "Home", scancode(74)),
    (KeyCode::PageUp, "PageUp", scancode(75)),
    (KeyCode::End, "End", scancode(77)),
    (KeyCode::PageDown, "PageDown", scancode(78)),
    (KeyCode::ArrowRight, "ArrowRight", scancode(79)),
    (KeyCode::ArrowLeft, "ArrowLeft", scancode(80)),
    (KeyCode::ArrowDown, "ArrowDown", scancode(81)),
    (KeyCode::ArrowUp, "ArrowUp", scancode(82)),
    (KeyCode::NumLock, "NumLock", scancode(83)),
    (KeyCode::NumpadDivide, "NumpadDivide", scancode(84)),
    (KeyCode::NumpadMultiply, "NumpadMultiply", scancode(85)),
    (KeyCode::NumpadSubtract, "NumpadSubtract", scancode(86)),
    (KeyCode::NumpadAdd, "NumpadAdd", scancode(87)),
    (KeyCode::NumpadEnter, "NumpadEnter", scancode(88)),
    (KeyCode::Numpad1, "Numpad1", scancode(89)),
    (KeyCode::Numpad2, "Numpad2", scancode(90)),
    (KeyCode::Numpad3, "Numpad3", scancode(91)),
    (KeyCode::Numpad4, "Numpad4", scancode(92)),
    (KeyCode::Numpad5, "Numpad5", scancode(93)),
    (KeyCode::Numpad6, "Numpad6", scancode(94)),
    (KeyCode::Numpad7, "Numpad7", scancode(95)),
    (KeyCode::Numpad8, "Numpad8", scancode(96)),
    (KeyCode::Numpad9, "Numpad9", scancode(97)),
    (KeyCode::Numpad0, "Numpad0", scancode(98)),
    (KeyCode::NumpadDecimal, "NumpadDecimal", scancode(99)),
    (KeyCode::ControlLeft, "ControlLeft", scancode(224)),
    (KeyCode::ShiftLeft, "ShiftLeft", scancode(225)),
    (KeyCode::AltLeft, "AltLeft", scancode(226)),
    (KeyCode::SuperLeft, "SuperLeft", scancode(227)),
    (KeyCode::ControlRight, "ControlRight", scancode(228)),
    (KeyCode::ShiftRight, "ShiftRight", scancode(229)),
    (KeyCode::AltRight, "AltRight", scancode(230)),
    (KeyCode::SuperRight, "SuperRight", scancode(231)),
];

/// The SDL keycode of a key that is not a character, by its position.
fn physical_keycode(code: KeyCode) -> Option<i64> {
    NAMED_KEYS.iter().find(|(key, _, _)| *key == code).map(|(_, _, sdl)| *sdl)
}

/// The position-mapped keys, as `(winit name, SDL keycode)` pairs.
#[pyfunction]
pub fn keycode_table() -> Vec<(&'static str, i64)> {
    NAMED_KEYS.iter().map(|(_, name, sdl)| (*name, *sdl)).collect()
}

/// The SDL keycode for a key event.
///
/// By position for everything that is not a character -- arrows, function
/// keys, the keypad, left against right modifiers -- and by the layout's
/// unshifted character otherwise, which is what SDL does: `A` on an AZERTY
/// layout is `q`'s key, and reports `a`.
fn keycode(physical: PhysicalKey, unmodified: &Key) -> Option<i64> {
    if let PhysicalKey::Code(code) = physical {
        if let Some(found) = physical_keycode(code) {
            return Some(found);
        }
    }
    match unmodified {
        Key::Character(text) => text
            .chars()
            .next()
            .map(|c| c.to_lowercase().next().unwrap_or(c) as i64),
        Key::Named(NamedKey::Space) => Some(32),
        _ => None,
    }
}

fn mouse_button(button: MouseButton) -> Option<u8> {
    // pygame's numbering: 4 and 5 were the wheel, so the side buttons are 6, 7.
    Some(match button {
        MouseButton::Left => 1,
        MouseButton::Middle => 2,
        MouseButton::Right => 3,
        MouseButton::Back => 6,
        MouseButton::Forward => 7,
        MouseButton::Other(_) => return None,
    })
}

impl ApplicationHandler for App {
    fn resumed(&mut self, event_loop: &ActiveEventLoop) {
        self.create_requested(event_loop);
    }

    fn new_events(&mut self, event_loop: &ActiveEventLoop, _cause: winit::event::StartCause) {
        self.create_requested(event_loop);
    }

    fn window_event(&mut self, _event_loop: &ActiveEventLoop, id: WindowId, event: WindowEvent) {
        let inbox = self.inboxes.entry(id).or_default();
        let mods = kmod(inbox.modifiers);
        match event {
            WindowEvent::CloseRequested => inbox.events.push(Event::Quit),
            WindowEvent::Resized(size) => inbox.events.push(Event::Resize(size.width, size.height)),
            WindowEvent::Focused(focused) => inbox.events.push(Event::Focus(focused)),
            WindowEvent::ModifiersChanged(modifiers) => inbox.modifiers = modifiers.state(),
            WindowEvent::KeyboardInput { event, is_synthetic, .. } => {
                // A key held when the window gains focus is replayed as a
                // synthetic press on some platforms; SDL reports neither.
                if is_synthetic {
                    return;
                }
                let pressed = event.state == ElementState::Pressed;
                if pressed {
                    if let Some(text) = &event.text {
                        // Control characters are keys, not text: Return,
                        // Backspace and Tab arrive as their key codes.
                        let printable: String = text.chars().filter(|c| !c.is_control()).collect();
                        if !printable.is_empty() {
                            inbox.events.push(Event::Text(printable));
                        }
                    }
                }
                // SDL as pygame opened it reports no key repeat, so a held
                // key is one press; the text above does repeat, as SDL's does.
                if event.repeat {
                    return;
                }
                if let Some(code) = keycode(event.physical_key, &event.key_without_modifiers()) {
                    inbox.events.push(if pressed {
                        Event::KeyDown(code, mods)
                    } else {
                        Event::KeyUp(code, mods)
                    });
                }
            }
            WindowEvent::CursorMoved { position, .. } => {
                let now = (position.x.floor() as i32, position.y.floor() as i32);
                let (rel_x, rel_y) = match inbox.cursor {
                    Some((x, y)) => (now.0 - x, now.1 - y),
                    None => (0, 0),
                };
                inbox.cursor = Some(now);
                inbox.events.push(Event::MouseMotion(now.0, now.1, rel_x, rel_y));
            }
            WindowEvent::MouseInput { state, button, .. } => {
                if let Some(button) = mouse_button(button) {
                    let (x, y) = inbox.cursor.unwrap_or((0, 0));
                    inbox
                        .events
                        .push(Event::MouseButton(button, x, y, state == ElementState::Pressed, mods));
                }
            }
            WindowEvent::MouseWheel { delta, .. } => {
                let (x, y) = match delta {
                    MouseScrollDelta::LineDelta(x, y) => (x as f64, y as f64),
                    MouseScrollDelta::PixelDelta(pixels) => (pixels.x / PIXELS_PER_LINE, pixels.y / PIXELS_PER_LINE),
                };
                inbox.events.push(Event::Wheel(x, y));
            }
            _ => {}
        }
    }
}

struct Platform {
    event_loop: EventLoop<()>,
    app: App,
}

impl Platform {
    fn pump(&mut self) {
        let _ = self.event_loop.pump_app_events(Some(Duration::ZERO), &mut self.app);
    }
}

thread_local! {
    static PLATFORM: RefCell<Option<Platform>> = const { RefCell::new(None) };
}

fn with_platform<T>(work: impl FnOnce(&mut Platform) -> PyResult<T>) -> PyResult<T> {
    PLATFORM.with(|cell| {
        let mut slot = cell.borrow_mut();
        if slot.is_none() {
            let event_loop = EventLoop::new().map_err(|error| {
                PyRuntimeError::new_err(format!("no window system is available: {error}"))
            })?;
            *slot = Some(Platform { event_loop, app: App::default() });
        }
        work(slot.as_mut().expect("made above"))
    })
}

/// A desktop window, with its input.
///
/// Made on the thread that will pump it, and used only there: winit's
/// windows are not `Send` on every platform, hence `unsendable`.
#[pyclass(unsendable)]
pub struct NativeWindow {
    window: Option<Rc<Window>>,
    id: WindowId,
    queued: Vec<Event>,
}

impl NativeWindow {
    fn window(&self) -> PyResult<&Window> {
        self.window
            .as_deref()
            .ok_or_else(|| PyRuntimeError::new_err("the window is closed"))
    }
}

#[pymethods]
impl NativeWindow {
    /// Open a window.
    ///
    /// Args:
    ///     title: The title bar's text.
    ///     width: Inner width, in physical pixels.
    ///     height: Inner height, in physical pixels.
    ///     fullscreen: Cover the monitor the window opens on, borderless.
    ///     resizable: Let the user size it.
    ///     borderless: No OS title bar or frame.
    #[new]
    #[pyo3(signature = (title, width, height, fullscreen=false, resizable=false, borderless=false))]
    fn new(
        title: &str,
        width: u32,
        height: u32,
        fullscreen: bool,
        resizable: bool,
        borderless: bool,
    ) -> PyResult<Self> {
        if width == 0 || height == 0 {
            return Err(PyValueError::new_err(format!("a window cannot be {width}x{height}")));
        }
        let attributes = Window::default_attributes()
            .with_title(title)
            .with_inner_size(PhysicalSize::new(width, height))
            .with_resizable(resizable)
            .with_decorations(!borderless)
            .with_fullscreen(fullscreen.then_some(Fullscreen::Borderless(None)));
        with_platform(|platform| {
            platform.app.request = Some(attributes);
            platform.app.created = None;
            // Some platforms only hand out an active loop after a pump or two.
            for _ in 0..100 {
                platform.pump();
                if platform.app.created.is_some() {
                    break;
                }
            }
            platform.app.request = None;
            let window = match platform.app.created.take() {
                Some(Ok(window)) => window,
                Some(Err(reason)) => {
                    return Err(PyRuntimeError::new_err(format!("the window could not be opened: {reason}")));
                }
                None => return Err(PyRuntimeError::new_err("the window system never became ready")),
            };
            let id = window.id();
            platform.app.inboxes.insert(id, Inbox::default());
            Ok(Self { window: Some(Rc::new(window)), id, queued: Vec::new() })
        })
    }

    /// Run the event loop once, without waiting, and return what arrived.
    ///
    /// Returns:
    ///     A list of tuples, oldest first: `("quit",)`,
    ///     `("key_down", code, mods)`, `("key_up", code, mods)`,
    ///     `("text", text)`, `("mouse_button", button, x, y, down, mods)`,
    ///     `("mouse_motion", x, y, rel_x, rel_y)`, `("wheel", x, y)`,
    ///     `("resize", width, height)` and `("focus", focused)`.
    fn pump<'py>(&mut self, py: Python<'py>) -> PyResult<Bound<'py, PyList>> {
        let mut events = std::mem::take(&mut self.queued);
        if self.window.is_some() {
            let id = self.id;
            with_platform(|platform| {
                platform.pump();
                if let Some(inbox) = platform.app.inboxes.get_mut(&id) {
                    events.append(&mut inbox.events);
                }
                Ok(())
            })?;
        }
        let list = PyList::empty(py);
        for event in events {
            match event {
                Event::Quit => list.append(("quit",))?,
                Event::KeyDown(code, mods) => list.append(("key_down", code, mods))?,
                Event::KeyUp(code, mods) => list.append(("key_up", code, mods))?,
                Event::Text(text) => list.append(("text", text))?,
                Event::MouseButton(button, x, y, down, mods) => {
                    list.append(("mouse_button", button, x, y, down, mods))?
                }
                Event::MouseMotion(x, y, rel_x, rel_y) => list.append(("mouse_motion", x, y, rel_x, rel_y))?,
                Event::Wheel(x, y) => list.append(("wheel", x, y))?,
                Event::Resize(width, height) => list.append(("resize", width, height))?,
                Event::Focus(focused) => list.append(("focus", focused))?,
            }
        }
        Ok(list)
    }

    /// Queue a quit, delivered by the next `pump`, as the close button does.
    fn request_close(&mut self) {
        self.queued.push(Event::Quit);
    }

    /// The inner size in physical pixels.
    #[getter]
    fn size(&self) -> PyResult<(u32, u32)> {
        let size = self.window()?.inner_size();
        Ok((size.width, size.height))
    }

    /// Set the title bar's text.
    fn set_title(&self, title: &str) -> PyResult<()> {
        self.window()?.set_title(title);
        Ok(())
    }

    /// Iconify the window.
    fn minimize(&self) -> PyResult<()> {
        self.window()?.set_minimized(true);
        Ok(())
    }

    /// Fill the work area.
    fn maximize(&self) -> PyResult<()> {
        self.window()?.set_maximized(true);
        Ok(())
    }

    /// Return from maximised to the size before.
    fn restore(&self) -> PyResult<()> {
        self.window()?.set_maximized(false);
        Ok(())
    }

    /// Whether the window fills the work area, as the window system says.
    #[getter]
    fn is_maximized(&self) -> PyResult<bool> {
        Ok(self.window()?.is_maximized())
    }

    /// The outer top-left corner on the desktop, or None where the window
    /// system does not say (Wayland).
    #[getter]
    fn position(&self) -> PyResult<Option<(i32, i32)>> {
        Ok(self.window()?.outer_position().ok().map(|at| (at.x, at.y)))
    }

    /// Move the outer top-left corner. Ignored where the window system
    /// does not let a client place its window (Wayland).
    fn set_position(&self, x: i32, y: i32) -> PyResult<()> {
        self.window()?.set_outer_position(PhysicalPosition::new(x, y));
        Ok(())
    }

    /// Hand a drag of the window to the window system, from a pressed
    /// button. The only way to move a window on Wayland.
    fn drag(&self) -> PyResult<bool> {
        Ok(self.window()?.drag_window().is_ok())
    }

    /// Name the window as `NativeGpu.for_window` wants it.
    ///
    /// Returns:
    ///     `(kind, window, display)`, or None for a window system wgpu is
    ///     not handed here.
    fn native_handles(&self) -> PyResult<Option<(String, usize, usize)>> {
        let window = self.window()?;
        let (Ok(handle), Ok(display)) = (window.window_handle(), window.display_handle()) else {
            return Ok(None);
        };
        Ok(match (handle.as_raw(), display.as_raw()) {
            (RawWindowHandle::Win32(handle), _) => Some(("win32".into(), handle.hwnd.get() as usize, 0)),
            (RawWindowHandle::Xlib(handle), RawDisplayHandle::Xlib(display)) => display
                .display
                .map(|pointer| ("x11".into(), handle.window as usize, pointer.as_ptr() as usize)),
            (RawWindowHandle::Wayland(handle), RawDisplayHandle::Wayland(display)) => Some((
                "wayland".into(),
                handle.surface.as_ptr() as usize,
                display.display.as_ptr() as usize,
            )),
            (RawWindowHandle::AppKit(handle), _) => Some(("appkit".into(), handle.ns_view.as_ptr() as usize, 0)),
            _ => None,
        })
    }

    /// Close the window. Pumping a closed window returns only queued events.
    fn close(&mut self) {
        if self.window.take().is_some() {
            let id = self.id;
            let _ = with_platform(|platform| {
                platform.app.inboxes.remove(&id);
                // Let the window system see the window go.
                platform.pump();
                Ok(())
            });
        }
    }
}

/// The desktop clipboard's text.
///
/// Separate from the window because a clipboard outlives one, and opening it
/// can fail where a window does not (no clipboard manager under X11).
#[pyclass(unsendable)]
pub struct NativeClipboard {
    clipboard: Option<arboard::Clipboard>,
}

#[pymethods]
impl NativeClipboard {
    /// Open the clipboard. Never raises: one that cannot be opened is empty.
    #[new]
    fn new() -> Self {
        Self { clipboard: arboard::Clipboard::new().ok() }
    }

    /// The clipboard's text, or "" when it holds none or cannot be read.
    fn get_text(&mut self) -> String {
        self.clipboard
            .as_mut()
            .and_then(|clipboard| clipboard.get_text().ok())
            .unwrap_or_default()
    }

    /// Put text on the clipboard. Returns whether the platform took it.
    fn set_text(&mut self, text: &str) -> bool {
        self.clipboard
            .as_mut()
            .is_some_and(|clipboard| clipboard.set_text(text).is_ok())
    }
}
