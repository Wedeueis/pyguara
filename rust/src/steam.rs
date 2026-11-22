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
//! Lobbies (5c) are friends-only Steam lobbies. Their asynchronous results
//! (`LobbyCreated_t`, `LobbyEnter_t`) are taken as **call results** for the
//! handles this object asked for, never from the broadcast copies Steam may
//! also post, so each request yields exactly one event. Membership changes and
//! overlay join requests are broadcast callbacks.
//!
//! **Every offset, size, callback id and constant read here** is the one the
//! Steamworks headers give, for Linux and macOS (callbacks packed to 4) and
//! Windows (packed to 8): `tools/steam_offsets.cpp` prints them from an SDK,
//! and should be rerun when the SDK moves. They coincide on both packings
//! except `LobbyCreated_t`'s lobby id, at 4 or 8 (`CREATED_LOBBY`).
//! `SteamNetworkingIdentity` is 136 bytes and only ever read or written
//! through Steam's own accessors.
//!
//! **Nothing from Steam is trusted to be in range**: a callback is read only
//! as far as its reported size, a string field only to its buffer's end and
//! lossily, a message count only as far as the array Steam was given, and a
//! null interface or string is refused or read as empty.
//! `tests/test_native_steam_hostile.py` drives each of these through a
//! stand-in `steam_api`.

use std::cell::RefCell;
use std::ffi::{CStr, CString, c_char, c_int, c_void};
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
/// `SteamAPICallCompleted_t`, `LobbyEnter_t`, `LobbyCreated_t`,
/// `LobbyChatUpdate_t`, `GameLobbyJoinRequested_t` and
/// `GameRichPresenceJoinRequested_t`.
const CALL_COMPLETED: c_int = 703;
const LOBBY_ENTER: c_int = 504;
const LOBBY_CREATED: c_int = 513;
const LOBBY_CHAT_UPDATE: c_int = 506;
const LOBBY_JOIN_REQUESTED: c_int = 333;
const RICH_PRESENCE_JOIN_REQUESTED: c_int = 337;
/// `k_ELobbyTypeFriendsOnly`.
const LOBBY_FRIENDS_ONLY: c_int = 1;
/// `k_EChatMemberStateChangeEntered`, and every flag that means gone.
const MEMBER_ENTERED: u32 = 0x1;
const MEMBER_REMOVED: u32 = 0x2 | 0x4 | 0x8 | 0x10;
/// `LobbyCreated_t::m_ulSteamIDLobby` follows a 4-byte `EResult`: callbacks
/// are packed to 8 on Windows and to 4 elsewhere, so it moves.
const CREATED_LOBBY: usize = if cfg!(target_os = "windows") { 8 } else { 4 };
/// `LobbyEnter_t::m_EChatRoomEnterResponse`, after a u64, a u32 and a bool.
const ENTER_RESPONSE: usize = 16;
/// `k_cchMaxRichPresenceValueLength`, the connect string's buffer.
const CONNECT_BYTES: usize = 256;
/// Steam's own limits on rich presence and lobby data.
const KEY_BYTES: usize = 64;
const VALUE_BYTES: usize = 256;
const LOBBY_DATA_BYTES: usize = 8192;
/// Steam lobbies hold at most 250 members.
const MAX_LOBBY_MEMBERS: c_int = 250;

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
    call_result: unsafe extern "C" fn(c_int, u64, *mut c_void, c_int, c_int, *mut bool) -> bool,
    matchmaking: unsafe extern "C" fn() -> Interface,
    create_lobby: unsafe extern "C" fn(Interface, c_int, c_int) -> u64,
    join_lobby: unsafe extern "C" fn(Interface, u64) -> u64,
    leave_lobby: unsafe extern "C" fn(Interface, u64),
    lobby_owner: unsafe extern "C" fn(Interface, u64) -> u64,
    lobby_member_count: unsafe extern "C" fn(Interface, u64) -> c_int,
    lobby_member: unsafe extern "C" fn(Interface, u64, c_int) -> u64,
    get_lobby_data: unsafe extern "C" fn(Interface, u64, *const c_char) -> *const c_char,
    set_lobby_data: unsafe extern "C" fn(Interface, u64, *const c_char, *const c_char) -> bool,
    set_rich_presence: unsafe extern "C" fn(Interface, *const c_char, *const c_char) -> bool,
    clear_rich_presence: unsafe extern "C" fn(Interface),
    invite_dialog: unsafe extern "C" fn(Interface, u64),
    apps: unsafe extern "C" fn() -> Interface,
    game_language: unsafe extern "C" fn(Interface) -> *const c_char,
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
                call_result: symbol!(b"SteamAPI_ManualDispatch_GetAPICallResult\0"),
                matchmaking: symbol!(b"SteamAPI_SteamMatchmaking_v009\0"),
                create_lobby: symbol!(b"SteamAPI_ISteamMatchmaking_CreateLobby\0"),
                join_lobby: symbol!(b"SteamAPI_ISteamMatchmaking_JoinLobby\0"),
                leave_lobby: symbol!(b"SteamAPI_ISteamMatchmaking_LeaveLobby\0"),
                lobby_owner: symbol!(b"SteamAPI_ISteamMatchmaking_GetLobbyOwner\0"),
                lobby_member_count: symbol!(b"SteamAPI_ISteamMatchmaking_GetNumLobbyMembers\0"),
                lobby_member: symbol!(b"SteamAPI_ISteamMatchmaking_GetLobbyMemberByIndex\0"),
                get_lobby_data: symbol!(b"SteamAPI_ISteamMatchmaking_GetLobbyData\0"),
                set_lobby_data: symbol!(b"SteamAPI_ISteamMatchmaking_SetLobbyData\0"),
                set_rich_presence: symbol!(b"SteamAPI_ISteamFriends_SetRichPresence\0"),
                clear_rich_presence: symbol!(b"SteamAPI_ISteamFriends_ClearRichPresence\0"),
                invite_dialog: symbol!(b"SteamAPI_ISteamFriends_ActivateGameOverlayInviteDialog\0"),
                apps: symbol!(b"SteamAPI_SteamApps_v009\0"),
                game_language: symbol!(b"SteamAPI_ISteamApps_GetCurrentGameLanguage\0"),
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

