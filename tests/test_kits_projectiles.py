"""Tests for `pyguara/kits/projectiles/` (Projectile, ProjectileSystem)."""

from __future__ import annotations

from typing import Any

from pyguara.common.components import Transform
from pyguara.common.modifiers import ModifiableValue
from pyguara.common.spatial import SpatialHash
from pyguara.common.types import Vector2
from pyguara.ecs.manager import EntityManager
from pyguara.graphics.components.camera import Camera2D
from pyguara.kits.action_combat import ARMOR_STAT, DamageDealt, Health, Hurtbox
from pyguara.kits.projectiles import ProjectileEnd, ProjectileSystem
from pyguara.kits.stats import DamageType, StatBlock


class _FakeRenderer:
    def __init__(self) -> None:
        self.batches: list[Any] = []

    def render_batch(self, batch: Any) -> None:
        self.batches.append(batch)

    width = 800
    height = 600


class _FakeTexture:
    pass


def _system(
    event_dispatcher: Any,
) -> tuple[ProjectileSystem, EntityManager, SpatialHash]:
    manager = EntityManager()
    index: SpatialHash[str] = SpatialHash()
    system = ProjectileSystem(manager, event_dispatcher, index, capacity=4)
    return system, manager, index


def _target(
    manager: EntityManager,
    index: SpatialHash,
    position: Vector2,
    team: str | None = None,
    health: float = 100.0,
) -> Any:
    entity = manager.create_entity()
    entity.add_component(Transform(position=position))
    entity.add_component(Health(current=health, max_health=health))
    entity.add_component(Hurtbox(team=team))
    index.insert(entity.id, position)
    return entity


# ========== spawn / pool ==========


def test_spawn_activates_one_slot(event_dispatcher: Any) -> None:
    system, _, _ = _system(event_dispatcher)

    system.spawn(None, Vector2(0, 0), Vector2(100, 0), damage=5.0)

    active = [p for p in system._pool if p.active]
    assert len(active) == 1
    assert active[0].damage == 5.0


def test_spawn_beyond_capacity_is_dropped(event_dispatcher: Any) -> None:
    system, _, _ = _system(event_dispatcher)

    for _ in range(5):  # capacity is 4
        system.spawn(None, Vector2(0, 0), Vector2(0, 0), life=10.0)

    active = [p for p in system._pool if p.active]
    assert len(active) == 4


def test_recycled_slot_is_available_for_a_new_spawn(event_dispatcher: Any) -> None:
    system, _, _ = _system(event_dispatcher)
    system.spawn(None, Vector2(0, 0), Vector2(0, 0), life=0.1)
    system.update(0.2)  # expires

    system.spawn(None, Vector2(5, 5), Vector2(0, 0), life=10.0)

    active = [p for p in system._pool if p.active]
    assert len(active) == 1
    assert active[0].position == Vector2(5, 5)


# ========== get_active ==========


def test_get_active_is_empty_for_a_fresh_system(event_dispatcher: Any) -> None:
    system, _, _ = _system(event_dispatcher)

    assert system.get_active() == []


def test_get_active_returns_only_active_projectiles(event_dispatcher: Any) -> None:
    system, _, _ = _system(event_dispatcher)
    system.spawn(None, Vector2(1, 2), Vector2(0, 0), life=10.0)
    system.spawn(None, Vector2(3, 4), Vector2(0, 0), life=0.1)

    system.update(0.2)  # expires the second one

    active = system.get_active()
    assert len(active) == 1
    assert active[0].position == Vector2(1, 2)


# ========== movement / expiry ==========


def test_update_moves_by_velocity(event_dispatcher: Any) -> None:
    system, _, _ = _system(event_dispatcher)
    system.spawn(None, Vector2(0, 0), Vector2(100, 0), life=10.0)

    system.update(0.5)

    active = [p for p in system._pool if p.active][0]
    assert active.position == Vector2(50, 0)


