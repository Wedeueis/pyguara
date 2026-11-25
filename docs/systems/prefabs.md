# Prefab System

`pyguara.prefabs` turns a **data description of an entity** — components and
their field values, optional inheritance, optional child entities — into a
live entity in a scene's `EntityManager`. Prefabs can be built in memory or
loaded from `.prefab` / `.prefab.json` / `.prefab.yaml` files.

## Layers

1. **`PrefabData`** (`pyguara.prefabs.types`) — the template: a `name`, a
   `components` dict (`{ComponentName: {field: value}}`), an optional
   `extends` path, an optional `children` list, `tags`, and a `version`.
2. **`ComponentRegistry`** (`pyguara.prefabs.registry`) — maps a component
   *name* to its class so `{"Transform": {...}}` can be turned into a
   `Transform` instance. The bootstrap registers every core engine component
   (`Transform`, `Tag`, `RigidBody`, `Collider`, the AI/animation/audio
   components, `PrefabInstance`, …) on a process-global registry, exposed
   through DI as `ComponentRegistry`.
3. **`PrefabLoader`** / **`PrefabCache`** (`pyguara.prefabs.loader`) — read a
   file into `PrefabData`. `PrefabLoader` is also registered with the
   `ResourceManager` for the `.prefab` extension. `PrefabCache` adds a
   path→`PrefabData` cache and is the DI-registered singleton.
4. **`PrefabFactory`** (`pyguara.prefabs.factory`) — instantiates a
   `PrefabData` into an entity. One is created per scene in
   `Scene.resolve_dependencies()`, bound to that scene's `EntityManager` and
   with its resolver wired to `PrefabCache.load`, so `extends` and `children`
   paths resolve against files on disk.

```python
from pyguara.prefabs import PrefabData

goblin = PrefabData(
    name="Goblin",
    components={
        "Transform": {"position": {"x": 100, "y": 80}},
        "Tag": {"name": "enemy"},
    },
)
entity = self.prefab_factory.create(goblin)
```

## The component registry

`registry.create(name, data)` builds one component:

- **Dataclass components** are filled field by field, converting by the
  field's type. A field typed `X | None` converts as `X`.
  - **`Vector2`:** `{"x": ..., "y": ...}` or `[x, y]`.
  - **`Color`:** `{"r", "g", "b"}` with an optional `"a"`, `[r, g, b]` or
    `[r, g, b, a]`, or `"#rrggbb"` / `"#rrggbbaa"`.
  - **`Enum`:** a member name (case-insensitive) or a raw member value.
  - **Anything else** is taken as written.
- **Data that does not fit its type raises `ValueError`**, naming the type:
  a vector missing `"y"`, a colour with two channels, a channel that is a
  string. Nothing falls back to zero or keeps the raw dict.
- **A field whose annotation names a type imported only for type
  checking** cannot be converted. Its other fields still work, and data
  that sets it raises, naming the field.
- **A key that matches no field raises `ValueError`.** A typo in a prefab
  (`"colour"` for `"color"`) is an authoring error, caught at instantiation
  rather than surfacing later as a missing value.
- **`Transform`** has a custom `__init__` and is not a dataclass, so it goes
  through a built-in deserializer, which holds its four fields to the same
  rules. `clear()` wipes user registrations and
  **re-seeds the built-ins**, so a cleared registry can still round-trip
  `Transform` once it is re-registered.

Register your own components with the class or the decorator:

```python
from pyguara.prefabs import register_component

@register_component
class Health(BaseComponent):
    current: int = 100
    maximum: int = 100
```

## Inheritance — `extends`

`extends` names another prefab (by resolver path). Parent components are
resolved first, then the child's `components` are **deep-merged** over them:
nested dicts merge key by key, so a child can override
`Transform.position.x` alone and inherit `y` and `scale`.

A resolver is required for `extends` to do anything — the per-scene factory
has one. An `extends` chain that refers back to a prefab already being
resolved raises `ValueError` naming the cycle (`a -> b -> a`) instead of
recursing until the stack runs out.

## Children

`PrefabData.children` is a list of `PrefabChild(prefab, offset, name,
overrides)`. Each child is instantiated as its **own entity**, linked to
its parent twice:

- **Ownership:** `entity_manager.set_parent(child, parent)`, so destroying
  the parent destroys its children, and theirs. Destroying a child leaves
  the parent.
- **Position:** the child's `Transform` is parented to the parent's
  (`set_parent(..., keep_world_transform=False)`). Its authored position is
  **local** to the parent, `offset` (`{"x": .., "y": ..}`) is added to it,
  and moving the parent moves the child.

A child with an `offset` but no `Transform` logs a warning and the offset
is ignored.