/// A string for Steam, refused if Steam's own limit or a NUL would cut it.
fn c_string(what: &str, text: &str, limit: usize) -> PyResult<CString> {
    if text.len() >= limit {
        return Err(PyValueError::new_err(format!("{what} is at most {} bytes", limit - 1)));
    }
    CString::new(text).map_err(|_| PyValueError::new_err(format!("{what} contains a NUL")))
}

/// Read a u64 at `offset` of a callback's parameter.
///
/// # Safety
/// `param` must hold at least `offset + 8` bytes.
unsafe fn read_u64(param: *const u8, offset: usize) -> u64 {
    // SAFETY: the caller guarantees the 8 bytes; an unaligned read needs no
    // alignment.
    unsafe { param.add(offset).cast::<u64>().read_unaligned() }
}

/// Read a 32-bit value at `offset` of a callback's parameter.
///
/// # Safety
/// `param` must hold at least `offset + 4` bytes.
unsafe fn read_u32(param: *const u8, offset: usize) -> u32 {
    // SAFETY: as `read_u64`, for 4 bytes.
    unsafe { param.add(offset).cast::<u32>().read_unaligned() }
}

/// A callback, read out of Steam's buffer before that buffer is freed.
enum Event {
    SessionRequest(u64),
    SessionFailed(u64, c_int, String),
    LobbyCreated(u32, u64),
    LobbyEntered(u64, u32),
    LobbyMember(u64, u64, bool),
    JoinRequested(u64),
    ConnectRequested(String),
}

