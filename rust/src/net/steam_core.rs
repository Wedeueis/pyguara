//! The sans-IO core for Steam: `renet` keyed by Steam ID, with no `renetcode`.
//!
//! Over Steam's networking, Steam does what `renetcode` does over UDP: it
//! authenticates who sent each packet (a Steam ID it has verified), encrypts
//! it, and -- through its relay -- carries it without either side learning the
//! other's address. So this core keeps `renet` for what it does everywhere
//! (channels, acks, slicing, backpressure, link stats) and drops `renetcode`.
//! Datagrams in and out are Steam messages, sent unreliably; I/O is someone
//! else's job (5b's binding, or `SimulatedNetwork` in the tests).
//!
//! **A Steam ID is not trust.** Steam proves who a sender is, not that they
//! were invited. The host admits only IDs it was told to (`allow`, which 5c's
//! lobby drives), or anyone when opened for development; everyone else gets a
//! `REFUSED`, rate-limited, and nothing else.
//!
//! The wire, one tag byte then a body:
//!
//! | tag | who | body |
//! | --- | --- | --- |
//! | `HELLO` | client | the user data, up to 256 bytes: versions, content hash |
//! | `WELCOME` | host | nothing; the answer to every `HELLO` from a peer |
//! | `PAYLOAD` | both | one `renet` packet |
//! | `BYE` | both | why, as UTF-8; sent three times |
//! | `KEEPALIVE` | both | nothing; when quiet for 250 ms |
//! | `REFUSED` | host | why, as UTF-8 |
//!
//! A client's reasons are `renetcode`'s names (`ConnectionDenied`,
//! `ConnectionTimedOut`, `ConnectionRequestTimedOut`, `DisconnectedByServer`),
//! so the session explains a Steam disconnect to a player in the same words.
//!
//! A client repeats `HELLO` every 100 ms until it hears the host, so a lost
//! `WELCOME` costs a resend rather than a deadlock (the trap `core.rs`'s
//! module docs describe for `renetcode`). Either side drops the other after
//! ten seconds of silence, as `renetcode` did.
//!
//! `renet`'s slice panic (`core.rs`) is reachable here exactly as there, by a
//! peer the host admitted; `catch_unwind` still drops that peer and no one else.

use std::collections::{HashMap, HashSet, VecDeque};
use std::panic::{AssertUnwindSafe, catch_unwind};
use std::time::Duration;

use renet::{RenetClient, RenetServer, ServerEvent};

use super::core::{
    Bucket, CHANNELS, Counters, DISCONNECT_REPEATS, Event, FLUSH_TIMEOUT, INBOX_LIMIT_BYTES,
    LinkStats, PEER_DATAGRAM_BURST, PEER_DATAGRAMS_PER_SECOND, PEER_DROPS_BEFORE_KICK,
    SLICE_SIZE, TIMEOUT_SECONDS, UNAUTH_DATAGRAM_BURST, UNAUTH_DATAGRAMS_PER_SECOND,
    bytes_to_check, connection_config,
};

pub const HELLO: u8 = 0x01;
pub const WELCOME: u8 = 0x02;
pub const PAYLOAD: u8 = 0x03;
pub const BYE: u8 = 0x04;
pub const KEEPALIVE: u8 = 0x05;
pub const REFUSED: u8 = 0x06;

/// What a client's `HELLO` may carry, as `renetcode`'s token user data did.
pub const USER_DATA_BYTES: usize = 256;
/// A `renet` packet is at most a slice and its header; anything longer is not one.
const MAX_DATAGRAM_BYTES: usize = SLICE_SIZE + 128;
/// A reason is a sentence, not a payload.
const MAX_REASON_BYTES: usize = 200;
const HELLO_INTERVAL: Duration = Duration::from_millis(100);
const KEEPALIVE_INTERVAL: Duration = Duration::from_millis(250);
const TIMEOUT: Duration = Duration::from_secs(TIMEOUT_SECONDS as u64);

type Outgoing = Vec<(u64, Vec<u8>)>;