def test_update_expires_at_end_of_life(event_dispatcher: Any) -> None:
    system, _, _ = _system(event_dispatcher)
    system.spawn(None, Vector2(0, 0), Vector2(0, 0), life=1.0)

    system.update(0.5)
    assert any(p.active for p in system._pool)

    system.update(0.6)
    assert not any(p.active for p in system._pool)


# ========== hit detection ==========


def test_hit_applies_damage_and_deactivates(event_dispatcher: Any) -> None:
    system, manager, index = _system(event_dispatcher)
    target = _target(manager, index, Vector2(100, 0))
    system.spawn(
        None, Vector2(0, 0), Vector2(100, 0), damage=20.0, damage_type=DamageType.TRUE
    )

    system.update(1.0)  # moves to (100, 0), lands on the target

    assert target.get_component(Health).current == 80.0
    assert not any(p.active for p in system._pool)


def test_hit_dispatches_damage_dealt(event_dispatcher: Any) -> None:
    system, manager, index = _system(event_dispatcher)
    events: list[DamageDealt] = []
    event_dispatcher.subscribe(DamageDealt, events.append)
    target = _target(manager, index, Vector2(100, 0))
    system.spawn(
        None, Vector2(0, 0), Vector2(100, 0), damage=10.0, damage_type=DamageType.TRUE
    )

    system.update(1.0)

    assert len(events) == 1
    assert events[0].target == target.id
    assert events[0].amount == 10.0


def test_no_target_nearby_leaves_the_projectile_flying(event_dispatcher: Any) -> None:
    system, _, _ = _system(event_dispatcher)
    system.spawn(
        None, Vector2(0, 0), Vector2(100, 0), damage=10.0, life=10.0, hit_radius=1.0
    )

    system.update(0.1)  # moves to (10, 0), nothing there

    assert any(p.active for p in system._pool)


def test_candidate_without_hurtbox_is_ignored(event_dispatcher: Any) -> None:
    system, manager, index = _system(event_dispatcher)
    bystander = manager.create_entity()
    bystander.add_component(Health(current=100.0))  # no Hurtbox
    index.insert(bystander.id, Vector2(100, 0))
    system.spawn(
        None, Vector2(0, 0), Vector2(100, 0), damage=10.0, damage_type=DamageType.TRUE
    )

    system.update(1.0)

    assert bystander.get_component(Health).current == 100.0
    assert any(p.active for p in system._pool)  # kept flying, no valid target


def test_candidate_without_health_is_ignored(event_dispatcher: Any) -> None:
    system, manager, index = _system(event_dispatcher)
    healthless = manager.create_entity()
    healthless.add_component(Hurtbox())  # no Health
    index.insert(healthless.id, Vector2(100, 0))
    system.spawn(None, Vector2(0, 0), Vector2(100, 0), damage=10.0)

    system.update(1.0)  # must not raise

    assert any(p.active for p in system._pool)


def test_same_team_never_damages(event_dispatcher: Any) -> None:
    system, manager, index = _system(event_dispatcher)
    target = _target(manager, index, Vector2(100, 0), team="allies")
    system.spawn(
        None,
        Vector2(0, 0),
        Vector2(100, 0),
        damage=10.0,
        damage_type=DamageType.TRUE,
        team="allies",
    )

    system.update(1.0)

    assert target.get_component(Health).current == 100.0


def test_different_teams_damages(event_dispatcher: Any) -> None:
    system, manager, index = _system(event_dispatcher)
    target = _target(manager, index, Vector2(100, 0), team="allies")
    system.spawn(
        None,
        Vector2(0, 0),
        Vector2(100, 0),
        damage=10.0,
        damage_type=DamageType.TRUE,
        team="enemies",
    )

    system.update(1.0)

    assert target.get_component(Health).current == 90.0


def test_projectile_with_no_team_hits_anyone(event_dispatcher: Any) -> None:
    system, manager, index = _system(event_dispatcher)
    target = _target(manager, index, Vector2(100, 0), team="allies")
    system.spawn(
        None, Vector2(0, 0), Vector2(100, 0), damage=10.0, damage_type=DamageType.TRUE
    )

    system.update(1.0)

    assert target.get_component(Health).current == 90.0


