//! Steam, loaded at run time: the slice of Steamworks the network transport
//! needs (workstream 5b).
//!
//! **Not linked.** `steam_api` is Valve's library: the game ships it beside
//! itself (Steam's own licence lets a game redistribute it; this repository
//! cannot), so the extension opens it by path with `libloading` when a game
//! asks for Steam, and a missing library or a Steam that is not running is an
//! error naming which -- never a failed import, as a linked `libasound` was.
//!
//! Only Steam's flat C API (`steam_api_flat.h`) is called, so no C++ ABI is
//! involved, and callbacks are taken by **manual dispatch**
//! (`SteamAPI_ManualDispatch_*`): `run_callbacks` drains them on the caller's
//! thread, so nothing Steam does ever runs Python behind the engine's back.
//!
//! Struct offsets read here (`SteamNetworkingMessage_t`, `CallbackMsg_t`,
//! `SteamNetConnectionInfo_t`) were checked with `offset_of!` against the
//! Steamworks SDK's own layouts for both Linux (pack 4) and Windows (pack 8),
//! where they coincide. `SteamNetworkingIdentity` is 136 bytes, packed to 1,
//! and only ever read or written through Steam's own accessors.

use std::ffi::{CStr, c_char, c_int, c_void};
use std::sync::atomic::{AtomicBool, Ordering};

use libloading::Library;
use pyo3::exceptions::{PyRuntimeError, PyValueError};
use pyo3::prelude::*;
use pyo3::types::{PyBytes, PyList, PyTuple};

/// `k_cchMaxSteamErrMsg`.
const ERROR_BYTES: usize = 1024;
/// `sizeof(SteamNetworkingIdentity)`.
const IDENTITY_BYTES: usize = 136;
/// `k_EResultOK`.
const RESULT_OK: c_int = 1;
/// `k_nSteamNetworkingSend_UnreliableNoNagle | ..._AutoRestartBrokenSession`.
const SEND_UNRELIABLE: c_int = 1 | 32;
/// `k_nSteamNetworkingSend_ReliableNoNagle | ..._AutoRestartBrokenSession`.
const SEND_RELIABLE: c_int = 8 | 1 | 32;
/// `k_iSteamNetworkingMessagesCallbacks + 1` and `+ 2`.
const SESSION_REQUEST: c_int = 1251;
const SESSION_FAILED: c_int = 1252;
/// Offsets into `SteamNetworkingMessage_t` and `SteamNetConnectionInfo_t`.
const MESSAGE_DATA: usize = 0;
const MESSAGE_SIZE: usize = 8;
const MESSAGE_PEER: usize = 16;
const INFO_END_REASON: usize = 180;
const INFO_END_DEBUG: usize = 184;
const INFO_END_DEBUG_BYTES: usize = 128;
const MAX_MESSAGES: usize = 256;

/// Steam allows one API instance per process.
static OPEN: AtomicBool = AtomicBool::new(false);

#[repr(C, align(8))]
struct Identity([u8; IDENTITY_BYTES]);

/// `CallbackMsg_t`. Laid out at Windows' pack 8; Linux's pack 4 has the same
/// offsets and four bytes less, which Steam writes into this.
#[repr(C)]
struct CallbackMsg {
    user: c_int,
    callback: c_int,
    param: *mut u8,
    param_bytes: c_int,
}

type Interface = *mut c_void;

/// The functions used, by name, as `steam_api_flat.h` declares them.
struct Api {
    _library: Library,
    init_flat: unsafe extern "C" fn(*mut c_char) -> c_int,
    shutdown: unsafe extern "C" fn(),
    dispatch_init: unsafe extern "C" fn(),
    dispatch_run_frame: unsafe extern "C" fn(c_int),
    dispatch_next: unsafe extern "C" fn(c_int, *mut CallbackMsg) -> bool,
    dispatch_free: unsafe extern "C" fn(c_int),
    pipe: unsafe extern "C" fn() -> c_int,
    user: unsafe extern "C" fn() -> Interface,
    user_steam_id: unsafe extern "C" fn(Interface) -> u64,
    friends: unsafe extern "C" fn() -> Interface,
    persona_name: unsafe extern "C" fn(Interface) -> *const c_char,
    messages: unsafe extern "C" fn() -> Interface,
    send: unsafe extern "C" fn(Interface, *const Identity, *const c_void, u32, c_int, c_int) -> c_int,
    receive: unsafe extern "C" fn(Interface, c_int, *mut *mut c_void, c_int) -> c_int,
    accept: unsafe extern "C" fn(Interface, *const Identity) -> bool,
    close: unsafe extern "C" fn(Interface, *const Identity) -> bool,
    release: unsafe extern "C" fn(*mut c_void),
    utils: unsafe extern "C" fn() -> Interface,
    init_relay: unsafe extern "C" fn(Interface),
    set_id: unsafe extern "C" fn(*mut Identity, u64),
    get_id: unsafe extern "C" fn(*const c_void) -> u64,
}

