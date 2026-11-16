"""Opt-in kits: composable, genre-specific systems built on core mechanism.

`pyguara/` core is genre-agnostic and never imports from here. A kit
is systems, components and a thin facade, constructed and ticked by
the game that wants it; nothing under `pyguara/kits/` registers itself.
A kit may depend on another kit if the dependency is explicit, acyclic
and shallow; prefer core events at the seams.

This package imports nothing: a game imports `pyguara.kits.<name>`.
"""
