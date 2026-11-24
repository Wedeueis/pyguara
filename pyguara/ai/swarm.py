"""A swarm: thousands of flocking agents held natively, not as entities.

Use a swarm for a horde whose members share their logic, and
`FlockingSystem` for a flock of entities that each run their own. A swarm's
agents have no components; game code spawns, kills and queries them in
batches, by id. Every agent steers from the state at the start of the
tick, so the result does not depend on the order agents are computed in.

Example:
    swarm = Swarm(cell_size=26.0)
    ant = swarm.add_kind(SwarmKind(max_speed=120.0, neighbor_radius=26.0))
    ids = swarm.spawn(ant, [Vector2(10, 20), Vector2(30, 40)])
    swarm.set_kind_seek(ant, player_position)
    swarm.set_detail_bands([(900.0, 1), (2000.0, 4)])  # far ants think less
    swarm.set_detail_focus(camera_centre)
    swarm.update(dt)
    swarm.kill(swarm.query_radius(player_position, 150.0))
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Sequence
from dataclasses import astuple, dataclass, field
from functools import partial
from typing import Any

from pyguara.common.types import Vector2
from pyguara.graphics.components.camera import Camera2D
from pyguara.graphics.pipeline.render_system import RenderSystem
from pyguara.graphics.pipeline.viewport import Viewport
from pyguara.graphics.types import RenderBatch
from pyguara.native import require_extension
from pyguara.resources.types import Texture


@dataclass(frozen=True, slots=True)
class SwarmKind:
    """The tuning every agent of one kind shares.

    The fields mean what `FlockingAgent`'s of the same names mean, and
    default to the same values.

    Attributes:
        max_speed: Maximum movement speed.
        max_force: Maximum steering force.
        mass: Divides the force into an acceleration.
        neighbor_radius: Distance within which others count as flockmates.
        separation_radius: Distance within which flockmates push apart.
        cohesion_weight: Weight of steering toward the flockmates' centre.
        alignment_weight: Weight of matching the flockmates' heading.
        separation_weight: Weight of pushing apart from close flockmates.
        seek_weight: Weight of steering toward an agent's seek target.
    """

    max_speed: float = 150.0
    max_force: float = 400.0
    mass: float = 1.0
    neighbor_radius: float = 80.0
    separation_radius: float = 30.0
    cohesion_weight: float = 1.0
    alignment_weight: float = 1.0
    separation_weight: float = 1.5
    seek_weight: float = 1.0

    def __post_init__(self) -> None:
        """Reject tuning the solver cannot use.

        Raises:
            ValueError: If a value is not finite, `mass` is not positive,
                or a speed, force or radius is negative.
        """
        for name, value in zip(self.__dataclass_fields__, astuple(self), strict=True):
            if not math.isfinite(value):
                raise ValueError(f"SwarmKind.{name} must be finite, got {value}")
        if self.mass <= 0.0:
            raise ValueError(f"SwarmKind.mass must be positive, got {self.mass}")
        for name in ("max_speed", "max_force", "neighbor_radius", "separation_radius"):
            if getattr(self, name) < 0.0:
                raise ValueError(f"SwarmKind.{name} must not be negative")


@dataclass(frozen=True, slots=True)
class SwarmLook:
    """How every agent of one kind is drawn.

    An agent's box is placed as a `Sprite`'s is: its top-left corner at the
    agent's position plus `offset`, and a turned frame's box is the one
    bounding it after turning.

    Attributes:
        frames: The textures of a looping clip; one for a still image.
        frame_rate: Frames a second. Each agent's clip starts when it is
            spawned. 0 holds the first frame.
        layer: The render layer, sorted with sprites on the same layers.
        z_index: Depth within the layer.
        offset: From an agent's position to its box's top-left corner.
        scale: Drawn scale.
        face_heading: Turn each agent to point along its velocity, as a
            `Sprite.rotation` of its heading in degrees.
    """

    frames: tuple[Texture, ...]
    frame_rate: float = 0.0
    layer: int = 0
    z_index: float = 0.0
    offset: Vector2 = field(default_factory=lambda: Vector2(0.0, 0.0))
    scale: Vector2 = field(default_factory=lambda: Vector2(1.0, 1.0))
    face_heading: bool = False

    def __post_init__(self) -> None:
        """Reject a look that cannot be drawn.

        Raises:
            ValueError: If there are no frames, or `frame_rate` is negative
                or not finite.
        """
        if not self.frames:
            raise ValueError("SwarmLook needs at least one frame")
        if not (math.isfinite(self.frame_rate) and self.frame_rate >= 0.0):
            raise ValueError(
                f"SwarmLook.frame_rate must be finite and not negative, got "
                f"{self.frame_rate}"
            )


class Swarm:
    """A pool of flocking agents, stepped together natively.

    Ids are integers that stay valid until the agent is killed; a killed
    agent's id never names another agent. Methods taking ids raise
    `KeyError` for one that is not alive, and change nothing.
    """

    def __init__(self, cell_size: float = 64.0, threads: int | None = None) -> None:
        """Create an empty swarm.

        The result is the same bits on any number of threads.

        Args:
            cell_size: The neighbour grid's bucket size; pick something
                close to the kinds' `neighbor_radius`.
            threads: `None` steers a large swarm on a pool shared with
                other swarms, sized to the machine. 1 steers on the calling
                thread; more, on a pool of this swarm's own.

        Raises:
            ValueError: If `cell_size` is not finite and positive, or
                `threads` is below 1.
            RuntimeError: If the native extension cannot be imported.
        """
        self._native: Any = require_extension("Swarm").NativeSwarm(cell_size, threads)
        self._kinds: list[SwarmKind] = []
        self._looks: dict[int, SwarmLook] = {}

    @property
    def count(self) -> int:
        """How many agents are alive."""
        return int(self._native.count())

    @property
    def time(self) -> float:
        """Seconds the swarm has been stepped; agents' clips run on it."""
        return float(self._native.time())

    @property
    def kinds(self) -> tuple[SwarmKind, ...]:
        """The registered kinds, by index."""
        return tuple(self._kinds)

    def add_kind(self, kind: SwarmKind) -> int:
        """Register a kind and return the index agents are spawned with.

        Raises:
            ValueError: If its `neighbor_radius` spans too many cells.
        """
        index = int(self._native.add_kind(list(astuple(kind))))
        self._kinds.append(kind)
        return index

    def spawn(
        self,
        kind: int,
        positions: Sequence[Vector2],
        velocities: Sequence[Vector2] | None = None,
    ) -> list[int]:
        """Add agents of one kind and return their ids, in order.

        Args:
            kind: An index from `add_kind`.
            positions: Where each agent starts.
            velocities: Each agent's starting velocity; at rest if omitted.

        Raises:
            ValueError: For an unknown kind, a non-finite value, or
                mismatched lengths. Nothing is spawned.
        """
        return list(self._native.spawn(kind, positions, velocities))

    def kill(self, ids: Iterable[int]) -> None:
        """Remove agents.

        Raises:
            KeyError: If an id is not alive.
            ValueError: If an id is listed twice. Nothing is removed.
        """
        self._native.kill(list(ids))

    def is_alive(self, agent: int) -> bool:
        """Whether an id names a live agent."""
        return bool(self._native.is_alive(agent))

    def ids(self) -> list[int]:
        """Every live agent's id."""
        return list(self._native.ids())

    def positions(self, ids: Sequence[int]) -> list[Vector2]:
        """The given agents' positions."""
        return list(self._native.positions(list(ids)))

    def velocities(self, ids: Sequence[int]) -> list[Vector2]:
        """The given agents' velocities."""
        return list(self._native.velocities(list(ids)))

    def kinds_of(self, ids: Sequence[int]) -> list[int]:
        """The given agents' kind indices."""
        return list(self._native.kinds_of(list(ids)))

    def set_kind_seek(self, kind: int, target: Vector2 | None) -> None:
        """Point every live agent of a kind at a target, or at none.

        Agents spawned later start with no target.
        """
        self._native.set_kind_seek(kind, target)

    def set_seek(self, ids: Sequence[int], targets: Sequence[Vector2]) -> None:
        """Point each given agent at its own target."""
        self._native.set_seek(list(ids), targets)

    def query_radius(self, centre: Vector2, radius: float) -> list[int]:
        """Ids of the live agents within `radius` of `centre`, sorted."""
        return list(self._native.query_radius(centre, radius))

    def query_outside(self, centre: Vector2, radius: float) -> list[int]:
        """Ids of the live agents farther than `radius` from `centre`, sorted."""
        return list(self._native.query_outside(centre, radius))

    def set_detail_bands(self, bands: Sequence[tuple[float, int]]) -> None:
        """Steer agents far from the detail focus less often.

        Each band is `(radius, period)`, radii rising. An agent within a
        band's radius of the focus steers every `period`-th tick, and one
        past every radius takes the last band's period. On the ticks
        between it keeps its velocity, so it still moves smoothly. No bands
        steers every agent every tick.

        Raises:
            ValueError: If the radii do not rise from 0, or a period is
                below 1.
        """
        self._native.set_detail_bands(list(bands))

    def set_detail_focus(self, focus: Vector2 | None) -> None:
        """Measure the detail bands from `focus`, or steer everyone with `None`.

        Usually the camera centre, set each frame.
        """
        self._native.set_detail_focus(focus)

    def set_look(self, kind: int, look: SwarmLook) -> None:
        """Draw a kind's agents with `look` from the next `submit` on.

        Raises:
            ValueError: For an unknown kind.
        """
        scale = look.scale
        extent = max(
            math.hypot(frame.width * scale.x, frame.height * scale.y)
            for frame in look.frames
        )
        self._native.set_look(
            kind,
            len(look.frames),
            look.frame_rate,
            look.face_heading,
            look.offset,
            extent,
        )
        self._looks[kind] = look

    def submit(self, render_system: RenderSystem) -> None:
        """Queue every drawn kind's visible agents for this frame.

        Call from a scene's `render`, before the render system flushes; the
        base `Scene.render` flushes, so call this before it. Agents are
        culled against the camera's view as `Scene.render` culls sprites.
        """
        for kind, look in self._looks.items():
            render_system.submit_batches(
                partial(self._batches, kind, look), look.layer, look.z_index
            )

    def _batches(
        self, kind: int, look: SwarmLook, camera: Camera2D, viewport: Viewport
    ) -> list[RenderBatch]:
        view = camera.get_view_bounds()
        offset = camera.screen_offset(viewport)
        scale = (look.scale.x, look.scale.y)
        transformed = look.face_heading or scale != (1.0, 1.0)
        batches = []
        for frame, destinations, rotations in self._native.pack(
            kind,
            camera.zoom,
            offset.x,
            offset.y,
            view.x - 1,
            view.y - 1,
            view.x + view.width + 1,
            view.y + view.height + 1,
        ):
            batches.append(
                RenderBatch(
                    texture=look.frames[frame],
                    destinations=destinations,
                    rotations=(rotations or [0.0] * len(destinations))
                    if transformed
                    else [],
                    scales=[scale] * len(destinations) if transformed else [],
                    transforms_enabled=transformed,
                )
            )
        return batches

    def update(self, dt: float) -> None:
        """Steer and move every agent by one step.

        Args:
            dt: The step, in seconds.
        """
        self._native.tick(dt)

    def neighbour_counts(self) -> list[int]:
        """How many flockmates each live agent steered by last tick, in `ids()` order."""
        return list(self._native.neighbour_counts())