impl Api {
    fn load(path: &str) -> Result<Self, String> {
        // SAFETY: loading steam_api runs only its own initialisers, and each
        // symbol is read with the signature steam_api_flat.h gives it.
        unsafe {
            let library =
                Library::new(path).map_err(|error| format!("could not load {path}: {error}"))?;
            macro_rules! symbol {
                ($name:literal) => {
                    *library.get($name).map_err(|error| {
                        format!("{path} is not a steam_api this engine can use: {error}")
                    })?
                };
            }
            Ok(Self {
                init_flat: symbol!(b"SteamAPI_InitFlat\0"),
                shutdown: symbol!(b"SteamAPI_Shutdown\0"),
                dispatch_init: symbol!(b"SteamAPI_ManualDispatch_Init\0"),
                dispatch_run_frame: symbol!(b"SteamAPI_ManualDispatch_RunFrame\0"),
                dispatch_next: symbol!(b"SteamAPI_ManualDispatch_GetNextCallback\0"),
                dispatch_free: symbol!(b"SteamAPI_ManualDispatch_FreeLastCallback\0"),
                pipe: symbol!(b"SteamAPI_GetHSteamPipe\0"),
                user: symbol!(b"SteamAPI_SteamUser_v023\0"),
                user_steam_id: symbol!(b"SteamAPI_ISteamUser_GetSteamID\0"),
                friends: symbol!(b"SteamAPI_SteamFriends_v018\0"),
                persona_name: symbol!(b"SteamAPI_ISteamFriends_GetPersonaName\0"),
                messages: symbol!(b"SteamAPI_SteamNetworkingMessages_SteamAPI_v002\0"),
                send: symbol!(b"SteamAPI_ISteamNetworkingMessages_SendMessageToUser\0"),
                receive: symbol!(b"SteamAPI_ISteamNetworkingMessages_ReceiveMessagesOnChannel\0"),
                accept: symbol!(b"SteamAPI_ISteamNetworkingMessages_AcceptSessionWithUser\0"),
                close: symbol!(b"SteamAPI_ISteamNetworkingMessages_CloseSessionWithUser\0"),
                release: symbol!(b"SteamAPI_SteamNetworkingMessage_t_Release\0"),
                utils: symbol!(b"SteamAPI_SteamNetworkingUtils_SteamAPI_v004\0"),
                init_relay: symbol!(b"SteamAPI_ISteamNetworkingUtils_InitRelayNetworkAccess\0"),
                set_id: symbol!(b"SteamAPI_SteamNetworkingIdentity_SetSteamID64\0"),
                get_id: symbol!(b"SteamAPI_SteamNetworkingIdentity_GetSteamID64\0"),
                _library: library,
            })
        }
    }

    fn identity(&self, steam_id: u64) -> Identity {
        let mut identity = Identity([0; IDENTITY_BYTES]);
        // SAFETY: `identity` is a whole SteamNetworkingIdentity.
        unsafe { (self.set_id)(&mut identity, steam_id) };
        identity
    }
}

/// What `SteamAPI_InitFlat`'s result means, for the error a player sees.
fn init_failure(code: c_int) -> &'static str {
    match code {
        2 => "Steam is not running, or not logged in",
        3 => "the Steam client is out of date",
        _ => "Steam failed to start",
    }
}

/// Steam, for one process: the local player and peer-to-peer messages.
///
/// Made and used on one thread (`unsendable`), the one that calls
/// `run_callbacks`.
#[pyclass(unsendable)]
pub struct NativeSteam {
    api: Option<Api>,
    messages: Interface,
    friends: Interface,
    steam_id: u64,
}

