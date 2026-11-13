//! The sans-IO network core: datagrams and a time step in, datagrams and
//! messages out. No socket, no thread and no clock, so a test can run two real
//! cores through a seeded fake network.
//!
//! `renetcode` does the handshake, authenticates and encrypts every packet, and
//! detects timeouts. `renet` does acks, channels and slicing. What this file
//! adds is what those two do not promise.
//!
//! **Neither crate is safe to expose as shipped.** Measured against the exact
//! versions `Cargo.toml` pins:
//!
//! - One datagram from anyone, before any authentication, panics `renetcode`:
//!   a sequence length over 8 at `packet.rs:375`, or a body too short for its
//!   MAC at `crypto.rs:10`. `plausible()` rejects both before it is called.
//! - Two slices of one message with different `num_slices` panic `renet` at
//!   `slice_constructor.rs:41`. Only someone holding the invite can reach it,
//!   and `catch_unwind` drops that peer and nobody else.
//! - `renet` alone disconnects a peer on one malformed packet. It only ever
//!   sees what `renetcode` authenticated, so a forged packet cannot do that.
//!
//! **Neither end counts as connected until both know it.** `renetcode` can deadlock
//! a join: if the host's first keepalive is lost, the client ignores payloads while
//! it waits for another, and every payload resets the host's keepalive timer. With
//! a reliable resend every 100 ms against a 250 ms keepalive, the next one never
//! comes, and the host admits a player whose client then times out. So a client
//! sends `CONFIRM` until it hears a payload, and the host neither sends to a peer
//! nor reports it until it has heard one. Any authenticated payload confirms.
//!
//! `catch_unwind` needs `panic = "unwind"`, the release profile's default. If
//! `abort` is ever set, a remote client can kill the host again, which is what
//! `tests/test_net_hostile.py` would catch.
//!
//! **Only authenticated traffic counts against a peer.** A UDP source address
//! is spoofable, so throttling by address before the MAC check would hand any
//! stranger a way to remove a real player. Unauthenticated datagrams share one
//! global budget instead, which can delay a joiner and nothing else.

use std::collections::{HashMap, VecDeque};
use std::net::SocketAddr;
use std::panic::{AssertUnwindSafe, catch_unwind};
use std::time::Duration;

use renet::{ChannelConfig, ConnectionConfig, RenetClient, RenetServer, SendType, ServerEvent};
use renetcode::{
    ClientAuthentication, ConnectToken, NETCODE_KEY_BYTES, NETCODE_MAX_PACKET_BYTES,
    NETCODE_USER_DATA_BYTES, NetcodeClient, NetcodeServer, ServerAuthentication, ServerConfig,
    ServerResult,
};

/// Bump on any wire change. Python compares it at session start, which is what
/// turns a stale extension into an error naming `make native`.
pub const PROTOCOL_VERSION: u32 = 1;

/// Fixed for good: a mismatch makes `renetcode` ignore a client in silence, so
/// versions travel in the token's user data, where they can be refused aloud.
const PROTOCOL_ID: u64 = u64::from_le_bytes(*b"PYGUARA1");

/// What both ends agree the token's server address is. Secure mode checks it
/// against the host's public addresses, and a host behind NAT does not know
/// its own. Nothing else reads the value.
const TOKEN_SERVER_ADDRESS: ([u8; 4], u16) = ([127, 0, 0, 1], 1);

/// Netcode time starts at zero on both ends, so no wall clock is ever compared
/// and a guest's wrong clock cannot refuse them. A replayed token still gains
/// nothing: its keys are sealed inside, and one token cannot be used from a
/// second address.
const TOKEN_EXPIRY_SECONDS: u64 = 10 * 365 * 24 * 3600;
pub(super) const TIMEOUT_SECONDS: i32 = 10;

