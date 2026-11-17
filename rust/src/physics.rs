//! A Rapier world behind `RapierEngine` (`pyguara/physics/backends/rapier_impl.py`).
//!
//! The second physics backend of roadmap item 6e, built to the contract the
//! pymunk one keeps, in pixels and seconds. Bodies and colliders carry an
//! owner slot that Python maps to an entity id, so nothing here knows what
//! an entity is.
//!
//! Three places where Chipmunk's behaviour is reproduced on purpose:
//!
//! - Friction and restitution combine by multiplying, as Chipmunk does, not
//!   by Rapier's default average.
//! - A force lasts one solver step, as Chipmunk clears `force` after each
//!   `space.step`; with substeps that is the first substep only.
//! - Two shapes in the same non-zero group never touch, which Rapier's
//!   group bits cannot say, so a hook filters those pairs.
//!
//! Queries read the broad phase, which only a step refreshes. A change since
//! the last step -- a body created, moved or removed -- is flushed with a
//! collision pass before the next query, so a query sees the world as it
//! now is, as Chipmunk's does.

use std::collections::{HashMap, HashSet};

use pyo3::exceptions::{PyKeyError, PyValueError};
use pyo3::prelude::*;
use rapier2d_f64::parry::bounding_volume::Aabb;
use rapier2d_f64::parry::query::intersection_test;
use rapier2d_f64::parry::shape::{Ball, Cuboid};
use rapier2d_f64::prelude::*;

/// Mask that a query accepts everything with.
const FULL_MASK: u32 = u32::MAX;

/// Pixels in one of Rapier's length units: its tolerances are tuned for
/// metre-sized bodies, and the engine's are tens of pixels.
const PIXELS_PER_UNIT: f64 = 100.0;

fn pack(id: u32, generation: u32) -> u64 {
    (u64::from(generation) << 32) | u64::from(id)
}

fn unpack(handle: u64) -> (u32, u32) {
    (handle as u32, (handle >> 32) as u32)
}

fn owner_of(user_data: u128) -> u64 {
    user_data as u64
}

fn group_of(user_data: u128) -> u32 {
    (user_data >> 64) as u32
}

/// A pair of colliders, smaller handle first.
type Pair = (ColliderHandle, ColliderHandle);

fn pair(first: ColliderHandle, second: ColliderHandle) -> Pair {
    if first.into_raw_parts() <= second.into_raw_parts() {
        (first, second)
    } else {
        (second, first)
    }
}

fn collider_key(handle: ColliderHandle) -> u64 {
    let (id, generation) = handle.into_raw_parts();
    pack(id, generation)
}

/// Drops contacts between shapes in the same non-zero group, and pairs the
/// collision system asked not to resolve.
struct Filter<'a> {
    suppressed: &'a HashSet<Pair>,
}

impl Filter<'_> {
    fn allows(&self, context: &PairFilterContext) -> bool {
        let first = group_of(context.colliders[context.collider1].user_data);
        let second = group_of(context.colliders[context.collider2].user_data);
        if first != 0 && first == second {
            return false;
        }
        !self.suppressed.contains(&pair(context.collider1, context.collider2))
    }
}

impl PhysicsHooks for Filter<'_> {
    fn filter_contact_pair(&self, context: &PairFilterContext) -> Option<SolverFlags> {
        self.allows(context).then_some(SolverFlags::COMPUTE_RIGID_IMPULSES)
    }

    fn filter_intersection_pair(&self, context: &PairFilterContext) -> bool {
        // A sensor reports its overlaps whatever the collision system said.
        let first = group_of(context.colliders[context.collider1].user_data);
        let second = group_of(context.colliders[context.collider2].user_data);
        first == 0 || first != second
    }
}

/// One pair touching after a substep: where and how hard, and which side
/// is a sensor, if either.
#[derive(Clone, Copy)]
struct Touch {
    point: Vector,
    normal: Vector,
    impulse: f64,
    /// The two colliders' owners, kept so an end can still name them after
    /// a collider is removed.
    owners: (u64, u64),
    sensor_owner: Option<u64>,
}

