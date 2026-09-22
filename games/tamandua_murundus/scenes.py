"""The clearing: one scene, one run, from dusk toward dawn.

D1 builds the place and the verbs -- move, lash, break a mound. The run
clock, the swarm, the day/night curve, the motes and the cards arrive in
D2 through D5, each hanging off what is here.
"""

from __future__ import annotations

import math

from games.tamandua_murundus import render
from games.tamandua_murundus.bootstrap import WINDOW_HEIGHT, WINDOW_WIDTH
from games.tamandua_murundus.cerrado_fx import CerradoFX
from games.tamandua_murundus.components import Murundu, Tamandua
from games.tamandua_murundus.events import (
    InsectKilled,
    MurunduBroken,
    TongueLashed,
)
from games.tamandua_murundus.motes import MOTE_VALUE, Motes
from games.tamandua_murundus.phases import (
    DAWN_HOLD_PHASE,
    PHASES,
    Phase,
    glow_for_intensity,
    phase_at,
)
from games.tamandua_murundus.swarm import (
    INSECT_LIT,
    STEERING_GROUPS,
    SWARM_CAP,
    Swarm,
    build_batch,
    insect_tint,
    make_insect_texture,
)
from games.tamandua_murundus.systems import MurunduSystem, TongueSystem
from games.tamandua_murundus.upgrade_ui import (
    CardElement,
    card_views,
    layout_cards,
)
from games.tamandua_murundus.upgrades import Card, build_pool
from pyguara.ai.flocking_system import FlockingAgent, FlockingSystem
from pyguara.common.components import Transform
from pyguara.common.random import RandomStream
from pyguara.common.spatial import SpatialHash
from pyguara.common.types import Color, Rect, Vector2
from pyguara.events.dispatcher import EventDispatcher
from pyguara.graphics.components.camera import Camera2D
from pyguara.graphics.protocols import IRenderer, TextureFactory, UIRenderer
from pyguara.input.events import OnActionEvent
from pyguara.input.keys import (
    DOWN,
    ESCAPE,
    LEFT,
    RETURN,
    RIGHT,
    SPACE,
    UP,
    A,
    D,
    S,
    W,
)
from pyguara.input.manager import InputManager
from pyguara.input.types import ActionType, InputDevice
from pyguara.kits.progression import (
    Experience,
    Geometric,
    LeveledUp,
    Magnet,
    MagnetSystem,
    PickupCollected,
    UpgradeRecord,
    grant_experience,
    offer,
    take,
)
from pyguara.scene.base import Scene
from pyguara.spatial.system import SpatialIndexSystem
from pyguara.ui.manager import UIManager

# The clearing, inset from the window so the vignette has something to
# darken that is not gameplay.
ARENA = Rect(40, 96, WINDOW_WIDTH - 80, WINDOW_HEIGHT - 152)