impl NativeSteam {
    fn api(&self) -> PyResult<&Api> {
        self.api.as_ref().ok_or_else(|| PyRuntimeError::new_err("Steam has been shut down"))
    }
}

#[pymethods]
impl NativeSteam {
    /// Load `steam_api` from `library` and start Steam.
    ///
    /// The app ID comes from Steam's usual places: the `SteamAppId`
    /// environment variable or `steam_appid.txt` in the working directory
    /// during development, the launch through Steam in a release.
    ///
    /// Raises:
    ///     RuntimeError: The library is missing or not a steam_api; Steam is
    ///         not running or not logged in; or Steam is already open.
    #[new]
    fn new(library: &str) -> PyResult<Self> {
        if OPEN.swap(true, Ordering::SeqCst) {
            return Err(PyRuntimeError::new_err("Steam is already open in this process"));
        }
        let opened = (|| -> Result<Self, String> {
            let api = Api::load(library)?;
            let mut error = [0 as c_char; ERROR_BYTES];
            // SAFETY: manual dispatch is set before Steam starts, as Steam
            // requires; `error` is the buffer SteamAPI_InitFlat takes.
            let code = unsafe {
                (api.dispatch_init)();
                (api.init_flat)(error.as_mut_ptr())
            };
            if code != 0 {
                // SAFETY: Steam writes a NUL-terminated message into `error`.
                let detail = unsafe { CStr::from_ptr(error.as_ptr()) }.to_string_lossy();
                return Err(format!("{}: {detail}", init_failure(code)));
            }
            // SAFETY: Steam is started, so its interface accessors are valid.
            let (messages, friends, steam_id) = unsafe {
                let user = (api.user)();
                ((api.messages)(), (api.friends)(), (api.user_steam_id)(user))
            };
            if messages.is_null() || friends.is_null() {
                // SAFETY: Steam started above.
                unsafe { (api.shutdown)() };
                return Err("this steam_api lacks the networking interfaces".into());
            }
            Ok(Self { api: Some(api), messages, friends, steam_id })
        })();
        opened.map_err(|reason| {
            OPEN.store(false, Ordering::SeqCst);
            PyRuntimeError::new_err(reason)
        })
    }

    /// The local player's Steam ID.
    #[getter]
    fn steam_id(&self) -> u64 {
        self.steam_id
    }

    /// The local player's Steam name.
    #[getter]
    fn persona_name(&self) -> PyResult<String> {
        let api = self.api()?;
        // SAFETY: Steam returns a string it owns, valid until the next call.
        let name = unsafe { CStr::from_ptr((api.persona_name)(self.friends)) };
        Ok(name.to_string_lossy().into_owned())
    }

    /// Start reaching Valve's relay network now, rather than on first send.
    fn init_relay(&self) -> PyResult<()> {
        let api = self.api()?;
        // SAFETY: Steam is open.
        unsafe { (api.init_relay)((api.utils)()) };
        Ok(())
    }

