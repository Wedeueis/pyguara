# Persistence

`pyguara.persistence` is the save/load layer: it turns an object graph into
a durable file on disk and back, verifies it has not been corrupted, and
migrates old save files forward as your schema changes.

```python
from pyguara.persistence import PersistenceManager

pm = container.get(PersistenceManager)

pm.save_data("slot_1", {"level": 3, "hp": 100})
state = pm.load_data("slot_1")            # -> {"level": 3, "hp": 100} or None
```

The bootstrap wires a `PersistenceManager` backed by a `FileStorageBackend`
rooted at `./saves` and a `MigrationManager` at `current_version=1`.

## `save_data` / `load_data`

| | |
| --- | --- |
| `save_data(key, data, save_version=1, compress=False, fmt=JSON)` | Serialize, checksum, and write one blob. Returns `True` only if the bytes reached storage. |
| `load_data(key, verify_integrity=True)` | Read, verify, deserialize, migrate. Returns the object, or `None` if the key is absent, the blob is corrupt, or a migration failed. |

`data` may be any JSON-friendly graph; `Vector2`, `Color` and `Rect` are
recognised and round-trip as themselves. A `dict` is the only top-level
shape that migrations apply to.

- **`fmt`** — `SerializationFormat.JSON` (default, human-readable),
  `MSGPACK` (compact binary, same value-type support as JSON), or `BINARY`
  (pickle — handles arbitrary objects but **only load a `BINARY` file you
  trust**; deserializing a pickle runs code).
- **`compress`** — gzip the payload before writing. Transparent on load
  (the header records it).
- **`save_version`** — the schema version stamped into the file, read back
  by the migration step.

`load_data` never raises for a bad file: a missing key, a truncated blob, a
failed checksum, or a failed migration all log and return `None`.

## On-disk format

Each key is stored as **one file** — `saves/<key>.save` for the file
backend — laid out as a single-line JSON metadata header, a newline, then
the payload bytes:

```
{"version":"0.4.0","timestamp":"2026-09-08T17:02:37+00:00","data_type":"dict","checksum":"87f0…","save_version":1,"format":"json","compressed":false}
{
  "level": 3,
  "hp": 100
}
```

Metadata and payload share one file so there is no window in which they can
disagree — the write either lands whole or not at all. The `checksum` is an
MD5 of the payload bytes exactly as written (after compression, if any);
`load_data(verify_integrity=False)` skips the comparison.

## Storage backends

`PersistenceManager` talks to a `StorageBackend` — a plain key → blob
store:

```python
class StorageBackend(Protocol):
    def save(self, key: str, blob: bytes) -> bool: ...
    def load(self, key: str) -> bytes | None: ...
    def delete(self, key: str) -> bool: ...
    def list_keys(self) -> list[str]: ...
```

`FileStorageBackend(base_path="saves")` is the built-in implementation. It
writes atomically (temp file, `fsync`, `os.replace`, then an `fsync` of the
directory) and sweeps orphaned `.tmp_*` files left by a crashed write on
startup.

**Keys must be filesystem-safe as given** — letters, digits, `_` and `-`.
A key containing a space, a dot, or a path separator is rejected with
`ValueError` rather than silently rewritten: `"slot 1"` and `"slot/1"` would
otherwise both collapse onto `slot1` and overwrite each other.

## Migrations

When a loaded save's `save_version` is older than the
`MigrationManager`'s `current_version`, `load_data` walks the registered
migrations in order and applies each one before returning.

```python
from pyguara.persistence import register_migration

@register_migration(from_version=1, to_version=2, description="hp -> health")
def _v1_to_v2(data: dict) -> dict:
    data["health"] = data.pop("hp")
    return data
```

A migration function takes the data `dict`, mutates and returns it. The
`MigrationManager` threads one dict through the whole chain
(`1 → 2 → 3 → …`), so a migration sees the output of the previous step.

- Register via `@register_migration` (collected in the global registry,
  which the bootstrap drains into the manager) or
  `MigrationManager.register(Migration(...))` directly.
- `to_version` must be greater than `from_version`, both `>= 1`, and no two
  migrations may share a `from_version`.
- The chain must be **contiguous** from the save's version to
  `current_version` — a gap raises `ValueError` (caught by `load_data`,
  logged, returns `None`).
- **No downgrades.** Loading a save whose version is *newer* than
  `current_version` fails rather than guessing.
- A migration that raises is wrapped in `MigrationError` with the failing
  step; the partly-migrated data is discarded.

`MigrationManager.needs_migration(v)` and `has_migration_path(v)` let you
check ahead of a load.

## Scenes

`SceneSerializer` (`pyguara.scene`) is the higher-level entry point for
saving a whole scene's entities and components; it serializes each entity to
a dict and hands the result to `PersistenceManager.save_data`. See the
Scenes page for that layer.
