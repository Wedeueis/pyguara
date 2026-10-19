# ADR 0005: `System.update` is the fixed step, and keeps its name

- **Status:** accepted
- **Date:** 2026-10-18

## Context

The engine has two update channels, and the names for them are inverted
between the two halves of the API.

| | fixed rate | display rate |
| --- | --- | --- |
| `Scene` | `fixed_update(fixed_dt)` | **`update(dt)`** |
| `System` | **`update(dt)`** | `variable_update(dt)` |

`SceneManager.fixed_update()` calls `scene.system_manager.update(fixed_dt)`
and then `scene.fixed_update(fixed_dt)`; `SceneManager.update()` calls
`scene.system_manager.variable_update(dt)` and then `scene.update(dt)`. So
`update` means the opposite thing depending on which object you are
holding, and a developer who has just written one is primed to misread the
other.

An external audit raised this as a defect and proposed renaming
`System.update` to `fixed_update`.

### Why the collision exists

Systems ticked on the fixed step before there was a variable channel to
offer them. When one was added it could not take the free name, so it
became `variable_update` on an opt-in `VariableStepSystem` protocol, and
the already-correct `System.update` kept the name it had.

### What makes a rename dangerous rather than merely churny

A rename here is not a refactor with a compiler to lean on. `System` is a
`runtime_checkable` Protocol, so **conformance is checked by method name at
runtime**, and nothing annotates itself as implementing it. Renaming the
method would therefore:

- Silently re-time every system that was not updated. A class still
  defining `update` keeps satisfying `System` — `SystemManager` would call
  the new name, find nothing, and the system would simply stop ticking,
  with no error anywhere. 55 `def update(self, dt` definitions exist under
  `pyguara/` alone, plus every system in `games/` and in any game built on
  the engine.
- Break the one thing the asymmetry buys. `Scene.fixed_update` and
  `System.update` being spelled differently is what lets a reader see, at
  a call site, whether they are looking at a scene hook or a system tick.

Mypy does not help: strict mode is on for `pyguara/`, but a structural
protocol nobody inherits from has nothing to check against. The failure
mode is a system that quietly never runs, which is the worst shape a
regression can take in a frame loop.

### What is actually wrong

Not the names — the documentation. `System.update`'s own docstring read:

> Update system logic.
>
> Args:
>     dt: Delta time in seconds since last update

Every word of that is true of either channel. The fixed-step meaning was
written down in exactly one place: the class docstring of
`VariableStepSystem` — the one protocol a system does **not** have to
implement in order to have `update` called on it. A reader who implements
`System` and nothing else, which is every system in the engine, never
passes the sentence that would tell them what they just wrote.

The same bare docstring is copied onto `InitializableSystem.update` and
`CleanupSystem.update`, so all three entry points into the API are
equally silent.

## Decision

**Do not rename `System.update`.** The inversion stays.

Instead:

1. Every protocol in `pyguara/systems/protocols.py` that declares `update`
   states in its own docstring that it is the **fixed** step, names
   `Scene.update` as the opposite channel, and cites this ADR.
2. `VariableStepSystem.variable_update` says which step it is in words,
   rather than only describing its `dt` as "seconds since the last
   rendered frame" and leaving the reader to infer it.
3. `tests/test_system_step_naming.py` pins those docstrings, so the bare
   copies cannot come back.

## Consequences

**The asymmetry is now a documented contract rather than an accident.** A
reader meeting `System.update` learns which step it is from the thing they
are already reading.

**The cost is that the documentation has to carry what the name cannot.**
That is load-bearing prose, which is why it is tested. A docstring test is
an unusual thing to write; it is justified here because the docstring is
the *only* mechanism conveying a fact that a mistake about re-times a game
loop.

**The hazard is reduced, not removed.** Someone can still write
`def fixed_update` on a system and watch it never be called. That is a
different gap — there is no diagnostic for a system defining a method no
protocol declares — and it is not solved by naming.

**If this is ever revisited**, the safe sequence is: accept both names on
`SystemManager` for a release, warn on the old one, then drop it. Not a
rename in place.

## Alternatives considered

**Rename `System.update` to `fixed_update`.** Rejected above: silent
re-timing, no compiler or type checker to catch it, and the breakage lands
in third-party game code.

**Rename `Scene.update` to `variable_update` instead.** Worse. `Scene` is
the class every tutorial and every demo subclasses, `update` is the first
method anyone overrides, and the same structural-typing problem applies —
`Scene.update` is `@abstractmethod`, so an outdated override would at
least raise, but it would raise in every game at once for a naming
preference.

**Accept both names on `System`, dispatching to whichever exists.** Two
spellings for one hook, forever, and `isinstance` against a
`runtime_checkable` protocol compares names — so a system defining both,
or neither, becomes ambiguous rather than wrong. The engine would be
carrying the confusion in code instead of in a docstring.

## See also

- `pyguara/systems/protocols.py` — the protocols and their docstrings.
- `pyguara/systems/manager.py` — `update()` and `variable_update()`, the
  two channels.
- `tests/integration/test_scene_owned_systems.py` — pins the **wiring**: a
  system recording each channel separately, driven three frames to one
  fixed tick so neither can stand in for the other.
- `tests/test_system_step_naming.py` — pins the docstrings.
