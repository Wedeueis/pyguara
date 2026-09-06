# Decide which Label class is canonical

Type: grilling
Status: resolved
Assignee: Wedeueis Braz
Blocked by: —
Audit ref: found during Decide how Checkbox should compute its layout size without
mutating state in render(), ticket 36 — not that ticket's question, spun off

## Question

`pyguara/ui/components/label.py` and `pyguara/ui/components/text.py` each define an
unrelated class named `Label`. The package's public API (`pyguara/ui/__init__.py`,
`pyguara/ui/components/__init__.py`, `pyguara/graphics/components/__init__.py`) all
export `text.py`'s version. Every game (`guara_falcao`, `true_coral`,
`protocolo_bandeira`, `ui_scene_graph`) imports `label.py`'s version directly,
bypassing the package export entirely. The two have diverged: `text.py`'s `Label`
supports `_auto_size` (an opt-out flag the other lacks) and takes an `anchor`
constructor param; `label.py`'s always auto-sizes and has no anchor support.

- Which one is "the" `Label` going forward — the one every game actually uses
  (`label.py`), or the one the public API already exports (`text.py`)?
- Does the other get deleted outright, or does its extra behavior (whichever one
  loses) get merged into the winner first (e.g. if `text.py`'s `_auto_size`/`anchor`
  support is worth keeping, does it need to land in `label.py` before `text.py` is
  deleted, since games use `label.py`)?
- Are there other components affected by this same pattern (duplicate class name
  across two files, package export diverging from what games actually import), or is
  this isolated to `Label`?
- All 4 games would need an import-line update if the winner isn't the one they
  currently import — is that considered a breaking change worth a `CHANGELOG.md`
  entry (per this map's precedent, e.g. *Native Color and Rect value types*), or too
  small (a straight rename with no behavior change for 3 of 4 games, assuming
  `label.py`'s simpler behavior wins)?

## Resolution

`text.py`'s `Label` wins — matches what the public API (`pyguara/ui/__init__.py` and
the two other re-exporting `__init__.py`s) already exports, and is a strict superset
of `label.py`'s `Label` (adds `anchor` support and an `_auto_size` opt-out flag on top
of identical default behavior). Verified via all 13 `Label(...)` call sites across
the 4 games: none pass `anchor`, none call `.set_text()` — every call site uses only
`text`/`position`/`font_size`/`color`, so switching to `text.py`'s version with its
defaults is behaviorally identical, zero observable change.

`label.py`'s `Label` gets **deleted outright**, no merge needed (nothing in it isn't
already in the winner). All 4 games' import lines change from
`pyguara.ui.components.label` to `pyguara.ui.components.text`.

Checked for a wider pattern first (AST-scanned every class in `pyguara/ui/
components/` for duplicate names): isolated to `Label`, nothing else affected.

No `CHANGELOG.md` entry — nothing observable changes for any current caller, and
`label.py`'s `Label` was never the documented public import path to begin with (the
games importing it directly were already bypassing the public API `text.py` already
established as canonical). Reserved for actual behavior/capability changes, per this
map's *Native Color and Rect value types* precedent.

Lands as [Execute the canonical Label
merge](issues/43-execute-canonical-label-merge.md).
