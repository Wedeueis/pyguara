# Configuration

`pyguara.config` holds the engine's settings as nested dataclasses, loads and
saves them as JSON, and validates them against what the engine can actually
honour.

```python
from pyguara.config import ConfigManager

manager = ConfigManager()
manager.load()                                   # config/game_config.json

manager.config.display.fps_target                # read directly
manager.update_setting("audio", "master_volume", 0.5)   # write through here
```

Bootstrap builds one `ConfigManager`, loads it, and registers it in the DI
container, so any service can take a `ConfigManager` in its constructor.

## Sections

| Section | Holds |
| --- | --- |
| `display` | Resolution, FPS target, fullscreen, vsync, title, backend, clear colour |
| `audio` | Master, SFX and music volumes; mute |
| `input` | Mouse sensitivity, gamepad enable and deadzone |
| `physics` | Fixed timestep, max frame time, gravity |
| `debug` | Log level and destinations, profiler, inspector, collider and FPS overlays |

```python
manager.config.physics.fixed_dt   # 1 / fixed_timestep_hz, in seconds
```

### Game-defined sections

`GameConfig` is closed — those five, full stop. A game registers its own
section instead of growing a second JSON loader beside the engine's:

```python
from dataclasses import dataclass

@dataclass
class BalanceConfig:
    enemy_hp_scale: float = 1.0
    drop_rate: float = 0.25
    boss_waves: int = 3

manager.register_section("balance", BalanceConfig)
manager.load()

manager.section(BalanceConfig).drop_rate        # typed
manager.update_setting("balance", "drop_rate", 0.4)
```

It then gets everything an engine section gets: the same file (at the top
level, beside `display` — nothing is nested under a `custom` key), the same
type coercion on load, the same `PYGUARA_BALANCE_DROP_RATE` override, the same
`update_setting()` checks, the same profile layering, and validation if it asks
for it.

**Register before `load()`.** `from_dict()` can only build a section the
registry knows about, so a late registration would discard whatever the file
said and hand back defaults instead. Registering afterwards raises rather than
doing that quietly, and a section in the file that nothing registered is logged
by name:

```
Unknown config section 'balance' ignored. Register it with
ConfigManager.register_section('balance', ...) before load(), or remove it
from the file.
```

The dataclass must be constructible with no arguments — those values are what a
missing file falls back to.

`section()` is keyed by type rather than name because that is what game code
actually holds, and it stays type-checked where `config.custom["balance"]`
would be `Any`. It finds engine sections too
(`manager.section(PhysicsConfig)`).

#### Validating a game's own values

The engine cannot know what `drop_rate` means, so a section carries its own
rules by growing a `validate()` method (the `ValidatableSection` protocol —
opt-in; a section without one is simply unchecked):

```python
@dataclass
class BalanceConfig:
    drop_rate: float = 0.25

    def validate(self) -> list[ValidationIssue]:
        if 0.0 <= self.drop_rate <= 1.0:
            return []
        return [ValidationIssue(
            ValidationSeverity.ERROR, "balance", "drop_rate",
            f"drop_rate must be within 0..1, got {self.drop_rate}.",
        )]
```

`ValidationIssue.section` is overwritten with the registered name, so you
cannot get it wrong. An `ERROR` or `CRITICAL` from here blocks
`update_setting()` and `push_profile()` exactly as an engine rule does. A
`validate()` that raises becomes one `ERROR` naming the section rather than
taking down startup.

`fixed_dt` raises `ValueError` rather than `ZeroDivisionError` if
`fixed_timestep_hz` is not positive — `Application.run()` reads it on every
startup, so the message names the setting.

## Loading and saving

```python
manager.load()                      # default path
manager.load("saves/settings.json") # explicit path
manager.save()
```

A missing file is not an error: defaults are written to that path so the game
has something to edit, and the call succeeds.

`load()` returns whether the file was **readable**, not whether its contents
are sensible. Call `validate()` for that.

### Round-tripping

Values are coerced back to their declared types on load, which plain
construction would not do:

- `Color` is rebuilt from its `{"r": …, "g": …}` form.
- Enums resolve from either a member name (`"DEBUG"`, `"moderngl"`) or a raw
  value (`10`, `"pygame"`).

An unrecognised enum value falls back to the engine default and logs a warning
rather than raising, so one bad line does not stop the game from starting.

### Unknown keys

Keys the engine does not recognise are ignored and logged:

```
Unknown config key 'display.screen_widht' ignored. Check for a typo, or a
setting from a different engine version.
```

