# Correição

*Correição* is what the Brazilian northeast calls an army-ant raid: a
column of thousands that sweeps the ground and eats whatever cannot get
out of the way. Here a calango, a striped lizard, is in the way.

## What it is for

Correição is the engine's horde benchmark. Phase 9 of the roadmap decides
two performance changes, visibility culling (#161) and columnar components
(6g), on measurement rather than instinct, and no other demo can provide
it: every other demo draws by hand, and none has a horde in a world
larger than the screen. So this one is built to be the measurement:

- **Every sprite goes through the engine's own path.** The ground, the
  ants and the calango are entities with a `Sprite`, drawn by the base
  `Scene.render`, through `RenderSystem`'s sort and batching.
- **The world is larger than the screen.** It is about five screens on
  each side, strewn with 4,000 tufts and stones, and the camera follows the
  calango. At any moment most of the sprites are off screen, as in any
  scrolling game.
- **The raid's size is one argument.** `HordeScene(ants=...)`, or
  `--ants` on the command line, runs the same game at 1,000 or 10,000.
- **It plays itself.** Until a key is pressed the calango walks a fixed
  loop, so a benchmark run and a frame capture see the same world every
  time.

`tools/horde_probe.py` runs it at 1,000, 5,000 and 10,000 ants and prints
where each frame goes. The results are in `docs/guides/performance.md`.

## How it plays

- **WASD or the arrows** move the calango.
- **The pulse:** once a second the calango lets out a pulse that kills
  every ant within 150 pixels.
- **Bites:** an ant touching the calango bites, and the bites wear its
  health down. The calango recovers slowly; overrun, it gets back up at
  full health and the count goes up, so the demo never ends.
- **The raid** keeps its size. Ants killed, and ants left far behind, are
  replaced just out of view, up to 250 a tick.

## How it is built

| Piece | Where | What it does |
| --- | --- | --- |
| Movement of the raid | `FlockingSystem` (engine, native) | Steers every ant toward the calango and apart from its neighbours, in one call a tick |
| Animation | `AnimationSystem` (engine) | Two-frame walk cycle on every ant |
| `PlayerSystem` | `systems.py` | The keys, or the autopilot loop |
| `HordeSpawner` | `systems.py` | Tops the raid up on a ring just past the screen's corners |
| `CombatSystem` | `systems.py` | The only loop over the whole raid, ten times a second: pulses, bites, stragglers, each ant's seek target and facing |

The combat pass runs at 10 Hz on purpose. It is the one piece of Python
that visits every ant, and nothing it decides needs to happen within a
sixtieth of a second.

## Art

`make_art.py` draws every sprite pixel by pixel and writes the PNGs in
`assets/`, so the demo ships nothing it did not make. Run it again after
changing a sprite:

    uv run python -m examples.correicao.make_art