def test_target_stats_are_used_for_mitigation_when_present(
    event_dispatcher: Any,
) -> None:
    system, manager, index = _system(event_dispatcher)
    target = _target(manager, index, Vector2(100, 0))
    target.add_component(StatBlock(stats={ARMOR_STAT: ModifiableValue(50.0)}))
    system.spawn(
        None,
        Vector2(0, 0),
        Vector2(100, 0),
        damage=20.0,
        damage_type=DamageType.PHYSICAL,
    )

    system.update(1.0)

    # 50 armor against the default scaling=50 mitigates exactly half.
    assert target.get_component(Health).current == 90.0


def test_attacker_and_crit_are_forwarded(event_dispatcher: Any) -> None:
    system, manager, index = _system(event_dispatcher)
    events: list[DamageDealt] = []
    event_dispatcher.subscribe(DamageDealt, events.append)
    _target(manager, index, Vector2(100, 0))
    system.spawn(
        None,
        Vector2(0, 0),
        Vector2(100, 0),
        damage=10.0,
        damage_type=DamageType.TRUE,
        is_critical=True,
        attacker="player_1",
    )

    system.update(1.0)

    assert events[0].attacker == "player_1"
    assert events[0].is_critical is True
    assert events[0].amount == 15.0  # 10 * default 1.5 crit multiplier


# ========== render ==========


def test_render_batches_active_textured_projectiles(event_dispatcher: Any) -> None:
    system, _, _ = _system(event_dispatcher)
    texture = _FakeTexture()
    system.spawn(texture, Vector2(10, 10), Vector2(0, 0), life=10.0)
    renderer = _FakeRenderer()
    camera = Camera2D(800, 600)

    system.render(renderer, camera)

    assert len(renderer.batches) == 1
    assert renderer.batches[0].texture is texture
    assert len(renderer.batches[0].destinations) == 1


def test_render_skips_textureless_and_inactive_projectiles(
    event_dispatcher: Any,
) -> None:
    system, _, _ = _system(event_dispatcher)
    system.spawn(None, Vector2(0, 0), Vector2(0, 0), life=10.0)  # no texture
    renderer = _FakeRenderer()
    camera = Camera2D(800, 600)

    system.render(renderer, camera)

    assert renderer.batches == []


# ========== the whole step is checked ==========


def test_a_fast_shot_hits_a_target_it_passes_between_ticks(
    event_dispatcher: Any,
) -> None:
    """A shot moving further than its own reach in a tick must not skip a target."""
    system, manager, index = _system(event_dispatcher)
    target = _target(manager, index, Vector2(50, 0))
    system.spawn(
        None,
        Vector2(0, 0),
        Vector2(100, 0),
        damage=10.0,
        damage_type=DamageType.TRUE,
        hit_radius=4.0,
    )

    system.update(1.0)  # travels 0 -> 100; the target sits halfway

    assert target.get_component(Health).current == 90.0
    assert not system.get_active()


def test_a_target_beside_the_path_is_missed(event_dispatcher: Any) -> None:
    system, manager, index = _system(event_dispatcher)
    target = _target(manager, index, Vector2(50, 10))
    system.spawn(None, Vector2(0, 0), Vector2(100, 0), damage=10.0, hit_radius=4.0)

    system.update(1.0)

    assert target.get_component(Health).current == 100.0
    assert len(system.get_active()) == 1