**`create()` checks the whole tree before building any of it.** Each of
these raises `ValueError` with nothing created:

- a child, at any depth, that does not resolve, or a prefab with children
  and a factory with no resolver;
- a prefab that contains itself, directly or through its children;
- a child `name`, used as its entity id, that is already in use or
  appears twice in the tree.

If building fails partway, on component data for example, every entity
created so far is destroyed before the error propagates.

## Instantiation and metadata

`factory.create(prefab, entity_id=None, overrides=None, source_path=None)`
returns the entity. `overrides` is a second deep-merge layer applied after
inheritance. Every created entity gets a **`PrefabInstance`** component
recording `prefab_path` (the `source_path`, or `prefab.name` for an in-memory
prefab) and the `instance_overrides` that were applied.

`factory.create_from_path(path, ...)` resolves the path through the resolver
and passes it as `source_path`, so instances carry the real file path.

A component whose data cannot be built (unknown field, bad enum value, type
mismatch) makes `create()` **raise**, destroying what it had built, rather
than return a half-populated entity. An unregistered component name is skipped with a warning — register
it if it is meant to be there.

## Resources a prefab names

A `Texture` or `AudioClip` field takes the file's path, and the
application's component registry loads it through the `ResourceManager` as
the prefab is built:

```json
{"components": {"Sprite": {"texture": "sprites/goblin.png"}}}
```

- **A file that does not load fails `create()`** with a `ValueError`
  naming the prefab and the component, e.g. `prefab
  'enemies/goblin.prefab.json', component Sprite: FileNotFoundError: ...`.
  The original error is its `__cause__`. Before the registry loaded
  textures, the path stayed a string and failed only when drawn.
- **`factory.check(prefab)` and `factory.check_path(path)`** raise wherever
  `create` would, without creating an entity. They build, then discard,
  every component of the prefab and its children, with each child's
  overrides. Run them as a game loads, to fail on a missing texture then
  rather than mid-level; the resources stay cached for the real spawn.
- **The registry is process-wide**, so in a process that builds several
  applications, the most recent one's resource manager serves it.

## File format

```json
{
  "name": "Goblin",
  "version": 1,
  "extends": "enemies/base_enemy.prefab.json",
  "tags": ["enemy", "melee"],
  "components": {
    "Transform": { "position": { "x": 0, "y": 0 } },
    "Health": { "current": 30, "maximum": 30 }
  },
  "children": [
    { "prefab": "fx/torch.prefab.json", "name": "torch", "offset": { "x": 8, "y": -4 } }
  ]
}
```

`PrefabLoader` accepts `.prefab.json`, `.prefab.yaml` / `.prefab.yml` (when
PyYAML is installed), and `.prefab` (format auto-detected). A file whose
top-level value is not a mapping raises `ValueError`. If `name` is omitted the
file stem is used.

## Versions and migration

A prefab file's `version` says which schema it was written in. When a
component changes shape, bump the game's prefab version and register a
step that upgrades the old data. The loader runs every step on load,
before parsing, so files written under the old schema keep working.

```python
from pyguara.persistence.migration import Migration, MigrationManager
from pyguara.prefabs import PrefabLoader

def health_renamed(data: dict) -> dict:
    health = data.get("components", {}).get("Health")
    if health is not None:
        health["maximum"] = health.pop("max")
    return data

migrations = MigrationManager(current_version=2)
migrations.register(Migration(1, 2, health_renamed, "Health.max -> maximum"))
container.get(PrefabLoader).migrations = migrations
```

- **Steps:** each step takes and returns the file's whole data. The steps
  are persistence's `Migration` and `MigrationManager`, the same ones save
  files use.
- **What loads:** a file with no `version` is version 1, and a loaded
  prefab reports the current version. A parent named by `extends` upgrades
  too, because it loads through the same loader.
- **Errors:** a version newer than the game knows, a gap in the steps, a
  step that fails, or a version that is not a whole number from 1 each
  raise `ValueError`, naming the file.
- **Without migrations,** the loader keeps the version as written and
  changes nothing. Bootstrap registers its `PrefabLoader` in the container
  for this reason.

## Spawning from a map

`spawn_objects` turns the objects on a Tiled or LDtk map into entities. The map
says what an object's `type` is, and the game says which prefab that means:

```python
from pyguara.tilemap import load_tmx
from pyguara.tilemap.spawning import spawn_objects

level = load_tmx("levels/cave.tmx")
spawned = spawn_objects(
    level,
    factory,
    {"Bat": bat_prefab, "Door": door_prefab},
    ignore_types={"CameraBounds"},  # read through `level.objects(...)` instead
)
for item in spawned:
    item.entity, item.source  # the entity, and the MapObject it came from
```

