#!/usr/bin/env python3
"""The admission test for a native port, applied to every candidate.

`docs/adr/0004-the-native-boundary.md` says a subsystem earns a Rust
implementation when

    ceiling = T_py / (T_cross + T_pinned)

is large enough to be worth a second implementation forever, where

    T_py      what the candidate's per-tick work costs in Python now
    T_cross   what getting the data in and the results out costs, per
              tick, measured in Python -- because that is where it is paid
    T_pinned  Python work that cannot move at all: the ECS, the event
              dispatcher, resource handles, caller-supplied callbacks

This prices every candidate the same way, so the next one is evaluated
rather than argued about.

**On the landed rows.** For work that is already built, `T_cross` is
measured directly as what the native path still costs, so `ceiling` and
"achieved" are the same number by construction -- those rows calibrate
the *measurement*, not the formula. The formula was tested the only way
it can be, in advance:

    particles   predicted ~6x porting `update` alone, because `update` was
                84% of the frame; built the boundary out to include the
                render pack instead and got 18-20x.
    sparks      predicted 1.4-1.8x porting `update` alone, because render
                was 55-73%; predicted 13-20x with a batched handoff.
                Achieved 16.6-24.4x.
    flow field  predicted 161x, achieved 56x.

**The flow field is the row that shows what kind of number this is.** It
is a *ceiling*, and for the first time the limit turned out not to be the
boundary: the upload really is 0.5 ms against 83 ms, so the formula was
right that almost nothing is paid at the crossing, but the native sweep
itself costs 1.3 ms and the formula does not model it. Nothing is wrong
with that -- a ceiling that reads 161x says "far above the 5x threshold",
not "expect 161x" -- but a reader comparing a prediction to an outcome
should know that the pools' predictions landed close because their native
work was genuinely negligible beside their handoff, and that is a
property of those candidates rather than of the arithmetic.

    uv run python tools/price_native_boundary.py

Needs the extension for the landed rows (`cargo build --release`); they
are skipped without it and the unbuilt candidates still price.
"""

from __future__ import annotations

import math
import os
import sys
import time
from dataclasses import dataclass
from pathlib import Path

import numpy as np

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

from pyguara.ai.flocking_system import FlockingAgent, FlockingSystem  # noqa: E402
from pyguara.ai.pathfinding.flow_field import dijkstra_map, flow_field  # noqa: E402
from pyguara.ai.pathfinding.flow_field_service import (  # noqa: E402
    FlowFieldService,
)
from pyguara.ai.pathfinding.grid import GridGraph  # noqa: E402
from pyguara.common.components import Transform  # noqa: E402
from pyguara.common.random import RandomStream  # noqa: E402
from pyguara.common.spatial import SpatialHash  # noqa: E402
from pyguara.common.types import Color, Vector2  # noqa: E402
from pyguara.ecs.manager import EntityManager  # noqa: E402
from pyguara.events.dispatcher import EventDispatcher  # noqa: E402
from pyguara.graphics.backends.moderngl.instancing import (  # noqa: E402
    INSTANCE_FLOATS,
    pack_sprite_instances,
)
from pyguara.graphics.components.camera import Camera2D  # noqa: E402
from pyguara.graphics.components.particles import ParticleSystem  # noqa: E402
from pyguara.graphics.components.sprite import Sprite  # noqa: E402
from pyguara.graphics.pipeline.batch import Batcher  # noqa: E402
from pyguara.graphics.pipeline.render_system import RenderSystem  # noqa: E402
from pyguara.graphics.pipeline.viewport import Viewport  # noqa: E402
from pyguara.graphics.types import ShapeBatch  # noqa: E402
from pyguara.graphics.vfx.sparks import Sparks  # noqa: E402
from pyguara.kits.action_combat import Health, Hurtbox  # noqa: E402
from pyguara.kits.projectiles.projectile import Projectile  # noqa: E402
from pyguara.kits.projectiles.system import ProjectileSystem  # noqa: E402
from pyguara.native import native_module  # noqa: E402

