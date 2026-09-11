"""Opt-in kits: composable, genre-specific systems built on core mechanism.

Per #28's layering decision: `pyguara/` core is genre-agnostic and never
imports from here. A kit is opt-in systems + components + a thin facade,
constructed and ticked by the game that wants it -- nothing under
`pyguara/kits/` auto-registers itself anywhere. `kit -> kit` dependencies
are allowed if explicit, acyclic and shallow; prefer core events at the
seams where natural.

This package intentionally carries no imports of its own -- importing a
kit means importing `pyguara.kits.<name>` directly, the same way a game
picks exactly the kits it wants rather than getting all of them for free.
"""
