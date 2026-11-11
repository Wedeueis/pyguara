"""Pymunk implementation of the physics engine adapter."""

import contextlib
import math
from dataclasses import dataclass
from typing import Any

import pymunk

from pyguara import native
from pyguara.common.types import Rect, Vector2
from pyguara.physics.protocols import IPhysicsBody
from pyguara.physics.types import (
    BodyType,
    CollisionLayer,
    JointType,
    PhysicsMaterial,
    RaycastHit,
    ShapeType,
)

# One 1/60s step lets a body jump velocity/60 pixels; at 600 px/s that is 10
# pixels, which clears a 10px wall outright. Substepping shortens the jump:
# measured against a 10px wall, substeps 1/2/4 stop a body up to roughly
# 200/400/900 px/s respectively. Four is kept as the default because the cost
# is far lower than once feared -- 0.65ms/update at 200 dynamic bodies, 2.5ms
# at 500, well under a 16.7ms frame -- while the extra headroom matters for
# knockback and explosion-flung props in a top-down game. Drop to 2 only when
# simulating many hundreds of fast bodies; fast projectiles should raycast
# rather than lean on the solver catching them.
DEFAULT_SUBSTEPS = 4

# Seconds a body must stay still before Chipmunk lets it sleep and stop
# consuming solver time. inf (Chipmunk's own default) never sleeps anything,
# so a room full of settled props and debris is simulated forever. Half a
# second is long enough not to sleep something a slow nudge is still moving.
# Any direct state write (position, velocity, impulse) wakes a body again.
DEFAULT_SLEEP_TIME_THRESHOLD = 0.5

# Ray queries are swept circles in Chipmunk. Keep the radius small: it
# widens what the ray can touch, including the caster's own collider.
RAYCAST_RADIUS = 1.0

# Fraction of any remaining overlap Chipmunk removes per 1/60s. Its own
# default is 10%, which loses to gravity: a character that lands 9px inside
# the floor comes out at about 0.04px a tick, so it sits visibly sunk for
# seconds. 30% clears it in a few frames and leaves a stack of boxes just as
# steady -- measured, no jitter and no drift at 30% or even 50%.
DEFAULT_PENETRATION_RECOVERY = 0.3


def _one_way_allows_contact(
    arbiter: pymunk.Arbiter, shape_a: pymunk.Shape, shape_b: pymunk.Shape
) -> bool:
    """Decide whether a one-way surface should resist this contact.

    Rejected per step from the pass-through side, rather than switched off
    once at first contact: a character that jumps up through a platform and
    lands on it never separates in between, so a one-shot decision would keep
    letting it fall through the top.

    The test is the contact normal, not the body's velocity. Velocity is zero
    at the apex of a jump, so a velocity test flips to solid while the
    character still overlaps the platform and ejects it.

    Args:
        arbiter: The pymunk arbiter for this contact.
        shape_a: First shape in the pair.
        shape_b: Second shape.

    Returns:
        True to let the contact resolve normally, False to pass through. The
        caller suppresses the response via `arbiter.process_collision`, which
        is what pymunk 7 honours -- a callback's return value is ignored.
    """
    for shape, sign in ((shape_a, 1.0), (shape_b, -1.0)):
        solid = getattr(shape, "pyguara_one_way_normal", None)
        if solid is None:
            continue

        # The arbiter normal runs from the first shape to the second, so it
        # already points platform -> other body when the platform is first,
        # and must be flipped when it is second.
        normal = arbiter.contact_point_set.normal
        towards_other_x = normal.x * sign
        towards_other_y = normal.y * sign

        # Positive means the other body sits on the solid face.
        if towards_other_x * solid[0] + towards_other_y * solid[1] <= 0:
            return False

    return True


def _sensor_entity_id(
    shape_a: pymunk.Shape,
    shape_b: pymunk.Shape,
    entity_a: Any,
    entity_b: Any,
) -> str | None:
    """Return the entity id owning the sensor shape in this pair, or None.

    The collision system needs the sensor identified, not merely a flag that
    one exists: the pair arrives in Chipmunk's own order, so "which side is
    the trigger" is otherwise a coin flip. When both shapes are sensors the
    first is reported -- two overlapping sensors is a degenerate case the
    event model does not distinguish anyway.
    """
    if shape_a.sensor:
        return str(entity_a)
    if shape_b.sensor:
        return str(entity_b)
    return None


def _scaled_gravity(scale: float) -> Any:
    """Build a velocity callback applying scaled gravity to one body.

    Chipmunk has no per-body gravity multiplier; the integration callback is
    the supported place to vary it. Everything else about the default
    integration -- damping, the mass term -- is left alone.

    Args:
        scale: Multiplier on world gravity for this body.

    Returns:
        A callback suitable for `pymunk.Body.velocity_func`.
    """

    def velocity_func(
        body: pymunk.Body, gravity: Any, damping: float, dt: float
    ) -> None:
        pymunk.Body.update_velocity(
            body, (gravity[0] * scale, gravity[1] * scale), damping, dt
        )

    return velocity_func


_FULL_MASK = 0xFFFFFFFF

# `NativeSolids.overlap`'s "certainly nothing there". Its other negative
# answers all mean "ask Chipmunk".
_CLEAR = -1


@dataclass(frozen=True, slots=True)
class _SolidsMirror:
    """A space's static boxes held natively. See `_static_solids`.

    Attributes:
        native: The `NativeSolids` holding the boxes.
        owners: Owner index -> entity id.
        index_of: Entity id -> owner index.
        sensor_free: Whether the space holds no sensor shape at all. A ray
            may be answered from the mirror only then, because the mirror
            leaves sensors out and a ray query can report one.
    """

    native: Any
    owners: list[int | str]
    index_of: dict[int | str, int]
    sensor_free: bool

    def index_for(self, entity_id: int | str | None) -> int:
        """Return the owner index to ignore, or -1 for none."""
        if entity_id is None:
            return -1
        return self.index_of.get(entity_id, -1)