impl Touch {
    /// An overlap with no contact point: a sensor, or a declined pair.
    fn still(owners: (u64, u64), sensor_owner: Option<u64>) -> Self {
        Touch { point: Vector::ZERO, normal: Vector::new(0.0, 1.0), impulse: 0.0, owners, sensor_owner }
    }
}

/// One collision event for Python: kind (0 begin, 1 persist, 2 end), the
/// two colliders and their owners, the contact point, normal and impulse,
/// and the sensor's owner, if a sensor is involved.
type Event = (u8, u64, u64, u64, u64, f64, f64, f64, f64, f64, Option<u64>);

/// A Rapier world, its bodies and colliders, and the contacts between them.
#[pyclass]
pub struct NativePhysicsWorld {
    world: PhysicsWorld,
    substeps: usize,
    /// A change since the broad phase was last brought up to date.
    stale: bool,
    /// Bodies whose force was applied since the last step, to clear after it.
    forced: Vec<RigidBodyHandle>,
    /// Mass a dynamic body was given before it had a collider; Chipmunk
    /// replaces it with the colliders' own mass once one has density.
    pending_mass: HashMap<RigidBodyHandle, f64>,
    /// Pairs the collision system asked not to resolve, while they overlap.
    suppressed: HashSet<Pair>,
    /// What touched after the last substep.
    touching: HashMap<Pair, Touch>,
    /// Events since Python last took them.
    events: Vec<Event>,
    /// Whether anyone takes the events. Diffing every pair after every
    /// substep is the cost of reporting, and is skipped when nobody listens.
    reporting: bool,
}

impl NativePhysicsWorld {
    fn body_handle(handle: u64) -> RigidBodyHandle {
        let (id, generation) = unpack(handle);
        RigidBodyHandle::from_raw_parts(id, generation)
    }

    fn body(&self, handle: u64) -> PyResult<&RigidBody> {
        self.world
            .bodies
            .get(Self::body_handle(handle))
            .ok_or_else(|| PyKeyError::new_err("no such body"))
    }

    fn body_mut(&mut self, handle: u64) -> PyResult<&mut RigidBody> {
        self.world
            .bodies
            .get_mut(Self::body_handle(handle))
            .ok_or_else(|| PyKeyError::new_err("no such body"))
    }

    /// Bring the broad phase up to date if anything moved since it was.
    fn fresh(&mut self) {
        if self.stale {
            let filter = Filter { suppressed: &self.suppressed };
            self.world.detect_collisions(&filter, &());
            self.stale = false;
        }
    }

    /// Whether two colliders' shapes overlap where they now are.
    fn overlap(&self, first: ColliderHandle, second: ColliderHandle) -> bool {
        let (Some(a), Some(b)) = (self.world.colliders.get(first), self.world.colliders.get(second))
        else {
            return false;
        };
        intersection_test(a.position(), a.shape(), b.position(), b.shape())
            .is_ok_and(|hit| hit.intersecting)
    }