/// `renet`'s `SLICE_SIZE`, which it does not export. Pinned with the crate.
pub(super) const SLICE_SIZE: usize = 1200;
const MTU_BYTES: usize = NETCODE_MAX_PACKET_BYTES;
const MAC_BYTES: usize = 16;
const MAX_SEQUENCE_BYTES: u8 = 8;
const MIN_DATAGRAM_BYTES: usize = 2 + MAC_BYTES;

/// Per peer, once authenticated. A connected client's normal load is a few
/// hundred datagrams a second.
pub(super) const PEER_DATAGRAMS_PER_SECOND: f64 = 1500.0;
pub(super) const PEER_DATAGRAM_BURST: f64 = 2000.0;
pub(super) const PEER_DROPS_BEFORE_KICK: u32 = 30_000;

/// Shared by every address that has not authenticated.
pub(super) const UNAUTH_DATAGRAMS_PER_SECOND: f64 = 200.0;
pub(super) const UNAUTH_DATAGRAM_BURST: f64 = 400.0;

/// Past this, reliable messages wait in `renet`, whose own limit then ends the
/// connection, and unreliable ones are dropped. So a long stall is bounded.
pub(super) const INBOX_LIMIT_BYTES: usize = 32 * 1024 * 1024;
/// Sits outside `renet`'s packet types, so it can never be read as one.
const CONFIRM: [u8; 1] = [0xFF];
const CONFIRM_INTERVAL: Duration = Duration::from_millis(100);

pub(super) const FLUSH_TIMEOUT: Duration = Duration::from_secs(5);
pub(super) const DISCONNECT_REPEATS: usize = 3;

const CONTROL: u8 = 0;
const EVENTS: u8 = 1;
const COMMANDS: u8 = 2;
const SNAPSHOT: u8 = 3;
const LEVEL: u8 = 4;
pub const CHANNEL_COUNT: u8 = 5;

const KIB: usize = 1024;
const MIB: usize = 1024 * KIB;

pub(super) struct ChannelSpec {
    pub(super) id: u8,
    pub(super) reliable: bool,
    pub(super) client_to_host_bytes: usize,
    pub(super) host_to_client_bytes: usize,
}

/// In priority order: `renet` spends each tick's byte budget front to back, so
/// a level transfer can never starve events or snapshots. Client limits are
/// small on purpose. They bound what a client can make the host allocate, and
/// `renet` checks them before allocating for a slice.
pub(super) const CHANNELS: [ChannelSpec; CHANNEL_COUNT as usize] = [
    ChannelSpec { id: CONTROL, reliable: true, client_to_host_bytes: 16 * KIB, host_to_client_bytes: 16 * KIB },
    ChannelSpec { id: COMMANDS, reliable: false, client_to_host_bytes: 64 * KIB, host_to_client_bytes: 64 * KIB },
    ChannelSpec { id: EVENTS, reliable: true, client_to_host_bytes: 256 * KIB, host_to_client_bytes: MIB },
    ChannelSpec { id: SNAPSHOT, reliable: false, client_to_host_bytes: 64 * KIB, host_to_client_bytes: 2 * MIB },
    ChannelSpec { id: LEVEL, reliable: true, client_to_host_bytes: 64 * KIB, host_to_client_bytes: 16 * MIB },
];

pub(super) fn connection_config(send_bytes_per_tick: u64) -> ConnectionConfig {
    let config = |bytes: fn(&ChannelSpec) -> usize| -> Vec<ChannelConfig> {
        CHANNELS
            .iter()
            .map(|spec| ChannelConfig {
                channel_id: spec.id,
                max_memory_usage_bytes: bytes(spec),
                send_type: if spec.reliable {
                    SendType::ReliableOrdered { resend_time: Duration::from_millis(100) }
                } else {
                    SendType::Unreliable
                },
            })
            .collect()
    };
    ConnectionConfig {
        available_bytes_per_tick: send_bytes_per_tick,
        server_channels_config: config(|spec| spec.host_to_client_bytes),
        client_channels_config: config(|spec| spec.client_to_host_bytes),
    }
}