impl Event {
    fn into_tuple<'p>(self, py: Python<'p>) -> PyResult<Bound<'p, PyTuple>> {
        match self {
            Self::SessionRequest(peer) => ("session_request", peer).into_pyobject(py),
            Self::SessionFailed(peer, reason, detail) => {
                ("session_failed", peer, reason, detail).into_pyobject(py)
            }
            Self::LobbyCreated(code, lobby) => ("lobby_created", code, lobby).into_pyobject(py),
            Self::LobbyEntered(lobby, response) => ("lobby_entered", lobby, response).into_pyobject(py),
            Self::LobbyMember(lobby, member, joined) => {
                ("lobby_member", lobby, member, joined).into_pyobject(py)
            }
            Self::JoinRequested(lobby) => ("join_requested", lobby).into_pyobject(py),
            Self::ConnectRequested(connect) => ("connect_requested", connect).into_pyobject(py),
        }
    }
}

/// Read a NUL-terminated string from a fixed-size field, stopping at its end
/// if there is no NUL, and replacing what is not UTF-8.
fn field_string(field: &[u8]) -> String {
    let end = field.iter().position(|&b| b == 0).unwrap_or(field.len());
    String::from_utf8_lossy(&field[..end]).into_owned()
}

/// The largest call result read. Lobby results are 12 to 24 bytes.
const MAX_RESULT_BYTES: usize = 4096;

/// What a call handle this object holds was asked for.
#[derive(Clone, Copy)]
enum Pending {
    CreateLobby,
    JoinLobby(u64),
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
    matchmaking: Interface,
    utils: Interface,
    /// Null if this steam_api has none: only the game language needs it.
    apps: Interface,
    steam_id: u64,
    pending: RefCell<Vec<(u64, Pending)>>,
}

impl NativeSteam {
    fn api(&self) -> PyResult<&Api> {
        self.api.as_ref().ok_or_else(|| PyRuntimeError::new_err("Steam has been shut down"))
    }

    /// Remember a call handle, or refuse a request Steam would not make.
    fn expect(&self, handle: u64, what: Pending) -> PyResult<()> {
        if handle == 0 {
            return Err(PyRuntimeError::new_err("Steam refused the request"));
        }
        self.pending.borrow_mut().push((handle, what));
        Ok(())
    }

    /// Read the result of a call this object made, from the
    /// `SteamAPICallCompleted_t` at `param`. Another caller's handle, or a
    /// failed call, yields nothing.
    ///
    /// # Safety
    /// Steam must be open and `param` the 16-byte completion message, read
    /// before `FreeLastCallback`, as Steam requires of `GetAPICallResult`.
    unsafe fn call_result(&self, api: &Api, pipe: c_int, param: *const u8) -> Option<Event> {
        // SAFETY: the caller guarantees the 16 bytes of the completion
        // message: the handle at 0, the callback id at 8 and the size at 12.
        let (handle, expected, size) =
            unsafe { (read_u64(param, 0), read_u32(param, 8) as c_int, read_u32(param, 12) as usize) };
        let what = {
            let mut pending = self.pending.borrow_mut();
            let index = pending.iter().position(|(h, _)| *h == handle)?;
            pending.swap_remove(index).1
        };
        // A result too large to be one of ours is answered as a failure, so
        // the request still yields its one event.
        let size = if size > MAX_RESULT_BYTES { 0 } else { size };
        let mut buffer = vec![0u64; size.div_ceil(8)];
        let mut failed = false;
        // SAFETY: `buffer` holds at least `size` bytes, which is what Steam is
        // told it may write, and `failed` outlives the call.
        let read = size > 0
            && unsafe {
                (api.call_result)(pipe, handle, buffer.as_mut_ptr().cast(), size as c_int, expected, &mut failed)
            };
        let result = buffer.as_ptr().cast::<u8>();
        Some(match what {
            Pending::CreateLobby => {
                if !read || failed || expected != LOBBY_CREATED || size < CREATED_LOBBY + 8 {
                    Event::LobbyCreated(2, 0)
                } else {
                    // SAFETY: `size` covers both fields, checked above.
                    let (code, lobby) = unsafe { (read_u32(result, 0), read_u64(result, CREATED_LOBBY)) };
                    Event::LobbyCreated(code, if code == RESULT_OK as u32 { lobby } else { 0 })
                }
            }
            Pending::JoinLobby(lobby) => {
                if !read || failed || expected != LOBBY_ENTER || size < ENTER_RESPONSE + 4 {
                    Event::LobbyEntered(lobby, 5)
                } else {
                    // SAFETY: `size` covers the field, checked above.
                    Event::LobbyEntered(lobby, unsafe { read_u32(result, ENTER_RESPONSE) })
                }
            }
        })
    }