DT = 1.0 / 60.0
LIFE = 1e6  # outlive the measurement
FRAME_BUDGET_MS = 1000.0 / 60.0


@dataclass(frozen=True)
class Row:
    """One candidate's price."""

    name: str
    python_ms: float
    cross_ms: float
    pinned_ms: float
    note: str

    @property
    def ceiling(self) -> float:
        """How many times faster the whole candidate could get."""
        floor = self.cross_ms + self.pinned_ms
        return self.python_ms / floor if floor > 1e-9 else math.inf


def measure(fn: object, iterations: int = 40) -> float:
    """Fastest of `iterations` runs, in milliseconds.

    Fastest rather than mean: a shared machine's slow runs say something
    about the machine, and every figure here is compared against another
    figure from the same run.
    """
    fn()  # type: ignore[operator]
    best = math.inf
    for _ in range(iterations):
        start = time.perf_counter()
        fn()  # type: ignore[operator]
        best = min(best, time.perf_counter() - start)
    return best * 1000.0


class _FakeTexture:
    """A texture a pool can hold without a GL context.

    A real class rather than a `MagicMock`: the Python particle path
    groups by `p.texture not in batches`, so it hashes the texture once
    per particle, and a mock's `__hash__` goes through its call machinery.
    That inflated an early benchmark to a fictitious 325x.
    """

    @property
    def width(self) -> int:
        """Width in pixels."""
        return 8

    @property
    def height(self) -> int:
        """Height in pixels."""
        return 8

    @property
    def native_handle(self) -> object:
        """Never bound; the pool only stores it."""
        return self


class _Camera:
    """No zoom, no offset, so screen space is world space."""

    zoom = 1.0

    def screen_offset(self, _viewport: object) -> Vector2:
        """No offset."""
        return Vector2.zero()


class _Sink:
    """Consumes batches, so nothing is measured packing into a void."""

    width = 1280
    height = 720

    def render_batch(self, batch: object) -> None:
        """Walk the batch's destinations."""
        len(batch.destinations)  # type: ignore[attr-defined]

    def draw_circle(
        self, center: Vector2, radius: float, color: Color, width: int = 0
    ) -> None:
        """Count a circle."""
        self._count = getattr(self, "_count", 0) + 1

    def draw_line(
        self, start: Vector2, end: Vector2, color: Color, width: int = 1
    ) -> None:
        """Count a line."""
        self._count = getattr(self, "_count", 0) + 1

    def render_shapes(self, batch: ShapeBatch) -> None:
        """Walk a shape batch."""
        len(batch.instances)


def price_particles(live: int) -> Row | None:
    """Landed. Calibration row: predicted ceiling against achieved speedup."""
    if not ParticleSystem(capacity=1).accelerated:
        return None

    sink, camera = _Sink(), _Camera()
    pools = {}
    for accelerate in (False, True):
        pool = ParticleSystem(live, RandomStream(7), accelerate=accelerate)
        pool.emit(
            _FakeTexture(),  # type: ignore[arg-type]
            Vector2.zero(),
            count=live,
            speed=100.0,
            life=LIFE,
        )
        pools[accelerate] = pool

    python_ms = measure(lambda: pools[False].update(DT)) + measure(
        lambda: pools[False].render(sink, camera)  # type: ignore[arg-type]
    )
    # The native path's whole remaining cost *is* its boundary: `update` is
    # native and `pack_for_render`'s output is Python lists.
    cross_ms = measure(lambda: pools[True].update(DT)) + measure(
        lambda: pools[True].render(sink, camera)  # type: ignore[arg-type]
    )
    return Row(
        f"particles, {live} live",
        python_ms,
        cross_ms,
        0.0,
        f"LANDED, achieved {python_ms / cross_ms:.1f}x",
    )


