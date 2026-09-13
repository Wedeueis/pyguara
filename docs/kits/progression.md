# Progression kit

`pyguara.kits.progression` — experience and levels, the upgrade pick a level-up
offers, and the pickup magnet.

The genre this comes from asks for five separable things. **Three** are in the
kit; the other two are deliberately not:

| In the kit | Stays with the game |
|---|---|
| Experience, levels, the curve | The level-up UI scene |
| The upgrade offer and what's been taken | The upgrade content: names, weights, recipes |
| The pickup magnet | Any weapon / item / inventory model |

## Experience and levels

```python
from pyguara.kits.progression import Experience, Geometric, grant_experience

player.add_component(Experience())
curve = Geometric(base=100.0, growth=1.25)

levels = grant_experience(dispatcher, player.id, xp, curve, amount=250.0)
```

Data component plus a free function, matching `StatBlock`/`get_stat` and
`Health`/`apply_damage` — the component holds the numbers and the behaviour
that mutates them lives beside it, not on it.

**Carry-over is kept.** Crossing a level costs exactly that level's price and
the remainder counts toward the next, so a single large grant lands in the same
place as the same total delivered in pieces. One grant can cross several levels
— a boss early in a run — and each crossing gets its own `LeveledUp`.

`Experience.pending_levels` counts levels reached but not yet spent. **The kit
never spends them**: it has no idea what a level is worth. The game decrements
it as it hands out whatever a level buys.

`max_level` caps progression. At the cap `current` stops accumulating, because a
bar filling toward a level that will never arrive is worse than a full one — but
`total` keeps counting, because an end-of-run screen should report everything
collected.

### Curves

`LevelCurve` is a `Protocol`, so a bespoke curve is one method with nothing to
import and nothing to inherit from.

| Curve | Shape |
|---|---|
| `Linear(base, step)` | Each level costs a fixed amount more than the last. |
| `Geometric(base, growth)` | Each level costs a fixed *multiple* of the last. |
| `Table(costs)` | Costs read off a list a designer wrote. Past the end, the last entry repeats. |

### Events, not callbacks

```python
dispatcher.subscribe(LeveledUp, lambda event: scene_manager.push(LevelUpScene()))
```

This is the load-bearing decision in the kit: it's how a level-up *scene* gets
pushed without the kit knowing that scenes, or UI, or upgrade cards exist.

`ExperienceGained` carries the settled numbers and is dispatched **before** the
`LeveledUp`s it caused, so a listener redrawing an experience bar has already
done it by the time another pushes a scene over the top.

## Upgrades

```python
from pyguara.kits.progression import Upgrade, UpgradeRecord, offer, take

pool = [
    Upgrade(key="whip", apply=lambda eid: boost(eid, "damage", 0.1), max_taken=None),
    Upgrade(key="bracer", apply=lambda eid: boost(eid, "armor", 5)),
    Upgrade(
        key="evolved_whip",
        apply=lambda eid: give_evolved_whip(eid),
        requires={"whip": 5, "bracer": 1},
    ),
]

cards = offer(rng, pool, record, count=3)   # the 1-of-3 pick
take(record, cards[chosen], player.id)
```

**`Upgrade.apply` is an opaque callable.** The kit never learns that "+10% move
speed" means a `StatBlock` modifier, or that "pierce" means an `Effect` — the
game writes the closure. So this package imports neither `kits.stats` nor
`kits.effects` while composing perfectly with both, and with whatever a game
invents that neither anticipated. There is a test that parses the package's
imports and fails if that is ever quietly spent.

**`offer()` does not reimplement weighted selection.** It filters by eligibility
and delegates to `common.random.weighted_choice`, sampling without replacement
so a card cannot appear twice in one pick. A late run that has exhausted its
pool offers two cards rather than raising.

The same seed and the same record produce the same offer, which is what lets a
run be replayed.

**Weapon evolution needs no new type.** `requires` plus `UpgradeRecord.taken`
*is* the mechanism — "evolved whip requires whip ×5 and the bracer" is a
`requires` of `{"whip": 5, "bracer": 1}`. That's what earns `requires` its place
in an otherwise minimal kit, and it takes evolution trees out of the "needs an
item model" column entirely.

`take()` updates the record **before** running the closure, so an upgrade that
scales with its own stack count sees the take it is part of.

## The pickup magnet

```python
from pyguara.kits.progression import Attracted, Magnet, MagnetSystem

player.add_component(Magnet(radius=120.0, speed=120.0, acceleration=600.0))
orb.add_component(Attracted(payload=5.0, collect_radius=12.0))
orb.add_component(SpatialTracked())

magnets = MagnetSystem(entity_manager, dispatcher, spatial_index)
```

**Not a physics interaction.** A magnet is a radius query and a velocity — no
collider, no body, no contact resolution. An orb passes through walls on its way
to the player, which is what the genre wants and what keeps a thousand of them
affordable. A game that needs pickups to respect geometry gives them a
`Collider` and doesn't use this.

It's the second consumer of the shared `SpatialHash` (`kits/projectiles` was the
first), which is the point: attraction is a "what is near me" question, and that
index answers it in one cell walk rather than a scan over every orb on the
field. Entities must be tracked in it the usual way (`SpatialTracked` +
`SpatialIndexSystem`); this system never inserts into the index itself.

Collecting dispatches `PickupCollected` carrying the orb's opaque `payload` and
marks the pickup inactive. **Destroying it is left to the game**, which may want
to pool it, play something on it, or fade it out. A typical listener calls
`grant_experience()` with the payload.

`Attracted.active` exists so a just-dropped orb can sit inert for a moment
instead of flying straight back into whoever dropped it.