    /// What touches now: solid contacts, sensor overlaps, and suppressed
    /// pairs that still overlap, which Chipmunk keeps reporting.
    fn touching_now(&self) -> HashMap<Pair, Touch> {
        let mut now = HashMap::new();
        for contact in self.world.narrow_phase.contact_pairs() {
            if !contact.has_any_active_contact() {
                continue;
            }
            let Some((manifold, deepest)) = contact.find_deepest_contact() else {
                continue;
            };
            let point = self
                .world
                .colliders
                .get(contact.collider1)
                .map_or(Vector::ZERO, |c| c.position().transform_point(deepest.local_p1));
            let key = pair(contact.collider1, contact.collider2);
            let Some(owners) = self.owners(key) else { continue };
            // The normal points from collider1 to collider2; flip it when the
            // pair is stored the other way round.
            let normal = if key.0 == contact.collider1 {
                manifold.data.normal
            } else {
                -manifold.data.normal
            };
            now.insert(
                key,
                Touch {
                    point,
                    normal,
                    impulse: contact.total_impulse_magnitude(),
                    owners,
                    sensor_owner: None,
                },
            );
        }
        for (first, second, intersecting) in self.world.narrow_phase.intersection_pairs() {
            if !intersecting {
                continue;
            }
            let key = pair(first, second);
            let Some(owners) = self.owners(key) else { continue };
            let sensor_owner = [first, second]
                .into_iter()
                .find(|handle| self.world.colliders.get(*handle).is_some_and(|c| c.is_sensor()))
                .and_then(|handle| self.owner_of_collider(handle));
            now.insert(key, Touch::still(owners, sensor_owner));
        }
        for &suppressed in &self.suppressed {
            if !now.contains_key(&suppressed) && self.overlap(suppressed.0, suppressed.1) {
                if let Some(owners) = self.owners(suppressed) {
                    now.insert(suppressed, Touch::still(owners, None));
                }
            }
        }
        now
    }

    fn owner_of_collider(&self, handle: ColliderHandle) -> Option<u64> {
        self.world.colliders.get(handle).map(|c| owner_of(c.user_data))
    }

    /// Whether neither collider of a pair belongs to an awake moving body.
    fn asleep(&self, key: Pair) -> bool {
        [key.0, key.1].into_iter().all(|handle| {
            self.world
                .colliders
                .get(handle)
                .and_then(|collider| collider.parent())
                .and_then(|parent| self.world.bodies.get(parent))
                .is_none_or(|body| body.is_fixed() || body.is_sleeping())
        })
    }

    fn owners(&self, key: Pair) -> Option<(u64, u64)> {
        Some((self.owner_of_collider(key.0)?, self.owner_of_collider(key.1)?))
    }

    /// Compare what touches now with what touched before, as events.
    fn record_events(&mut self) {
        let now = self.touching_now();
        let mut begun: Vec<(&Pair, &Touch)> = now.iter().collect();
        // A fixed order, so a seeded world reports its events the same way
        // every run; a `HashMap` iterates in a different order each time.
        begun.sort_by_key(|(key, _)| (key.0.into_raw_parts(), key.1.into_raw_parts()));
        for (key, touch) in begun {
            let persisting = self.touching.contains_key(key);
            // As Chipmunk: a pair whose bodies are all asleep still touches,
            // and is not reported again until one of them wakes.
            if persisting && self.asleep(*key) {
                continue;
            }
            let kind = if persisting { 1 } else { 0 };
            self.events.push(Self::event(kind, *key, touch));
        }
        let mut ended: Vec<(Pair, Touch)> = self
            .touching
            .iter()
            .filter(|(key, _)| !now.contains_key(*key))
            .map(|(key, touch)| (*key, *touch))
            .collect();
        ended.sort_by_key(|(key, _)| (key.0.into_raw_parts(), key.1.into_raw_parts()));
        for (key, touch) in ended {
            self.suppressed.remove(&key);
            self.events.push(Self::event(2, key, &Touch { point: Vector::ZERO, normal: Vector::ZERO, impulse: 0.0, ..touch }));
        }
        self.touching = now;
    }

    fn event(kind: u8, key: Pair, touch: &Touch) -> Event {
        (
            kind,
            collider_key(key.0),
            collider_key(key.1),
            touch.owners.0,
            touch.owners.1,
            touch.point.x,
            touch.point.y,
            touch.normal.x,
            touch.normal.y,
            touch.impulse,
            touch.sensor_owner,
        )
    }

