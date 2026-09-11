"""Tests for `pyguara/kits/projectiles/` (Projectile, ProjectileSystem)."""

from __future__ import annotations

from typing import Any

from pyguara.common.modifiers import ModifiableValue
from pyguara.common.spatial import SpatialHash
from pyguara.common.types import Vector2
from pyguara.ecs.manager import EntityManager
from pyguara.graphics.components.camera import Camera2D
from pyguara.kits.action_combat import ARMOR_STAT, DamageDealt, Health, Hurtbox
from pyguara.kits.projectiles import ProjectileSystem
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