def test_the_target_nearest_along_the_path_is_hit_first(
    event_dispatcher: Any,
) -> None:
    """Earliest along the path, whatever order the index returns them in."""
    for near_first in (True, False):
        system, manager, index = _system(event_dispatcher)
        if near_first:
            near = _target(manager, index, Vector2(30, 0))
            far = _target(manager, index, Vector2(70, 0))
        else:
            far = _target(manager, index, Vector2(70, 0))
            near = _target(manager, index, Vector2(30, 0))
        system.spawn(
            None,
            Vector2(0, 0),
            Vector2(100, 0),
            damage=10.0,
            damage_type=DamageType.TRUE,
            hit_radius=4.0,
        )

        system.update(1.0)

        assert near.get_component(Health).current == 90.0
        assert far.get_component(Health).current == 100.0


def test_targets_equally_far_along_the_path_are_taken_by_id(
    event_dispatcher: Any,
) -> None:
    """Two targets at the same distance: the smaller id, not the index's order."""
    system, manager, index = _system(event_dispatcher)
    above = _target(manager, index, Vector2(50, -2))
    below = _target(manager, index, Vector2(50, 2))
    first, second = sorted([above, below], key=lambda entity: entity.id)
    system.spawn(
        None,
        Vector2(0, 0),
        Vector2(100, 0),
        damage=10.0,
        damage_type=DamageType.TRUE,
        hit_radius=4.0,
    )

    system.update(1.0)

    assert first.get_component(Health).current == 90.0
    assert second.get_component(Health).current == 100.0


def test_the_index_order_does_not_choose_the_target(event_dispatcher: Any) -> None:
    """The query's own order is reversed; the same target must still be hit."""

    class _Reversed(SpatialHash[str]):
        def query_radius(self, *args: Any, **kwargs: Any) -> list[str]:
            return list(reversed(super().query_radius(*args, **kwargs)))

    for reverse in (False, True):
        manager = EntityManager()
        index: SpatialHash[str] = (
            _Reversed(accelerate=False) if reverse else SpatialHash(accelerate=False)
        )
        system = ProjectileSystem(manager, event_dispatcher, index, capacity=4)
        targets = [_target(manager, index, Vector2(50, offset)) for offset in (-2, 2)]
        system.spawn(
            None,
            Vector2(0, 0),
            Vector2(100, 0),
            damage=10.0,
            damage_type=DamageType.TRUE,
            hit_radius=4.0,
        )
        system.update(1.0)
        hit = [
            entity.id
            for entity in targets
            if entity.get_component(Health).current < 100.0
        ]

        assert hit == [min(entity.id for entity in targets)]


# ========== on_hit ==========


def test_on_hit_replaces_the_built_in_damage(event_dispatcher: Any) -> None:
    calls: list[tuple[Any, str]] = []

    def on_hit(projectile: Any, entity: Any) -> bool:
        calls.append((projectile.damage, entity.id))
        return True

    manager = EntityManager()
    index: SpatialHash[str] = SpatialHash()
    system = ProjectileSystem(manager, event_dispatcher, index, on_hit=on_hit)
    target = _target(manager, index, Vector2(100, 0))
    system.spawn(None, Vector2(0, 0), Vector2(100, 0), damage=20.0)

    system.update(1.0)

    assert calls == [(20.0, target.id)]
    assert target.get_component(Health).current == 100.0  # the handler did nothing
    assert not system.get_active()


def test_on_hit_returning_false_lets_the_shot_fly_on(event_dispatcher: Any) -> None:
    """A handler can decline a target -- a dodge -- and the next one is tried."""
    seen: list[str] = []

    def on_hit(projectile: Any, entity: Any) -> bool:
        seen.append(entity.id)
        return entity.id == far.id

    manager = EntityManager()
    index: SpatialHash[str] = SpatialHash()
    system = ProjectileSystem(manager, event_dispatcher, index, on_hit=on_hit)
    near = _target(manager, index, Vector2(30, 0))
    far = _target(manager, index, Vector2(70, 0))
    system.spawn(None, Vector2(0, 0), Vector2(100, 0), hit_radius=4.0, life=10.0)

    system.update(1.0)

    assert seen == [near.id, far.id]
    assert not system.get_active()


