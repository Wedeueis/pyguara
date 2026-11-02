"""Net Horde: the scenes.

`SideBySideScene` needs nothing but a window: host and client run in one process over a
simulated bad network, drawn next to each other. It's the quickest way to feel what
prediction does. The keys steer the client, on the right, and the host shows the same
character arriving later.

`HostScene` and `JoinScene` are the same thing over a real socket, for two windows.
"""

from __future__ import annotations

import secrets
from typing import Any

from games.net_horde.world import (
    BACKGROUND,
    HOST_SLOT,
    NO_MOVE,
    HordeSimulation,
    Move,
    draw_world,
    make_commands,
    make_schema,
    make_solids,
    make_spawners,
    velocity_of,
)
from pyguara.application.application import Application
from pyguara.common.components import Transform
from pyguara.common.types import Color, Vector2
from pyguara.ecs.entity import Entity
from pyguara.ecs.manager import EntityManager
from pyguara.events.dispatcher import EventDispatcher
from pyguara.graphics.protocols import IRenderer, UIRenderer
from pyguara.input.events import OnActionEvent
from pyguara.input.keys import DOWN, LEFT, RIGHT, UP, A, D, S, W
from pyguara.input.manager import InputManager
from pyguara.input.types import ActionType, InputDevice
from pyguara.kits.topdown_movement import TopDownPrediction
from pyguara.net import (
    ClientDriver,
    ClientSession,
    HostDriver,
    HostSession,
    Invite,
    Joined,
    Left,
    LinkConditions,
    PlayerJoined,
    PlayerLeft,
    PredictionClient,
    PredictionHost,
    Refused,
    ReplicationClient,
    ReplicationHost,
    SessionFailed,
    SimulatedNetwork,
    UdpTransport,
    Versions,
)
from pyguara.scene.base import Scene

VERSIONS = Versions("net_horde", "1")
TEXT = Color(230, 230, 230)
_LEFT = Vector2(10, 60)
_RIGHT = Vector2(510, 60)
_PRIORITY_HIGHEST = 0


_BINDINGS = (
    ("net_up", (W, UP)),
    ("net_down", (S, DOWN)),
    ("net_left", (A, LEFT)),
    ("net_right", (D, RIGHT)),
)


class HeldMove:
    """Which way the movement keys are pushing right now."""

    def __init__(self, scene: Scene) -> None:
        """Bind the keys.

        Args:
            scene: Has the container and dispatcher, and must have entered.
        """
        self._held: dict[str, bool] = {}
        inputs = scene.container.get(InputManager)
        for action, keys in _BINDINGS:
            inputs.register_action(action, ActionType.HOLD)
            for key in keys:
                inputs.bind_input(InputDevice.KEYBOARD, key, action)
        scene.event_dispatcher.subscribe(OnActionEvent, self._on_action)

    def _on_action(self, event: OnActionEvent) -> None:
        self._held[event.action_name] = event.value > 0

    def command(self) -> Move:
        """Return the current command."""
        held = self._held
        return Move(
            float(held.get("net_right", False)) - float(held.get("net_left", False)),
            float(held.get("net_down", False)) - float(held.get("net_up", False)),
        )


def _prediction_status(prediction: PredictionClient[Move]) -> str:
    """Say how prediction is doing, as numbers a person can watch while playing."""
    return (
        f"corrections {prediction.corrections}, "
        f"last {prediction.last_correction:.1f}, "
        f"largest {prediction.largest_correction:.1f}"
    )


class _PredictedPlayer:
    """Everything a client needs to steer its own character."""

    def __init__(self, session: ClientSession) -> None:
        self.prediction = PredictionClient(make_commands(), NO_MOVE, session.send)
        _, self._mover = make_solids()

    def on_controlled(self, entity: Entity | None) -> None:
        self.prediction.bind(
            None
            if entity is None
            else TopDownPrediction(entity, self._mover, velocity_of)
        )