    /// Decode one callback Steam is holding.
    ///
    /// # Safety
    /// Steam must be open, and `param` must hold `bytes` bytes that stay
    /// valid until `FreeLastCallback`.
    unsafe fn decode(&self, api: &Api, pipe: c_int, callback: c_int, param: *const u8, bytes: usize) -> Option<Event> {
        // SAFETY: each arm reads only below the size its guard checked, and
        // the identity accessor reads the 136 bytes at the start of `param`.
        unsafe {
            match callback {
                SESSION_REQUEST if bytes >= IDENTITY_BYTES => {
                    Some(Event::SessionRequest((api.get_id)(param.cast())))
                }
                SESSION_FAILED if bytes >= INFO_END_DEBUG + INFO_END_DEBUG_BYTES => {
                    let peer = (api.get_id)(param.cast());
                    let reason = read_u32(param, INFO_END_REASON) as c_int;
                    let debug = std::slice::from_raw_parts(param.add(INFO_END_DEBUG), INFO_END_DEBUG_BYTES);
                    Some(Event::SessionFailed(peer, reason, field_string(debug)))
                }
                CALL_COMPLETED if bytes >= 16 => self.call_result(api, pipe, param),
                LOBBY_CHAT_UPDATE if bytes >= 28 => {
                    let (lobby, member, change) = (read_u64(param, 0), read_u64(param, 8), read_u32(param, 24));
                    if change & MEMBER_ENTERED != 0 {
                        Some(Event::LobbyMember(lobby, member, true))
                    } else if change & MEMBER_REMOVED != 0 {
                        Some(Event::LobbyMember(lobby, member, false))
                    } else {
                        None
                    }
                }
                LOBBY_JOIN_REQUESTED if bytes >= 16 => Some(Event::JoinRequested(read_u64(param, 0))),
                RICH_PRESENCE_JOIN_REQUESTED if bytes >= 8 + CONNECT_BYTES => {
                    let raw = std::slice::from_raw_parts(param.add(8), CONNECT_BYTES);
                    Some(Event::ConnectRequested(field_string(raw)))
                }
                _ => None,
            }
        }
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
            // SAFETY: `error` is the buffer SteamAPI_InitFlat takes.
            let code = unsafe { (api.init_flat)(error.as_mut_ptr()) };
            if code != 0 {
                // SAFETY: Steam writes a NUL-terminated message into `error`.
                let detail = unsafe { CStr::from_ptr(error.as_ptr()) }.to_string_lossy();
                return Err(format!("{}: {detail}", init_failure(code)));
            }
            // SAFETY: Steam is started, so manual dispatch may be chosen --
            // only now: steam_api.h requires it *after* SteamAPI_Init, and
            // before it no callback is ever delivered -- and the interface
            // accessors are valid.
            unsafe { (api.dispatch_init)() };
            // SAFETY: as above.
            let (user, messages, friends, matchmaking, utils) = unsafe {
                ((api.user)(), (api.messages)(), (api.friends)(), (api.matchmaking)(), (api.utils)())
            };
            if [user, messages, friends, matchmaking, utils].iter().any(|i| i.is_null()) {
                // SAFETY: Steam started above.
                unsafe { (api.shutdown)() };
                return Err("this steam_api lacks the interfaces the engine uses".into());
            }
            // SAFETY: Steam is open, as above.
            let apps = unsafe { (api.apps)() };
            // SAFETY: `user` is a live interface, checked above.
            let steam_id = unsafe { (api.user_steam_id)(user) };
            let pending = RefCell::new(Vec::new());
            Ok(Self {
                api: Some(api),
                messages,
                friends,
                matchmaking,
                utils,
                apps,
                steam_id,
                pending,
            })
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
        // SAFETY: Steam is open; it returns a string it owns, valid until the
        // next call, or null.
        let name = unsafe { (api.persona_name)(self.friends) };
        if name.is_null() {
            return Ok(String::new());
        }
        // SAFETY: non-null, and NUL-terminated by Steam.
        Ok(unsafe { CStr::from_ptr(name) }.to_string_lossy().into_owned())
    }

