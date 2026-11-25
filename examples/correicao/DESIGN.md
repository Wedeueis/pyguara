# Correição

*Correição* is what the Brazilian northeast calls an army-ant raid: a
column of thousands that sweeps the ground and eats whatever cannot get
out of the way. Here a calango, a striped lizard, is in the way.

## What it is for

Correição is the engine's horde benchmark. Phase 9 of the roadmap decided
visibility culling (#161) and how hordes are held (ADR 0013) on its
measurements, and no other demo could provide them: every other demo draws
by hand, and none has a horde in a world larger than the screen. So this
one is built to be the measurement:

- **It uses the engine's own paths.** The ground and the calango are
  prefabs, built by the scene's own `prefab_factory` and checked as the
  scene starts; the ground is picked from a spawn table, its boulder a
  named variant of the stone. Each is an entity with a `Sprite`, drawn by
  the base `Scene.render`. The raid is
  an engine `Swarm`, which steers, animates and draws its ants natively,
  sorted among those sprites by layer.
- **The world is larger than the screen.** It is about five screens on
  each side, strewn with 4,000 tufts, stones and boulders, and the camera follows the
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
| The raid | `Swarm` (engine, native) | Every ant, as an agent rather than an entity: steering, animation and drawing |
| `make_raid` | `systems.py` | Eight kinds of ant, from slow with slow legs to fast with fast ones |
| `RaidSystem` | `systems.py` | Points the raid at the calango and steps it, ants far off screen steering every fourth tick |
| `PlayerSystem` | `systems.py` | The keys, or the autopilot loop |
| `HordeSpawner` | `systems.py` | Tops the raid up on a ring just past the screen's corners |
| `CombatSystem` | `systems.py` | Ten times a second: who is in the pulse, who is biting, who is left behind, each one query to the swarm |

No Python in the demo visits the ants one at a time. The combat pass asks
the swarm for ids by distance, and kills them in one call.

## Art

`make_art.py` draws every sprite pixel by pixel and writes the PNGs in
`assets/`, so the demo ships nothing it did not make. Run it again after
changing a sprite:

    uv run python -m examples.correicao.make_art
