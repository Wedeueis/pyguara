"""The Revoada: the swarm, its tint, and the one batch it draws in.

This is the demo's centrepiece. Everything else in the clearing exists so
that this module has somewhere to happen.

**Two layers, and the split is deliberate** (GDD §2.3). The *interactive*
layer is `SWARM_CAP` pooled ECS insects that flock, collide with the
tongue and die. The *decorative* layer is a much larger set of cheap
drifting motes that do none of that. Both draw in **the same batch,
through the same tint channel**, so the screen looks like the cerrado at
midnight while the engine is only being measured on the first layer.
Stating that here, in the code as well as the GDD, is the point: nobody
should mistake the picture for the measurement.

**`build_batch()` is pure, and that is a design constraint rather than a
happy accident** (GDD §4.2). GL demos cannot boot headlessly -- SDL's
dummy video driver has no OpenGL -- so this demo is excluded from
`DEMOS_THAT_DRAW` and the tint showcase would otherwise ship covered by a
manual smoke test and nothing else. But `tests/visual/` rasterises
nothing; it snapshots data. A pure function from swarm state to a
`RenderBatch` makes the batch -- `colors_enabled`, the tint values, the
whole thing -- deterministically testable without a GPU.

**Insects are not lights.** Their glow is an additive tinted sprite
crossing the bloom threshold, not a `LightSource` each. See `scenes.py`'s
`_lights()` and GDD §3.2.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from games.tamandua_murundus.components import Insect
from pyguara.ai.flocking_system import FlockingAgent
from pyguara.common.components import Transform
from pyguara.common.random import RandomStream
from pyguara.common.types import Color, Rect, Vector2
from pyguara.ecs.entity import Entity
from pyguara.ecs.manager import EntityManager
from pyguara.ecs.pool import EntityPool, Poolable
from pyguara.graphics.types import RenderBatch
from pyguara.resources.types import Texture
from pyguara.spatial.components import SpatialTracked

# --- scale ---------------------------------------------------------
#
# Measured, not chosen. `docs/guides/performance.md` puts `FlockingSystem`
# alone at 7.4 ms/tick for 1000 agents with `groups=3`, against a 16.7 ms
# frame -- but flocking is not the only system billing against that frame
# here. Re-measured in this scene, with every CPU-side system a real frame
# runs (spatial index, mounds, flocking, tongue, motes, batch build) and
# the decorative layer at its shipping size:
#
#     interactive   ms/frame (CPU)
#           300         3.75
#           500         6.26
#           700         9.08   <- shipped
#           900        12.73
#          1100        16.88   over budget on CPU alone
#
# Same machine as the engine figures (WSL2, Mesa 23.2.1 over D3D12,
# RTX 3050, CPython 3.12). 700 leaves roughly 7 ms of the frame for the
# GL work those numbers exclude -- the instance pack, the light pass and
# three bloom blur passes -- which is what 900 does not.
SWARM_CAP = 700

# Steering staggered across three ticks: every insect still integrates its
# position every frame, so motion stays smooth, and only the *decision*
# rate drops to 20 Hz. This is the single largest lever on the frame.
STEERING_GROUPS = 3

# The cheap layer. These never flock, never collide and never die; they
# cost one position update and one row in the batch. A multiple of the
# interactive count, because that is the whole point of having them.
DECORATIVE_COUNT = 1400

# --- tint ----------------------------------------------------------

# Dull brown by day, bioluminescent by night. The same texture either way:
# one neutral blob, N colours, one draw call.
INSECT_DULL = Color(126, 96, 62)
INSECT_LIT = Color(120, 255, 196)

# How far past 1.0 the lit colour is pushed before it is written into the
# batch. The bloom threshold is 0.62, and a tint can only ever *attenuate*
# the texture it multiplies -- so a glow that merely reaches the lit
# colour never crosses the threshold and never blooms. The texture is
# authored bright (see `make_insect_texture`) and the tint rides it.
GLOW_GAIN = 1.0


def insect_tint(glow: float) -> Color:
    """The swarm's colour at a given glow level.

    Args:
        glow: 0.0 for dull daytime brown, 1.0 for full bioluminescence.
            Clamped, so a caller driving this off an unclamped curve
            cannot push the colour past either end.

    Returns:
        The tint to multiply the insect texture by.
    """
    glow = max(0.0, min(1.0, glow))
    return INSECT_DULL.lerp(INSECT_LIT, glow)


def make_insect_texture(factory, size: int = 8) -> Texture:
    """Generate the one texture every insect shares.

    No sprite art ships with this demo (GDD §3.1): a neutral blob is
    generated here and the *tint* is what makes a thousand of them
    different colours. That also makes the result legible -- if the tint
    path broke, every insect on screen would be this exact white.

    Args:
        factory: A `TextureFactory`.
        size: Edge length in pixels. Small on purpose; an insect is a few
            pixels on screen and a larger texture is bandwidth for
            nothing.

    Returns:
        A soft round white blob, ready to be tinted per instance.
    """
    pixels = bytearray()
    centre = (size - 1) / 2.0
    for y in range(size):
        for x in range(size):
            distance = math.hypot(x - centre, y - centre) / (centre + 0.5)
            # Soft edge rather than a hard circle: a hard-edged 8px sprite
            # reads as a square at this size once it is scaled.
            alpha = max(0.0, 1.0 - distance) ** 1.6
            pixels += bytes((255, 255, 255, int(255 * alpha)))
    return factory.create_from_bytes("<insect>", bytes(pixels), size, size)


@dataclass(slots=True)
class Mote:
    """One decorative insect: a position, a drift, and nothing else.

    Deliberately not an entity. A `Mote` has no components to resolve, no
    spatial-index entry and no flocking slot -- which is what makes the
    decorative layer cost a position update rather than a simulation tick.
    """

    position: Vector2 = field(default_factory=Vector2.zero)
    velocity: Vector2 = field(default_factory=Vector2.zero)
    phase: float = 0.0
    size: float = 2.4


@dataclass(slots=True)
class SwarmBatchInput:
    """Everything `build_batch()` needs, and nothing it does not.

    A plain value so the pure function has a pure input: a test can build
    one without an `EntityManager`, a texture loader or a scene.

    Attributes:
        texture: The shared insect texture.
        interactive: World positions of the flocking insects.
        decorative: World positions of the cheap layer.
        glow: 0..1 bioluminescence. In D2 this ramps with the run clock;
            D3 drives it from the ambient cycle instead, which is the only
            thing about this that changes.
        interactive_size: Drawn scale of a flocking insect.
        decorative_size: Drawn scale of a mote. Smaller, so the cheap
            layer reads as distance rather than as more of the same.
    """

    texture: Texture
    interactive: list[tuple[float, float]]
    decorative: list[tuple[float, float]]
    glow: float
    interactive_size: float = 1.4
    decorative_size: float = 0.8


def build_batch(state: SwarmBatchInput) -> RenderBatch:
    """Turn swarm state into the single batch that draws all of it.

    **Pure.** No entity lookups, no clock, no renderer, no globals -- the
    same input gives the same batch every time, which is what makes the
    tint snapshot-testable on a machine with no GPU.

    Both layers go into one batch because they share a texture, which is
    the whole claim the demo is making: one texture, N colours, one draw
    call. Splitting them would be two draw calls proving half as much.

    Args:
        state: The swarm, already resolved to plain positions.

    Returns:
        A batch with `colors_enabled` set and one tint per instance.
    """
    tint = insect_tint(state.glow)
    rgba = (tint.r, tint.g, tint.b, 255)

    # The decorative layer is dimmed rather than differently coloured: it
    # is the *same* insects further away, and a second hue would read as a
    # second species.
    dim = int(120 + 90 * state.glow)
    faded = (tint.r, tint.g, tint.b, dim)

    destinations = list(state.interactive) + list(state.decorative)
    colors = [rgba] * len(state.interactive) + [faded] * len(state.decorative)
    scales = [(state.interactive_size, state.interactive_size)] * len(
        state.interactive
    ) + [(state.decorative_size, state.decorative_size)] * len(state.decorative)

    return RenderBatch(
        texture=state.texture,
        destinations=destinations,
        rotations=[0.0] * len(destinations),
        scales=scales,
        transforms_enabled=True,
        colors=colors,
        colors_enabled=True,
    )


class Swarm:
    """Owns both layers: the pooled flock and the decorative motes."""

    def __init__(
        self,
        entity_manager: EntityManager,
        arena: Rect,
        rng: RandomStream,
        *,
        cap: int = SWARM_CAP,
        decorative: int = DECORATIVE_COUNT,
    ) -> None:
        """Pre-allocate both layers.

        Args:
            entity_manager: Where the interactive insects live.
            arena: The clearing, for the decorative drift and the wrap.
            rng: Drives the scatter and the drift.
            cap: Interactive insects. Defaults to the measured `SWARM_CAP`.
            decorative: Cheap motes.
        """
        self._entity_manager = entity_manager
        self._arena = arena
        self._rng = rng

        self._pool = EntityPool(entity_manager, "insects", cap, self._make_insect)

        self.motes: list[Mote] = [
            Mote(
                position=Vector2(
                    rng.uniform(arena.left, arena.right),
                    rng.uniform(arena.top, arena.bottom),
                ),
                velocity=Vector2(rng.uniform(-18.0, 18.0), rng.uniform(-18.0, 18.0)),
                phase=rng.uniform(0.0, math.tau),
                size=rng.uniform(1.8, 3.0),
            )
            for _ in range(decorative)
        ]

    def _make_insect(self, entity_manager: EntityManager, index: int) -> Entity:
        """Build one pooled insect, complete.

        Everything an insect will ever need is attached here, including
        the components systems query on. That is safe because `EntityPool`
        parks an idle entity with `EntityManager.set_entity_enabled()`, so
        it keeps its components and still matches no query -- see that
        method for what this used to cost when each game had to detach
        them by hand.
        """
        entity = entity_manager.create_entity()
        entity.add_component(Poolable())
        entity.add_component(Transform(position=Vector2.zero()))
        entity.add_component(Insect())
        entity.add_component(
            FlockingAgent(
                max_speed=self._rng.uniform(54.0, 82.0),
                max_force=150.0,
                neighbor_radius=46.0,
                separation_radius=15.0,
                cohesion_weight=0.8,
                alignment_weight=0.9,
                separation_weight=1.9,
            )
        )
        entity.add_component(SpatialTracked())
        return entity

    @property
    def active_count(self) -> int:
        """How many interactive insects are alive."""
        return self._pool.active_count

    def release_at(self, origin: Vector2, anchor: str) -> Entity | None:
        """Put one interactive insect into the world beside `origin`.

        Returns:
            The insect, or None if the pool is exhausted -- which is the
            cap doing its job, not an error.
        """
        entity = self._pool.acquire()
        if entity is None:
            return None

        angle = self._rng.uniform(0.0, math.tau)
        entity.get_component(Transform).position = Vector2(
            origin.x + math.cos(angle) * 38.0,
            origin.y + math.sin(angle) * 38.0,
        )
        insect = entity.get_component(Insect)
        insect.health = 1.0
        insect.anchor = anchor

        agent = entity.get_component(FlockingAgent)
        agent.velocity = Vector2(math.cos(angle) * 40.0, math.sin(angle) * 40.0)
        return entity

    def active_insects(self) -> list[Entity]:
        """Every interactive insect currently out of the pool."""
        return self._pool.get_active()

    def kill(self, entity: Entity) -> None:
        """Return one insect to the pool.

        Pooled rather than destroyed: at this rate of death, creating and
        removing entities is the cost the pool exists to avoid. The pool
        disables the entity, so an idle insect keeps its tuning and still
        costs nothing in `FlockingSystem` or the spatial index.
        """
        self._pool.release(entity)

    def update_motes(self, dt: float) -> None:
        """Drift the decorative layer and wrap it at the clearing's edge.

        Wrapped rather than turned back like the interactive insects: a
        mote has no flock to rejoin, and a wrap keeps the density even
        without any steering at all.
        """
        arena = self._arena
        for mote in self.motes:
            mote.phase += dt * 1.7
            drift = math.sin(mote.phase) * 8.0
            x = mote.position.x + (mote.velocity.x + drift) * dt
            y = mote.position.y + mote.velocity.y * dt

            if x < arena.left:
                x = arena.right
            elif x > arena.right:
                x = arena.left
            if y < arena.top:
                y = arena.bottom
            elif y > arena.bottom:
                y = arena.top

            mote.position = Vector2(x, y)

    def centroids(self, columns: int = 3, rows: int = 2) -> list[tuple[Vector2, float]]:
        """Aggregate the flock into at most `columns * rows` glow centres.

        **This is how the swarm blooms**, and it is worth
        being explicit about why it is not simply one light per insect.
        The composite pass multiplies the world by the light map, and the
        ambient is well below 1.0 for most of the run -- so a tinted
        sprite, however bright its tint, comes out *darker* than it was
        drawn and can never cross the bloom threshold on its own. It needs
        light falling on it.

        A `LightSource` per insect would do that and would also make
        `LightingSystem`'s per-entity collection and the light instance
        buffer both scale with `SWARM_CAP`, turning a crowd benchmark into
        a lighting benchmark (GDD §3.2). So the flock is bucketed into a
        fixed grid instead: one light per non-empty cell, six at most,
        weighted by how many insects are in it. Dense cells glow; a lone
        insect crossing the clearing does not.

        Args:
            columns: Horizontal buckets.
            rows: Vertical buckets.

        Returns:
            `(centre, weight)` per non-empty cell, weight in 0..1 relative
            to the busiest cell.
        """
        active = self._pool.get_active()
        if not active:
            return []

        arena = self._arena
        cell_width = max(1.0, arena.width / columns)
        cell_height = max(1.0, arena.height / rows)

        sums: dict[tuple[int, int], list[float]] = {}
        for entity in active:
            position = entity.get_component(Transform).position
            key = (
                min(columns - 1, max(0, int((position.x - arena.left) / cell_width))),
                min(rows - 1, max(0, int((position.y - arena.top) / cell_height))),
            )
            bucket = sums.get(key)
            if bucket is None:
                sums[key] = [position.x, position.y, 1.0]
            else:
                bucket[0] += position.x
                bucket[1] += position.y
                bucket[2] += 1.0

        busiest = max(bucket[2] for bucket in sums.values())
        return [
            (
                Vector2(bucket[0] / bucket[2], bucket[1] / bucket[2]),
                bucket[2] / busiest,
            )
            for bucket in sums.values()
        ]

    def batch_input(self, texture: Texture, glow: float) -> SwarmBatchInput:
        """Resolve both layers into the plain value `build_batch()` takes.

        This is where the entity lookups happen, so `build_batch()` itself
        stays free of them.
        """
        return SwarmBatchInput(
            texture=texture,
            interactive=[
                (
                    entity.get_component(Transform).position.x,
                    entity.get_component(Transform).position.y,
                )
                for entity in self._pool.get_active()
            ],
            decorative=[(mote.position.x, mote.position.y) for mote in self.motes],
            glow=glow,
        )
