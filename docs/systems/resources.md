# Resource Management

The `ResourceManager` (`pyguara.resources`) is the central asset hub: one
cache, one place that knows how to turn a file path into a typed engine
object.

```python
from pyguara.resources import ResourceManager, Texture

manager = container.get(ResourceManager)
hero = manager.load("assets/chars/hero.png", Texture)
```

## Loading and caching

`load(path_or_name, resource_type)` resolves the path, returns the cached
instance on a hit, or runs the registered loader on a miss and caches the
result. It is type-safe: asking for a `Texture` when the file loaded as an
`AudioClip` raises `TypeError` immediately (on the miss *and* on a later
cache hit with a mismatched type).

Loaders are registered per extension (the **Strategy pattern**). The
bootstrap wires:

| Loader | Extensions | Produces |
| --- | --- | --- |
| `JsonLoader` | `.json`, `.manifest`, `.config` | `DataResource` |
| `PygameImageLoader` / `GLTextureLoader` | `.png`, `.jpg`, `.jpeg`, `.bmp`, `.tga` | `Texture` |
| `PygameSoundLoader` | `.wav`, `.ogg`, `.mp3` | `AudioClip` |
| `PrefabLoader` | `.prefab` | prefab data |

Registering a second loader for an extension logs a warning and wins.

## Naming: `index_directory`

`index_directory(root)` scans a tree and lets you load an asset by its bare
name instead of its full path:

```python
manager.index_directory("assets")
hero = manager.load("hero", Texture)          # -> assets/chars/hero.png
```

Both the stem (`hero`) and the full filename (`hero.png`) are indexed. If two
files under the tree share a stem (`chars/hero.png` and `fx/hero.png`), the
bare name is **ambiguous**: it is dropped and a warning names both paths. The
full-name keys still work, so load the colliding asset as `"hero.png"` or by
its full path.

## Lifecycle: reference counting

A `load()` is a cache *get*, not a claim. The resource enters the cache
**unpinned** (reference count 0), and a repeated `load()` of the same asset
does not change that.

| Call | Effect |
| --- | --- |
| `acquire(name)` | +1. Pin the resource so `unload_unused()` cannot evict it. |
| `release(name)` | −1. Must balance an `acquire()`. Dropping to 0 evicts immediately. Releasing something at 0 raises `ValueError`. |
| `unload_unused()` | Evict every resource at count 0. Call it between scenes. Returns the count freed. |
| `unload(name, force=True)` | Evict now, whatever the count. |
| `unload(name)` | Decrement like `release()`, but tolerant: a no-op if the name is unknown. |

`acquire()` / `release()` on an unloaded name raise `KeyError`.

So the pattern for an asset a scene must hold for its whole life is
`load()` then `acquire()` in `on_enter()`, and `release()` (or a blanket
`unload_unused()`) in `on_exit()`.

## Hot reload: `reload`

`reload(name)` re-runs the loader for a cached resource, re-reading its
`.meta` sidecar too, and swaps the new instance into the cache. The
reference count is preserved.

Callers that already hold the **previous** instance keep that stale object —
`reload()` swaps the cache entry, it does not mutate the old object. Call
`load()` again after a reload to pick up the new one. This is what a
file-watching hot-reload loop does.

## `.meta` sidecar import settings

An asset `hero.png` can carry a sibling `hero.png.meta` (JSON) describing how
to import it. A meta-aware loader receives the parsed settings; the resolved
object is also attached to the resource as `resource.import_meta` for systems
that need it after load.

```json
{ "type": "texture", "filter": "nearest", "premultiply_alpha": true }
```

`type` may be omitted when the extension implies it (`.png` → `texture`,
`.ogg` → `audio`). Unknown fields are ignored; an invalid file logs a warning
and is treated as "no meta". The `MetaLoader` caches by path and re-reads
when the file's mtime changes; `MetaLoader.invalidate(path)` forces a re-read
and `save_meta()` writes one back.

| Meta type | Fields | What currently consumes it |
| --- | --- | --- |
| `TextureMeta` | `filter`, `premultiply_alpha`, `srgb`, `mipmaps`, `wrap_s`, `wrap_t` | `PygameImageLoader` applies `premultiply_alpha`/`srgb`; `GLTextureLoader` applies `filter` (nearest ↔ linear). `mipmaps`/`wrap_*` are not applied yet. |
| `AudioMeta` | `volume_db`, `load_mode`, `loop_start`, `loop_end`, `normalize` | The audio system applies `volume_db` as a per-asset gain per play. `load_mode: stream` warns (clips are always fully decoded — use `play_music`). `loop_*`/`normalize` are not applied yet. |
| `SpritesheetMeta` | `frame_width`, `frame_height`, `margin`, `spacing`, `filter` | `SpriteSheet.slice_from_meta(meta)` reads the grid geometry (`margin`/`spacing` included). `filter` is not applied. |

## Atlases

`load_atlas(texture_path, json_path)` loads a packed-sprite texture plus a
JSON region map and returns an `Atlas`. It `acquire()`s the underlying
texture so `unload_unused()` will not pull it out from under the atlas; drop
it with `unload(texture_path, force=True)`. A malformed region map raises
`InvalidMetadataError` with line/column info.

## Introspection

`get_cache_stats()` returns `{"resource_count", "total_references",
"resources": {path: {"type", "ref_count"}}}` — useful for a debug overlay or
a leak check between scenes.
