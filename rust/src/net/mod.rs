//! The network transport's Python face: one class, either side, with or
//! without a socket.
//!
//! Python calls `tick`, `receive` and `drain_transmit` itself on the sans-IO
//! path, which is what the simulated network drives; `start_udp` hands those to
//! a thread instead. Everything else is the same on both paths, so the tests
//! exercise the code that ships. The boundary stays message-shaped: one crossing
//! per message, never per entity.

mod core;
mod socket;
mod steam;
mod steam_core;

use std::net::SocketAddr;
use std::sync::{Arc, Mutex};
use std::time::Duration;

use pyo3::exceptions::{PyRuntimeError, PyValueError};
use pyo3::prelude::*;
use pyo3::types::{PyBytes, PyDict, PyList, PyTuple};

use self::core::{CHANNEL_COUNT, ClientCore, Core, Event, HostCore, PROTOCOL_VERSION};
use self::socket::{SocketThread, lock};

const KEY_BYTES: usize = 32;
const USER_DATA_BYTES: usize = 256;
const MAX_CLIENTS: usize = 64;

fn parse_key(key: &[u8]) -> PyResult<[u8; KEY_BYTES]> {
    let key: [u8; KEY_BYTES] = key
        .try_into()
        .map_err(|_| PyValueError::new_err(format!("a session key is {KEY_BYTES} bytes")))?;
    // renetcode's Unsecure mode uses exactly this key, so anyone could connect.
    if key.iter().all(|byte| *byte == 0) {
        return Err(PyValueError::new_err("refusing an all-zero session key"));
    }
    Ok(key)
}

fn parse_addr(address: &str) -> PyResult<SocketAddr> {
    address
        .parse()
        .map_err(|_| PyValueError::new_err(format!("not an ip:port address: {address:?}")))
}

fn check_channel(channel: u8) -> PyResult<()> {
    // `renet` panics on an unknown channel.
    if channel >= CHANNEL_COUNT {
        return Err(PyValueError::new_err(format!("no such channel: {channel}")));
    }
    Ok(())
}

/// One network endpoint, a host or a client.
#[pyclass]
pub struct NativeNetEndpoint {
    core: Arc<Mutex<Core>>,
    thread: Mutex<Option<SocketThread>>,
}

impl NativeNetEndpoint {
    fn from_core(core: Core) -> Self {
        Self { core: Arc::new(Mutex::new(core)), thread: Mutex::new(None) }
    }

    fn require_sans_io(&self) -> PyResult<()> {
        if self.thread.lock().unwrap_or_else(|e| e.into_inner()).is_some() {
            return Err(PyRuntimeError::new_err("a socket thread is driving this endpoint"));
        }
        Ok(())
    }

    fn stop_thread(&self) {
        let thread = self.thread.lock().unwrap_or_else(|e| e.into_inner()).take();
        if let Some(thread) = thread {
            thread.stop();
        }
    }
}

impl Drop for NativeNetEndpoint {
    fn drop(&mut self) {
        self.stop_thread();
    }
}

#[pymethods]
impl NativeNetEndpoint {
    /// Create a host.
    #[staticmethod]
    fn host(key: &[u8], max_clients: usize, send_bytes_per_tick: u64) -> PyResult<Self> {
        if !(1..=MAX_CLIENTS).contains(&max_clients) {
            return Err(PyValueError::new_err(format!(
                "max_clients must be between 1 and {MAX_CLIENTS}"
            )));
        }
        let core = HostCore::new(parse_key(key)?, max_clients, send_bytes_per_tick);
        Ok(Self::from_core(Core::Host(Box::new(core))))
    }

    /// Create a client that will connect to `server` once driven.
    #[staticmethod]
    fn client(
        key: &[u8],
        client_id: u64,
        server: &str,
        user_data: &[u8],
        send_bytes_per_tick: u64,
    ) -> PyResult<Self> {
        if user_data.len() > USER_DATA_BYTES {
            return Err(PyValueError::new_err(format!(
                "user data is at most {USER_DATA_BYTES} bytes"
            )));
        }
        let mut padded = [0u8; USER_DATA_BYTES];
        padded[..user_data.len()].copy_from_slice(user_data);
        let core = ClientCore::new(
            parse_key(key)?,
            client_id,
            parse_addr(server)?,
            &padded,
            send_bytes_per_tick,
        )
        .map_err(PyRuntimeError::new_err)?;
        Ok(Self::from_core(Core::Client(Box::new(core))))
    }

    /// Feed one received datagram to the core. Hostile bytes are fine here.
    fn receive(&self, source: &str, datagram: &[u8]) -> PyResult<()> {
        self.require_sans_io()?;
        let source = parse_addr(source)?;
        let mut buffer = datagram.to_vec();
        lock(&self.core).on_datagram(source, &mut buffer);
        Ok(())
    }

    /// Advance the core by `dt` seconds.
    fn tick(&self, dt: f64) -> PyResult<()> {
        self.require_sans_io()?;
        let dt = Duration::try_from_secs_f64(dt)
            .map_err(|_| PyValueError::new_err("dt must be finite and not negative"))?;
        lock(&self.core).tick(dt);
        Ok(())
    }

