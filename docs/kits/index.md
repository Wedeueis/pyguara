# Kits

`pyguara/kits/` is the **opt-in layer**. Core is what every game needs; a kit is
a genre's vocabulary, packaged so a game that wants it can import it and a game
that doesn't never pays for it. Nothing in core imports a kit, and kits reach
each other only through core event dispatch — never a direct import.

The kits that exist today: `action_combat`, `effects`, `stats`, `projectiles`,
`procgen`, `spawn`, `loot`, `progression`, plus the smaller `echolocation`,
`pack` and `trail`.

Only `progression` is documented here so far. The rest are documented in their
own module docstrings; pages get written as each kit is audited.

- [Progression](progression.md) — experience, levels, upgrade offers, pickup magnet