/// What a send may ask `renet` to check, so that a message accepted here cannot
/// end the connection at the other end.
///
/// `renet`'s sender counts actual bytes, but its receiver charges a sliced message
/// as whole slices, against the same limit, and disconnects when over. Rounding
/// can at most double a message's charge (1,201 bytes is charged 2,400), so a
/// reliable channel only accepts a send that would fit in half its limit.
pub(super) fn bytes_to_check(channel: u8, length: usize, limit: fn(&ChannelSpec) -> usize) -> usize {
    let Some(spec) = CHANNELS.iter().find(|spec| spec.id == channel) else {
        return length;
    };
    if spec.reliable {
        length.div_ceil(SLICE_SIZE) * SLICE_SIZE + limit(spec) / 2
    } else {
        length
    }
}

/// Reject what would panic `renetcode` when parsed. See the module docs.
pub fn plausible(datagram: &[u8]) -> bool {
    if datagram.len() < MIN_DATAGRAM_BYTES || datagram.len() > MTU_BYTES {
        return false;
    }
    let sequence_bytes = datagram[0] >> 4;
    sequence_bytes <= MAX_SEQUENCE_BYTES
        && datagram.len() >= 1 + sequence_bytes as usize + MAC_BYTES
}

/// What Python sees come out of a core.
pub enum Event {
    Connected { peer: u64, user_data: Vec<u8> },
    Disconnected { peer: u64, reason: String },
    Message { peer: u64, channel: u8, data: Vec<u8> },
    /// The core itself failed. It is inert from here, and says so rather than
    /// leaving Python to wonder why nothing arrives.
    Fatal { reason: String },
}

/// Counted so a test, and a debug overlay, can see what the guards are doing.
#[derive(Default, Clone, Copy)]
pub struct Counters {
    pub implausible: u64,
    pub wrong_source: u64,
    pub unauth_over_budget: u64,
    pub peer_over_budget: u64,
    pub panics: u64,
}

#[derive(Clone, Copy)]
pub struct LinkStats {
    pub rtt: f64,
    pub packet_loss: f64,
    pub bytes_sent_per_second: f64,
    pub bytes_received_per_second: f64,
}

pub(super) struct Bucket {
    tokens: f64,
    rate: f64,
    burst: f64,
}

impl Bucket {
    pub(super) fn new(rate: f64, burst: f64) -> Self {
        Self { tokens: burst, rate, burst }
    }

    pub(super) fn refill(&mut self, seconds: f64) {
        self.tokens = (self.tokens + seconds * self.rate).min(self.burst);
    }

    pub(super) fn take(&mut self) -> bool {
        if self.tokens >= 1.0 {
            self.tokens -= 1.0;
            true
        } else {
            false
        }
    }
}

type Outgoing = Vec<(SocketAddr, Vec<u8>)>;

struct Peer {
    addr: SocketAddr,
    budget: Bucket,
    consecutive_drops: u32,
    flush_deadline: Option<Duration>,
    kick_reason: Option<String>,
    /// Held until the client confirms: see the module docs. None once reported.
    unconfirmed_user_data: Option<Vec<u8>>,
}

/// The listen server's side.
pub struct HostCore {
    netcode: NetcodeServer,
    renet: RenetServer,
    peers: HashMap<u64, Peer>,
    addrs: HashMap<SocketAddr, u64>,
    unauth: Bucket,
    now: Duration,
    outgoing: Outgoing,
    events: VecDeque<Event>,
    inbox_bytes: usize,
    counters: Counters,
    fatal: bool,
}