fn tagged(tag: u8, body: &[u8]) -> Vec<u8> {
    let mut wire = Vec::with_capacity(1 + body.len());
    wire.push(tag);
    wire.extend_from_slice(body);
    wire
}

fn reason_bytes(reason: &str) -> Vec<u8> {
    let mut end = reason.len().min(MAX_REASON_BYTES);
    while !reason.is_char_boundary(end) {
        end -= 1;
    }
    tagged(BYE, &reason.as_bytes()[..end])
}

fn read_reason(body: &[u8]) -> String {
    String::from_utf8_lossy(&body[..body.len().min(MAX_REASON_BYTES)]).into_owned()
}

struct Peer {
    budget: Bucket,
    consecutive_drops: u32,
    last_heard: Duration,
    since_sent: Duration,
    flush_deadline: Option<Duration>,
    kick_reason: Option<String>,
}

/// The listen server's side.
pub struct SteamHostCore {
    renet: RenetServer,
    peers: HashMap<u64, Peer>,
    /// None admits anyone: development only.
    allowed: Option<HashSet<u64>>,
    max_clients: usize,
    strangers: Bucket,
    now: Duration,
    outgoing: Outgoing,
    events: VecDeque<Event>,
    inbox_bytes: usize,
    counters: Counters,
    fatal: bool,
}

impl SteamHostCore {
    pub fn new(max_clients: usize, send_bytes_per_tick: u64, open: bool) -> Self {
        Self {
            renet: RenetServer::new(connection_config(send_bytes_per_tick)),
            peers: HashMap::new(),
            allowed: if open { None } else { Some(HashSet::new()) },
            max_clients,
            strangers: Bucket::new(UNAUTH_DATAGRAMS_PER_SECOND, UNAUTH_DATAGRAM_BURST),
            now: Duration::ZERO,
            outgoing: Vec::new(),
            events: VecDeque::new(),
            inbox_bytes: 0,
            counters: Counters::default(),
            fatal: false,
        }
    }

    pub fn allow(&mut self, id: u64) {
        if let Some(allowed) = &mut self.allowed {
            allowed.insert(id);
        }
    }

    /// Stop admitting `id`, and drop it if connected.
    pub fn revoke(&mut self, id: u64) {
        if let Some(allowed) = &mut self.allowed {
            allowed.remove(&id);
        }
        if self.peers.contains_key(&id) {
            self.kick(id, "removed from the room");
            self.drain_renet_events();
        }
    }

    fn admits(&self, id: u64) -> bool {
        self.allowed.as_ref().is_none_or(|allowed| allowed.contains(&id))
    }

    fn refuse(&mut self, source: u64, reason: &str) {
        if self.strangers.take() {
            let mut wire = reason_bytes(reason);
            wire[0] = REFUSED;
            self.outgoing.push((source, wire));
        } else {
            self.counters.unauth_over_budget += 1;
        }
    }

    fn on_datagram(&mut self, source: u64, datagram: &[u8]) {
        let Some((&tag, body)) = datagram.split_first() else {
            self.counters.implausible += 1;
            return;
        };
        if datagram.len() > MAX_DATAGRAM_BYTES {
            self.counters.implausible += 1;
            return;
        }
        if !self.peers.contains_key(&source) {
            if tag != HELLO {
                self.counters.wrong_source += 1;
                return;
            }
            if body.len() > USER_DATA_BYTES {
                self.counters.implausible += 1;
                return;
            }
            if !self.admits(source) {
                self.counters.wrong_source += 1;
                self.refuse(source, "not invited to this room");
                return;
            }
            if self.peers.len() >= self.max_clients {
                self.refuse(source, "ConnectionDenied");
                return;
            }
            self.peers.insert(
                source,
                Peer {
                    budget: Bucket::new(PEER_DATAGRAMS_PER_SECOND, PEER_DATAGRAM_BURST),
                    consecutive_drops: 0,
                    last_heard: self.now,
                    since_sent: Duration::ZERO,
                    flush_deadline: None,
                    kick_reason: None,
                },
            );
            self.renet.add_connection(source);
            self.events.push_back(Event::Connected { peer: source, user_data: body.to_vec() });
            self.outgoing.push((source, vec![WELCOME]));
            return;
        }

        let now = self.now;
        let Some(peer) = self.peers.get_mut(&source) else {
            return;
        };
        if !peer.budget.take() {
            self.counters.peer_over_budget += 1;
            peer.consecutive_drops += 1;
            if peer.consecutive_drops > PEER_DROPS_BEFORE_KICK {
                self.kick(source, "dropped: sending far over the rate limit");
            }
            return;
        }
        peer.consecutive_drops = peer.consecutive_drops.saturating_sub(1);
        peer.last_heard = now;
        match tag {
            HELLO => self.outgoing.push((source, vec![WELCOME])),
            PAYLOAD => {
                let outcome = catch_unwind(AssertUnwindSafe(|| {
                    let _ = self.renet.process_packet_from(body, source);
                }));
                if outcome.is_err() {
                    self.counters.panics += 1;
                    self.kick(source, "dropped: a packet from this peer broke the protocol");
                }
            }
            BYE => {
                if let Some(peer) = self.peers.get_mut(&source) {
                    peer.kick_reason.get_or_insert_with(|| "left".to_string());
                }
                self.renet.remove_connection(source);
            }
            KEEPALIVE => {}
            _ => self.counters.implausible += 1,
        }
    }