    fn filter(mask: u32, ignore: Option<u64>) -> QueryFilter<'static> {
        let filter = QueryFilter::default()
            .exclude_sensors()
            .groups(InteractionGroups::new(
                Group::ALL,
                Group::from_bits_truncate(mask),
                InteractionTestMode::And,
            ));
        let _ = ignore;
        filter
    }

    /// The owner of a collider's body, unless it is the ignored one.
    fn owner(&self, collider: &Collider, ignore: Option<u64>) -> Option<u64> {
        let owner = owner_of(collider.user_data);
        if ignore == Some(owner) { None } else { Some(owner) }
    }

    /// Distinct owners, first seen first.
    fn distinct(owners: impl Iterator<Item = u64>) -> Vec<u64> {
        let mut seen = Vec::new();
        for owner in owners {
            if !seen.contains(&owner) {
                seen.push(owner);
            }
        }
        seen
    }

    fn overlapping(&mut self, shape: &dyn Shape, pose: Pose, mask: u32, ignore: Option<u64>) -> Vec<u64> {
        self.fresh();
        let found: Vec<u64> = self
            .world
            .intersect_shape(pose, shape, Self::filter(mask, ignore))
            .filter_map(|(_, collider)| self.owner(collider, ignore))
            .collect();
        Self::distinct(found.into_iter())
    }
}

#[pymethods]
impl NativePhysicsWorld {
    /// An empty world.
    ///
    /// Args:
    ///     gravity_x: Gravity, in pixels per second squared.
    ///     gravity_y: Likewise; positive is down the screen.
    ///     substeps: Solver steps per `step` call, each of `dt / substeps`.
    #[new]
    fn new(gravity_x: f64, gravity_y: f64, substeps: usize) -> PyResult<Self> {
        if substeps == 0 {
            return Err(PyValueError::new_err("substeps must be at least 1"));
        }
        let mut world = PhysicsWorld::new();
        world.gravity = Vector::new(gravity_x, gravity_y);
        world.integration_parameters.length_unit = PIXELS_PER_UNIT;
        Ok(Self {
            world,
            substeps,
            stale: true,
            forced: Vec::new(),
            pending_mass: HashMap::new(),
            suppressed: HashSet::new(),
            touching: HashMap::new(),
            events: Vec::new(),
            reporting: false,
        })
    }

    /// Change gravity.
    fn set_gravity(&mut self, x: f64, y: f64) {
        self.world.gravity = Vector::new(x, y);
    }

    /// Add a body.
    ///
    /// Args:
    ///     kind: 0 static, 1 kinematic (moved by its velocity), 2 dynamic.
    ///     x: World position.
    ///     y: World position.
    ///     mass: A dynamic body's mass until a collider with density gives it one.
    ///     fixed_rotation: Never let it turn.
    ///     gravity_scale: Multiplier on world gravity.
    ///     owner: The slot Python maps back to an entity.
    ///
    /// Returns:
    ///     The body's handle.
    #[allow(clippy::too_many_arguments)]
    fn create_body(
        &mut self,
        kind: u8,
        x: f64,
        y: f64,
        mass: f64,
        fixed_rotation: bool,
        gravity_scale: f64,
        owner: u64,
    ) -> PyResult<u64> {
        let builder = match kind {
            0 => RigidBodyBuilder::fixed(),
            1 => RigidBodyBuilder::kinematic_velocity_based(),
            2 => RigidBodyBuilder::dynamic(),
            other => return Err(PyValueError::new_err(format!("no body kind {other}"))),
        };
        let mut builder = builder
            .translation(Vector::new(x, y))
            .gravity_scale(gravity_scale)
            .user_data(u128::from(owner));
        if fixed_rotation {
            builder = builder.lock_rotations();
        }
        if kind == 2 && mass > 0.0 {
            builder = builder.additional_mass(mass);
        }
        let handle = self.world.insert_body(builder);
        if kind == 2 && mass > 0.0 {
            self.pending_mass.insert(handle, mass);
        }
        self.stale = true;
        let (id, generation) = handle.into_raw_parts();
        Ok(pack(id, generation))
    }

    /// Remove a body and its colliders. A no-op for an unknown handle.
    fn remove_body(&mut self, handle: u64) {
        let body = Self::body_handle(handle);
        self.world.remove_body(body);
        self.pending_mass.remove(&body);
        self.forced.retain(|forced| *forced != body);
        self.stale = true;
    }