impl HostCore {
    pub fn new(key: [u8; NETCODE_KEY_BYTES], max_clients: usize, send_bytes_per_tick: u64) -> Self {
        Self {
            netcode: NetcodeServer::new(ServerConfig {
                current_time: Duration::ZERO,
                max_clients,
                protocol_id: PROTOCOL_ID,
                public_addresses: vec![SocketAddr::from(TOKEN_SERVER_ADDRESS)],
                authentication: ServerAuthentication::Secure { private_key: key },
            }),
            renet: RenetServer::new(connection_config(send_bytes_per_tick)),
            peers: HashMap::new(),
            addrs: HashMap::new(),
            unauth: Bucket::new(UNAUTH_DATAGRAMS_PER_SECOND, UNAUTH_DATAGRAM_BURST),
            now: Duration::ZERO,
            outgoing: Vec::new(),
            events: VecDeque::new(),
            inbox_bytes: 0,
            counters: Counters::default(),
            fatal: false,
        }
    }

    fn on_datagram(&mut self, source: SocketAddr, datagram: &mut [u8]) {
        if !plausible(datagram) {
            self.counters.implausible += 1;
            return;
        }
        let known = self.addrs.get(&source).copied();
        if known.is_none() && !self.unauth.take() {
            self.counters.unauth_over_budget += 1;
            return;
        }
        let outcome = catch_unwind(AssertUnwindSafe(|| self.process(source, datagram)));
        if outcome.is_err() {
            self.counters.panics += 1;
            if let Some(peer) = known {
                self.kick(peer, "dropped: a packet from this peer broke the protocol");
            }
        }
    }

    fn process(&mut self, source: SocketAddr, datagram: &mut [u8]) {
        match self.netcode.process_packet(source, datagram) {
            ServerResult::None => {}
            ServerResult::PacketToSend { addr, payload } => {
                self.outgoing.push((addr, payload.to_vec()));
            }
            ServerResult::Payload { client_id, payload } => {
                let Some(peer) = self.peers.get_mut(&client_id) else {
                    return;
                };
                if !peer.budget.take() {
                    self.counters.peer_over_budget += 1;
                    peer.consecutive_drops += 1;
                    if peer.consecutive_drops > PEER_DROPS_BEFORE_KICK {
                        self.kick(client_id, "dropped: sending far over the rate limit");
                    }
                    return;
                }
                peer.consecutive_drops = peer.consecutive_drops.saturating_sub(1);
                if let Some(user_data) = peer.unconfirmed_user_data.take() {
                    self.events.push_back(Event::Connected { peer: client_id, user_data });
                }
                if payload != CONFIRM {
                    let _ = self.renet.process_packet_from(payload, client_id);
                }
            }
            ServerResult::ClientConnected { client_id, addr, user_data, payload } => {
                self.outgoing.push((addr, payload.to_vec()));
                self.peers.insert(
                    client_id,
                    Peer {
                        addr,
                        budget: Bucket::new(PEER_DATAGRAMS_PER_SECOND, PEER_DATAGRAM_BURST),
                        consecutive_drops: 0,
                        flush_deadline: None,
                        kick_reason: None,
                        unconfirmed_user_data: Some(user_data.to_vec()),
                    },
                );
                self.addrs.insert(addr, client_id);
                self.renet.add_connection(client_id);
            }
            ServerResult::ClientDisconnected { client_id, addr, payload } => {
                if let Some(payload) = payload {
                    for _ in 0..DISCONNECT_REPEATS {
                        self.outgoing.push((addr, payload.to_vec()));
                    }
                }
                if let Some(peer) = self.peers.get_mut(&client_id) {
                    peer.kick_reason.get_or_insert_with(|| "left".to_string());
                }
                self.renet.remove_connection(client_id);
            }
        }
    }

    /// Remove a peer now. Safe after a panic in that peer's connection, because
    /// the whole connection is discarded rather than used again.
    fn kick(&mut self, peer: u64, reason: &str) {
        if let Some(state) = self.peers.get_mut(&peer) {
            state.kick_reason.get_or_insert_with(|| reason.to_string());
        }
        self.end_connection(peer);
    }