def price_sparks(live: int, streak: bool) -> Row | None:
    """Landed. The row that justified `ShapeBatch`."""
    if not Sparks(capacity=1).accelerated:
        return None

    sink = _Sink()
    pools = {}
    for accelerate in (False, True):
        pool = Sparks(live, RandomStream(7), accelerate=accelerate)
        pool.burst(
            Vector2.zero(),
            Color(255, 180, 60),
            count=live,
            life=LIFE,
            streak=streak,
        )
        pools[accelerate] = pool

    python_ms = measure(lambda: pools[False].update(DT)) + measure(
        lambda: pools[False].render(sink)  # type: ignore[arg-type]
    )
    cross_ms = measure(lambda: pools[True].update(DT)) + measure(
        lambda: pools[True].render(sink)  # type: ignore[arg-type]
    )
    kind = "streaks" if streak else "dots"
    return Row(
        f"sparks, {live} {kind}",
        python_ms,
        cross_ms,
        0.0,
        f"LANDED, achieved {python_ms / cross_ms:.1f}x",
    )


def price_projectiles(live: int) -> Row:
    """Declined. The hit check is pinned and the pool is not opaque.

    Re-priced once `SpatialHash` grew a native store, because the old
    version of this row counted the whole hit check as pinned and named
    "the spatial query" as part of it. The broad-phase is no longer
    pinned -- but the ECS lookups and component checks that follow it
    are, and they are the bulk. Measured end to end, an accelerated index
    moves `ProjectileSystem.update` 2.82 ms -> 2.12 ms at 1000 live, or
    1.33x, which does not come close to rescuing the decline. Pinned here
    with `accelerate=False` so the row prices the same thing it always
    did, and the figure above is reported in `docs/guides/performance.md`
    instead.
    """
    manager = EntityManager()
    dispatcher = EventDispatcher()
    index: SpatialHash[str] = SpatialHash(accelerate=False)
    for i in range(200):
        entity = manager.create_entity(f"target_{i}")
        entity.add_component(Hurtbox(team="enemy"))
        entity.add_component(Health(current=100.0, max_health=100.0))
        # Far from the projectiles: the frame being priced is the common
        # one, flying rather than landing.
        index.insert(entity.id, Vector2(5000.0 + i * 40.0, 5000.0))

    system = ProjectileSystem(manager, dispatcher, index, capacity=live)
    texture = _FakeTexture()
    for i in range(live):
        system.spawn(
            texture,  # type: ignore[arg-type]
            Vector2(float(i), 0.0),
            Vector2(10.0, 5.0),
            life=LIFE,
            team="player",
            damage=5.0,
        )

    def integrate_only() -> None:
        """`update` minus the hit check, to price them apart."""
        for projectile in system._pool:
            if not projectile.active:
                continue
            projectile.life -= DT
            projectile.position = projectile.position + projectile.velocity * DT

    sink, camera = _Sink(), _Camera()
    full = measure(lambda: system.update(DT))
    integrate = measure(integrate_only)
    render = measure(lambda: system.render(sink, camera))  # type: ignore[arg-type]
    # The ECS lookups, the component checks and `apply_damage`. The
    # broad-phase inside this is no longer pinned -- a native index does
    # it -- but it is a small part of the whole: see the docstring.
    pinned = full - integrate

    # Not opaque: `get_active()` is public and `games/protocolo_bandeira`
    # reads `.position`/`.velocity` off it every frame, so a native pool
    # has to rebuild the `Vector2`s it removed.
    mirrors = [Projectile(active=True) for _ in range(live)]
    packed = [(float(i), float(i) * 2.0) for i in range(live)]

    def sync_back() -> None:
        for mirror, (x, y) in zip(mirrors, packed, strict=True):
            mirror.position = Vector2(x, y)

    # A native pool would also pack for render, which the particle pool
    # measures at ~0.10 ms per 1000 elements. Borrowed rather than guessed:
    # it is the same `Vec<(f32, f32)>`-into-Python-lists crossing.
    native_render_pack_ms = 0.10

    return Row(
        f"projectiles, {live} live",
        integrate + pinned + render,
        measure(sync_back) + native_render_pack_ms,
        pinned,
        "DECLINED, not opaque",
    )