class SideBySideScene(Scene):
    """A host and a client in one process, over a simulated bad network."""

    def __init__(
        self,
        event_dispatcher: EventDispatcher,
        latency: float = 0.05,
        loss: float = 0.02,
    ) -> None:
        """Create the scene.

        Args:
            event_dispatcher: The engine's dispatcher.
            latency: Seconds each way. 0.05 is a 100 ms round trip.
            loss: The share of packets lost.
        """
        super().__init__("SideBySideScene", event_dispatcher)
        self._latency = latency
        self._loss = loss
        self._keys: HeldMove | None = None
        self._player: _PredictedPlayer | None = None
        self._client_world = EntityManager()
        self._client_session: ClientSession | None = None
        self._host_session: HostSession | None = None
        self._network: SimulatedNetwork | None = None
        self._replication_client: ReplicationClient | None = None
        self._replication_host: ReplicationHost | None = None
        self._simulation: HordeSimulation | None = None
        self._my_slot = 0
        self._hooks: list[Any] = []

    def on_enter(self) -> None:
        """Start both sides."""
        self._network = SimulatedNetwork(
            seed=1,
            conditions=LinkConditions(
                latency=self._latency, jitter=self._latency / 5, loss=self._loss
            ),
        )
        key = secrets.token_bytes(32)
        host_transport = self._network.add_host(key)
        client_transport = self._network.add_client(
            key, self._network.address_of(host_transport), VERSIONS.encode()
        )
        self._host_session = HostSession(host_transport, VERSIONS)
        self._client_session = ClientSession(client_transport)
        prediction = PredictionHost(make_commands(), NO_MOVE, self._host_session.send)
        self._simulation = HordeSimulation(self.entity_manager, prediction)
        self._simulation.set_players([HOST_SLOT])
        self._keys = HeldMove(self)
        self._player = _PredictedPlayer(self._client_session)
        self._replication_host = ReplicationHost(
            self.entity_manager,
            make_schema(),
            self._host_session.send,
            digest_every=4,
        )
        self._replication_client = ReplicationClient(
            self._client_world,
            make_schema(),
            make_spawners(self._client_world),  # type: ignore[arg-type]
            predicted_components=(Transform,),
            on_controlled=self._player.on_controlled,
        )
        app = self.container.get(Application)

        def on_host_event(event: object) -> None:
            if isinstance(event, PlayerJoined):
                assert self._simulation is not None
                self._simulation.set_players([HOST_SLOT, event.slot])

        def on_client_event(event: object) -> None:
            if isinstance(event, Joined):
                self._my_slot = event.slot

        self._hooks = [
            _NetworkClock(self._network),
            HostDriver(
                app,
                self._host_session,
                self._replication_host,
                on_host_event,
                prediction,
            ),
            ClientDriver(
                self._client_session,
                self._replication_client,
                on_client_event,
                self._player.prediction,
            ),
        ]
        for hook in self._hooks:
            app.add_step_hook(hook)

    def on_exit(self) -> None:
        """Stop both sides."""
        app = self.container.get(Application)
        for hook in self._hooks:
            app.remove_step_hook(hook)

    def fixed_update(self, fixed_dt: float) -> None:
        """Run the host's simulation, and the client's own character."""
        assert self._simulation is not None
        assert self._keys is not None and self._player is not None
        tick = self.container.get(Application).fixed_tick
        self._simulation.fixed_update(tick)
        self._player.prediction.step(self._keys.command())

    def update(self, dt: float) -> None:
        """Nothing here: the hooks do the work."""

    def render(self, world_renderer: IRenderer, ui_renderer: UIRenderer) -> None:
        """Draw the host's view and the client's, next to each other."""
        client = self._replication_client
        assert client is not None and self._replication_host is not None
        world_renderer.clear(BACKGROUND)
        host_drawn = draw_world(world_renderer, self.entity_manager, _LEFT, HOST_SLOT)
        client_drawn = draw_world(
            world_renderer, self._client_world, _RIGHT, self._my_slot
        )
        ui_renderer.draw_text(
            f"HOST  {host_drawn} drawn", Vector2(_LEFT.x, 10), TEXT, 22
        )
        ui_renderer.draw_text(
            f"CLIENT  {client_drawn} drawn, slot {self._my_slot}",
            Vector2(_RIGHT.x, 10),
            TEXT,
            22,
        )
        assert self._player is not None
        round_trip = round(self._latency * 2000)
        ui_renderer.draw_text(
            f"WASD or arrows steer the right side. {round_trip} ms round trip, "
            f"{self._loss:.0%} loss.",
            Vector2(_LEFT.x, 36),
            TEXT,
            16,
        )
        ui_renderer.draw_text(
            f"{_prediction_status(self._player.prediction)}; "
            f"state hashes {client.digests_mismatched} wrong",
            Vector2(_RIGHT.x, 36),
            TEXT,
            16,
        )