    fn end_connection(&mut self, peer: u64) {
        let result = catch_unwind(AssertUnwindSafe(|| {
            match self.netcode.disconnect(peer) {
                ServerResult::ClientDisconnected { addr, payload: Some(payload), .. } => {
                    for _ in 0..DISCONNECT_REPEATS {
                        self.outgoing.push((addr, payload.to_vec()));
                    }
                }
                ServerResult::PacketToSend { addr, payload } => {
                    self.outgoing.push((addr, payload.to_vec()));
                }
                _ => {}
            }
        }));
        if result.is_err() {
            self.counters.panics += 1;
        }
        self.renet.remove_connection(peer);
    }

    fn is_flushed(&self, peer: u64) -> bool {
        CHANNELS.iter().filter(|spec| spec.reliable).all(|spec| {
            self.renet.channel_available_memory(peer, spec.id) == spec.host_to_client_bytes
        })
    }

    fn tick(&mut self, dt: Duration) {
        self.now += dt;
        let seconds = dt.as_secs_f64();
        self.unauth.refill(seconds);
        for peer in self.peers.values_mut() {
            peer.budget.refill(seconds);
        }

        self.netcode.update(dt);
        self.renet.update(dt);

        for client_id in self.netcode.clients_id() {
            match self.netcode.update_client(client_id) {
                ServerResult::PacketToSend { addr, payload } => {
                    self.outgoing.push((addr, payload.to_vec()));
                }
                ServerResult::ClientDisconnected { client_id, .. } => {
                    if let Some(peer) = self.peers.get_mut(&client_id) {
                        peer.kick_reason.get_or_insert_with(|| "timed out".to_string());
                    }
                    self.renet.remove_connection(client_id);
                }
                _ => {}
            }
        }

        let due: Vec<u64> = self
            .peers
            .iter()
            .filter(|(id, peer)| {
                peer.flush_deadline.is_some_and(|deadline| {
                    self.now >= deadline
                        || (self.renet.is_connected(**id) && self.is_flushed(**id))
                })
            })
            .map(|(id, _)| *id)
            .collect();
        for peer in due {
            self.kick(peer, "disconnected by the host");
        }

        // `renet` ended these itself, and its reason is the useful one.
        for peer in self.renet.disconnections_id() {
            self.end_connection(peer);
        }
        self.drain_renet_events();
        self.pump_messages();
        self.send_packets();
    }

    fn drain_renet_events(&mut self) {
        while let Some(event) = self.renet.get_event() {
            if let ServerEvent::ClientDisconnected { client_id, reason } = event {
                let state = self.peers.remove(&client_id);
                let kick_reason = state.as_ref().and_then(|peer| peer.kick_reason.clone());
                let was_reported = state
                    .as_ref()
                    .is_some_and(|peer| peer.unconfirmed_user_data.is_none());
                if let Some(state) = state {
                    self.addrs.remove(&state.addr);
                }
                if !was_reported {
                    continue;
                }
                self.events.push_back(Event::Disconnected {
                    peer: client_id,
                    reason: kick_reason.unwrap_or_else(|| format!("{reason:?}")),
                });
            }
        }
    }

    fn pump_messages(&mut self) {
        for peer in self.renet.clients_id() {
            for spec in &CHANNELS {
                while self.inbox_bytes < INBOX_LIMIT_BYTES {
                    let Some(message) = self.renet.receive_message(peer, spec.id) else {
                        break;
                    };
                    self.inbox_bytes += message.len();
                    self.events.push_back(Event::Message {
                        peer,
                        channel: spec.id,
                        data: message.to_vec(),
                    });
                }
            }
        }
    }