class PymunkBodyAdapter:
    """Wrapper around pymunk.Body to conform to IPhysicsBody."""

    def __init__(
        self, body: pymunk.Body, static_moved: list[bool] | None = None
    ) -> None:
        """Initialize the adapter with a pymunk Body.

        Args:
            body: The pymunk body wrapped.
            static_moved: A one-element flag the engine shares with every
                adapter it makes, set when a *static* body is repositioned
                so the engine can drop what it derived from where static
                geometry was. A flag and not a callback on purpose: a
                bound method would make this adapter reference the engine,
                and a `RigidBody` holding the adapter is deep-copied when
                Studio snapshots a scene -- which then walked into the
                engine and every entity it knows.
        """
        self._body = body
        self._static_moved = static_moved

    def _moved(self) -> None:
        """Flag a reposition, if this body is static and anyone asked."""
        if (
            self._static_moved is not None
            and self._body.body_type == pymunk.Body.STATIC
        ):
            self._static_moved[0] = True

    @property
    def position(self) -> Vector2:
        """Get the body's world position."""
        return Vector2(self._body.position.x, self._body.position.y)

    @position.setter
    def position(self, value: Vector2) -> None:
        """Set the body's world position."""
        self._body.position = value.x, value.y
        self._moved()

    @property
    def rotation(self) -> float:
        """Get the body's rotation in degrees."""
        return math.degrees(self._body.angle)

    @rotation.setter
    def rotation(self, value: float) -> None:
        """Set the body's rotation in degrees."""
        self._body.angle = math.radians(value)
        self._moved()

    @property
    def velocity(self) -> Vector2:
        """Get the linear velocity."""
        return Vector2(self._body.velocity.x, self._body.velocity.y)

    @velocity.setter
    def velocity(self, value: Vector2) -> None:
        """Set the linear velocity."""
        self._body.velocity = value.x, value.y

    def apply_force(self, force: Vector2, point: Vector2 | None = None) -> None:
        """Apply a continuous force to the body."""
        p = (point.x, point.y) if point else (0, 0)
        self._body.apply_force_at_local_point((force.x, force.y), p)

    def apply_impulse(self, impulse: Vector2, point: Vector2 | None = None) -> None:
        """Apply an instant impulse to the body."""
        p = (point.x, point.y) if point else (0, 0)
        self._body.apply_impulse_at_local_point((impulse.x, impulse.y), p)