def test_a_declined_target_is_not_offered_again(event_dispatcher: Any) -> None:
    """A shot that dodged a target must not hit it on the next tick instead."""
    seen: list[str] = []

    def on_hit(projectile: Any, entity: Any) -> bool:
        seen.append(entity.id)
        return False

    manager = EntityManager()
    index: SpatialHash[str] = SpatialHash()
    system = ProjectileSystem(manager, event_dispatcher, index, on_hit=on_hit)
    target = _target(manager, index, Vector2(10, 0))
    system.spawn(None, Vector2(0, 0), Vector2(10, 0), hit_radius=8.0, life=10.0)

    for _ in range(3):
        system.update(0.5)  # within reach of the target on every tick

    assert seen == [target.id]


def test_a_recycled_slot_forgets_whom_it_passed(event_dispatcher: Any) -> None:
    seen: list[str] = []

    def on_hit(projectile: Any, entity: Any) -> bool:
        seen.append(entity.id)
        return False

    manager = EntityManager()
    index: SpatialHash[str] = SpatialHash()
    system = ProjectileSystem(
        manager, event_dispatcher, index, capacity=1, on_hit=on_hit
    )
    target = _target(manager, index, Vector2(0, 0))
    system.spawn(None, Vector2(0, 0), Vector2(0, 0), life=0.1)
    system.update(0.05)  # passes the target
    system.update(0.1)  # expires
    system.spawn(None, Vector2(0, 0), Vector2(0, 0), life=0.1)
    system.update(0.05)

    assert seen == [target.id, target.id]


def test_on_hit_still_skips_teammates(event_dispatcher: Any) -> None:
    seen: list[str] = []
    manager = EntityManager()
    index: SpatialHash[str] = SpatialHash()
    system = ProjectileSystem(
        manager,
        event_dispatcher,
        index,
        on_hit=lambda projectile, entity: seen.append(entity.id) or True,
    )
    _target(manager, index, Vector2(100, 0), team="players")
    system.spawn(None, Vector2(0, 0), Vector2(100, 0), team="players")

    system.update(1.0)

    assert seen == []


# ========== walls ==========


class _Wall:
    """A stand-in physics world with one wall across the x axis at `x`."""

    def __init__(self, x: float) -> None:
        self.x = x
        self.masks: list[int] = []

    def raycast(
        self, start: Vector2, end: Vector2, mask: int = 0xFFFFFFFF, **_: Any
    ) -> Any:
        from pyguara.physics.types import RaycastHit

        self.masks.append(mask)
        if not (min(start.x, end.x) <= self.x <= max(start.x, end.x)):
            return None
        if end.x == start.x:
            return None
        t = (self.x - start.x) / (end.x - start.x)
        point = start + (end - start) * t
        return RaycastHit(
            position=point, normal=Vector2(-1, 0), distance=(point - start).length
        )


def test_a_wall_stops_the_shot_where_it_meets_it(event_dispatcher: Any) -> None:
    manager = EntityManager()
    index: SpatialHash[str] = SpatialHash()
    system = ProjectileSystem(manager, event_dispatcher, index, solids=_Wall(40.0))
    system.spawn(None, Vector2(0, 0), Vector2(100, 0), life=10.0)

    system.update(1.0)

    assert not system.get_active()


def test_a_target_behind_a_wall_is_safe(event_dispatcher: Any) -> None:
    manager = EntityManager()
    index: SpatialHash[str] = SpatialHash()
    system = ProjectileSystem(manager, event_dispatcher, index, solids=_Wall(40.0))
    target = _target(manager, index, Vector2(70, 0))
    system.spawn(
        None,
        Vector2(0, 0),
        Vector2(100, 0),
        damage=10.0,
        damage_type=DamageType.TRUE,
        hit_radius=4.0,
    )

    system.update(1.0)

    assert target.get_component(Health).current == 100.0