    /// Take the datagrams waiting to go out, as `(destination, bytes)`.
    fn drain_transmit<'p>(&self, py: Python<'p>) -> PyResult<Bound<'p, PyList>> {
        self.require_sans_io()?;
        let outgoing = lock(&self.core).take_outgoing();
        let items = outgoing
            .iter()
            .map(|(address, wire)| (address.to_string(), PyBytes::new(py, wire)));
        PyList::new(py, items)
    }

    /// Move this endpoint onto a real socket and return its local address.
    fn start_udp(&self, py: Python<'_>, bind: &str) -> PyResult<String> {
        let bind = parse_addr(bind)?;
        let mut slot = self.thread.lock().unwrap_or_else(|e| e.into_inner());
        if slot.is_some() {
            return Err(PyRuntimeError::new_err("the socket is already running"));
        }
        let core = Arc::clone(&self.core);
        let thread = py.detach(|| SocketThread::start(core, bind))?;
        let local = thread.local_addr.to_string();
        *slot = Some(thread);
        Ok(local)
    }

    /// Queue a message. False means it was not accepted: no such peer, or the
    /// channel's memory limit, which on a reliable channel means a backlog.
    fn send(&self, peer: u64, channel: u8, data: &[u8]) -> PyResult<bool> {
        check_channel(channel)?;
        Ok(lock(&self.core).send(peer, channel, data))
    }

    /// Everything that happened since the last poll, as tuples.
    fn poll<'p>(&self, py: Python<'p>) -> PyResult<Bound<'p, PyList>> {
        let events = lock(&self.core).take_events();
        let items = events
            .into_iter()
            .map(|event| -> PyResult<Bound<'p, PyTuple>> {
                match event {
                    Event::Connected { peer, user_data } => {
                        ("connected", peer, PyBytes::new(py, &user_data)).into_pyobject(py)
                    }
                    Event::Disconnected { peer, reason } => {
                        ("disconnected", peer, reason).into_pyobject(py)
                    }
                    Event::Message { peer, channel, data } => {
                        ("message", peer, channel, PyBytes::new(py, &data)).into_pyobject(py)
                    }
                    Event::Fatal { reason } => ("fatal", 0u64, reason).into_pyobject(py),
                }
            })
            .collect::<PyResult<Vec<_>>>()?;
        PyList::new(py, items)
    }

    /// End a peer's connection. With `flush`, after its reliable messages are
    /// acknowledged or five seconds pass, so a refusal can be read.
    #[pyo3(signature = (peer, flush = false))]
    fn disconnect(&self, peer: u64, flush: bool) {
        lock(&self.core).disconnect(peer, flush);
    }

    /// Round trip, loss and throughput for a peer, or None if it is gone.
    fn stats<'p>(&self, py: Python<'p>, peer: u64) -> PyResult<Option<Bound<'p, PyDict>>> {
        let Some(stats) = lock(&self.core).stats(peer) else {
            return Ok(None);
        };
        let dict = PyDict::new(py);
        dict.set_item("rtt", stats.rtt)?;
        dict.set_item("packet_loss", stats.packet_loss)?;
        dict.set_item("bytes_sent_per_second", stats.bytes_sent_per_second)?;
        dict.set_item("bytes_received_per_second", stats.bytes_received_per_second)?;
        Ok(Some(dict))
    }

    /// What the guards have rejected so far.
    fn counters<'p>(&self, py: Python<'p>) -> PyResult<Bound<'p, PyDict>> {
        let counters = lock(&self.core).counters();
        let dict = PyDict::new(py);
        dict.set_item("implausible", counters.implausible)?;
        dict.set_item("wrong_source", counters.wrong_source)?;
        dict.set_item("unauth_over_budget", counters.unauth_over_budget)?;
        dict.set_item("peer_over_budget", counters.peer_over_budget)?;
        dict.set_item("panics", counters.panics)?;
        Ok(dict)
    }

    /// Whether the socket thread is still running.
    fn is_running(&self) -> bool {
        self.thread
            .lock()
            .unwrap_or_else(|e| e.into_inner())
            .as_ref()
            .is_some_and(SocketThread::is_running)
    }

    /// Say goodbye to every peer and stop the socket thread.
    fn close(&self, py: Python<'_>) {
        let had_thread = self.thread.lock().unwrap_or_else(|e| e.into_inner()).is_some();
        if had_thread {
            py.detach(|| self.stop_thread());
        } else {
            lock(&self.core).shutdown();
        }
    }

    /// Test only: send raw bytes under this client's encryption, skipping
    /// `renet`. See `ClientCore::inject_payload`.
    fn _inject_payload(&self, payload: &[u8]) -> bool {
        lock(&self.core).inject_payload(payload)
    }
}

/// Add the transport to the extension module.
pub fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add_class::<NativeNetEndpoint>()?;
    module.add_class::<steam::NativeSteamEndpoint>()?;
    module.add("NET_PROTOCOL_VERSION", PROTOCOL_VERSION)?;
    Ok(())
}