class _NetworkClock:
    """Runs the simulated wire once a frame, ahead of both sides."""

    def __init__(self, network: SimulatedNetwork) -> None:
        self._network = network

    def before_fixed_updates(self, frame_time: float) -> None:
        self._network.advance(frame_time)

    def after_fixed_updates(self, frame_time: float) -> None:
        pass


class HostScene(Scene):
    """Host over a real socket. The invite to share is printed and shown on screen."""

    def __init__(
        self, event_dispatcher: EventDispatcher, port: int, public_host: str
    ) -> None:
        """Create the scene.

        Args:
            event_dispatcher: The engine's dispatcher.
            port: UDP port to listen on.
            public_host: The address to put in the invite.
        """
        super().__init__("HostScene", event_dispatcher)
        self._port = port
        self._public_host = public_host
        self._session: HostSession | None = None
        self._simulation: HordeSimulation | None = None
        self._slots: list[int] = []
        self._driver: HostDriver | None = None
        self._invite = ""
        self._keys: HeldMove | None = None
        self._prediction: PredictionHost[Move] | None = None

    def on_enter(self) -> None:
        """Start hosting."""
        key = secrets.token_bytes(32)
        transport = UdpTransport.host(key, self._port, max_clients=3)
        port = int(transport.local_address.rsplit(":", 1)[1])
        self._invite = str(Invite(self._public_host, port, key))
        print(f"Invite: {self._invite}", flush=True)
        self._session = HostSession(transport, VERSIONS)
        self._prediction = PredictionHost(make_commands(), NO_MOVE, self._session.send)
        self._simulation = HordeSimulation(self.entity_manager, self._prediction)
        self._simulation.set_players([HOST_SLOT])
        self._keys = HeldMove(self)
        replication = ReplicationHost(
            self.entity_manager, make_schema(), self._session.send, digest_every=4
        )
        app = self.container.get(Application)
        self._driver = HostDriver(
            app, self._session, replication, self._on_event, self._prediction
        )
        app.add_step_hook(self._driver)

    def _on_event(self, event: object) -> None:
        assert self._simulation is not None
        if isinstance(event, PlayerJoined):
            self._slots.append(event.slot)
        elif isinstance(event, PlayerLeft):
            self._slots = [
                slot
                for slot in self._slots
                if self._session is not None
                and slot in {self._session.slot_of(p) for p in self._session.players}
            ]
        self._simulation.set_players([HOST_SLOT, *self._slots])

    def on_exit(self) -> None:
        """Stop hosting."""
        assert self._driver is not None and self._session is not None
        self.container.get(Application).remove_step_hook(self._driver)
        self._session.close()

    def fixed_update(self, fixed_dt: float) -> None:
        """Run the simulation, with the host's own player on the keys."""
        assert self._simulation is not None and self._keys is not None
        tick = self.container.get(Application).fixed_tick
        self._simulation.fixed_update(tick, self._keys.command())

    def update(self, dt: float) -> None:
        """Nothing here: the hook does the work."""

    def render(self, world_renderer: IRenderer, ui_renderer: UIRenderer) -> None:
        """Draw the host's view, and how many have joined."""
        world_renderer.clear(BACKGROUND)
        drawn = draw_world(world_renderer, self.entity_manager, _LEFT, HOST_SLOT)
        ui_renderer.draw_text(
            f"HOST  {drawn} drawn, {len(self._slots)} joined",
            Vector2(_LEFT.x, 10),
            TEXT,
            22,
        )
        ui_renderer.draw_text(
            "The invite is in the terminal.", Vector2(_LEFT.x, 36), TEXT, 16
        )