    fn send_packets(&mut self) {
        for peer in self.renet.clients_id() {
            let result = catch_unwind(AssertUnwindSafe(|| -> Result<(), ()> {
                let state = self.peers.get(&peer).ok_or(())?;
                if state.unconfirmed_user_data.is_some() {
                    return Ok(());
                }
                let addr = state.addr;
                let packets = self.renet.get_packets_to_send(peer).map_err(|_| ())?;
                for packet in packets {
                    let (_, wire) = self
                        .netcode
                        .generate_payload_packet(peer, &packet)
                        .map_err(|_| ())?;
                    self.outgoing.push((addr, wire.to_vec()));
                }
                Ok(())
            }));
            if result.is_err() {
                self.counters.panics += 1;
                self.kick(peer, "dropped: its connection failed internally");
            }
        }
    }

    fn send(&mut self, peer: u64, channel: u8, data: &[u8]) -> bool {
        let needed = bytes_to_check(channel, data.len(), |spec| spec.host_to_client_bytes);
        if !self.renet.is_connected(peer) || !self.renet.can_send_message(peer, channel, needed) {
            return false;
        }
        self.renet.send_message(peer, channel, data.to_vec());
        true
    }

    fn disconnect(&mut self, peer: u64, flush: bool) {
        if flush {
            let deadline = self.now + FLUSH_TIMEOUT;
            if let Some(state) = self.peers.get_mut(&peer) {
                state.flush_deadline = Some(deadline);
            }
        } else {
            self.kick(peer, "disconnected by the host");
            self.drain_renet_events();
        }
    }

    fn shutdown(&mut self) {
        let peers: Vec<u64> = self.peers.keys().copied().collect();
        for peer in peers {
            self.kick(peer, "the host closed");
        }
        self.drain_renet_events();
    }

    fn stats(&self, peer: u64) -> Option<LinkStats> {
        self.renet.network_info(peer).ok().map(|info| LinkStats {
            rtt: info.rtt,
            packet_loss: info.packet_loss,
            bytes_sent_per_second: info.bytes_sent_per_second,
            bytes_received_per_second: info.bytes_received_per_second,
        })
    }
}

/// A joining player's side.
pub struct ClientCore {
    netcode: NetcodeClient,
    renet: RenetClient,
    server: SocketAddr,
    outgoing: Outgoing,
    events: VecDeque<Event>,
    inbox_bytes: usize,
    counters: Counters,
    announced_connect: bool,
    announced_disconnect: bool,
    heard_payload: bool,
    since_confirm: Duration,
    fatal: bool,
}

impl ClientCore {
    pub fn new(
        key: [u8; NETCODE_KEY_BYTES],
        client_id: u64,
        server: SocketAddr,
        user_data: &[u8; NETCODE_USER_DATA_BYTES],
        send_bytes_per_tick: u64,
    ) -> Result<Self, String> {
        let token = ConnectToken::generate(
            Duration::ZERO,
            PROTOCOL_ID,
            TOKEN_EXPIRY_SECONDS,
            client_id,
            TIMEOUT_SECONDS,
            vec![SocketAddr::from(TOKEN_SERVER_ADDRESS)],
            Some(user_data),
            &key,
        )
        .map_err(|error| error.to_string())?;
        let netcode = NetcodeClient::new(
            Duration::ZERO,
            ClientAuthentication::Secure { connect_token: token },
        )
        .map_err(|error| error.to_string())?;
        Ok(Self {
            netcode,
            renet: RenetClient::new(connection_config(send_bytes_per_tick)),
            server,
            outgoing: Vec::new(),
            events: VecDeque::new(),
            inbox_bytes: 0,
            counters: Counters::default(),
            announced_connect: false,
            announced_disconnect: false,
            heard_payload: false,
            since_confirm: CONFIRM_INTERVAL,
            fatal: false,
        })
    }

    fn on_datagram(&mut self, source: SocketAddr, datagram: &mut [u8]) {
        if source != self.server {
            self.counters.wrong_source += 1;
            return;
        }
        if !plausible(datagram) {
            self.counters.implausible += 1;
            return;
        }
        let outcome = catch_unwind(AssertUnwindSafe(|| {
            if let Some(payload) = self.netcode.process_packet(datagram) {
                self.heard_payload = true;
                self.renet.process_packet(payload);
            }
        }));
        if outcome.is_err() {
            self.counters.panics += 1;
            self.fail("the connection failed internally");
        }
    }