    /// Attach a collider.
    ///
    /// Args:
    ///     body: The body's handle.
    ///     kind: "circle" (`a` is the radius) or "box" (`a`, `b` are width and height).
    ///     a: First dimension.
    ///     b: Second dimension, for a box.
    ///     offset_x: Offset from the body's origin.
    ///     offset_y: Likewise.
    ///     friction: Multiplied with the other shape's.
    ///     restitution: Multiplied with the other shape's.
    ///     density: Mass per square pixel.
    ///     category: What this shape is.
    ///     mask: What it collides with.
    ///     group: Shapes in the same non-zero group never collide.
    ///     sensor: Detect overlaps without blocking.
    ///
    /// Returns:
    ///     The collider's handle.
    #[allow(clippy::too_many_arguments)]
    fn add_collider(
        &mut self,
        body: u64,
        kind: &str,
        a: f64,
        b: f64,
        offset_x: f64,
        offset_y: f64,
        friction: f64,
        restitution: f64,
        density: f64,
        category: u32,
        mask: u32,
        group: u32,
        sensor: bool,
    ) -> PyResult<u64> {
        let owner = owner_of(self.body(body)?.user_data);
        let builder = match kind {
            "circle" => ColliderBuilder::ball(a),
            "box" => ColliderBuilder::cuboid(a / 2.0, b / 2.0),
            other => return Err(PyValueError::new_err(format!("no collider kind {other:?}"))),
        };
        let mut builder = builder
            .translation(Vector::new(offset_x, offset_y))
            .friction(friction)
            .friction_combine_rule(CoefficientCombineRule::Multiply)
            .restitution(restitution)
            .restitution_combine_rule(CoefficientCombineRule::Multiply)
            .density(density)
            .collision_groups(InteractionGroups::new(
                Group::from_bits_truncate(category),
                Group::from_bits_truncate(mask),
                InteractionTestMode::And,
            ))
            .sensor(sensor)
            .user_data(u128::from(owner) | (u128::from(group) << 64));
        // On every collider, not only grouped ones: a pair the collision
        // system declines can be any pair.
        builder = builder
            .active_hooks(ActiveHooks::FILTER_CONTACT_PAIRS | ActiveHooks::FILTER_INTERSECTION_PAIR);
        let parent = Self::body_handle(body);
        let collider = self.world.insert_collider(builder, Some(parent));
        if density > 0.0 && self.pending_mass.remove(&parent).is_some() {
            // As Chipmunk: a shape with density replaces the body's own mass.
            if let Some(rigid) = self.world.bodies.get_mut(parent) {
                rigid.set_additional_mass(0.0, true);
            }
        }
        self.stale = true;
        let (id, generation) = collider.into_raw_parts();
        Ok(pack(id, generation))
    }

    /// `(x, y, angle_radians, velocity_x, velocity_y)` of a body.
    fn state(&self, handle: u64) -> PyResult<(f64, f64, f64, f64, f64)> {
        let body = self.body(handle)?;
        let position = body.translation();
        let velocity = body.linvel();
        Ok((position.x, position.y, body.rotation().angle(), velocity.x, velocity.y))
    }

    /// Move a body, waking it.
    fn set_position(&mut self, handle: u64, x: f64, y: f64) -> PyResult<()> {
        self.body_mut(handle)?.set_translation(Vector::new(x, y), true);
        self.stale = true;
        Ok(())
    }

    /// Turn a body to an angle in radians, waking it.
    fn set_rotation(&mut self, handle: u64, angle: f64) -> PyResult<()> {
        self.body_mut(handle)?.set_rotation(Rotation::new(angle), true);
        self.stale = true;
        Ok(())
    }

    /// Set a body's linear velocity, waking it.
    fn set_velocity(&mut self, handle: u64, x: f64, y: f64) -> PyResult<()> {
        self.body_mut(handle)?.set_linvel(Vector::new(x, y), true);
        Ok(())
    }