class JoinScene(Scene):
    """Join a host over a real socket. Everything drawn here came over the network."""

    def __init__(self, event_dispatcher: EventDispatcher, invite: str) -> None:
        """Create the scene.

        Args:
            event_dispatcher: The engine's dispatcher.
            invite: The invite string from the host.
        """
        super().__init__("JoinScene", event_dispatcher)
        self._invite = Invite.parse(invite)
        self._session: ClientSession | None = None
        self._replication: ReplicationClient | None = None
        self._driver: ClientDriver | None = None
        self._transport: UdpTransport | None = None
        self._status = "Connecting..."
        self._slot = 0
        self._keys: HeldMove | None = None
        self._player: _PredictedPlayer | None = None

    def on_enter(self) -> None:
        """Start connecting."""
        self._transport = UdpTransport.client(
            self._invite.key,
            secrets.randbits(63),
            self._invite.host,
            self._invite.port,
            VERSIONS.encode(),
        )
        self._session = ClientSession(self._transport)
        self._keys = HeldMove(self)
        self._player = _PredictedPlayer(self._session)
        self._replication = ReplicationClient(
            self.entity_manager,
            make_schema(),
            make_spawners(self.entity_manager),  # type: ignore[arg-type]
            predicted_components=(Transform,),
            on_controlled=self._player.on_controlled,
        )
        self._driver = ClientDriver(
            self._session, self._replication, self._on_event, self._player.prediction
        )
        self.container.get(Application).add_step_hook(self._driver)

    def _on_event(self, event: object) -> None:
        if isinstance(event, Joined):
            self._slot = event.slot
            self._status = f"Joined as slot {event.slot}"
        elif isinstance(event, Refused | Left | SessionFailed):
            self._status = event.reason

    def on_exit(self) -> None:
        """Leave."""
        assert self._driver is not None and self._session is not None
        self.container.get(Application).remove_step_hook(self._driver)
        self._session.close()

    def fixed_update(self, fixed_dt: float) -> None:
        """Run this player's own character."""
        assert self._keys is not None and self._player is not None
        self._player.prediction.step(self._keys.command())

    def update(self, dt: float) -> None:
        """Nothing here: the hook does the work."""

    def render(self, world_renderer: IRenderer, ui_renderer: UIRenderer) -> None:
        """Draw what arrived, and how the link is doing."""
        assert self._replication is not None and self._transport is not None
        world_renderer.clear(BACKGROUND)
        drawn = draw_world(world_renderer, self.entity_manager, _LEFT, self._slot)
        ui_renderer.draw_text(
            f"CLIENT  {drawn} drawn. {self._status}", Vector2(_LEFT.x, 10), TEXT, 22
        )
        stats = self._transport.stats(0)
        rtt = 0.0 if stats is None else stats.rtt * 1000
        client = self._replication
        assert self._player is not None
        ui_renderer.draw_text(
            f"rtt {rtt:.0f} ms, {_prediction_status(self._player.prediction)}; "
            f"state hashes {client.digests_mismatched} wrong",
            Vector2(_LEFT.x, 36),
            TEXT,
            16,
        )