    fn fail(&mut self, reason: &str) {
        self.renet.disconnect_due_to_transport();
        if !self.announced_disconnect {
            self.announced_disconnect = true;
            self.events.push_back(Event::Disconnected { peer: 0, reason: reason.to_string() });
        }
    }

    fn tick(&mut self, dt: Duration) {
        if let Some((wire, _)) = self.netcode.update(dt) {
            self.outgoing.push((self.server, wire.to_vec()));
        }
        self.renet.update(dt);

        if self.netcode.is_connected() {
            self.renet.set_connected();
            if !self.announced_connect {
                self.announced_connect = true;
                self.events.push_back(Event::Connected { peer: 0, user_data: Vec::new() });
            }
        }

        // Before noticing a disconnect: `renet` hands out nothing afterwards,
        // and a refused guest has to be able to read why.
        self.pump_messages();

        let netcode_reason = self.netcode.disconnect_reason();
        if netcode_reason.is_some() {
            self.renet.disconnect_due_to_transport();
        }
        if let Some(reason) = self.renet.disconnect_reason() {
            if !self.netcode.is_disconnected() {
                if let Ok((_, wire)) = self.netcode.disconnect() {
                    for _ in 0..DISCONNECT_REPEATS {
                        self.outgoing.push((self.server, wire.to_vec()));
                    }
                }
            }
            if !self.announced_disconnect {
                self.announced_disconnect = true;
                let text = match netcode_reason {
                    Some(transport) => format!("{transport:?}"),
                    None => format!("{reason:?}"),
                };
                self.events.push_back(Event::Disconnected { peer: 0, reason: text });
            }
            return;
        }

        if self.netcode.is_connected() {
            self.since_confirm += dt;
            if !self.heard_payload && self.since_confirm >= CONFIRM_INTERVAL {
                self.since_confirm = Duration::ZERO;
                if let Ok((_, wire)) = self.netcode.generate_payload_packet(&CONFIRM) {
                    self.outgoing.push((self.server, wire.to_vec()));
                }
            }
            for packet in self.renet.get_packets_to_send() {
                match self.netcode.generate_payload_packet(&packet) {
                    Ok((_, wire)) => self.outgoing.push((self.server, wire.to_vec())),
                    Err(_) => self.renet.disconnect_due_to_transport(),
                }
            }
        }
    }

    fn pump_messages(&mut self) {
        for spec in &CHANNELS {
            while self.inbox_bytes < INBOX_LIMIT_BYTES {
                let Some(message) = self.renet.receive_message(spec.id) else {
                    break;
                };
                self.inbox_bytes += message.len();
                self.events.push_back(Event::Message {
                    peer: 0,
                    channel: spec.id,
                    data: message.to_vec(),
                });
            }
        }
    }

    fn send(&mut self, channel: u8, data: &[u8]) -> bool {
        let needed = bytes_to_check(channel, data.len(), |spec| spec.client_to_host_bytes);
        if !self.netcode.is_connected()
            || !self.renet.is_connected()
            || !self.renet.can_send_message(channel, needed)
        {
            return false;
        }
        self.renet.send_message(channel, data.to_vec());
        true
    }

    fn shutdown(&mut self) {
        self.renet.disconnect();
        if !self.netcode.is_disconnected() {
            if let Ok((_, wire)) = self.netcode.disconnect() {
                for _ in 0..DISCONNECT_REPEATS {
                    self.outgoing.push((self.server, wire.to_vec()));
                }
            }
        }
    }