    /// The language the player chose for this game in Steam, as Steam names
    /// it (`"german"`, `"schinese"`), or None if Steam does not say.
    #[getter]
    fn game_language(&self) -> PyResult<Option<String>> {
        let api = self.api()?;
        if self.apps.is_null() {
            return Ok(None);
        }
        // SAFETY: Steam is open and `apps` is not null; Steam returns a
        // string it owns, or null.
        let language = unsafe { (api.game_language)(self.apps) };
        if language.is_null() {
            return Ok(None);
        }
        // SAFETY: non-null, and NUL-terminated by Steam.
        let text = unsafe { CStr::from_ptr(language) }.to_string_lossy().into_owned();
        Ok(if text.is_empty() { None } else { Some(text) })
    }

    /// Start reaching Valve's relay network now, rather than on first send.
    fn init_relay(&self) -> PyResult<()> {
        let api = self.api()?;
        // SAFETY: Steam is open and `utils` was checked at open.
        unsafe { (api.init_relay)(self.utils) };
        Ok(())
    }

    /// Drain Steam's callbacks.
    ///
    /// Returns:
    ///     Tuples, by their first item:
    ///
    ///     - `("session_request", steam_id)`: someone new sent to us; accept
    ///       or ignore it.
    ///     - `("session_failed", steam_id, reason, detail)`: a session could
    ///       not be made, or broke.
    ///     - `("lobby_created", result, lobby_id)`: `create_lobby` finished;
    ///       `result` is an `EResult`, 1 on success, and the id 0 on failure.
    ///     - `("lobby_entered", lobby_id, response)`: `join_lobby` finished;
    ///       `response` is an `EChatRoomEnterResponse`, 1 on success.
    ///     - `("lobby_member", lobby_id, steam_id, joined)`: someone entered
    ///       (`True`) or left, was kicked or dropped (`False`).
    ///     - `("join_requested", lobby_id)`: the player accepted an overlay
    ///       invite while the game was running.
    ///     - `("connect_requested", connect)`: the player joined a friend
    ///       through their rich presence; `connect` is that friend's
    ///       untrusted `connect` string.
    fn run_callbacks<'p>(&self, py: Python<'p>) -> PyResult<Bound<'p, PyList>> {
        let api = self.api()?;
        let mut events = Vec::new();
        // SAFETY: manual dispatch as steam_api.h prescribes: run the frame,
        // then read each callback and free it before asking for the next.
        // Nothing between the read and the free can return early.
        unsafe {
            let pipe = (api.pipe)();
            (api.dispatch_run_frame)(pipe);
            let mut message = CallbackMsg { user: 0, callback: 0, param: std::ptr::null_mut(), param_bytes: 0 };
            while (api.dispatch_next)(pipe, &mut message) {
                let bytes = usize::try_from(message.param_bytes).unwrap_or(0);
                if !message.param.is_null() {
                    events.extend(self.decode(api, pipe, message.callback, message.param, bytes));
                }
                (api.dispatch_free)(pipe);
            }
        }
        let tuples = events.into_iter().map(|event| event.into_tuple(py)).collect::<PyResult<Vec<_>>>()?;
        PyList::new(py, tuples)
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
            // Never more than the array Steam was given, and never a slot it
            // did not fill.
            let count = usize::try_from(count).unwrap_or(0).min(MAX_MESSAGES);
            for &message in pointers[..count].iter().filter(|message| !message.is_null()) {
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

    /// Create a friends-only lobby; `run_callbacks` reports `lobby_created`.
    fn create_lobby(&self, max_members: c_int) -> PyResult<()> {
        if !(1..=MAX_LOBBY_MEMBERS).contains(&max_members) {
            return Err(PyValueError::new_err(format!(
                "max_members must be between 1 and {MAX_LOBBY_MEMBERS}"
            )));
        }
        let api = self.api()?;
        // SAFETY: Steam is open.
        let handle = unsafe { (api.create_lobby)(self.matchmaking, LOBBY_FRIENDS_ONLY, max_members) };
        self.expect(handle, Pending::CreateLobby)
    }

    /// Enter a lobby; `run_callbacks` reports `lobby_entered`.
    fn join_lobby(&self, lobby_id: u64) -> PyResult<()> {
        let api = self.api()?;
        // SAFETY: Steam is open.
        let handle = unsafe { (api.join_lobby)(self.matchmaking, lobby_id) };
        self.expect(handle, Pending::JoinLobby(lobby_id))
    }

    /// Leave a lobby. Leaving one this player is not in does nothing.
    fn leave_lobby(&self, lobby_id: u64) -> PyResult<()> {
        let api = self.api()?;
        // SAFETY: Steam is open.
        unsafe { (api.leave_lobby)(self.matchmaking, lobby_id) };
        Ok(())
    }

    /// The Steam ID owning a lobby this player is in, or 0.
    fn lobby_owner(&self, lobby_id: u64) -> PyResult<u64> {
        let api = self.api()?;
        // SAFETY: Steam is open.
        Ok(unsafe { (api.lobby_owner)(self.matchmaking, lobby_id) })
    }

    /// The members of a lobby this player is in.
    fn lobby_members(&self, lobby_id: u64) -> PyResult<Vec<u64>> {
        let api = self.api()?;
        // SAFETY: Steam is open; indices are below the count it gave.
        Ok(unsafe {
            let count = (api.lobby_member_count)(self.matchmaking, lobby_id).clamp(0, MAX_LOBBY_MEMBERS);
            (0..count).map(|i| (api.lobby_member)(self.matchmaking, lobby_id, i)).collect()
        })
    }

    /// A lobby's value for `key`, empty if unset. Written by its owner, so
    /// untrusted.
    fn lobby_data(&self, lobby_id: u64, key: &str) -> PyResult<String> {
        let api = self.api()?;
        let key = c_string("a lobby data key", key, VALUE_BYTES)?;
        // SAFETY: Steam returns a string it owns, valid until the next call.
        let value = unsafe { (api.get_lobby_data)(self.matchmaking, lobby_id, key.as_ptr()) };
        if value.is_null() {
            return Ok(String::new());
        }
        // SAFETY: non-null, NUL-terminated.
        Ok(unsafe { CStr::from_ptr(value) }.to_string_lossy().into_owned())
    }

    /// Set a lobby's value for `key` (its owner only).
    fn set_lobby_data(&self, lobby_id: u64, key: &str, value: &str) -> PyResult<bool> {
        let api = self.api()?;
        let key = c_string("a lobby data key", key, VALUE_BYTES)?;
        let value = c_string("a lobby data value", value, LOBBY_DATA_BYTES)?;
        // SAFETY: Steam copies both strings.
        Ok(unsafe { (api.set_lobby_data)(self.matchmaking, lobby_id, key.as_ptr(), value.as_ptr()) })
    }

    /// Set one rich presence key; `connect` makes "Join Game" appear for
    /// friends.
    fn set_rich_presence(&self, key: &str, value: &str) -> PyResult<bool> {
        let api = self.api()?;
        let key = c_string("a rich presence key", key, KEY_BYTES)?;
        let value = c_string("a rich presence value", value, VALUE_BYTES)?;
        // SAFETY: Steam copies both strings.
        Ok(unsafe { (api.set_rich_presence)(self.friends, key.as_ptr(), value.as_ptr()) })
    }

    /// Clear every rich presence key.
    fn clear_rich_presence(&self) -> PyResult<()> {
        let api = self.api()?;
        // SAFETY: Steam is open.
        unsafe { (api.clear_rich_presence)(self.friends) };
        Ok(())
    }

    /// Open the overlay's dialog for inviting friends to a lobby.
    fn open_invite_dialog(&self, lobby_id: u64) -> PyResult<()> {
        let api = self.api()?;
        // SAFETY: Steam is open.
        unsafe { (api.invite_dialog)(self.friends, lobby_id) };
        Ok(())
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