def price_flocking(agents: int) -> Row:
    """Landed, and the row that priced worst of the three gameplay ports.

    It passes the threshold despite not being opaque -- every agent is an
    ECS entity, so positions and velocities cross every tick -- purely on
    the density of the per-agent work. That is also why it prices at 19x
    where the flow field prices at 161x, and why what it *achieves* is
    lower again: the crossing is 63% of a native tick here, against
    almost nothing there.
    """
    from tests.performance.conftest import build_flock, uniform_spread_for

    manager, system = build_flock(
        agents, spread=uniform_spread_for(agents), accelerate=False
    )
    system.update(DT)

    entities = list(manager.get_entities_with_cached(FlockingAgent, Transform))
    flock = [entity.get_component(FlockingAgent) for entity in entities]
    transforms = [entity.get_component(Transform) for entity in entities]

    def upload() -> list[float]:
        """Positions, velocities and every per-agent parameter."""
        out: list[float] = []
        for transform, agent in zip(transforms, flock, strict=True):
            position, velocity = transform.position, agent.velocity
            out += [position.x, position.y, velocity.x, velocity.y]
            out += [
                agent.neighbor_radius,
                agent.separation_radius,
                agent.cohesion_weight,
                agent.alignment_weight,
                agent.separation_weight,
                agent.max_speed,
                agent.max_force,
                agent.mass,
                agent.seek_weight,
                1.0 if agent.enabled else 0.0,
            ]
            target = agent.seek_target
            out += [1.0, target.x, target.y] if target else [0.0, 0.0, 0.0]
        return out

    packed = [0.5] * (agents * 4)

    def download() -> None:
        """Back into the ECS components everything else reads."""
        for slot, (transform, agent) in enumerate(zip(transforms, flock, strict=True)):
            base = slot * 4
            transform.position = Vector2(packed[base], packed[base + 1])
            agent.velocity = Vector2(packed[base + 2], packed[base + 3])

    python_ms = measure(lambda: system.update(DT), iterations=12)
    native = FlockingSystem(manager, accelerate=None)
    if not native.accelerated:
        return Row(
            f"flocking, {agents} agents",
            python_ms,
            measure(upload, iterations=12) + measure(download, iterations=12),
            0.0,
            "every agent would cross every tick (extension not built)",
        )

    # The whole landed tick, not the handoff alone: for this candidate the
    # two are nearly the same thing, which is the finding.
    cross_ms = measure(lambda: native.update(DT), iterations=12)
    return Row(
        f"flocking, {agents} agents",
        python_ms,
        cross_ms,
        0.0,
        f"LANDED, achieved {python_ms / cross_ms:.1f}x",
    )