    /// Say goodbye and remove a peer now. Safe after a panic in that peer's
    /// connection, which is discarded rather than used again.
    fn kick(&mut self, peer: u64, reason: &str) {
        if let Some(state) = self.peers.get_mut(&peer) {
            let reason = state.kick_reason.get_or_insert_with(|| reason.to_string()).clone();
            let wire = reason_bytes(&reason);
            for _ in 0..DISCONNECT_REPEATS {
                self.outgoing.push((peer, wire.clone()));
            }
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
        self.strangers.refill(seconds);
        for peer in self.peers.values_mut() {
            peer.budget.refill(seconds);
            peer.since_sent += dt;
        }
        self.renet.update(dt);

        let now = self.now;
        let silent: Vec<u64> = self
            .peers
            .iter()
            .filter(|(_, peer)| now.saturating_sub(peer.last_heard) > TIMEOUT)
            .map(|(id, _)| *id)
            .collect();
        for peer in silent {
            self.kick(peer, "timed out");
        }
        let due: Vec<u64> = self
            .peers
            .iter()
            .filter(|(id, peer)| {
                peer.flush_deadline.is_some_and(|deadline| {
                    now >= deadline || (self.renet.is_connected(**id) && self.is_flushed(**id))
                })
            })
            .map(|(id, _)| *id)
            .collect();
        for peer in due {
            self.kick(peer, "disconnected by the host");
        }
        for peer in self.renet.disconnections_id() {
            self.kick(peer, "the connection failed");
        }
        self.drain_renet_events();
        self.pump_messages();
        self.send_packets();
    }

    fn drain_renet_events(&mut self) {
        while let Some(event) = self.renet.get_event() {
            if let ServerEvent::ClientDisconnected { client_id, reason } = event {
                let Some(state) = self.peers.remove(&client_id) else {
                    continue;
                };
                self.events.push_back(Event::Disconnected {
                    peer: client_id,
                    reason: state.kick_reason.unwrap_or_else(|| format!("{reason:?}")),
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
                let packets = self.renet.get_packets_to_send(peer).map_err(|_| ())?;
                let state = self.peers.get_mut(&peer).ok_or(())?;
                if !packets.is_empty() {
                    state.since_sent = Duration::ZERO;
                } else if state.since_sent >= KEEPALIVE_INTERVAL {
                    state.since_sent = Duration::ZERO;
                    self.outgoing.push((peer, vec![KEEPALIVE]));
                }
                for packet in packets {
                    self.outgoing.push((peer, tagged(PAYLOAD, &packet)));
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

#[derive(PartialEq)]
enum ClientState {
    Joining { since_hello: Duration },
    Connected,
    Gone,
}

/// A joining player's side.
pub struct SteamClientCore {
    renet: RenetClient,
    server: u64,
    user_data: Vec<u8>,
    state: ClientState,
    now: Duration,
    last_heard: Duration,
    since_sent: Duration,
    outgoing: Outgoing,
    events: VecDeque<Event>,
    inbox_bytes: usize,
    counters: Counters,
    fatal: bool,
}

impl SteamClientCore {
    pub fn new(server: u64, user_data: &[u8], send_bytes_per_tick: u64) -> Self {
        Self {
            renet: RenetClient::new(connection_config(send_bytes_per_tick)),
            server,
            user_data: user_data.to_vec(),
            state: ClientState::Joining { since_hello: HELLO_INTERVAL },
            now: Duration::ZERO,
            last_heard: Duration::ZERO,
            since_sent: Duration::ZERO,
            outgoing: Vec::new(),
            events: VecDeque::new(),
            inbox_bytes: 0,
            counters: Counters::default(),
            fatal: false,
        }
    }

    fn on_datagram(&mut self, source: u64, datagram: &[u8]) {
        if source != self.server {
            self.counters.wrong_source += 1;
            return;
        }
        let Some((&tag, body)) = datagram.split_first() else {
            self.counters.implausible += 1;
            return;
        };
        if datagram.len() > MAX_DATAGRAM_BYTES || self.state == ClientState::Gone {
            self.counters.implausible += 1;
            return;
        }
        match tag {
            WELCOME | PAYLOAD | KEEPALIVE => {
                self.last_heard = self.now;
                if matches!(self.state, ClientState::Joining { .. }) {
                    self.state = ClientState::Connected;
                    self.renet.set_connected();
                    self.events.push_back(Event::Connected { peer: 0, user_data: Vec::new() });
                }
                if tag == PAYLOAD {
                    let outcome = catch_unwind(AssertUnwindSafe(|| self.renet.process_packet(body)));
                    if outcome.is_err() {
                        self.counters.panics += 1;
                        self.fail("the connection failed internally", true);
                    }
                }
            }
            BYE | REFUSED => {
                // Hand out what arrived before the goodbye: a refusal sent on
                // CONTROL has to be readable.
                self.pump_messages();
                let reason = if tag == BYE { "DisconnectedByServer".to_string() } else { read_reason(body) };
                self.fail(&reason, false);
            }
            _ => self.counters.implausible += 1,
        }
    }

    fn fail(&mut self, reason: &str, tell_host: bool) {
        if self.state == ClientState::Gone {
            return;
        }
        if tell_host {
            let wire = reason_bytes(reason);
            for _ in 0..DISCONNECT_REPEATS {
                self.outgoing.push((self.server, wire.clone()));
            }
        }
        self.state = ClientState::Gone;
        self.renet.disconnect_due_to_transport();
        self.events.push_back(Event::Disconnected { peer: 0, reason: reason.to_string() });
    }

    fn tick(&mut self, dt: Duration) {
        self.now += dt;
        self.since_sent += dt;
        self.renet.update(dt);
        match &mut self.state {
            ClientState::Gone => {}
            ClientState::Joining { since_hello } => {
                *since_hello += dt;
                if self.now > TIMEOUT {
                    self.fail("ConnectionRequestTimedOut", false);
                } else if *since_hello >= HELLO_INTERVAL {
                    *since_hello = Duration::ZERO;
                    self.outgoing.push((self.server, tagged(HELLO, &self.user_data)));
                }
            }
            ClientState::Connected => {
                self.pump_messages();
                if self.now.saturating_sub(self.last_heard) > TIMEOUT {
                    self.fail("ConnectionTimedOut", false);
                    return;
                }
                if let Some(reason) = self.renet.disconnect_reason() {
                    self.fail(&format!("{reason:?}"), true);
                    return;
                }
                let packets = self.renet.get_packets_to_send();
                if !packets.is_empty() {
                    self.since_sent = Duration::ZERO;
                } else if self.since_sent >= KEEPALIVE_INTERVAL {
                    self.since_sent = Duration::ZERO;
                    self.outgoing.push((self.server, vec![KEEPALIVE]));
                }
                for packet in packets {
                    self.outgoing.push((self.server, tagged(PAYLOAD, &packet)));
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
                self.events.push_back(Event::Message { peer: 0, channel: spec.id, data: message.to_vec() });
            }
        }
    }

    fn send(&mut self, channel: u8, data: &[u8]) -> bool {
        let needed = bytes_to_check(channel, data.len(), |spec| spec.client_to_host_bytes);
        if self.state != ClientState::Connected || !self.renet.can_send_message(channel, needed) {
            return false;
        }
        self.renet.send_message(channel, data.to_vec());
        true
    }

    fn shutdown(&mut self) {
        self.fail("left", true);
    }
}

/// Either side, so the Python class is written once.
pub enum SteamCore {
    Host(Box<SteamHostCore>),
    Client(Box<SteamClientCore>),
}

impl SteamCore {
    fn parts(&mut self) -> (&mut VecDeque<Event>, &mut bool, &mut Counters, &mut usize) {
        match self {
            SteamCore::Host(core) => {
                (&mut core.events, &mut core.fatal, &mut core.counters, &mut core.inbox_bytes)
            }
            SteamCore::Client(core) => {
                (&mut core.events, &mut core.fatal, &mut core.counters, &mut core.inbox_bytes)
            }
        }
    }

    pub fn is_fatal(&self) -> bool {
        match self {
            SteamCore::Host(core) => core.fatal,
            SteamCore::Client(core) => core.fatal,
        }
    }

    pub fn on_datagram(&mut self, source: u64, datagram: &[u8]) {
        if self.is_fatal() {
            return;
        }
        match self {
            SteamCore::Host(core) => core.on_datagram(source, datagram),
            SteamCore::Client(core) => core.on_datagram(source, datagram),
        }
    }

    /// A panic here cannot be pinned on one peer, so the core stops, says so,
    /// and never raises into the frame loop.
    pub fn tick(&mut self, dt: Duration) {
        if self.is_fatal() {
            return;
        }
        let outcome = catch_unwind(AssertUnwindSafe(|| match self {
            SteamCore::Host(core) => core.tick(dt),
            SteamCore::Client(core) => core.tick(dt),
        }));
        if outcome.is_err() {
            let (events, fatal, counters, _) = self.parts();
            *fatal = true;
            counters.panics += 1;
            events.push_back(Event::Fatal { reason: "the network core failed internally".into() });
        }
    }

    pub fn allow(&mut self, id: u64) {
        if let SteamCore::Host(core) = self {
            core.allow(id);
        }
    }

    pub fn revoke(&mut self, id: u64) {
        if let SteamCore::Host(core) = self {
            core.revoke(id);
        }
    }

    pub fn send(&mut self, peer: u64, channel: u8, data: &[u8]) -> bool {
        if self.is_fatal() {
            return false;
        }
        match self {
            SteamCore::Host(core) => core.send(peer, channel, data),
            SteamCore::Client(core) => core.send(channel, data),
        }
    }

    pub fn disconnect(&mut self, peer: u64, flush: bool) {
        match self {
            SteamCore::Host(core) => core.disconnect(peer, flush),
            SteamCore::Client(core) => core.shutdown(),
        }
    }

    pub fn shutdown(&mut self) {
        match self {
            SteamCore::Host(core) => core.shutdown(),
            SteamCore::Client(core) => core.shutdown(),
        }
    }

    pub fn take_outgoing(&mut self) -> Outgoing {
        match self {
            SteamCore::Host(core) => std::mem::take(&mut core.outgoing),
            SteamCore::Client(core) => std::mem::take(&mut core.outgoing),
        }
    }

    pub fn take_events(&mut self) -> Vec<Event> {
        let (events, _, _, inbox) = self.parts();
        *inbox = 0;
        events.drain(..).collect()
    }

    pub fn counters(&self) -> Counters {
        match self {
            SteamCore::Host(core) => core.counters,
            SteamCore::Client(core) => core.counters,
        }
    }

    pub fn stats(&self, peer: u64) -> Option<LinkStats> {
        match self {
            SteamCore::Host(core) => core.stats(peer),
            SteamCore::Client(core) => {
                if core.state != ClientState::Connected {
                    return None;
                }
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
}