    /// Apply a force at a point in the body's own frame, for the next solver step.
    fn apply_force(&mut self, handle: u64, fx: f64, fy: f64, px: f64, py: f64) -> PyResult<()> {
        let body = self.body_mut(handle)?;
        let point = body.position().transform_point(Vector::new(px, py));
        body.add_force_at_point(Vector::new(fx, fy), point, true);
        let key = Self::body_handle(handle);
        if !self.forced.contains(&key) {
            self.forced.push(key);
        }
        Ok(())
    }

    /// Apply an impulse at a point in the body's own frame.
    fn apply_impulse(&mut self, handle: u64, ix: f64, iy: f64, px: f64, py: f64) -> PyResult<()> {
        let body = self.body_mut(handle)?;
        let point = body.position().transform_point(Vector::new(px, py));
        body.apply_impulse_at_point(Vector::new(ix, iy), point, true);
        Ok(())
    }

    /// Advance by `dt` seconds, in `substeps` equal solver steps.
    fn step(&mut self, dt: f64) {
        if dt <= 0.0 {
            return;
        }
        self.world.integration_parameters.dt = dt / self.substeps as f64;
        for substep in 0..self.substeps {
            let filter = Filter { suppressed: &self.suppressed };
            self.world.step_with_events(&filter, &());
            if self.reporting {
                self.record_events();
            }
            if substep == 0 {
                for handle in self.forced.drain(..) {
                    if let Some(body) = self.world.bodies.get_mut(handle) {
                        body.reset_forces(false);
                    }
                }
            }
        }
        self.stale = false;
    }

    /// The nearest solid hit along a segment.
    ///
    /// Returns:
    ///     `(x, y, normal_x, normal_y, owner)`, or None.
    #[pyo3(signature = (start_x, start_y, end_x, end_y, mask = FULL_MASK, ignore = None))]
    #[allow(clippy::too_many_arguments)]
    fn raycast(
        &mut self,
        start_x: f64,
        start_y: f64,
        end_x: f64,
        end_y: f64,
        mask: u32,
        ignore: Option<u64>,
    ) -> Option<(f64, f64, f64, f64, u64)> {
        self.raycast_all(start_x, start_y, end_x, end_y, mask, ignore)
            .into_iter()
            .next()
    }

    /// Every solid hit along a segment, nearest first, one per shape.
    #[pyo3(signature = (start_x, start_y, end_x, end_y, mask = FULL_MASK, ignore = None))]
    #[allow(clippy::too_many_arguments)]
    fn raycast_all(
        &mut self,
        start_x: f64,
        start_y: f64,
        end_x: f64,
        end_y: f64,
        mask: u32,
        ignore: Option<u64>,
    ) -> Vec<(f64, f64, f64, f64, u64)> {
        self.fresh();
        let origin = Vector::new(start_x, start_y);
        let direction = Vector::new(end_x - start_x, end_y - start_y);
        if direction.length_squared() == 0.0 {
            return Vec::new();
        }
        let ray = Ray::new(origin, direction);
        let mut hits: Vec<(f64, f64, f64, f64, f64, u64)> = self
            .world
            .intersect_ray(ray, 1.0, true, Self::filter(mask, ignore))
            .filter_map(|(_, collider, hit)| {
                let owner = self.owner(collider, ignore)?;
                let point = origin + direction * hit.time_of_impact;
                Some((hit.time_of_impact, point.x, point.y, hit.normal.x, hit.normal.y, owner))
            })
            .collect();
        hits.sort_by(|a, b| a.0.total_cmp(&b.0));
        hits.into_iter()
            .map(|(_, x, y, nx, ny, owner)| (x, y, nx, ny, owner))
            .collect()
    }