    /// Drain Steam's callbacks.
    ///
    /// Returns:
    ///     `("session_request", steam_id)` when someone new sends to us --
    ///     accept or ignore it -- and `("session_failed", steam_id, reason,
    ///     detail)` when a session could not be made or broke.
    fn run_callbacks<'p>(&self, py: Python<'p>) -> PyResult<Bound<'p, PyList>> {
        let api = self.api()?;
        let mut events: Vec<Bound<'p, PyTuple>> = Vec::new();
        // SAFETY: manual dispatch as steam_api.h prescribes: run the frame,
        // read each callback, free it before asking for the next.
        unsafe {
            let pipe = (api.pipe)();
            (api.dispatch_run_frame)(pipe);
            let mut message = CallbackMsg { user: 0, callback: 0, param: std::ptr::null_mut(), param_bytes: 0 };
            while (api.dispatch_next)(pipe, &mut message) {
                let bytes = usize::try_from(message.param_bytes).unwrap_or(0);
                let param = message.param;
                match message.callback {
                    SESSION_REQUEST if bytes >= IDENTITY_BYTES => {
                        let peer = (api.get_id)(param.cast());
                        events.push(("session_request", peer).into_pyobject(py)?);
                    }
                    SESSION_FAILED if bytes >= INFO_END_DEBUG + INFO_END_DEBUG_BYTES => {
                        let peer = (api.get_id)(param.cast());
                        let reason = param.add(INFO_END_REASON).cast::<c_int>().read_unaligned();
                        let debug = std::slice::from_raw_parts(param.add(INFO_END_DEBUG), INFO_END_DEBUG_BYTES);
                        let end = debug.iter().position(|&b| b == 0).unwrap_or(debug.len());
                        let detail = String::from_utf8_lossy(&debug[..end]).into_owned();
                        events.push(("session_failed", peer, reason, detail).into_pyobject(py)?);
                    }
                    _ => {}
                }
                (api.dispatch_free)(pipe);
            }
        }
        PyList::new(py, events)
    }

    /// Accept a session someone asked for (see `run_callbacks`).
    fn accept_session(&self, steam_id: u64) -> PyResult<bool> {
        let api = self.api()?;
        let identity = api.identity(steam_id);
        // SAFETY: Steam is open; `identity` outlives the call.
        Ok(unsafe { (api.accept)(self.messages, &identity) })
    }

    /// End a session with a peer.
    fn close_session(&self, steam_id: u64) -> PyResult<bool> {
        let api = self.api()?;
        let identity = api.identity(steam_id);
        // SAFETY: as `accept_session`.
        Ok(unsafe { (api.close)(self.messages, &identity) })
    }

    /// Send one message to a peer on channel 0.
    ///
    /// Returns:
    ///     Whether Steam accepted it (`k_EResultOK`).
    #[pyo3(signature = (steam_id, data, reliable = false))]
    fn send(&self, steam_id: u64, data: &[u8], reliable: bool) -> PyResult<bool> {
        let api = self.api()?;
        let size = u32::try_from(data.len()).map_err(|_| PyValueError::new_err("message too large"))?;
        let identity = api.identity(steam_id);
        let flags = if reliable { SEND_RELIABLE } else { SEND_UNRELIABLE };
        // SAFETY: Steam copies `data` before returning.
        let result = unsafe { (api.send)(self.messages, &identity, data.as_ptr().cast(), size, flags, 0) };
        Ok(result == RESULT_OK)
    }

    /// Take the messages waiting on channel 0, as `(steam_id, bytes)`.
    fn receive<'p>(&self, py: Python<'p>) -> PyResult<Bound<'p, PyList>> {
        let api = self.api()?;
        let mut pointers = [std::ptr::null_mut::<c_void>(); MAX_MESSAGES];
        let mut items: Vec<(u64, Bound<'p, PyBytes>)> = Vec::new();
        // SAFETY: Steam fills `count` pointers to messages it owns; each is
        // read, then released exactly once.
        unsafe {
            let count = (api.receive)(self.messages, 0, pointers.as_mut_ptr(), MAX_MESSAGES as c_int);
            for &message in &pointers[..usize::try_from(count).unwrap_or(0)] {
                let base = message.cast::<u8>();
                let data = base.add(MESSAGE_DATA).cast::<*const u8>().read_unaligned();
                let size = base.add(MESSAGE_SIZE).cast::<c_int>().read_unaligned();
                let peer = (api.get_id)(base.add(MESSAGE_PEER).cast());
                let body = if data.is_null() || size <= 0 {
                    &[][..]
                } else {
                    std::slice::from_raw_parts(data, size as usize)
                };
                items.push((peer, PyBytes::new(py, body)));
                (api.release)(message);
            }
        }
        PyList::new(py, items)
    }

    /// Shut Steam down. Safe to call twice; the object is inert after.
    fn shutdown(&mut self) {
        if let Some(api) = self.api.take() {
            // SAFETY: Steam was started by this object and is stopped once.
            unsafe { (api.shutdown)() };
            OPEN.store(false, Ordering::SeqCst);
        }
    }
}

impl Drop for NativeSteam {
    fn drop(&mut self) {
        self.shutdown();
    }
}

/// The file name `steam_api` has on this platform.
#[pyfunction]
pub fn steam_library_name() -> &'static str {
    if cfg!(target_os = "windows") {
        "steam_api64.dll"
    } else if cfg!(target_os = "macos") {
        "libsteam_api.dylib"
    } else {
        "libsteam_api.so"
    }
}