It lives in its own module, not `pyguara.tilemap`, so reading a map never imports
the ECS.

| Rule | Why |
| --- | --- |
| **All or nothing.** Every object is checked first, and `MapSpawnError` lists every problem with nothing spawned | A mistake should not leave half a level in the world |
| An object whose `type` has no prefab raises | A silently unspawned enemy is found by noticing a room is empty. Use `ignore_types` for what the game handles itself |
| An object with no `type` is skipped | It names nothing |
| `Transform` goes at the object's **centre** | A collider is centred on its transform. Tile objects, whose corner is the bottom left, and rotated objects are handled |
| A sized rectangle or a circle shapes any `Collider` or `TriggerVolume` in the prefab | So a door is the size it was drawn |
| A polygon or polyline on a prefab with a collider raises | `Collider.dimensions` cannot carry vertices, and a bounding box would collide where nothing is drawn |
| Objects and layers hidden in the editor are skipped | `include_hidden=True` to spawn them |

**Properties.** A custom property named `Component.field` overrides that field,
and can go deeper (`Health.max = 30`, `Transform.scale.x = 2`). It beats the
object's own shape, and a component or field that does not exist raises. Any
other property is the game's own, on `item.source.properties`.

`offset=` moves everything, for a room placed inside a larger world.

## Spawn tables

A spawn table names prefabs and how likely each is, so waves, room contents
or scattered scenery are authored as data and rolled the same way for the
same seed. A `.spawn.json` file:

```json
{
  "choices": [
    {"prefab": "prefabs/goblin.prefab.json", "weight": 3},
    {"prefab": "prefabs/orc.prefab.json", "weight": 1,
     "overrides": {"Health": {"max": 40}}}
  ]
}
```

```python
from pyguara.prefabs import load_spawn_table

table = load_spawn_table("data/cave.spawn.json")
enemies = factory.spawn(table, rng, count=5, positions=spawn_points)
```

- **Weights** need not sum to 1. A choice weighted 0 stays in the table and
  is never picked. A table with no positive weight is refused when it is
  built.
- **Picking:**
  - `table.pick(rng)` picks one choice.
  - `table.pick_many(rng, n)` picks `n`, each independently.
  - `table.pick_many(rng, n, unique=True)` picks `n` different choices.
- **Spawning:** `factory.spawn` applies each choice's overrides, then sets
  `Transform.position` from `positions`, in order, when they are given.
  Every pick is resolved before anything is created, so a choice whose
  prefab does not load raises and spawns nothing.
- **Textures:** a prefab's `Sprite` names its texture by path, and a
  scene's `prefab_factory` loads it (see "Resources a prefab names").
  Correição scatters its ground this way, after checking each prefab with
  `check_path` (`examples/correicao/prefabs/`).

## Named variants

A variant is a prefab with some fields replaced and some numbers scaled,
named once in a library instead of written as an `extends` file per
variant or as overrides repeated at every spawn site.

```json
{
  "variants": {
    "elite_goblin": {
      "base": "prefabs/goblin.prefab.json",
      "overrides": {"Tag": {"name": "Elite goblin"}},
      "multiply": {"Health": {"max_health": 1.5, "current": 1.5}},
      "tags": ["elite"]
    }
  }
}
```

```python
from pyguara.prefabs import PrefabCache, PrefabFactory, load_variants

variants = load_variants("data/enemies.variants.json")
factory = PrefabFactory(manager, registry, variants.resolver(PrefabCache().load))
elite = factory.create_from_path("elite_goblin")
```

- **Where a variant works:** `variants.resolver(base)` wraps a prefab
  resolver. Any lookup through the factory can then name a variant
  wherever it takes a prefab path: `create_from_path`, a spawn table's
  choice, a child, or another variant's `base`.
- **What a variant resolves to:**
  - its base's component data, with the base's `extends` chain already
    applied;
  - its base's children;
  - the tags of both.
  - The entity's `PrefabInstance.prefab_path` is the variant's name.
- **`multiply`** scales numbers the base already sets, nested as the
  component data is. An `int` field stays an `int`, rounded to the
  nearest. These all raise, naming the variant and the field:
  - multiplying a field the base does not set, or one that is not a
    number;
  - a negative or non-finite factor;
  - multiplying a field that `overrides` also sets.
- **Names** contain no slash, backslash or dot, so a variant can never
  shadow a prefab path. A variant whose base does not load resolves to
  `None`, as a missing prefab does. A cycle of bases raises.
- **Example:** Correição's boulder is its stone at twice the size,
  scattered by the same spawn table
  (`examples/correicao/prefabs/ground.variants.json`).
