"""The agentic harness: how a coding agent drives Studio.

Three concerns live here:

- `journal` -- an append-only record of every action and who asked for it.
- `instructions` -- generating the instruction files agents actually read
  (`AGENTS.md` and its per-tool shims) from a project's real contents.
- `harness` -- the headless open/edit/run/capture/assert loop.
"""

from pyguara.studio.agent.journal import Actor, Journal, JournalEntry

__all__ = ["Actor", "Journal", "JournalEntry"]