A config written by a newer engine therefore still loads.

## Changing settings

Write through `update_setting()` rather than assigning to the dataclass. It
type-checks the value, refuses anything the validator considers unusable, and
dispatches `OnConfigurationChanged`.

```python
manager.update_setting("display", "fps_target", 144)     # True
manager.update_setting("display", "fps_target", "fast")  # False, unchanged
manager.update_setting("display", "fps_target", True)    # False — bool is not an int here
manager.update_setting("audio", "master_volume", 99.0)   # False, out of range
manager.update_setting("display", "fps_target", 20)      # True — a warning is advice
```

Type rules are stricter than `isinstance` in one place and looser in another:

- A `bool` is **not** accepted for an `int` field, though Python says
  `isinstance(True, int)`.
- An `int` **is** accepted where a `float` is declared, the one widening both
  JSON and Python expect.

A rejected change mutates nothing and dispatches no event.

Direct assignment (`manager.config.audio.master_volume = 99.0`) bypasses all of
this. It is legal, and occasionally what you want during bootstrap, but nothing
will check it.

## Validation

```python
for issue in manager.validate():
    print(issue.severity, issue.section, issue.setting, issue.message)
```

| Severity | Meaning |
| --- | --- |
| `INFO` | Worth knowing; harmless |
| `WARNING` | Legal but likely to disappoint |
| `ERROR` | The engine will misbehave, but can still start |
| `CRITICAL` | The engine cannot start with this value |

`load()` logs each issue **at its own level**, so an `ERROR` appears as an
error rather than being buried among warnings.

`update_setting()` blocks a change that introduces an `ERROR` or `CRITICAL`
issue for the field being set. `WARNING` and `INFO` pass through — they are
advice, not a veto.

## Environment overrides

Applied after the file is read, so they win.

Any setting in any section — including a game's own — is reachable as
`PYGUARA_<SECTION>_<FIELD>`:

```bash
PYGUARA_DISPLAY_FPS_TARGET=144
PYGUARA_AUDIO_MUTED=true
PYGUARA_BALANCE_DROP_RATE=0.75
```

Four short aliases predate that rule and do not follow it. They stay because
launch scripts and CI jobs set them:

| Variable | Overrides |
| --- | --- |
| `PYGUARA_LOG_LEVEL` | `debug.log_level` — a name, e.g. `DEBUG` |
| `PYGUARA_BACKEND` | `display.backend` — `pygame` or `moderngl` |
| `PYGUARA_WINDOW_WIDTH` | `display.screen_width` |
| `PYGUARA_WINDOW_HEIGHT` | `display.screen_height` |

The explicit form wins where both name the same field — it says which field it
means, so it is the more deliberate of the two.

Booleans accept `1/true/yes/on` and `0/false/no/off`. Enums accept a member
name or a value. A `Color` or a nested dataclass is **refused** rather than
parsed from an invented syntax — the file is the place for those.

An unparseable value is reported and skipped:

```
Ignoring PYGUARA_BACKEND='vulkan': not a valid RenderingBackend.
Expected one of PYGAME, MODERNGL.
```

A variable whose section matches but whose field does not is reported too — a
mistyped field under a real section is a typo, not someone else's variable:

```
Ignoring PYGUARA_DISPLAY_FPS_TARGEET: 'display' has no setting 'fps_targeet'.
```

One naming no section at all is left alone; it belongs to something else.

A **missing** config file is written with the engine's defaults *before*
overrides are applied: the file is the game's to edit, while an override
belongs to one launch. (It also means the first launch now applies them at all,
which it previously skipped.)

## Events

With a dispatcher wired in, three events are published:

```python
from pyguara.config.events import (
    OnConfigurationChanged,
    OnConfigurationLoaded,
    OnConfigurationSaved,
)

dispatcher.subscribe(OnConfigurationChanged, settings_menu.refresh)
```

`OnConfigurationChanged` carries `section`, `setting`, `old_value` and
`new_value` — enough for a settings screen to react without re-reading the
whole config.

## Rules of thumb

1. Load once at bootstrap; read from the injected `ConfigManager` afterwards.
2. Write through `update_setting()`. Assign directly only when you mean to
   skip validation.
3. `load()` returning True means the file parsed, not that it is sane — check
   `validate()` if you care.
4. Adding a field to a config dataclass is enough; loading, saving and
   coercion are driven by the declared types.
5. A game's own tunables belong in a registered section, not a second JSON
   file. Register them before `load()`.