def test_a_target_before_the_wall_is_still_hit(event_dispatcher: Any) -> None:
    manager = EntityManager()
    index: SpatialHash[str] = SpatialHash()
    system = ProjectileSystem(manager, event_dispatcher, index, solids=_Wall(80.0))
    target = _target(manager, index, Vector2(50, 0))
    system.spawn(
        None,
        Vector2(0, 0),
        Vector2(100, 0),
        damage=10.0,
        damage_type=DamageType.TRUE,
        hit_radius=4.0,
    )

    system.update(1.0)

    assert target.get_component(Health).current == 90.0


def test_the_solid_mask_reaches_the_raycast(event_dispatcher: Any) -> None:
    wall = _Wall(1000.0)
    system = ProjectileSystem(
        EntityManager(), event_dispatcher, SpatialHash(), solids=wall, solid_mask=0b10
    )
    system.spawn(None, Vector2(0, 0), Vector2(100, 0), life=10.0)

    system.update(0.1)

    assert wall.masks == [0b10]


def test_without_solids_a_shot_flies_through_anything(event_dispatcher: Any) -> None:
    system, _, _ = _system(event_dispatcher)
    system.spawn(None, Vector2(0, 0), Vector2(100, 0), life=10.0)

    system.update(1.0)

    assert system.get_active()[0].position == Vector2(100, 0)


def test_on_hit_sees_the_shot_where_it_reached_the_target(
    event_dispatcher: Any,
) -> None:
    where: list[Vector2] = []

    def on_hit(projectile: Any, entity: Any) -> bool:
        where.append(projectile.position)
        return True

    manager = EntityManager()
    index: SpatialHash[str] = SpatialHash()
    system = ProjectileSystem(manager, event_dispatcher, index, on_hit=on_hit)
    _target(manager, index, Vector2(40, 3))
    system.spawn(None, Vector2(0, 0), Vector2(100, 0), hit_radius=4.0)

    system.update(1.0)

    assert where == [Vector2(40, 0)]


def test_a_declined_shot_still_ends_its_step(event_dispatcher: Any) -> None:
    manager = EntityManager()
    index: SpatialHash[str] = SpatialHash()
    system = ProjectileSystem(
        manager, event_dispatcher, index, on_hit=lambda projectile, entity: False
    )
    _target(manager, index, Vector2(40, 0))
    system.spawn(None, Vector2(0, 0), Vector2(100, 0), hit_radius=4.0, life=10.0)

    system.update(1.0)

    assert system.get_active()[0].position == Vector2(100, 0)


def test_a_target_just_past_the_step_waits_for_the_next_one(
    event_dispatcher: Any,
) -> None:
    """Reach is measured from the step's end, not from the line it lies on."""
    system, manager, index = _system(event_dispatcher)
    target = _target(manager, index, Vector2(103, 3))
    system.spawn(
        None,
        Vector2(0, 0),
        Vector2(100, 0),
        damage=10.0,
        damage_type=DamageType.TRUE,
        hit_radius=4.0,
        life=10.0,
    )

    system.update(1.0)

    assert target.get_component(Health).current == 100.0


def test_candidate_without_transform_is_ignored(event_dispatcher: Any) -> None:
    """In the index but with no `Transform`: nowhere to judge a hit from."""
    system, manager, index = _system(event_dispatcher)
    entity = manager.create_entity()
    entity.add_component(Health(current=100.0, max_health=100.0))
    entity.add_component(Hurtbox())
    index.insert(entity.id, Vector2(50, 0))
    system.spawn(None, Vector2(0, 0), Vector2(100, 0), damage=10.0, life=10.0)

    system.update(1.0)

    assert entity.get_component(Health).current == 100.0
    assert len(system.get_active()) == 1


# ========== what a game attaches ==========


def test_spawn_returns_the_projectile(event_dispatcher: Any) -> None:
    system, _, _ = _system(event_dispatcher)

    projectile = system.spawn(None, Vector2(0, 0), Vector2(1, 0), damage=3.0)

    assert projectile is not None
    assert projectile.active
    assert system.get_active() == [projectile]