    /// Owners of solid shapes overlapping an axis-aligned box.
    #[pyo3(signature = (x, y, half_width, half_height, mask = FULL_MASK, ignore = None))]
    fn overlap_box(
        &mut self,
        x: f64,
        y: f64,
        half_width: f64,
        half_height: f64,
        mask: u32,
        ignore: Option<u64>,
    ) -> Vec<u64> {
        let shape = Cuboid::new(Vector::new(half_width, half_height));
        self.overlapping(&shape, Pose::from_translation(Vector::new(x, y)), mask, ignore)
    }

    /// Owners of solid shapes overlapping a circle.
    #[pyo3(signature = (x, y, radius, mask = FULL_MASK, ignore = None))]
    fn overlap_circle(&mut self, x: f64, y: f64, radius: f64, mask: u32, ignore: Option<u64>) -> Vec<u64> {
        let shape = Ball::new(radius);
        self.overlapping(&shape, Pose::from_translation(Vector::new(x, y)), mask, ignore)
    }

    /// Owners of solid shapes containing a point, deepest first.
    #[pyo3(signature = (x, y, mask = FULL_MASK, ignore = None))]
    fn point_query(&mut self, x: f64, y: f64, mask: u32, ignore: Option<u64>) -> Vec<u64> {
        self.fresh();
        let point = Vector::new(x, y);
        let mut found: Vec<(f64, u64)> = self
            .world
            .intersect_point(point, Self::filter(mask, ignore))
            .filter_map(|(_, collider)| {
                let owner = self.owner(collider, ignore)?;
                // How far inside: the distance to the boundary, deepest first.
                let depth = collider
                    .shape()
                    .project_point(collider.position(), point, false)
                    .point
                    .distance(point);
                Some((depth, owner))
            })
            .collect();
        found.sort_by(|a, b| b.0.total_cmp(&a.0));
        Self::distinct(found.into_iter().map(|(_, owner)| owner))
    }

    /// Owners of solid shapes whose bounding box overlaps a rectangle.
    #[pyo3(signature = (left, top, right, bottom, mask = FULL_MASK, ignore = None))]
    #[allow(clippy::too_many_arguments)]
    fn region_query(
        &mut self,
        left: f64,
        top: f64,
        right: f64,
        bottom: f64,
        mask: u32,
        ignore: Option<u64>,
    ) -> Vec<u64> {
        self.fresh();
        let bounds = Aabb::new(Vector::new(left, top), Vector::new(right, bottom));
        let found: Vec<u64> = self
            .world
            .intersect_aabb_conservative(bounds, Self::filter(mask, ignore))
            .filter(|(_, collider)| collider.compute_aabb().intersects(&bounds))
            .filter_map(|(_, collider)| self.owner(collider, ignore))
            .collect();
        Self::distinct(found.into_iter())
    }

    /// Start or stop recording collision events. Off, nothing is recorded
    /// and pairs already touching are forgotten.
    fn set_reporting(&mut self, reporting: bool) {
        self.reporting = reporting;
        if !reporting {
            self.touching.clear();
            self.events.clear();
        }
    }

    /// Take the collision events recorded since the last call.
    ///
    /// Returns:
    ///     `(kind, collider_a, collider_b, owner_a, owner_b, x, y, normal_x,
    ///     normal_y, impulse, sensor_owner)` per event, kind 0 begin,
    ///     1 persist, 2 end, in the order they happened.
    fn take_events(&mut self) -> Vec<Event> {
        std::mem::take(&mut self.events)
    }

    /// Stop resolving a pair physically while it overlaps; it is still
    /// reported, as Chipmunk reports a pair whose `process_collision` is off.
    fn suppress(&mut self, collider_a: u64, collider_b: u64) {
        let (a_id, a_gen) = unpack(collider_a);
        let (b_id, b_gen) = unpack(collider_b);
        self.suppressed.insert(pair(
            ColliderHandle::from_raw_parts(a_id, a_gen),
            ColliderHandle::from_raw_parts(b_id, b_gen),
        ));
    }

    /// How many bodies the world holds. For tests.
    fn __len__(&self) -> usize {
        self.world.bodies.len()
    }
}
