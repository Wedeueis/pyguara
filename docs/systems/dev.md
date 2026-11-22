# Dev Tools

`pyguara.dev` holds development-only helpers: **asset hot-reload**, where
an edited texture, tilemap or data file is re-imported by the running game,
and **code hot-reload** for a game's systems.

## Code hot-reload

Edit a system and the running game uses the new code from the next frame,
without replaying it back to the state you were tuning.

```python
app = create_application()
app.enable_code_hot_reload()       # optional poll_interval, default 0.5s
app.run(MyScene())
```

Off by default, and refused in a frozen build. `SandboxApplication` does
not turn it on.

- **What is watched.** The source file of every game module that defines
  a registered system, in every scene, kept in step as systems are
  registered. Engine modules are never watched.
- **Only a module of nothing but systems.** Every class the module defines
  must have an `update` method. A component, event or enum defined beside
  a system has instances elsewhere that would keep the old class, so a
  query or an `is` check would quietly stop matching; such a module is not
  watched, and the log says which class to move out.
- **What happens on a change.** Between frames, on the main thread, the
  module is re-imported and each live system of one of its classes becomes
  an instance of the new class. Its attributes stay: its state, and the
  services it was constructed with. A system the new code needs to set up
  differently defines `on_reload(self)`, which is called after the swap.
  `get_system()` finds it by the old class or the new one.
- **When it fails.** A syntax error, an exception while importing, a
  non-system class added, or an `on_reload()` that raises: the module and
  every system are put back as they were, the old code keeps running, and
  the error is logged with the file and line. Fix the file and save again.

Not reloaded: scenes, components, and any other module. A function the
system's module imports from elsewhere keeps its old code until that
module is reloaded by a restart.

## Asset hot-reload

### Turning it on

Off by default. Enable it on the `Application`:

```python
app = create_application()
app.enable_asset_hot_reload()      # optional poll_interval, default 0.5s
app.run(MyScene("main", event_dispatcher))
```

`SandboxApplication` calls `enable_asset_hot_reload()` for you, so a sandbox
build has it from the start. The call is idempotent; there is no `disable()`
— `Application.shutdown()` stops the watcher.

### How it works

`AssetReloadWatcher` wraps a `PollingFileWatcher` and bridges it to
`ResourceManager.reload()`:

1. On `start()`, and periodically after, it reconciles its watch set with the
   `ResourceManager` cache — every cached resource whose `path` is a real
   file on disk is watched. Assets loaded later are picked up; evicted ones
   are dropped.
2. The polling thread detects a modified file (mtime or size change) and
   **queues** the resource's cache key. It does not reload anything itself.
3. `Application._update()` calls `watcher.drain()` once per frame, on the
   main thread. `drain()` calls `ResourceManager.reload(key)` for each queued
   asset, de-duplicating repeated changes to one reload, and returns the keys
   it reloaded.

The queue-then-drain split is deliberate: `ResourceManager` is not safe to
mutate from under a running frame, so the reload always happens on the loop
thread, never the watcher thread.

### The stale-reference caveat

`reload()` swaps the **cache entry**. Code that already holds the previous
resource instance keeps that stale object — reload does not mutate it in
place. Re-`load()` after a change to pick up the new instance:

```python
class MyScene(Scene):
    def update(self, dt: float) -> None:
        # cheap: a cache hit unless the asset was just reloaded
        self._tiles = self.container.get(ResourceManager).load("level1", TileMap)
```

An asset held only through `acquire()` (never re-`load()`ed) will not visibly
change until something re-fetches it.

## `PollingFileWatcher`

The watcher is usable on its own for any "run this when a file changes" need:

```python
from pyguara.dev import PollingFileWatcher

watcher = PollingFileWatcher(poll_interval=0.5)
watcher.watch("assets/levels/1.json", on_level_changed)
watcher.watch_directory("assets/shaders", rebuild_shader, pattern="*.glsl")
watcher.start()
...
watcher.stop()
```

It polls modification time and size — cross-platform, no native dependency,
not instantaneous. A change callback runs on the polling thread and **may**
call back into the watcher (`watch()`, `unwatch()`, `watched_count`); the
watcher fires callbacks with its lock released so that cannot deadlock. An
exception from one callback is logged and does not stop the others or the
poll loop.

`check_now()` runs one poll cycle synchronously and returns the changed
paths — useful in tests or a manually pumped loop instead of `start()`.

## Capability gaps

Polling only — no `inotify` / `FSEvents` / `ReadDirectoryChangesW` backend,
so detection lags by up to `poll_interval` and a burst of rapid saves is
coalesced rather than debounced. The watch set follows the resource cache,
so an asset that is not loaded yet is not watched (no "watch the whole
`assets/` tree" mode). These, and the stale-holder problem `reload()` leaves,
are tracked under issue #40.