    /// Hand raw bytes straight to the encrypted layer, skipping `renet`. Only
    /// tests use this, and it gives a client nothing it could not do by
    /// compiling its own: it is how the suite proves a hostile invited peer
    /// loses only its own connection.
    pub fn inject_payload(&mut self, payload: &[u8]) -> bool {
        match self.netcode.generate_payload_packet(payload) {
            Ok((_, wire)) => {
                self.outgoing.push((self.server, wire.to_vec()));
                true
            }
            Err(_) => false,
        }
    }
}

/// Either side, so the socket thread and the Python class are written once.
pub enum Core {
    Host(Box<HostCore>),
    Client(Box<ClientCore>),
}

impl Core {
    pub fn on_datagram(&mut self, source: SocketAddr, datagram: &mut [u8]) {
        if self.is_fatal() {
            return;
        }
        match self {
            Core::Host(core) => core.on_datagram(source, datagram),
            Core::Client(core) => core.on_datagram(source, datagram),
        }
    }

    /// A panic here cannot be pinned on one peer, so the core stops, says so,
    /// and never raises into the frame loop.
    pub fn tick(&mut self, dt: Duration) {
        if self.is_fatal() {
            return;
        }
        let outcome = catch_unwind(AssertUnwindSafe(|| match self {
            Core::Host(core) => core.tick(dt),
            Core::Client(core) => core.tick(dt),
        }));
        if outcome.is_err() {
            self.fatal("the network core failed internally");
        }
    }

    pub fn fatal(&mut self, reason: &str) {
        let (events, fatal, counters) = match self {
            Core::Host(core) => (&mut core.events, &mut core.fatal, &mut core.counters),
            Core::Client(core) => (&mut core.events, &mut core.fatal, &mut core.counters),
        };
        if !*fatal {
            *fatal = true;
            counters.panics += 1;
            events.push_back(Event::Fatal { reason: reason.to_string() });
        }
    }

    pub fn is_fatal(&self) -> bool {
        match self {
            Core::Host(core) => core.fatal,
            Core::Client(core) => core.fatal,
        }
    }

    pub fn send(&mut self, peer: u64, channel: u8, data: &[u8]) -> bool {
        if self.is_fatal() {
            return false;
        }
        match self {
            Core::Host(core) => core.send(peer, channel, data),
            Core::Client(core) => core.send(channel, data),
        }
    }

    pub fn disconnect(&mut self, peer: u64, flush: bool) {
        match self {
            Core::Host(core) => core.disconnect(peer, flush),
            Core::Client(core) => core.shutdown(),
        }
    }

    pub fn shutdown(&mut self) {
        match self {
            Core::Host(core) => core.shutdown(),
            Core::Client(core) => core.shutdown(),
        }
    }

    pub fn take_outgoing(&mut self) -> Outgoing {
        match self {
            Core::Host(core) => std::mem::take(&mut core.outgoing),
            Core::Client(core) => std::mem::take(&mut core.outgoing),
        }
    }

    pub fn take_events(&mut self) -> Vec<Event> {
        let (events, inbox) = match self {
            Core::Host(core) => (&mut core.events, &mut core.inbox_bytes),
            Core::Client(core) => (&mut core.events, &mut core.inbox_bytes),
        };
        *inbox = 0;
        events.drain(..).collect()
    }

    pub fn counters(&self) -> Counters {
        match self {
            Core::Host(core) => core.counters,
            Core::Client(core) => core.counters,
        }
    }

    pub fn stats(&self, peer: u64) -> Option<LinkStats> {
        match self {
            Core::Host(core) => core.stats(peer),
            Core::Client(core) => {
                let info = core.renet.network_info();
                Some(LinkStats {
                    rtt: info.rtt,
                    packet_loss: info.packet_loss,
                    bytes_sent_per_second: info.bytes_sent_per_second,
                    bytes_received_per_second: info.bytes_received_per_second,
                })
            }
        }
    }

    pub fn inject_payload(&mut self, payload: &[u8]) -> bool {
        match self {
            Core::Host(_) => false,
            Core::Client(core) => core.inject_payload(payload),
        }
    }
}