# Where the mounds stand. Fixed rather than scattered: they are the
# clearing's landmarks, and a player who learns where they are is the
# player the design wants.
MURUNDU_POSITIONS = [
    Vector2(ARENA.left + 140, ARENA.top + 120),
    Vector2(ARENA.right - 150, ARENA.top + 96),
    Vector2(ARENA.left + 108, ARENA.bottom - 130),
    Vector2(ARENA.right - 128, ARENA.bottom - 108),
    Vector2(ARENA.x + ARENA.width // 2, ARENA.top + 62),
]

TONGUE_DAMAGE_TO_MOUND = 1.0

# The anteater's drawn body radius, used to keep its silhouette inside
# the clearing rather than clamping its centre to the edge.
BODY_RADIUS = 16.0

# The level curve. Geometric rather than linear, so the run slows without
# stopping -- and measured, not guessed.
#
# A simulated run with the player orbiting the clearing (an engaged
# player, not an idle one) kills ~242 insects over the 240-second night
# and collects **~236** of them -- the handful it does not are motes that
# fell outside the magnet's reach and were never returned to, which is
# the gap `MAGNET_RADIUS` exists to create. Against that yield:
#
#     base  growth   levels reached
#     14.0    1.28        8
#     10.0    1.24        9
#      8.0    1.20       11
#      6.0    1.18       13
#
# Eight is the fit, because D5's card table is six to eight upgrades: a
# run should offer about as many picks as there are distinct things to
# pick. An idle player reaches level 2 on the same curve, which is the
# spread that makes the levels feel earned.
#
# Note what the same simulation says about the swarm: 242 kills still
# leaves 638 of 700 alive. The player cannot clear the clearing, which is
# the point of a density climax.
LEVEL_CURVE = Geometric(base=14.0, growth=1.28)

# What that simulated run yielded, kept so the test below pins the curve
# against a measurement rather than against itself.
MEASURED_RUN_YIELD = 236.0

# The magnet's reach, deliberately *shorter* than the tongue's 150.
#
# Matching them made the magnet invisible: every kill landed inside the
# pull radius, so every mote was collected on the frame it dropped and
# the signature mechanic of the genre never visibly happened. Shorter,
# the far half of the kills leave motes on the ground that the anteater
# has to drift toward -- which is both what makes the magnet legible and
# what gives the player a reason to keep moving through the swarm rather
# than standing in it.
MAGNET_RADIUS = 108.0


LASH_ANIMATION = 0.16


class ClearingScene(Scene):
    """One run in the clearing."""

    def __init__(self, event_dispatcher: EventDispatcher) -> None:
        """Initialize the scene."""
        super().__init__("ClearingScene", event_dispatcher)
        self.fx: CerradoFX | None = None
        self._rng = RandomStream(seed=11)
        self._camera = Camera2D(WINDOW_WIDTH, WINDOW_HEIGHT)
        # Centred on the window, so `screen_offset` comes out zero and the
        # scene's world coordinates *are* screen coordinates. A camera
        # left at the origin displaces the whole light map by half a
        # screen while the geometry stays put -- the lights end up in the
        # bottom-right corner and nothing else moves.
        self._camera.position = Vector2(WINDOW_WIDTH / 2, WINDOW_HEIGHT / 2)
        self._player_id: str | None = None
        self._lash = 0.0
        self._kills = 0
        self._mounds_broken = 0
        self._move = Vector2.zero()
        self._held_up = False
        self._held_down = False
        self._held_left = False
        self._held_right = False

        self._murundus: MurunduSystem | None = None
        self._tongue: TongueSystem | None = None
        self._spatial: SpatialIndexSystem | None = None
        self._flocking: FlockingSystem | None = None
        self._swarm: Swarm | None = None
        self._insect_texture = None
        self._elapsed = 0.0
        self._dawn = False
        self._motes: Motes | None = None
        self._magnets: MagnetSystem | None = None
        self._levels = 0

        # The 1-of-3 pick. `_cards` being non-empty *is* the paused state:
        # one flag would be a second source of truth for the same thing.
        self._pool: list[Card] = []
        self._record = UpgradeRecord()
        self._cards: list[CardElement] = []

    # ---- setup -----------------------------------------------------

    def on_enter(self) -> None:
        """Build the clearing, the mounds and the anteater."""
        self.fx = CerradoFX(
            self.container,
            self.entity_manager,
            width=WINDOW_WIDTH,
            height=WINDOW_HEIGHT,
            arena=ARENA,
            seed=11,
        )

        dispatcher = self.event_dispatcher
        index = self.container.get(SpatialHash)

        self._swarm = Swarm(self.entity_manager, ARENA, self._rng)
        self._insect_texture = make_insect_texture(self.container.get(TextureFactory))

        self._spatial = SpatialIndexSystem(self.entity_manager, index, dispatcher)
        self._murundus = MurunduSystem(self.entity_manager, dispatcher, self._swarm)
        self._tongue = TongueSystem(self.entity_manager, dispatcher, index, self._swarm)

        # Steering staggered across three ticks. Every insect still
        # integrates every frame -- only the decision rate drops -- which
        # is the difference between 1000 agents costing 16.0 ms and
        # 7.4 ms (docs/guides/performance.md).
        self._flocking = FlockingSystem(
            self.entity_manager, cell_size=48.0, groups=STEERING_GROUPS
        )

        self._motes = Motes(self.entity_manager, ARENA, self._rng)
        self._magnets = MagnetSystem(self.entity_manager, dispatcher, index)

        dispatcher.subscribe(PickupCollected, self._on_mote_collected)
        dispatcher.subscribe(LeveledUp, self._on_level_up)
        dispatcher.subscribe(InsectKilled, self._on_insect_killed)
        dispatcher.subscribe(MurunduBroken, self._on_murundu_broken)
        dispatcher.subscribe(TongueLashed, self._on_tongue_lashed)

        self._pool = build_pool(self.entity_manager)

        self._create_player()
        self._create_murundus()
        self._setup_input()

    def _setup_input(self) -> None:
        """Bind movement.

        Actions rather than a per-frame key poll, because that is what
        `InputManager` offers and what the replay layer records -- a
        scene that read the keyboard directly would not replay.
        """
        inputs = self.container.get(InputManager)
        for action in ("move_up", "move_down", "move_left", "move_right"):
            inputs.register_action(action, ActionType.HOLD)
        inputs.register_action("back", ActionType.PRESS)
        inputs.register_action("confirm", ActionType.PRESS)

        for key, action in (
            (W, "move_up"),
            (UP, "move_up"),
            (S, "move_down"),
            (DOWN, "move_down"),
            (A, "move_left"),
            (LEFT, "move_left"),
            (D, "move_right"),
            (RIGHT, "move_right"),
            (ESCAPE, "back"),
            (RETURN, "confirm"),
            (SPACE, "confirm"),
        ):
            inputs.bind_input(InputDevice.KEYBOARD, key, action)

        self.event_dispatcher.subscribe(OnActionEvent, self._on_action)

    def _on_action(self, event: OnActionEvent) -> None:
        """Track which directions are held, and take a card on confirm."""
        held = event.value > 0
        if event.action_name == "confirm":
            if held and self.picking:
                self._take_card()
            return
        if event.action_name == "move_up":
            self._held_up = held
        elif event.action_name == "move_down":
            self._held_down = held
        elif event.action_name == "move_left":
            self._held_left = held
        elif event.action_name == "move_right":
            self._held_right = held

    def _create_player(self) -> None:
        """Place the anteater in the middle of the clearing."""
        entity = self.entity_manager.create_entity("tamandua")
        entity.add_component(
            Transform(
                position=Vector2(ARENA.x + ARENA.width / 2, ARENA.y + ARENA.height / 2)
            )
        )
        entity.add_component(Tamandua())
        entity.add_component(Experience())
        entity.add_component(Magnet(radius=MAGNET_RADIUS))
        self._player_id = entity.id

    def _create_murundus(self) -> None:
        """Stand the mounds up, each with its own pulsing glow.

        The pulse is a per-mound `sin()` phase resolved straight into the
        light tuple `_lights()` hands the renderer each frame, not a
        `LightSource.flicker_enabled` component -- these lights are
        ephemeral and aggregated for the same reason the swarm's are (see
        `_lights()`), so there is no per-entity `LightSource` to flag.
        """
        for offset, position in enumerate(MURUNDU_POSITIONS):
            entity = self.entity_manager.create_entity()
            entity.add_component(Transform(position=position))
            entity.add_component(
                Murundu(
                    feed_timer=offset * 0.28,
                    glow_phase=offset * 1.31,
                )
            )

    def on_exit(self) -> None:
        """Drop the UI this scene put up.

        The entities, the lights and the spatial index go with the
        scene's own world; the `UIManager` is a container singleton and
        outlives it.
        """

        self.container.get(UIManager).clear()

    # ---- events ----------------------------------------------------

    def _on_mote_collected(self, event: PickupCollected) -> None:
        """Turn a collected mote into experience.

        The kit dispatches the payload and stops; deciding that a mote is
        worth experience is the game's, which is why `Attracted.payload`
        is opaque to `kits/progression` in the first place.
        """
        if self._motes is None:
            return
        self._motes.collect(event.pickup)

        player = self._player()
        if player is None:
            return
        grant_experience(
            self.event_dispatcher,
            player.id,
            player.get_component(Experience),
            LEVEL_CURVE,
            float(event.payload),
        )

    def _on_level_up(self, event: LeveledUp) -> None:
        """Freeze the run and offer a pick.

        The kit counts levels into `pending_levels` and never spends them
        -- it has no idea what a level is worth here. Spending one is
        this method and `_take_card()`: a level buys exactly one upgrade,
        and a grant that crossed several levels queues several picks
        rather than collapsing them.
        """
        self._levels = event.level
        if self.fx is None:
            return
        self.fx.flash.trigger(Color(150, 255, 210, 40), 0.2)
        if not self._cards:
            self._open_pick()

    # ---- the 1-of-3 pick -------------------------------------------

    @property
    def picking(self) -> bool:
        """Whether the run is paused on an upgrade pick."""
        return bool(self._cards)

    def _open_pick(self) -> None:
        """Offer up to three eligible upgrades and hand focus to them.

        Drawn from `kits/progression`'s `offer()`, which filters by
        eligibility and samples without replacement -- this scene
        contributes the content and the layout, and no weighting logic of
        its own.
        """
        drawn = offer(self._rng, [card.upgrade for card in self._pool], self._record)
        by_key = {card.upgrade.key: card for card in self._pool}
        cards = [by_key[upgrade.key] for upgrade in drawn]
        if not cards:
            # The pool is spent. Bank the level rather than freezing the
            # run on an empty menu.
            self._spend_level()
            return

        ui_manager = self.container.get(UIManager)
        ui_manager.clear()
        self._cards = [
            CardElement(card, position)
            for card, position in zip(
                cards, layout_cards(cards, WINDOW_WIDTH, WINDOW_HEIGHT), strict=True
            )
        ]
        for element in self._cards:
            ui_manager.add_element(element)
        # Focus the first card, so the ring starts somewhere rather than
        # needing a Tab to enter it.
        ui_manager.set_focus(self._cards[0])

    def _take_card(self) -> None:
        """Take the focused card, close the pick, and resume the run."""
        ui_manager = self.container.get(UIManager)
        focused = ui_manager.focused_element
        chosen = next((element for element in self._cards if element is focused), None)
        if chosen is None:
            return

        take(self._record, chosen.card.upgrade, self._player_id or "")
        if self.fx is not None:
            self.fx.popup(
                chosen.card.title,
                Vector2(WINDOW_WIDTH / 2 - 60, WINDOW_HEIGHT / 2 - 40),
                INSECT_LIT,
                size=22,
            )
        self._close_pick()
        self._spend_level()

        # Several levels can be owed at once -- a boss-sized grant, or a
        # mote collected while one pick was already open. Offer the next
        # immediately rather than making the player earn it again.
        player = self._player()
        if player is not None and player.get_component(Experience).pending_levels > 0:
            self._open_pick()

    def _close_pick(self) -> None:
        """Take the cards down and give focus back to nothing."""
        ui_manager = self.container.get(UIManager)
        ui_manager.set_focus(None)
        ui_manager.clear()
        self._cards = []

    def _spend_level(self) -> None:
        """Decrement what the kit banked. The kit never does this itself."""
        player = self._player()
        if player is None:
            return
        experience = player.get_component(Experience)
        experience.pending_levels = max(0, experience.pending_levels - 1)

    def _on_insect_killed(self, event: InsectKilled) -> None:
        """Spark, flare, count the kill, and leave what it was worth."""
        if self._motes is not None:
            self._motes.drop(event.position, MOTE_VALUE)
        self._kills += 1
        if self.fx is not None:
            self.fx.kill(event.position, insect_tint(self._glow()))

    def _on_murundu_broken(self, event: MurunduBroken) -> None:
        """The run's biggest beat: shake, flash, hit-stop, a word."""
        self._mounds_broken += 1
        if self.fx is not None:
            self.fx.mound_broken(event.position)
            self.fx.popup(
                "MURUNDU QUEBRADO",
                Vector2(event.position.x, event.position.y - 44),
                render.MURUNDU_GLOW,
                size=18,
            )

    def _on_tongue_lashed(self, event: TongueLashed) -> None:
        """Start the lash animation."""
        self._lash = LASH_ANIMATION

    # ---- frame -----------------------------------------------------

    def update(self, dt: float) -> None:
        """Read input, step the simulation, advance the presentation."""
        if self.fx is None:
            return

        self._read_input()
        self._advance_presentation(dt)

        # A pick stops the world. Not a hit-stop -- that is a timed beat
        # and this lasts as long as the player takes -- so it gates the
        # step directly rather than going through `gameplay_dt`, which
        # still runs so an in-flight hit-stop keeps decaying underneath.
        gameplay_dt = self.fx.gameplay_dt(dt)
        if gameplay_dt > 0.0 and not self.picking:
            self._step_simulation(gameplay_dt)

    def _read_input(self) -> None:
        """Fold the held directions into a movement vector.

        Zero while a pick is open: the arrow keys belong to the focus ring
        then, and an anteater drifting behind the cards would be the
        player steering something they cannot see.
        """
        if self.picking:
            self._move = Vector2.zero()
            return
        self._move = Vector2(
            float(self._held_right) - float(self._held_left),
            float(self._held_down) - float(self._held_up),
        )

    def _advance_presentation(self, dt: float) -> None:
        """Advance everything that keeps running through a hit-stop."""
        if self.fx is None:
            return
        self._elapsed += dt
        self._lash = max(0.0, self._lash - dt)
        self.fx.update(dt, self._camera)

        # One loop of the cycle is one run. Stopping it just before the
        # wrap is what makes this a run with an end instead of an endless
        # clearing -- and it has to be *before*: the cycle is a ring, so a
        # phase allowed to reach 1.0 is back at 0, which is dusk. The run
        # would flash from first light to nightfall and hold there.
        if self.fx.cycle.phase >= DAWN_HOLD_PHASE and self.fx.cycle.playing:
            self.fx.cycle.playing = False
            self._dawn = True
            self.fx.popup(
                "AMANHECEU",
                Vector2(WINDOW_WIDTH / 2 - 50, WINDOW_HEIGHT / 2),
                render.MURUNDU_GLOW,
                size=28,
            )

    def _step_simulation(self, dt: float) -> None:
        """Move the anteater, then run the clearing's systems."""
        if self.fx is None:
            return

        player = self._player()
        if player is not None:
            hunter = player.get_component(Tamandua)
            transform = player.get_component(Transform)

            magnitude = self._move.magnitude
            if magnitude > 0.0:
                step = hunter.speed * dt / magnitude
                # Inset by the body radius, so the anteater stops with
                # its whole silhouette inside the clearing rather than
                # half of it over the HUD.
                transform.position = Vector2(
                    min(
                        max(
                            transform.position.x + self._move.x * step,
                            ARENA.left + BODY_RADIUS,
                        ),
                        ARENA.right - BODY_RADIUS,
                    ),
                    min(
                        max(
                            transform.position.y + self._move.y * step,
                            ARENA.top + BODY_RADIUS,
                        ),
                        ARENA.bottom - BODY_RADIUS,
                    ),
                )
                hunter.facing = math.atan2(self._move.y, self._move.x)

            self.fx.aim_snout(transform.position, hunter.facing)
            self._try_break_mound(transform.position, hunter)

        if self._spatial is not None:
            self._spatial.update(dt)
        if self._murundus is not None:
            # The difficulty curve, straight off the phase table. Dawn's
            # phase asks for zero, which ends the run's pressure without a
            # separate "stop spawning" flag.
            self._murundus.release_per_feed = self._phase().release_per_feed
            self._murundus.update(dt)
        if self._flocking is not None:
            self._flocking.update(dt)
        self._keep_swarm_in_the_clearing()
        if self._tongue is not None:
            self._tongue.update(dt)
        if self._swarm is not None:
            self._swarm.update_motes(dt)
        if self._motes is not None:
            self._motes.update(dt)
        # After the motes settle, so a mote dropped this frame is already
        # where it belongs before the magnet decides whether to pull it.
        if self._magnets is not None:
            self._magnets.update(dt)

    def _keep_swarm_in_the_clearing(self) -> None:
        """Turn any insect that has left the clearing back into it.

        `FlockingSystem` has no notion of bounds -- cohesion holds the
        flock together but nothing holds the flock anywhere, so a swarm
        given one direction long enough leaves the screen and the demo
        becomes an empty clearing. Reflecting the velocity at the edge
        costs a comparison per insect and keeps the density where the
        player can see it.
        """
        if self._swarm is None:
            return

        for entity in self._swarm.active_insects():
            transform = entity.get_component(Transform)
            agent = entity.get_component(FlockingAgent)
            position, velocity = transform.position, agent.velocity

            if position.x < ARENA.left or position.x > ARENA.right:
                agent.velocity = Vector2(-velocity.x, velocity.y)
                transform.position = Vector2(
                    min(max(position.x, ARENA.left), ARENA.right), position.y
                )
            if position.y < ARENA.top or position.y > ARENA.bottom:
                agent.velocity = Vector2(agent.velocity.x, -velocity.y)
                transform.position = Vector2(
                    transform.position.x,
                    min(max(position.y, ARENA.top), ARENA.bottom),
                )

    def _try_break_mound(self, position: Vector2, hunter: Tamandua) -> None:
        """Chew the mound the anteater is standing against, if any."""
        if self._murundus is None or hunter.tongue_cooldown > 0.0:
            return

        for entity in self.entity_manager.get_entities_with(Murundu, Transform):
            mound = entity.get_component(Murundu)
            if mound.broken:
                continue
            offset = entity.get_component(Transform).position - position
            if offset.magnitude > mound.radius + 22.0:
                continue

            hunter.tongue_cooldown = hunter.tongue_interval
            self._lash = LASH_ANIMATION
            if not self._murundus.damage(entity.id, TONGUE_DAMAGE_TO_MOUND):
                self.fx and self.fx.sparks.burst(
                    entity.get_component(Transform).position,
                    render.MURUNDU_RIM,
                    count=5,
                )
            return

    # ---- render ----------------------------------------------------

    def render(self, world_renderer: IRenderer, ui_renderer: UIRenderer) -> None:
        """Draw the clearing, then run the lighting/post pipeline.

        Everything goes through `world_renderer`, including the HUD, so it
        all passes through the light map and the bloom -- a HUD drawn on
        the UI renderer after the final blit would be the only unlit thing
        on screen. The `end_frame()` calls are the flush discipline: the
        GL backend buckets shapes by type and flushes all of them at once,
        so anything whose layering matters needs its own batch.
        """
        if self.fx is None:
            return

        offset = self.fx.offset
        self.fx.draw_ground(world_renderer)

        for view in self._murundu_views():
            render.draw_murundu(world_renderer, view)

        self._draw_swarm(world_renderer)
        self._draw_motes(world_renderer)

        player = self._player()
        if player is not None:
            hunter = player.get_component(Tamandua)
            position = player.get_component(Transform).position
            shaken = Vector2(position.x + offset.x, position.y + offset.y)
            render.draw_tongue_arc(
                world_renderer,
                shaken,
                hunter.facing,
                hunter.tongue_range,
                hunter.tongue_arc,
                1.0 if hunter.tongue_cooldown <= 0.0 else 0.0,
            )
            render.draw_tamandua(
                world_renderer,
                shaken,
                hunter.facing,
                self._lash / LASH_ANIMATION if self._lash > 0.0 else 0.0,
            )

        self.fx.sparks.render(world_renderer, offset)
        world_renderer.end_frame()

        # The mound-break flash is a full-screen rect, and rects flush
        # before circles and lines -- so it needs a batch of its own to
        # land over the clearing rather than under it.
        self.fx.flash.render(world_renderer, Rect(0, 0, WINDOW_WIDTH, WINDOW_HEIGHT))
        world_renderer.end_frame()

        # Popups stay in the world: a number floating off a mound belongs
        # in the clearing, lit like everything else in it.
        self.fx.popups.render(world_renderer, self._camera)

        self.fx.set_dynamic_lights(self._lights())
        self.fx.configure_pipeline(self._camera)

        # The HUD does not go in the world. D1 drew it there, so it picked
        # up the light map -- which read well at a fixed dusk, but the
        # clearing now spends the middle of the run at an ambient of 0.11,
        # and a HUD multiplied by that is unreadable exactly when the run
        # is busiest. Drawn onto the finished frame instead: unlit,
        # unbloomed, and still inside what `agent_view` can capture.
        self.fx.bind_finished_frame()
        self._draw_hud(world_renderer)
        self._draw_cards(world_renderer)
        world_renderer.end_frame()

    def _murundu_views(self) -> list[render.MurunduView]:
        """One view per mound, with its pulse resolved."""
        views = []
        for entity in self.entity_manager.get_entities_with(Murundu, Transform):
            mound = entity.get_component(Murundu)
            views.append(
                render.MurunduView(
                    position=entity.get_component(Transform).position,
                    radius=mound.radius,
                    health_fraction=mound.health / mound.max_health,
                    broken=mound.broken,
                    glow=0.5 + 0.5 * math.sin(mound.glow_phase * 3.1),
                )
            )
        return views

    def _draw_motes(self, renderer: IRenderer) -> None:
        """Draw the motes, in their own instanced batch.

        A second batch rather than a row in the swarm's: they share the
        texture but not the tint, and folding them in would mean the
        swarm's `build_batch()` taking a second colour and a second size
        for a layer that is not the swarm.
        """
        if self._motes is None or self._insect_texture is None:
            return
        if self._motes.active_count == 0:
            return
        renderer.render_batch(
            self._motes.build_batch(self._insect_texture, self._glow())
        )

    def _phase(self) -> Phase:
        """Which stretch of the night the run is in."""
        if self.fx is None:
            return PHASES[0]
        return phase_at(self.fx.cycle.phase)

    def _draw_swarm(self, renderer: IRenderer) -> None:
        """Draw both swarm layers as one instanced, tinted batch.

        This is the demo's thesis in four lines: one texture, N colours,
        one `render_batch()`. The batch itself is built by the pure
        `build_batch()`, which is what makes the tint values testable
        without a GPU -- see `tests/visual/`.
        """
        if self._swarm is None or self._insect_texture is None:
            return
        renderer.render_batch(
            build_batch(self._swarm.batch_input(self._insect_texture, self._glow()))
        )

    def _glow(self) -> float:
        """How bioluminescent the swarm is right now, 0..1.

        Read off the ambient light the cycle is writing, so the swarm
        lights up exactly as the clearing goes dark -- the same number
        from the other end, rather than a second curve running alongside
        the first and free to drift from it.
        """
        if self.fx is None:
            return 0.0
        return glow_for_intensity(self.fx.ambient_intensity)

    def _lights(self) -> list[tuple[Vector2, Color, float, float]]:
        """This frame's dynamic lights: one per intact mound.

        Note what is *not* here: the insects. Each one as a `LightSource`
        would make `LightingSystem`'s per-entity collection scale with the
        swarm, and D2's crowd measurement would quietly become a lighting
        measurement (GDD §3.2).
        """
        lights: list[tuple[Vector2, Color, float, float]] = []

        # The flock's own glow: a handful of aggregate lights at cell
        # centroids, not one per insect. This is what lifts the swarm past
        # the bloom threshold -- the composite multiplies the world by the
        # light map, so a tinted sprite under a sub-1.0 ambient comes out
        # darker than it was drawn and never blooms unaided.
        glow = self._glow()
        if self._swarm is not None and glow > 0.05:
            tint = insect_tint(glow)
            for centre, weight in self._swarm.centroids():
                lights.append((centre, tint, 150.0 + 90.0 * weight, glow * weight))

        for entity in self.entity_manager.get_entities_with(Murundu, Transform):
            mound = entity.get_component(Murundu)
            if mound.broken:
                continue
            pulse = 0.5 + 0.5 * math.sin(mound.glow_phase * 3.1)
            lights.append(
                (
                    entity.get_component(Transform).position,
                    render.MURUNDU_GLOW,
                    150.0,
                    0.34 + pulse * 0.2,
                )
            )
        return lights

    def _draw_cards(self, renderer: IRenderer) -> None:
        """Draw the 1-of-3 pick over the frozen clearing.

        Drawn here rather than by the card widgets themselves because
        `UIRenderer` composites after the final blit, where no capture can
        reach it (#162). The elements still own layout and focus -- this
        only reads their rects and asks the manager which one is focused.
        """
        if not self._cards:
            return

        ui_manager = self.container.get(UIManager)
        views = card_views(self._cards, ui_manager.focused_element)

        # Every box first, then a flush, then every label. The GL backend
        # buckets shapes by type and flushes them at `end_frame()`, while
        # `draw_text` draws immediately -- so text written before the
        # flush ends up *under* the rectangles, however late it was
        # issued. The first version of this drew each card's box and label
        # together and produced unreadable cards.
        renderer.draw_rect(
            Rect(0, 0, WINDOW_WIDTH, WINDOW_HEIGHT), Color(6, 9, 12, 168)
        )
        for view in views:
            renderer.draw_rect(view.bounds, Color(16, 24, 22, 240))
            renderer.draw_rect(
                view.bounds,
                INSECT_LIT if view.focused else render.HUD_DIM,
                width=3 if view.focused else 1,
            )
        renderer.end_frame()

        renderer.draw_text(
            "ESCOLHA UMA DÁDIVA DO CERRADO",
            Vector2(WINDOW_WIDTH / 2 - 175, WINDOW_HEIGHT / 2 - 128),
            INSECT_LIT,
            20,
        )
        for view in views:
            bounds = view.bounds
            renderer.draw_text(
                view.title,
                Vector2(bounds.x + 16, bounds.y + 22),
                INSECT_LIT if view.focused else render.HUD_TEXT,
                18,
            )
            renderer.draw_text(
                view.blurb,
                Vector2(bounds.x + 16, bounds.y + 60),
                render.HUD_TEXT if view.focused else render.HUD_DIM,
                12,
            )
            taken = self._record.taken.get(view.card_key, 0)
            if taken:
                renderer.draw_text(
                    f"x{taken}",
                    Vector2(bounds.x + bounds.width - 44, bounds.y + 22),
                    render.HUD_DIM,
                    14,
                )

        # Plain words, not arrow glyphs: the default font has no arrows and
        # renders them as boxes.
        renderer.draw_text(
            "[A/D ou TAB] escolher   ·   [ENTER] aceitar",
            Vector2(WINDOW_WIDTH / 2 - 145, WINDOW_HEIGHT / 2 + 104),
            render.HUD_TEXT,
            13,
        )

    def _draw_hud(self, renderer: IRenderer) -> None:
        """Counters and the control hint."""
        renderer.draw_text(
            "TAMANDUÁ: O GUARDIÃO DOS MURUNDUS", Vector2(28, 22), render.HUD_TEXT, 20
        )

        # The clock, as a name rather than a number: "NOITE FECHADA" says
        # what the player is about to be in the middle of, where "2:47"
        # would not.
        phase = self._phase()
        renderer.draw_text(
            phase.name,
            Vector2(WINDOW_WIDTH - 250, 22),
            insect_tint(self._glow()),
            20,
        )
        renderer.draw_text(
            "o guardião segurou a clareira até o primeiro sol"
            if self._dawn
            else "[WASD] mover   ·   a língua ataca sozinha   ·   "
            "encoste num murundu para quebrá-lo",
            Vector2(28, 50),
            render.HUD_DIM,
            13,
        )

        intact = sum(
            1
            for entity in self.entity_manager.get_entities_with(Murundu)
            if not entity.get_component(Murundu).broken
        )
        renderer.draw_text(
            f"MURUNDUS {intact}/{len(MURUNDU_POSITIONS)}",
            Vector2(268, WINDOW_HEIGHT - 44),
            render.MURUNDU_GLOW,
            16,
        )
        renderer.draw_text(
            f"INSETOS COMIDOS {self._kills}",
            Vector2(WINDOW_WIDTH - 250, WINDOW_HEIGHT - 44),
            INSECT_LIT,
            16,
        )

        # The count the demo is actually about. `SWARM_CAP` is a measured
        # ceiling (see `swarm.py`), so showing the live number against it
        # is the difference between a claim and a readout.
        player = self._player()
        if player is not None:
            experience = player.get_component(Experience)
            cost = LEVEL_CURVE.cost_for(experience.level)
            renderer.draw_text(
                f"NÍVEL {experience.level}   {int(experience.current)}/{int(cost)}",
                Vector2(28, WINDOW_HEIGHT - 68),
                INSECT_LIT,
                16,
            )
            # The bar under it: a level-up is the run's only reward, so
            # how close one is has to be readable at a glance rather than
            # by parsing two numbers.
            width = 220
            renderer.draw_rect(Rect(28, WINDOW_HEIGHT - 46, width, 4), render.HUD_DIM)
            filled = int(width * max(0.0, min(1.0, experience.current / cost)))
            if filled > 0:
                renderer.draw_rect(Rect(28, WINDOW_HEIGHT - 46, filled, 4), INSECT_LIT)

        if self._swarm is not None:
            renderer.draw_text(
                f"ENXAME {self._swarm.active_count}/{SWARM_CAP}",
                Vector2(WINDOW_WIDTH // 2 - 70, WINDOW_HEIGHT - 44),
                insect_tint(self._glow()),
                16,
            )

    def _player(self):
        """The anteater entity, or None if it is gone."""
        if self._player_id is None:
            return None
        return self.entity_manager.get_entity(self._player_id)
