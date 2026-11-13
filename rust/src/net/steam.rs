//! The Steam core's Python face: `NativeNetEndpoint`'s, keyed by Steam ID.
//!
//! Sans-IO only. Datagrams arrive through `receive` and leave through
//! `drain_transmit`, with each source and destination a Steam ID written in
//! decimal -- so `SimulatedNetwork`, which speaks in address strings, drives it
//! unchanged. Steam's own send and receive are the binding's job (5b).

use std::sync::Mutex;
use std::time::Duration;

use pyo3::exceptions::PyValueError;
use pyo3::prelude::*;
use pyo3::types::{PyBytes, PyDict, PyList, PyTuple};

use super::check_channel;
use super::core::Event;
use super::steam_core::{SteamClientCore, SteamCore, SteamHostCore, USER_DATA_BYTES};

const MAX_CLIENTS: usize = 64;

fn parse_id(id: &str) -> PyResult<u64> {
    id.parse().map_err(|_| PyValueError::new_err(format!("not a Steam ID: {id:?}")))
}

/// One Steam endpoint, a host or a client.
#[pyclass]
pub struct NativeSteamEndpoint {
    core: Mutex<SteamCore>,
}

impl NativeSteamEndpoint {
    fn core(&self) -> std::sync::MutexGuard<'_, SteamCore> {
        self.core.lock().unwrap_or_else(|e| e.into_inner())
    }
}

#[pymethods]
impl NativeSteamEndpoint {
    /// Create a host. Closed, it admits only the Steam IDs `allow` names;
    /// `open` admits anyone, for development.
    #[staticmethod]
    #[pyo3(signature = (max_clients, send_bytes_per_tick, open = false))]
    fn host(max_clients: usize, send_bytes_per_tick: u64, open: bool) -> PyResult<Self> {
        if !(1..=MAX_CLIENTS).contains(&max_clients) {
            return Err(PyValueError::new_err(format!(
                "max_clients must be between 1 and {MAX_CLIENTS}"
            )));
        }
        let core = SteamHostCore::new(max_clients, send_bytes_per_tick, open);
        Ok(Self { core: Mutex::new(SteamCore::Host(Box::new(core))) })
    }

    /// Create a client that will join the host with Steam ID `server`.
    #[staticmethod]
    fn client(server: u64, user_data: &[u8], send_bytes_per_tick: u64) -> PyResult<Self> {
        if user_data.len() > USER_DATA_BYTES {
            return Err(PyValueError::new_err(format!(
                "user data is at most {USER_DATA_BYTES} bytes"
            )));
        }
        let core = SteamClientCore::new(server, user_data, send_bytes_per_tick);
        Ok(Self { core: Mutex::new(SteamCore::Client(Box::new(core))) })
    }

    /// Admit a Steam ID (a host's; a client ignores it).
    fn allow(&self, steam_id: u64) {
        self.core().allow(steam_id);
    }

    /// Stop admitting a Steam ID, dropping it if connected.
    fn revoke(&self, steam_id: u64) {
        self.core().revoke(steam_id);
    }

    /// Feed one received message, from the Steam ID `source`. Hostile bytes
    /// are fine here.
    fn receive(&self, source: &str, datagram: &[u8]) -> PyResult<()> {
        let source = parse_id(source)?;
        self.core().on_datagram(source, datagram);
        Ok(())
    }

    /// Advance the core by `dt` seconds.
    fn tick(&self, dt: f64) -> PyResult<()> {
        let dt = Duration::try_from_secs_f64(dt)
            .map_err(|_| PyValueError::new_err("dt must be finite and not negative"))?;
        self.core().tick(dt);
        Ok(())
    }

    /// Take the messages waiting to go out, as `(steam_id, bytes)`.
    fn drain_transmit<'p>(&self, py: Python<'p>) -> PyResult<Bound<'p, PyList>> {
        let outgoing = self.core().take_outgoing();
        let items = outgoing.iter().map(|(id, wire)| (id.to_string(), PyBytes::new(py, wire)));
        PyList::new(py, items)
    }

    /// Queue a message; see `NativeNetEndpoint.send`.
    fn send(&self, peer: u64, channel: u8, data: &[u8]) -> PyResult<bool> {
        check_channel(channel)?;
        Ok(self.core().send(peer, channel, data))
    }

    /// Everything that happened since the last poll, as tuples.
    fn poll<'p>(&self, py: Python<'p>) -> PyResult<Bound<'p, PyList>> {
        let events = self.core().take_events();
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

    /// End a peer's connection; see `NativeNetEndpoint.disconnect`.
    #[pyo3(signature = (peer, flush = false))]
    fn disconnect(&self, peer: u64, flush: bool) {
        self.core().disconnect(peer, flush);
    }

    /// Round trip, loss and throughput for a peer, or None if it is gone.
    fn stats<'p>(&self, py: Python<'p>, peer: u64) -> PyResult<Option<Bound<'p, PyDict>>> {
        let Some(stats) = self.core().stats(peer) else {
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
        let counters = self.core().counters();
        let dict = PyDict::new(py);
        dict.set_item("implausible", counters.implausible)?;
        dict.set_item("wrong_source", counters.wrong_source)?;
        dict.set_item("unauth_over_budget", counters.unauth_over_budget)?;
        dict.set_item("peer_over_budget", counters.peer_over_budget)?;
        dict.set_item("panics", counters.panics)?;
        Ok(dict)
    }

    /// Say goodbye to every peer.
    fn close(&self) {
        self.core().shutdown();
    }
}
