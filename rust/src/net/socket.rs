//! The UDP socket and its thread: a thin loop around the sans-IO core.
//!
//! This thread never takes the GIL, so a stalled Python frame delays game state
//! and not the connection: it keeps acknowledging, resending and sending
//! keepalives. Every `recv` and `send` error is survivable. Windows reports an
//! earlier ICMP port-unreachable as a failed `recv_from`, for one, and anyone
//! can provoke that, so an error must never end the loop.

use std::net::{SocketAddr, UdpSocket};
use std::panic::{AssertUnwindSafe, catch_unwind};
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::{Arc, Mutex, MutexGuard};
use std::thread::JoinHandle;
use std::time::{Duration, Instant};

use super::core::Core;

/// `renet` spends its byte budget per tick, so this also paces sends.
pub const TICK: Duration = Duration::from_micros(8_333);
/// How long a `recv` may block, which bounds how late a tick can start. Incoming
/// traffic wakes it sooner.
const POLL: Duration = Duration::from_millis(2);
/// Over any real MTU, so a datagram too large for the protocol arrives whole
/// and is rejected, rather than being truncated into something plausible.
const RECEIVE_BUFFER_BYTES: usize = 2048;

/// A panic elsewhere must not stop the rest of the network working.
pub fn lock(core: &Mutex<Core>) -> MutexGuard<'_, Core> {
    core.lock().unwrap_or_else(|poisoned| poisoned.into_inner())
}

pub struct SocketThread {
    stop: Arc<AtomicBool>,
    handle: JoinHandle<()>,
    pub local_addr: SocketAddr,
}

impl SocketThread {
    pub fn start(core: Arc<Mutex<Core>>, bind: SocketAddr) -> std::io::Result<Self> {
        let socket = UdpSocket::bind(bind)?;
        socket.set_read_timeout(Some(POLL))?;
        let local_addr = socket.local_addr()?;
        let stop = Arc::new(AtomicBool::new(false));
        let thread_stop = Arc::clone(&stop);
        let handle = std::thread::Builder::new()
            .name("pyguara-net".to_string())
            .spawn(move || run(&core, &socket, &thread_stop))?;
        Ok(Self { stop, handle, local_addr })
    }

    pub fn is_running(&self) -> bool {
        !self.handle.is_finished()
    }

    pub fn stop(self) {
        self.stop.store(true, Ordering::Release);
        let _ = self.handle.join();
    }
}

fn run(core: &Mutex<Core>, socket: &UdpSocket, stop: &AtomicBool) {
    // The core guards each peer. This is the last line behind that: if the loop
    // itself dies, Python is told, because a thread that vanished silently is
    // exactly what the plan forbids.
    let outcome = catch_unwind(AssertUnwindSafe(|| pump(core, socket, stop)));
    if outcome.is_err() {
        lock(core).fatal("the network thread failed");
    }
}

fn pump(core: &Mutex<Core>, socket: &UdpSocket, stop: &AtomicBool) {
    let mut buffer = [0u8; RECEIVE_BUFFER_BYTES];
    let mut last_tick = Instant::now();
    while !stop.load(Ordering::Acquire) {
        if let Ok((length, source)) = socket.recv_from(&mut buffer) {
            lock(core).on_datagram(source, &mut buffer[..length]);
        }
        let elapsed = last_tick.elapsed();
        if elapsed >= TICK {
            last_tick += elapsed;
            let outgoing = {
                let mut guard = lock(core);
                guard.tick(elapsed);
                guard.take_outgoing()
            };
            for (address, wire) in outgoing {
                let _ = socket.send_to(&wire, address);
            }
        }
    }

    let outgoing = {
        let mut guard = lock(core);
        guard.shutdown();
        guard.take_outgoing()
    };
    for (address, wire) in outgoing {
        let _ = socket.send_to(&wire, address);
    }
}
