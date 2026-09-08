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

- **Dataclass components** are filled field by field. `{"x": ..., "y": ...}`
  dicts become `Vector2`; an `Enum` field accepts a member name
  (case-insensitive) or a raw member value.
- **A key that matches no field raises `ValueError`.** A typo in a prefab
  (`"colour"` for `"color"`) is an authoring error, caught at instantiation
  rather than surfacing later as a missing value.
- **`Transform`** has a custom `__init__` and is not a dataclass, so it goes
  through a built-in deserializer. `clear()` wipes user registrations and
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
overrides)`. Each child is instantiated as its **own entity** and its
`Transform` is parented to the parent entity's `Transform`
(`set_parent(..., keep_world_transform=False)`):

- The child's authored position is treated as **local** to the parent.
- `offset` (`{"x": .., "y": ..}`) is added to that local position.
- Moving the parent entity moves the children with it.

A child needs a resolver to be found (the per-scene factory has one); without
one, children are skipped with a warning. A child with an `offset` but no
`Transform` component logs a warning and the offset is ignored.

## Instantiation and metadata

`factory.create(prefab, entity_id=None, overrides=None, source_path=None)`
returns the entity. `overrides` is a second deep-merge layer applied after
inheritance. Every created entity gets a **`PrefabInstance`** component
recording `prefab_path` (the `source_path`, or `prefab.name` for an in-memory
prefab) and the `instance_overrides` that were applied.

`factory.create_from_path(path, ...)` resolves the path through the resolver
and passes it as `source_path`, so instances carry the real file path.

A component whose data cannot be built (unknown field, bad enum value, type
mismatch) makes `create()` **raise** rather than return a half-populated
entity. An unregistered component name is skipped with a warning — register
it if it is meant to be there.

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