def price_flow_field(side: int) -> Row:
    """Landed, and the largest margin in the engine.

    `T_cross` is what the native path still costs per genuine recompute,
    which for this candidate is the wall-mask upload plus the sweep
    itself -- there is no download at all, because the field stays native
    and is queried through `vector_at`. That is the opacity ADR 0004's
    Decision 3 describes, and it is why this row prices so much better
    than flocking's, which has to hand every agent back every tick.
    """
    graph = GridGraph(side, side, allow_diagonal=True)
    goals = [(side // 2, side // 2)]
    for y in range(side):
        for x in range(side):
            if (x * 7 + y * 13) % 8 == 0 and (x, y) != goals[0]:
                graph.walls.add((x, y))

    cost_map = dijkstra_map(graph, goals)
    python_ms = measure(lambda: dijkstra_map(graph, goals), iterations=5) + measure(
        lambda: flow_field(graph, cost_map), iterations=5
    )

    if not FlowFieldService(graph).accelerated:

        def upload() -> tuple[list[int], list[float]]:
            """The grid, flattened. Changes rarely, so this is a ceiling."""
            blocked = [0] * (side * side)
            for x, y in graph.walls:
                blocked[y * side + x] = 1
            weights = [
                graph.weights.get((x, y), 1.0) for y in range(side) for x in range(side)
            ]
            return blocked, weights

        return Row(
            f"flow field, {side}x{side}",
            python_ms,
            measure(upload, iterations=5),
            0.0,
            "the field would stay native and be queried (extension not built)",
        )

    # A fresh service per round, so the upload is paid rather than skipped:
    # the guard would otherwise answer the second ask from cache and this
    # would price a cache hit.
    cross_ms = measure(lambda: FlowFieldService(graph).recompute(goals), iterations=5)
    return Row(
        f"flow field, {side}x{side}",
        python_ms,
        cross_ms,
        0.0,
        f"LANDED, achieved {python_ms / cross_ms:.1f}x",
    )


def price_spatial_index(count: int) -> Row | None:
    """Landed, and the row that is a shared primitive rather than a system.

    Every other row prices a subsystem, so `T_py` is a tick of it and the
    ceiling is what a game would feel. This one prices the *index* five
    subsystems share, which makes the number mean something narrower: it
    is what the index costs, not what any consumer saves. The consumers
    save between 1.33x and 4.2x, because in each of them the broad-phase
    was only ever a fraction of the tick -- `docs/guides/performance.md`
    has the table, and the gap between 9x here and 1.33x there is the
    most useful thing this row records.

    `T_cross` is the Python list of keys each query hands back, which is
    the term ADR 0004 originally declined this port on. Measured, it is
    4-6% of the Python broad-phase it replaces, and it stays that fraction
    as density rises, because both sides scale with the candidate count
    and Python's per-candidate cost is about twenty times the crossing's.
    """
    if native_module() is None:
        return None

    spread = math.sqrt(count) * 64.0
    keys = [f"entity-{index:08d}" for index in range(count)]
    points = [
        Vector2((index * spread / count) % spread, (index * 7.3) % spread)
        for index in range(count)
    ]

    def tick(accelerate: bool) -> None:
        index: SpatialHash[str] = SpatialHash(accelerate=accelerate)
        for key, point in zip(keys, points, strict=True):
            index.insert(key, point)
        for point in points:
            index.query_radius(point, 80.0)

    python_ms = measure(lambda: tick(False), iterations=8)
    native_ms = measure(lambda: tick(True), iterations=8)

    return Row(
        f"spatial index, {count} keys",
        python_ms,
        native_ms,
        0.0,
        f"LANDED, achieved {python_ms / native_ms:.1f}x",
    )


def price_render_batcher(sprites: int) -> Row | None:
    """Item 4, Marco 2's buffer handoff, priced after Decision 6.

    The whole CPU-side frame, because a native batcher replaces all four
    of its stages at once: `RenderSystem.submit` building a command per
    renderable, `RenderQueue.sort`, `Batcher.create_batches`, and
    `pack_sprite_instances` filling the instance array. Pricing the
    batcher alone would be the error Decision 7 names.

    **`T_pinned` is the attribute reads**, and nothing else moves them.
    Each command's data lives on a Python object -- a `Sprite`, or an
    entity's `Transform` -- and a native command buffer still has to read
    `position`, `rotation`, `scale`, `color`, `layer` and `sort_group` off
    it in Python before it can push anything. Measured directly, by
    running the same loop and building a tuple instead of crossing.

    **`T_cross` is one crossing per sprite**, and that is the *cheap*
    shape. Passing the whole frame in one call instead needs Python to
    materialise a list per column first, measured at 6.36 ms against the
    1.47 ms the single call saves -- so the "one crossing per system per
    frame" rule RFC-0003 states as a design law is, here, the more
    expensive of the two.

    It is priced from `NativeSpatialHash.insert`, the only per-element
    crossing the engine ships: three arguments into the same SoA shape a
    command buffer would use, plus a CPython dict store a push would not
    do. Measured at 0.092 us a call, against 0.114 us for a throwaway
    eleven-argument probe push -- so this term is **good to about 25%,
    and low**, which puts the real ceiling nearer 7.4x than the 8.8x
    printed here.

    The bracket worth knowing is the other end: `NativeParticlePool.emit`
    takes *seventeen* arguments and costs 0.405 us a call. That is not
    what argument count does -- three of them are Python lists, and
    extracting each into a `Vec<f32>` is an allocation. Scalars are
    nearly free to cross; containers are not, which is the same finding
    as the paragraph above arrived at from the other direction.

    Returns None without the extension, since the crossing term needs it.
    """
    native = native_module()
    if native is None:
        return None

    texture = _FakeTexture()
    pool = [
        Sprite(
            texture=texture,  # type: ignore[arg-type]
            position=Vector2(index * 0.5, index * 0.5),
            rotation=index * 1.0,
            scale=Vector2(1.0 + index * 0.001, 1.0),
            color=Color(255, index % 256, 128, 255),
        )
        for index in range(sprites)
    ]
    system = RenderSystem(_Sink())  # type: ignore[arg-type]
    camera = Camera2D(1280, 720)
    viewport = Viewport.create_fullscreen(1280, 720)
    batcher = Batcher()
    instances = np.zeros((sprites, INSTANCE_FLOATS), dtype="f4")

    def submit_all() -> None:
        system._queue.clear()
        for sprite in pool:
            system.submit(sprite)

    submit_all()
    commands = list(system._queue.commands)

    def sort_only() -> None:
        system._queue._commands = list(commands)
        system._queue.sort()

    sort_only()
    sorted_commands = list(system._queue.commands)
    batches = batcher.create_batches(sorted_commands, camera, viewport)

    def batch_only() -> None:
        batcher.create_batches(sorted_commands, camera, viewport)

    def pack_only() -> None:
        for batch in batches:
            pack_sprite_instances(batch, instances)

    python_ms = (
        measure(submit_all)
        + measure(sort_only)
        + measure(batch_only)
        + measure(pack_only)
    )

    # Pinned: reading the fields off each Python object, which happens in
    # either language.
    def read_only() -> None:
        for sprite in pool:
            position = sprite.position
            scale = sprite.scale
            colour = sprite.color
            # Bound to a dummy rather than left as an expression
            # statement: the work is the attribute reads, and a tuple of
            # them is the cheapest way to force every one.
            _ = (
                position.x,
                position.y,
                sprite.rotation,
                scale.x,
                scale.y,
                colour.r,
                colour.g,
                colour.b,
                colour.a,
                sprite.layer,
                sprite.sort_group,
            )

    pinned_ms = measure(read_only)

    # Crossing: one push per sprite. Priced from the index's `insert`,
    # with its own Python-side loop subtracted so only the call remains.
    index = native.NativeSpatialHash(64.0)
    keys = list(range(sprites))
    points = [(float(i), float(i) * 1.5) for i in range(sprites)]

    def insert_all() -> None:
        for key, point in zip(keys, points, strict=True):
            index.insert(key, point, 0xFFFFFFFF)

    def insert_loop_only() -> None:
        for key, point in zip(keys, points, strict=True):
            _ = (key, point)

    cross_ms = measure(insert_all) - measure(insert_loop_only)

    return Row(
        f"render batcher, {sprites} sprites",
        python_ms,
        cross_ms,
        pinned_ms,
        "DEFERRED; ceiling is an upper bound",
    )


def main() -> int:
    """Price every candidate and print the table.

    Returns:
        0 always; this reports rather than asserts.
    """
    rows: list[Row | None] = [
        price_particles(1000),
        price_sparks(1000, streak=False),
        price_sparks(1000, streak=True),
        price_flow_field(96),
        price_flocking(1000),
        price_projectiles(1000),
        price_spatial_index(1000),
        price_render_batcher(20000),
    ]

    header = (
        f"{'candidate':26} {'T_py':>9} {'T_cross':>9} {'T_pinned':>9} "
        f"{'ceiling':>9}  note"
    )
    print(header)
    print("-" * (len(header) + 12))
    for row in rows:
        if row is None:
            continue
        print(
            f"{row.name:26} {row.python_ms:8.3f}m {row.cross_ms:8.3f}m "
            f"{row.pinned_ms:8.3f}m {row.ceiling:8.1f}x  {row.note}"
        )

    print(f"\nT_py as a share of a {FRAME_BUDGET_MS:.1f} ms frame, for scale:")
    for row in rows:
        if row is None:
            continue
        print(f"  {row.name:26} {row.python_ms / FRAME_BUDGET_MS:6.0%}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