def test_spawn_into_a_full_pool_returns_none(event_dispatcher: Any) -> None:
    system, _, _ = _system(event_dispatcher)
    for _ in range(4):  # capacity is 4
        system.spawn(None, Vector2(0, 0), Vector2(0, 0), life=10.0)

    assert system.spawn(None, Vector2(0, 0), Vector2(0, 0)) is None


def test_on_hit_receives_the_payload_given_at_spawn(event_dispatcher: Any) -> None:
    payloads: list[Any] = []

    def on_hit(projectile: Any, entity: Any) -> bool:
        payloads.append(projectile.payload)
        return True

    manager = EntityManager()
    index: SpatialHash[str] = SpatialHash()
    system = ProjectileSystem(manager, event_dispatcher, index, on_hit=on_hit)
    _target(manager, index, Vector2(100, 0))
    rules = {"physical": 12.0, "statuses": ["bleed"]}
    system.spawn(None, Vector2(0, 0), Vector2(100, 0), payload=rules)

    system.update(1.0)

    assert payloads == [rules]


def test_a_reused_slot_drops_the_old_payload(event_dispatcher: Any) -> None:
    manager = EntityManager()
    system = ProjectileSystem(manager, event_dispatcher, SpatialHash(), capacity=1)
    system.spawn(None, Vector2(0, 0), Vector2(0, 0), life=0.1, payload="old")
    system.update(0.2)

    projectile = system.spawn(None, Vector2(0, 0), Vector2(0, 0))

    assert projectile is not None
    assert projectile.payload is None


# ========== on_end ==========


def _ends(
    event_dispatcher: Any, solids: Any = None
) -> tuple[ProjectileSystem, EntityManager, SpatialHash, list[Any]]:
    manager = EntityManager()
    index: SpatialHash[str] = SpatialHash()
    ends: list[Any] = []
    system = ProjectileSystem(
        manager,
        event_dispatcher,
        index,
        solids=solids,
        on_end=lambda p, reason: ends.append((reason, p.position, p.active)),
    )
    return system, manager, index, ends


def test_on_end_hears_a_hit_where_it_landed(event_dispatcher: Any) -> None:
    system, manager, index, ends = _ends(event_dispatcher)
    _target(manager, index, Vector2(50, 0))
    system.spawn(None, Vector2(0, 0), Vector2(100, 0), hit_radius=4.0)

    system.update(1.0)

    assert ends == [(ProjectileEnd.HIT, Vector2(50, 0), False)]


def test_on_end_hears_a_wall(event_dispatcher: Any) -> None:
    system, _, _, ends = _ends(event_dispatcher, solids=_Wall(40.0))
    system.spawn(None, Vector2(0, 0), Vector2(100, 0), life=10.0)

    system.update(1.0)

    assert ends == [(ProjectileEnd.WALL, Vector2(40, 0), False)]


def test_on_end_hears_an_expiry(event_dispatcher: Any) -> None:
    system, _, _, ends = _ends(event_dispatcher)
    system.spawn(None, Vector2(0, 0), Vector2(100, 0), life=0.5)

    system.update(1.0)

    assert [end[0] for end in ends] == [ProjectileEnd.EXPIRED]


def test_a_dodge_is_not_an_end(event_dispatcher: Any) -> None:
    system, manager, index, ends = _ends(event_dispatcher)
    system.on_hit = lambda projectile, target: False
    _target(manager, index, Vector2(50, 0))
    system.spawn(None, Vector2(0, 0), Vector2(100, 0), life=10.0, hit_radius=4.0)

    system.update(1.0)

    assert ends == []
    assert len(system.get_active()) == 1


def test_clear_ends_every_active_projectile(event_dispatcher: Any) -> None:
    system, _, _, ends = _ends(event_dispatcher)
    for _ in range(3):
        system.spawn(None, Vector2(0, 0), Vector2(1, 0), life=10.0)

    system.clear()

    assert not system.get_active()
    assert [end[0] for end in ends] == [ProjectileEnd.CLEARED] * 3