class PymunkEngine:
    """Pymunk backend implementation."""

    def __init__(
        self,
        substeps: int = DEFAULT_SUBSTEPS,
        penetration_recovery: float = DEFAULT_PENETRATION_RECOVERY,
        sleep_time_threshold: float = DEFAULT_SLEEP_TIME_THRESHOLD,
        accelerate: bool | None = None,
    ) -> None:
        """Initialize the Pymunk engine wrapper.

        Args:
            accelerate: Whether box and ray queries may be answered from a
                native mirror of the static geometry (see
                `_static_solids`). None follows the engine-wide
                `native_acceleration` switch; False never does; True does
                whenever the extension can be loaded. The answers are the
                same either way -- this exists so a test can hold the two
                paths side by side.
            penetration_recovery: Fraction of remaining overlap removed per
                1/60s, between 0 and 1. Chipmunk's own 10% is too weak to
                beat continuous gravity, leaving a landed character visibly
                sunk; too high and stacks jitter.
            substeps: How many solver steps one call to `update()` becomes.
                Chipmunk has no continuous collision detection, so a body
                moves `velocity * dt` in a straight jump each step and passes
                through anything thinner than that jump. Substepping shortens
                the jump proportionally: each doubling roughly doubles the
                speed a thin wall can stop.
            sleep_time_threshold: Seconds a body must be still before it is
                allowed to sleep and drop out of the solver. 0 disables
                sleeping (a body is then simulated forever, however idle).

        Raises:
            ValueError: If `substeps` is not positive. Zero would step the
                simulation not at all and negative is meaningless; both are
                far better caught here than as a frozen world. Also if
                `penetration_recovery` is outside (0, 1]: zero never separates
                overlapping bodies at all. Also if `sleep_time_threshold` is
                negative.
        """
        if not 0.0 < penetration_recovery <= 1.0:
            raise ValueError(
                f"penetration_recovery must be within (0, 1], got "
                f"{penetration_recovery}. It is the fraction of overlap "
                f"removed per 1/60s."
            )
        self._penetration_recovery = penetration_recovery
        if substeps <= 0:
            raise ValueError(
                f"substeps must be positive, got {substeps}. It is the number "
                f"of solver steps per update; 1 disables substepping."
            )
        self._substeps = substeps
        if sleep_time_threshold < 0.0:
            raise ValueError(
                f"sleep_time_threshold must be non-negative, got "
                f"{sleep_time_threshold}. It is seconds of stillness before a "
                f"body may sleep; 0 disables sleeping."
            )
        self._sleep_time_threshold = sleep_time_threshold
        self.space: pymunk.Space | None = None
        # Map entity_id -> PymunkBodyAdapter
        self._bodies: dict[int | str, PymunkBodyAdapter] = {}
        # Collision system for event routing (injected after construction)
        self._collision_system: Any | None = None
        self._accelerate = accelerate
        self._solids: _SolidsMirror | None = None
        # One element, shared with every body adapter: see
        # `PymunkBodyAdapter.__init__` for why it is not a callback.
        self._solids_stale: list[bool] = [True]

    def _mark_solids_stale(self) -> None:
        """Forget the native mirror; the next query rebuilds it."""
        self._solids_stale[0] = True

    def _static_solids(self) -> _SolidsMirror | None:
        """Return the native mirror of this space's solids, if it is exact.

        The mirror holds the boxes of static, unrotated, non-sensor box
        shapes. It exists only while those are the *only* solids in the
        space: one dynamic or kinematic body, one circle, one rotated
        wall, and this returns None and every query goes to Chipmunk as
        before. So it serves a world of level geometry -- which is what a
        character mover sweeps against -- and steps aside for anything
        richer rather than approximating it.

        Rebuilt lazily after anything that can change static geometry:
        `initialize`, `cleanup`, `create_body`, `destroy_body`,
        `add_shape`, and a static body being repositioned through its
        adapter. Geometry is read from each shape's cached bounding box,
        which is what Chipmunk's own queries test against, so a static
        body moved without a reindex is mirrored where Chipmunk still
        believes it is.

        Returns:
            The mirror, or None when the space cannot be mirrored exactly
            or acceleration is off.
        """
        if not self._solids_stale[0]:
            return self._solids
        self._solids_stale[0] = False
        self._solids = None
        if self.space is None or self._accelerate is False:
            return None
        extension = (
            native.native_module()
            if self._accelerate is None
            else native.require_extension("PymunkEngine(accelerate=True)")
        )
        if extension is None:
            return None

        rows: list[tuple[float, float, float, float, int, int, int]] = []
        owners: list[int | str] = []
        index_of: dict[int | str, int] = {}
        sensor_free = True
        for shape in self.space.shapes:
            if shape.sensor:
                sensor_free = False
                continue
            body = shape.body
            entity_id = getattr(body, "entity_id", None)
            if (
                body is None
                or entity_id is None
                or not getattr(shape, "pyguara_box", False)
                or body.body_type != pymunk.Body.STATIC
                or body.angle != 0.0
            ):
                return None
            owner = index_of.get(entity_id)
            if owner is None:
                owner = len(owners)
                index_of[entity_id] = owner
                owners.append(entity_id)
            box = shape.bb
            shape_filter = shape.filter
            rows.append(
                (
                    box.left,
                    box.bottom,
                    box.right,
                    box.top,
                    shape_filter.categories & _FULL_MASK,
                    shape_filter.mask & _FULL_MASK,
                    owner,
                )
            )
        self._solids = _SolidsMirror(
            extension.NativeSolids(rows), owners, index_of, sensor_free
        )
        return self._solids

    def initialize(self, gravity: Vector2) -> None:
        """Initialize the physics space with gravity."""
        self.space = pymunk.Space()
        self._mark_solids_stale()
        self.space.gravity = (gravity.x, gravity.y)
        # Chipmunk expresses this as the error *remaining* after one second.
        self.space.collision_bias = pow(1.0 - self._penetration_recovery, 60)
        # Chipmunk treats 0 here as "never sleep"; it stores it as inf.
        if self._sleep_time_threshold > 0.0:
            self.space.sleep_time_threshold = self._sleep_time_threshold

        # Setup collision handlers if collision system is already registered
        if self._collision_system:
            self._setup_collision_handlers()

    def cleanup(self) -> None:
        """Destroy the pymunk Space to prevent dangling callbacks."""
        if self.space:
            # Clear the default collision handler so callbacks cannot fire
            # while the space is being torn down. Tolerated if it fails: the
            # space may already be closing.
            with contextlib.suppress(Exception):
                self.space.on_collision(
                    begin=None, pre_solve=None, post_solve=None, separate=None
                )

            try:
                # Explicitly remove everything to ensure internal iterators don't run
                # during garbage collection
                if self.space.constraints:
                    self.space.remove(*self.space.constraints)
                if self.space.shapes:
                    self.space.remove(*self.space.shapes)
                if self.space.bodies:
                    self.space.remove(*self.space.bodies)
            except Exception:
                # Ignore errors during object removal
                pass

            self.space = None
            self._mark_solids_stale()
            self._bodies.clear()
            self._collision_system = None

    def set_collision_system(self, collision_system: Any) -> None:
        """Register the CollisionSystem for event routing.

        Args:
            collision_system: CollisionSystem instance to handle callbacks.
        """
        self._collision_system = collision_system

        # Setup handlers if space is already initialized
        if self.space:
            self._setup_collision_handlers()

    def _setup_collision_handlers(self) -> None:
        """Configure pymunk collision handlers to route to CollisionSystem."""
        if not self.space:
            return

        # Default collision handler for all collision types
        # Pymunk 7.0+ uses on_collision(None, None) for default handler
        self.space.on_collision(
            begin=self._on_pymunk_begin,  # type: ignore[arg-type]
            pre_solve=self._on_pymunk_persist,  # type: ignore[arg-type]
            separate=self._on_pymunk_end,
        )

    def _on_pymunk_begin(
        self, arbiter: pymunk.Arbiter, space: pymunk.Space, data: dict
    ) -> bool:
        """Pymunk callback when collision begins.

        Args:
            arbiter: Pymunk collision arbiter with collision data.
            space: Pymunk space.
            data: User data dict.

        Returns:
            True to process collision, False to ignore.
        """
        shape_a, shape_b = arbiter.shapes

        if not _one_way_allows_contact(arbiter, shape_a, shape_b):
            # pymunk 7 ignores the callback's return value; `process_collision`
            # is what actually suppresses the response.
            arbiter.process_collision = False
            return False

        if not self._collision_system:
            return True

        entity_a = getattr(shape_a.body, "entity_id", None)
        entity_b = getattr(shape_b.body, "entity_id", None)

        if entity_a is None or entity_b is None:
            return True

        # Extract collision details
        contact_point_set = arbiter.contact_point_set
        if contact_point_set.points:
            contact = contact_point_set.points[0]
            point = Vector2(contact.point_a.x, contact.point_a.y)
            normal = Vector2(contact_point_set.normal.x, contact_point_set.normal.y)
        else:
            point = Vector2.zero()
            normal = Vector2(0, 1)

        impulse = arbiter.total_impulse.length
        sensor_id = _sensor_entity_id(shape_a, shape_b, entity_a, entity_b)

        process = self._collision_system.on_collision_begin(
            str(entity_a), str(entity_b), point, normal, impulse, sensor_id
        )

        # The collision system returns False to mean "report this but do not
        # resolve it physically" -- how a trigger that is not a sensor is meant
        # to work. pymunk 7 ignores a callback's return value, so that has to
        # be expressed through the arbiter or it does nothing at all.
        if not process:
            arbiter.process_collision = False

        return bool(process)

    def _on_pymunk_persist(
        self, arbiter: pymunk.Arbiter, space: pymunk.Space, data: dict
    ) -> bool:
        """Pymunk callback during collision (each frame).

        Args:
            arbiter: Pymunk collision arbiter with collision data.
            space: Pymunk space.
            data: User data dict.

        Returns:
            True to continue processing, False to ignore.
        """
        if not self._collision_system:
            return True

        shape_a, shape_b = arbiter.shapes
        entity_a = getattr(shape_a.body, "entity_id", None)
        entity_b = getattr(shape_b.body, "entity_id", None)

        if entity_a is None or entity_b is None:
            return True

        # Extract collision details
        contact_point_set = arbiter.contact_point_set
        if contact_point_set.points:
            contact = contact_point_set.points[0]
            point = Vector2(contact.point_a.x, contact.point_a.y)
            normal = Vector2(contact_point_set.normal.x, contact_point_set.normal.y)
        else:
            point = Vector2.zero()
            normal = Vector2(0, 1)

        impulse = arbiter.total_impulse.length
        sensor_id = _sensor_entity_id(shape_a, shape_b, entity_a, entity_b)

        process = self._collision_system.on_collision_persist(
            str(entity_a), str(entity_b), point, normal, impulse, sensor_id
        )

        # The collision system returns False to mean "report this but do not
        # resolve it physically" -- how a trigger that is not a sensor is meant
        # to work. pymunk 7 ignores a callback's return value, so that has to
        # be expressed through the arbiter or it does nothing at all.
        if not process:
            arbiter.process_collision = False

        return bool(process)

    def _on_pymunk_end(
        self, arbiter: pymunk.Arbiter, space: pymunk.Space, data: dict
    ) -> None:
        """Pymunk callback when collision ends.

        Args:
            arbiter: Pymunk collision arbiter.
            space: Pymunk space.
            data: User data dict.
        """
        if not self._collision_system:
            return

        shape_a, shape_b = arbiter.shapes
        entity_a = getattr(shape_a.body, "entity_id", None)
        entity_b = getattr(shape_b.body, "entity_id", None)

        if entity_a is None or entity_b is None:
            return

        sensor_id = _sensor_entity_id(shape_a, shape_b, entity_a, entity_b)

        self._collision_system.on_collision_end(str(entity_a), str(entity_b), sensor_id)

    def update(self, delta_time: float) -> None:
        """Step the physics simulation forward.

        Splits the tick into `substeps` equal solver steps. The step size is
        what decides whether a fast body is caught or passes through a thin
        collider, and it is deliberately derived from a fixed count rather
        than from the bodies' speeds: this engine supports deterministic
        replay, so the number of steps must not depend on the simulation's
        own state.

        Args:
            delta_time: Seconds to advance, normally one fixed tick.
        """
        if not self.space:
            return
        step = delta_time / self._substeps
        for _ in range(self._substeps):
            self.space.step(step)

    def create_body(
        self,
        entity_id: int | str,
        body_type: BodyType,
        position: Vector2,
        mass: float = 1.0,
        fixed_rotation: bool = False,
        gravity_scale: float = 1.0,
    ) -> IPhysicsBody:
        """Create and register a new physics body.

        Args:
            entity_id: Owning entity, stored on the body for collision routing.
            body_type: Static, kinematic or dynamic.
            position: World position.
            mass: Mass for dynamic bodies.
            fixed_rotation: Stop the body rotating. A character box that can
                tip over is almost never wanted; this is how you keep one
                upright without freezing its position.
            gravity_scale: Multiplier on world gravity for this body alone.
                0.0 floats, 2.0 falls twice as fast -- the usual way to give
                a character a floaty jump or a fast fall.
        """
        if not self.space:
            raise RuntimeError(
                "Physics engine not initialized. Call initialize(gravity) first."
            )

        pm_type = pymunk.Body.DYNAMIC
        if body_type == BodyType.STATIC:
            pm_type = pymunk.Body.STATIC
        elif body_type == BodyType.KINEMATIC:
            pm_type = pymunk.Body.KINEMATIC

        # For dynamic bodies, set mass and moment (moment will be recalculated when shape is added)
        # Use a default moment based on mass; actual moment is set when shape is attached
        if pm_type == pymunk.Body.DYNAMIC:
            # Use a placeholder moment; it will be overwritten by add_shape
            moment = pymunk.moment_for_box(mass, (32, 32))
            body = pymunk.Body(mass=mass, moment=moment, body_type=pm_type)
        else:
            body = pymunk.Body(body_type=pm_type)

        body.position = (position.x, position.y)

        if pm_type == pymunk.Body.DYNAMIC:
            if fixed_rotation:
                # Infinite moment of inertia: torque produces no angular
                # acceleration, so the body cannot be turned. Recorded on the
                # body as well, because attaching a shape re-derives mass and
                # moment from its density and would undo this.
                body.moment = float("inf")
            body.pyguara_fixed_rotation = fixed_rotation
            if gravity_scale != 1.0:
                body.velocity_func = _scaled_gravity(gravity_scale)

        # Store entity ID on body for collisions
        body.entity_id = entity_id

        self.space.add(body)
        self._mark_solids_stale()

        adapter = PymunkBodyAdapter(body, self._solids_stale)
        self._bodies[entity_id] = adapter
        return adapter

    def destroy_body(self, body_handle: IPhysicsBody) -> None:
        """Remove a body and its attached shapes from the simulation.

        Pymunk's own `body.shapes` is authoritative for what's attached, so
        no separate adapter-level shape tracking is needed.
        """
        if not self.space:
            return

        if not isinstance(body_handle, PymunkBodyAdapter):
            raise TypeError(
                f"Invalid body handle for Pymunk backend: expected PymunkBodyAdapter, "
                f"got {type(body_handle).__name__}"
            )

        body = body_handle._body
        # Constraints must leave the space before the body they anchor, or
        # pymunk raises. A JointSystem normally tears its own joints down on
        # EntityDestroyed, but a body destroyed for any other reason (or in a
        # different order) would otherwise strand them.
        for constraint in list(body.constraints):
            with contextlib.suppress(Exception):
                self.space.remove(constraint)
        for shape in list(body.shapes):
            self.space.remove(shape)
        self.space.remove(body)
        self._mark_solids_stale()
        self._bodies.pop(body.entity_id, None)

    def add_shape(
        self,
        body_handle: IPhysicsBody,
        shape_type: ShapeType,
        dimensions: list[float],
        offset: Vector2,
        material: PhysicsMaterial,
        collision_layer: CollisionLayer,
        is_sensor: bool,
        one_way: bool = False,
        one_way_normal: Vector2 | None = None,
    ) -> Any:
        """Attach a collision shape to a body.

        Args:
            body_handle: The body to attach to.
            shape_type: Circle, box, segment or polygon.
            dimensions: Radius, or width and height.
            offset: Local offset from the body's centre.
            material: Friction, restitution and density.
            collision_layer: Category, mask and group filtering.
            is_sensor: Detect overlaps without blocking.
            one_way: Solid from one side only.
            one_way_normal: Which side is solid, in world space. Defaults to
                `(0, -1)` when `one_way` is set.

        Returns:
            The pymunk shape, or None if there is no space or shape type.
        """
        if not self.space:
            return None

        if not isinstance(body_handle, PymunkBodyAdapter):
            raise TypeError(
                f"Invalid body handle for Pymunk backend: expected PymunkBodyAdapter, "
                f"got {type(body_handle).__name__}"
            )

        body = body_handle._body
        shape: pymunk.Shape | None = None

        if shape_type == ShapeType.CIRCLE:
            radius = dimensions[0]
            shape = pymunk.Circle(body, radius, (offset.x, offset.y))
        elif shape_type == ShapeType.BOX:
            width, height = dimensions
            # Built from vertices rather than `Poly.create_box`, because
            # only the `Poly` constructor takes a transform and the
            # transform is what applies `offset`. `create_box` always
            # centres on the body's origin, so a collider that does not sit
            # on its entity's origin simulated in the wrong place while
            # `debug_draw` drew it in the right one. BOX is the default
            # shape type, so this was the common path -- unnoticed only
            # because nothing in the engine or the demos sets an offset.
            half_width, half_height = width / 2.0, height / 2.0
            shape = pymunk.Poly(
                body,
                [
                    (-half_width, -half_height),
                    (-half_width, half_height),
                    (half_width, half_height),
                    (half_width, -half_height),
                ],
                pymunk.Transform(tx=offset.x, ty=offset.y),
            )
        else:
            # SEGMENT and POLYGON are in `ShapeType` and are not handled
            # here. Before this they fell through with `shape` still None,
            # so `add_shape` returned None having attached nothing: a
            # collider that silently does not exist, on a body that still
            # moves and still reports as physical. Raising is the lesser
            # surprise.
            raise NotImplementedError(
                f"{shape_type.name} colliders are not implemented by the "
                f"pymunk backend. Supported: "
                f"{ShapeType.CIRCLE.name}, {ShapeType.BOX.name}."
            )

        if shape:
            shape.density = material.density
            shape.friction = material.friction
            shape.elasticity = material.restitution
            shape.sensor = is_sensor

            # Bitmask filtering
            filter = pymunk.ShapeFilter(
                categories=collision_layer.category,
                mask=collision_layer.mask,
                group=collision_layer.group,
            )
            shape.filter = filter

            # Recorded on the shape so the pre-solve handler can find it: it
            # sees pymunk shapes, not PyGuara components.
            if one_way:
                solid = one_way_normal if one_way_normal is not None else Vector2(0, -1)
                shape.pyguara_one_way_normal = (solid.x, solid.y)

            # What `_static_solids` may mirror as an axis-aligned box: built
            # here from four axis-aligned vertices, so its cached bounding
            # box *is* the shape while its body is unrotated.
            shape.pyguara_box = shape_type == ShapeType.BOX

            self.space.add(shape)
            self._mark_solids_stale()

            # Setting density makes Chipmunk recompute the body's mass and
            # moment from its shapes, which silently discards the infinite
            # moment that fixed_rotation asked for.
            if getattr(body, "pyguara_fixed_rotation", False):
                body.moment = float("inf")

            return shape

    def raycast(
        self,
        start: Vector2,
        end: Vector2,
        mask: int = 0xFFFFFFFF,
        ignore_entity_id: int | str | None = None,
    ) -> RaycastHit | None:
        """Perform a raycast query.

        Args:
            start: Ray origin in world space.
            end: Ray end in world space.
            mask: Collision mask; shapes outside it are ignored.
            ignore_entity_id: Skip hits on this entity's own body.

        Returns:
            The nearest hit that is not excluded, or None.
        """
        if not self.space:
            return None

        # A ray that certainly clears every static box misses in Chipmunk
        # too. Only a miss is answered here; a possible hit goes on to
        # Chipmunk, which owns the hit point and the normal.
        mirror = self._static_solids()
        if (
            mirror is not None
            and mirror.sensor_free
            and 0 <= mask <= _FULL_MASK
            and mirror.native.segment_clear(
                start.x, start.y, end.x, end.y, RAYCAST_RADIUS, mask
            )
        ):
            return None

        shape_filter = pymunk.ShapeFilter(mask=mask)

        if ignore_entity_id is None:
            query = self.space.segment_query_first(
                (start.x, start.y), (end.x, end.y), RAYCAST_RADIUS, shape_filter
            )
            return self._to_hit(query, start)

        # segment_query_first cannot exclude one body, so take every hit and
        # return the nearest that is not the caster's own. A character casting
        # for the ground under its feet starts the ray at its own edge, and a
        # self-hit reads as permanently grounded.
        hits = self.space.segment_query(
            (start.x, start.y), (end.x, end.y), RAYCAST_RADIUS, shape_filter
        )
        for hit in sorted(hits, key=lambda h: h.alpha):
            if getattr(hit.shape.body, "entity_id", None) != ignore_entity_id:
                return self._to_hit(hit, start)
        return None

    @staticmethod
    def _to_hit(query: Any, start: Vector2) -> RaycastHit | None:
        """Convert a pymunk query result into a `RaycastHit`.

        Args:
            query: A pymunk segment query result, or None.
            start: The ray origin, for computing distance.

        Returns:
            The hit, or None when the query found nothing.
        """
        if not query:
            return None
        point = Vector2(query.point.x, query.point.y)
        return RaycastHit(
            position=point,
            normal=Vector2(query.normal.x, query.normal.y),
            distance=start.distance_to(point),
            entity_id=getattr(query.shape.body, "entity_id", None),
        )

    @staticmethod
    def _probe_shape(kind: str, *args: Any, mask: int) -> Any:
        """Build a free-floating probe shape for a `shape_query`.

        The probe body is kinematic and never added to the space; it exists
        only to give the shape a transform. `pymunk.Circle` / `Poly` keep a
        Python reference to it, so it lives as long as the shape does.

        Args:
            kind: "box" (args: centre, half_extents) or "circle" (args:
                centre, radius).
            args: Geometry for `kind`, as above.
            mask: Collision mask baked into the probe's filter so Chipmunk
                does the category filtering, exactly as `raycast` does.

        Returns:
            A pymunk shape ready to pass to `space.shape_query`.
        """
        body = pymunk.Body(body_type=pymunk.Body.KINEMATIC)
        if kind == "box":
            centre, half_extents = args
            body.position = (centre.x, centre.y)
            shape: pymunk.Shape = pymunk.Poly.create_box(
                body, (half_extents.x * 2, half_extents.y * 2)
            )
        else:  # circle
            centre, radius = args
            body.position = (centre.x, centre.y)
            shape = pymunk.Circle(body, radius)
        shape.filter = pymunk.ShapeFilter(mask=mask)
        return shape

    @staticmethod
    def _solid_ids(shapes: Any, ignore_entity_id: int | str | None) -> list[int | str]:
        """Entity ids of the non-sensor shapes in a query result.

        Order is preserved and each entity appears once, so a body carrying
        several shapes is reported a single time.

        Args:
            shapes: Iterable of pymunk shapes (or None entries, tolerated).
            ignore_entity_id: Entity to leave out, usually the query source.

        Returns:
            The distinct owning entity ids, first occurrence order.
        """
        seen: set[int | str] = set()
        ids: list[int | str] = []
        for shape in shapes:
            if shape is None or shape.sensor:
                continue
            entity_id = getattr(shape.body, "entity_id", None)
            if entity_id is None or entity_id == ignore_entity_id or entity_id in seen:
                continue
            seen.add(entity_id)
            ids.append(entity_id)
        return ids

    def overlap_box(
        self,
        centre: Vector2,
        half_extents: Vector2,
        mask: int = 0xFFFFFFFF,
        ignore_entity_id: int | str | None = None,
    ) -> int | str | None:
        """Report which entity's solid shape an axis-aligned box overlaps.

        Args:
            centre: Box centre in world space.
            half_extents: Half width and half height.
            mask: Collision mask; shapes outside it are ignored.
            ignore_entity_id: Body to disregard, normally the mover itself.

        Returns:
            The entity id of the first solid, non-sensor shape found
            overlapping, or None if the box is clear.
        """
        if not self.space:
            return None

        mirror = self._static_solids()
        if mirror is not None and 0 <= mask <= _FULL_MASK:
            found: int = mirror.native.overlap(
                centre.x,
                centre.y,
                half_extents.x,
                half_extents.y,
                mask,
                mirror.index_for(ignore_entity_id),
            )
            if found == _CLEAR:
                return None
            if found >= 0:
                return mirror.owners[found]
            # Too close to call, or several owners: Chipmunk decides.
        return self._overlap_box_exact(centre, half_extents, mask, ignore_entity_id)

    def _overlap_box_exact(
        self,
        centre: Vector2,
        half_extents: Vector2,
        mask: int,
        ignore_entity_id: int | str | None,
    ) -> int | str | None:
        """`overlap_box` as Chipmunk answers it, with no mirror involved."""
        assert self.space is not None
        probe = self._probe_shape("box", centre, half_extents, mask=mask)
        for hit in self.space.shape_query(probe):
            if hit.shape is None or hit.shape.sensor:
                continue
            entity_id = getattr(hit.shape.body, "entity_id", None)
            if entity_id == ignore_entity_id:
                continue
            return entity_id
        return None

    def sweep_box(
        self,
        position: Vector2,
        half_extents: Vector2,
        delta: Vector2,
        remainder: Vector2,
        ignore_entity_id: int | str | None = None,
    ) -> tuple[float, float, float, float, int | str | None, int | str | None] | None:
        """Run a whole `CharacterMover.move` natively, when that is exact.

        The mover's per-pixel loop asks `overlap_box` once per pixel per
        axis. Against mirrored static geometry the entire loop -- both
        axes, the rounding, the remainder -- runs in one native call.

        Args:
            position: Current centre of the box.
            half_extents: The *probe's* half extents, skin already removed.
            delta: Desired movement.
            remainder: Sub-pixel motion carried in.
            ignore_entity_id: Body to disregard.

        Returns:
            `(x, y, remainder_x, remainder_y, blocking_x, blocking_y)`, or
            None when this world cannot be swept natively or a probe on
            the way was too close to call -- in which case the caller
            runs its own loop and reaches the same answer the slow way.
        """
        mirror = self._static_solids()
        if mirror is None:
            return None
        # The loop this replaces does arithmetic on whatever it is given,
        # so an integer position stays an integer through it. Anything
        # that is not a plain float or int is left to that loop.
        kinds = (
            type(position.x),
            type(position.y),
            type(delta.x),
            type(delta.y),
            type(remainder.x),
            type(remainder.y),
        )
        for kind in kinds:
            if kind is not float and kind is not int:
                return None
        swept = mirror.native.sweep(
            position.x,
            position.y,
            half_extents.x,
            half_extents.y,
            delta.x,
            delta.y,
            remainder.x,
            remainder.y,
            _FULL_MASK,
            mirror.index_for(ignore_entity_id),
        )
        if swept is None:
            return None
        x, y, remainder_x, remainder_y, found_x, found_y = swept
        blocking_x: int | str | None = None
        blocking_y: int | str | None = None
        if found_x >= 0:
            blocking_x = mirror.owners[found_x]
        elif found_x != _CLEAR:
            # Several owners overlap the blocked pixel. Which one Chipmunk
            # names depends on its index, so ask it about that one pixel.
            step = 1.0 if remainder.x + delta.x > 0 else -1.0
            blocking_x = self._overlap_box_exact(
                Vector2(x + step, position.y),
                half_extents,
                _FULL_MASK,
                ignore_entity_id,
            )
            if blocking_x is None:
                return None
        if found_y >= 0:
            blocking_y = mirror.owners[found_y]
        elif found_y != _CLEAR:
            step = 1.0 if remainder.y + delta.y > 0 else -1.0
            blocking_y = self._overlap_box_exact(
                Vector2(x, y + step), half_extents, _FULL_MASK, ignore_entity_id
            )
            if blocking_y is None:
                return None
        # Give back the types the loop would have: an int coordinate plus
        # whole steps is an int, and an int remainder plus an int distance
        # stays one unless a block reset it to 0.0.
        if kinds[0] is int:
            x = int(x)
        if kinds[1] is int:
            y = int(y)
        if kinds[2] is int and kinds[4] is int and blocking_x is None:
            remainder_x = int(remainder_x)
        if kinds[3] is int and kinds[5] is int and blocking_y is None:
            remainder_y = int(remainder_y)
        return x, y, remainder_x, remainder_y, blocking_x, blocking_y

    def step_bodies(
        self,
        rows: list[
            tuple[
                float,
                float,
                float,
                float,
                float,
                float,
                float,
                float,
                float,
                float,
                int | str,
            ]
        ],
        delta_time: float,
        skin: float,
    ) -> list[tuple[float, float, float, float] | None] | None:
        """Run `step_body` for many bodies in one native call, when exact.

        `sweep_box` saves the per-pixel probes of one move; this saves the
        Python around each move as well -- the bounds, the scaled velocity,
        the result object -- which at 200 enemies was most of what a
        top-down step still cost once the probes were native.

        Args:
            rows: Per body, `(centre_x, centre_y, offset_x, offset_y, half_x,
                half_y, velocity_x, velocity_y, remainder_x, remainder_y,
                entity_id)`: the box centre and offset as `collider_bounds`
                gives them, and the half extents before the skin.
            delta_time: Length of the step in seconds.
            skin: What the mover shrinks its probe by on each side.

        Returns:
            Per row, the body's new `(x, y, remainder_x, remainder_y)` --
            the position already less the offset -- or None for a body
            that must be stepped the ordinary way. None for the whole call
            when this world has no exact mirror.
        """
        mirror = self._static_solids()
        if mirror is None:
            return None
        steps: list[tuple[float, float, float, float] | None] = (
            mirror.native.step_bodies(
                rows, mirror.index_of, delta_time, skin, _FULL_MASK
            )
        )
        return steps

    def overlap_box_all(
        self,
        centre: Vector2,
        half_extents: Vector2,
        mask: int = 0xFFFFFFFF,
        ignore_entity_id: int | str | None = None,
    ) -> list[int | str]:
        """Report every entity whose solid shape an axis-aligned box overlaps.

        Args:
            centre: Box centre in world space.
            half_extents: Half width and half height.
            mask: Collision mask; shapes outside it are ignored.
            ignore_entity_id: Body to disregard.

        Returns:
            Distinct entity ids of the solid, non-sensor shapes the box
            overlaps. Empty when the box is clear.
        """
        if not self.space:
            return []
        probe = self._probe_shape("box", centre, half_extents, mask=mask)
        return self._solid_ids(
            (info.shape for info in self.space.shape_query(probe)), ignore_entity_id
        )

    def overlap_circle(
        self,
        centre: Vector2,
        radius: float,
        mask: int = 0xFFFFFFFF,
        ignore_entity_id: int | str | None = None,
    ) -> list[int | str]:
        """Report every entity whose solid shape a circle overlaps.

        Args:
            centre: Circle centre in world space.
            radius: Circle radius.
            mask: Collision mask; shapes outside it are ignored.
            ignore_entity_id: Body to disregard, normally the source.

        Returns:
            Distinct entity ids of the solid, non-sensor shapes the circle
            overlaps. Empty when nothing is in range.
        """
        if not self.space:
            return []
        probe = self._probe_shape("circle", centre, radius, mask=mask)
        return self._solid_ids(
            (info.shape for info in self.space.shape_query(probe)), ignore_entity_id
        )

    def point_query(
        self,
        point: Vector2,
        mask: int = 0xFFFFFFFF,
        ignore_entity_id: int | str | None = None,
    ) -> list[int | str]:
        """Report every entity whose solid shape contains a world point.

        Args:
            point: The world-space point to test.
            mask: Collision mask; shapes outside it are ignored.
            ignore_entity_id: Body to disregard.

        Returns:
            Distinct entity ids under the point, most-enclosed first (the
            shape the point is furthest inside comes first). Empty when the
            point is in open space.
        """
        if not self.space:
            return []
        shape_filter = pymunk.ShapeFilter(mask=mask)
        infos = [
            info
            for info in self.space.point_query((point.x, point.y), 0.0, shape_filter)
            if info.distance <= 0.0
        ]
        infos.sort(key=lambda info: info.distance)
        return self._solid_ids((info.shape for info in infos), ignore_entity_id)

    def region_query(
        self,
        bounds: Rect,
        mask: int = 0xFFFFFFFF,
        ignore_entity_id: int | str | None = None,
    ) -> list[int | str]:
        """Report every entity whose *bounding box* overlaps a rectangle.

        Broad-phase only -- this compares axis-aligned bounding boxes, not
        the shapes, so a circle or rotated polygon whose box reaches into
        `bounds` is reported even when the shape itself does not.

        Args:
            bounds: World-space rectangle to test against.
            mask: Collision mask; shapes outside it are ignored.
            ignore_entity_id: Body to disregard.

        Returns:
            Distinct entity ids whose bounding box overlaps `bounds`. Empty
            when the rectangle is clear.
        """
        if not self.space:
            return []
        shape_filter = pymunk.ShapeFilter(mask=mask)
        # Rect.top is the smaller y (screen space is y-down); pymunk.BB wants
        # bottom <= top numerically.
        bb = pymunk.BB(bounds.left, bounds.top, bounds.right, bounds.bottom)
        return self._solid_ids(self.space.bb_query(bb, shape_filter), ignore_entity_id)

    def raycast_all(
        self,
        start: Vector2,
        end: Vector2,
        mask: int = 0xFFFFFFFF,
        ignore_entity_id: int | str | None = None,
    ) -> list[RaycastHit]:
        """Cast a ray and return every shape along it, nearest first.

        Args:
            start: Ray origin in world space.
            end: Ray end in world space.
            mask: Collision mask; shapes outside it are ignored.
            ignore_entity_id: Skip hits on this entity's own body.

        Returns:
            One `RaycastHit` per entity the segment crosses, ordered by
            distance from `start`. A multi-shape entity yields its nearest
            hit only. Empty when the ray hits nothing.
        """
        if not self.space:
            return []
        shape_filter = pymunk.ShapeFilter(mask=mask)
        hits = self.space.segment_query(
            (start.x, start.y), (end.x, end.y), RAYCAST_RADIUS, shape_filter
        )
        result: list[RaycastHit] = []
        seen: set[int | str | None] = set()
        for hit in sorted(hits, key=lambda h: h.alpha):
            if hit.shape is None or hit.shape.sensor:
                continue
            entity_id = getattr(hit.shape.body, "entity_id", None)
            if entity_id == ignore_entity_id or entity_id in seen:
                continue
            seen.add(entity_id)
            converted = self._to_hit(hit, start)
            if converted is not None:
                result.append(converted)
        return result

    def create_joint(
        self,
        body_a: IPhysicsBody,
        body_b: IPhysicsBody,
        joint_type: JointType,
        anchor_a: Vector2,
        anchor_b: Vector2,
        min_distance: float,
        max_distance: float,
        stiffness: float,
        damping: float,
        max_force: float,
        collide_connected: bool,
    ) -> Any:
        """Create a pymunk constraint between two bodies.

        Args:
            body_a: First physics body.
            body_b: Second physics body.
            joint_type: Type of joint to create.
            anchor_a: Local anchor point on body A.
            anchor_b: Local anchor point on body B.
            min_distance: Minimum distance for distance/slider joints.
            max_distance: Maximum distance for distance/slider joints.
            stiffness: Spring stiffness coefficient.
            damping: Spring damping coefficient.
            max_force: Maximum force the joint can apply (0 = infinite).
            collide_connected: Whether connected bodies can collide.

        Returns:
            Pymunk constraint object.
        """
        if not self.space:
            return None

        if not isinstance(body_a, PymunkBodyAdapter) or not isinstance(
            body_b, PymunkBodyAdapter
        ):
            raise TypeError(
                f"Invalid body handles for Pymunk backend: expected PymunkBodyAdapter, "
                f"got {type(body_a).__name__} and {type(body_b).__name__}"
            )

        pm_body_a = body_a._body
        pm_body_b = body_b._body

        constraint: pymunk.Constraint | None = None

        if joint_type == JointType.PIN:
            # Pin joint (revolute) - allows rotation around shared point
            constraint = pymunk.PinJoint(
                pm_body_a, pm_body_b, (anchor_a.x, anchor_a.y), (anchor_b.x, anchor_b.y)
            )

        elif joint_type == JointType.DISTANCE:
            # Distance joint - maintains fixed or bounded distance
            if min_distance == max_distance:
                # Fixed distance - use damped spring with high stiffness
                constraint = pymunk.DampedSpring(
                    pm_body_a,
                    pm_body_b,
                    (anchor_a.x, anchor_a.y),
                    (anchor_b.x, anchor_b.y),
                    rest_length=min_distance,
                    stiffness=10000.0,  # Very stiff for rigid connection
                    damping=100.0,
                )
            else:
                # Bounded distance - use slide joint
                constraint = pymunk.SlideJoint(
                    pm_body_a,
                    pm_body_b,
                    (anchor_a.x, anchor_a.y),
                    (anchor_b.x, anchor_b.y),
                    min_distance,
                    max_distance,
                )

        elif joint_type == JointType.SPRING:
            # Spring-damper joint
            constraint = pymunk.DampedSpring(
                pm_body_a,
                pm_body_b,
                (anchor_a.x, anchor_a.y),
                (anchor_b.x, anchor_b.y),
                rest_length=min_distance,  # Use min_distance as rest length
                stiffness=stiffness,
                damping=damping,
            )

        elif joint_type == JointType.SLIDER:
            # Slider/prismatic joint
            constraint = pymunk.SlideJoint(
                pm_body_a,
                pm_body_b,
                (anchor_a.x, anchor_a.y),
                (anchor_b.x, anchor_b.y),
                min_distance,
                max_distance,
            )

        elif joint_type == JointType.GEAR:
            # Gear joint - links rotation
            constraint = pymunk.GearJoint(pm_body_a, pm_body_b, phase=0.0, ratio=1.0)

        elif joint_type == JointType.MOTOR:
            # Simple motor - applies rotational force
            constraint = pymunk.SimpleMotor(pm_body_a, pm_body_b, rate=0.0)

        if constraint:
            # Apply max force limit if specified
            if max_force > 0:
                constraint.max_force = max_force

            # Set collision behavior
            constraint.collide_bodies = collide_connected

            # Add to space
            self.space.add(constraint)

        return constraint

    def destroy_joint(self, joint_handle: Any) -> None:
        """Remove a joint from the simulation.

        Args:
            joint_handle: Pymunk constraint object to remove.
        """
        if self.space and joint_handle:
            # The joint may already have been removed with its bodies.
            with contextlib.suppress(Exception):
                self.space.remove(joint_handle)
