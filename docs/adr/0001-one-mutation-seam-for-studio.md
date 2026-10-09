# ADR 0001: One mutation seam for PyGuara Studio

- **Status:** accepted
- **Date:** 2026-10-09
- **Context:** [issue #53](https://github.com/Wedeueis/pyguara/issues/53)

## Context

Studio has three kinds of caller that all change a scene: a developer
clicking in a panel, a developer typing in a command palette, and a coding
agent calling a tool over MCP or JSON lines. Each of them needs the same
four things — the change applied, undoable, recorded, and describable
afterwards.

The engine had none of that. `pyguara/tools` and the ImGui Inspector both
`setattr` straight onto a component, so no edit was reversible and no edit
left a trace. Adding a second path for agents would have meant building
undo, audit and diffing twice, and the copy nobody watches is the one that
drifts.

An earlier audit had already rejected the obvious shortcut. Backing undo
with `EventDispatcher._event_history` was considered and refused because
engine events carry no inverse: nothing in that stream can say what a
value held before it changed.

## Decision

**Every change to authored state becomes an `EditCommand` on a
`CommandStack`, whoever asked for it.**

```
  human UI      command palette      agent (MCP / JSON-lines)
      |                |                        |
      +----------------+------------------------+
                       |
                  ops registry
                       |
               EditCommand objects
                       |
               CommandStack --> Journal
                       |
                 EntityManager
```

Three consequences follow, and they are the reason for the decision rather
than side effects of it.

**Commands capture their own inverse, at apply time.** They are mementos,
not descriptions: `SetField` records the old value as it writes the new
one. A command instance therefore records *one* application, and applying
it twice without reverting raises — the second call would capture the
state the first produced and the undo would restore the wrong value.

**Plan mode is free.** Reporting what an edit *would* do is implemented by
applying it, capturing the diff, and reverting. The reported consequence
is the real one rather than a prediction: destroying an entity names every
id the ownership cascade would take with it, which no description could be
trusted to get right. Approval mode (`ask`) uses the same mechanism to
queue an edit with its diff attached, so a reviewer decides against the
consequence rather than the request.

**The journal is not the stack.** An undo *moves* the stack and removes
what it undid from the undoable history; the journal records that undo as
another entry. "What did the agent do, in order" is a question only the
journal can answer.

## Alternatives considered

**A second, agent-only edit API.** Rejected: undo, audit and diffing would
each be built twice, and the agent-facing copy is the one nobody looks at,
so it is the one that rots.

**Deriving undo from the event stream.** Rejected before this work, in the
`EventDispatcher` audit: engine events carry no inverse.

**Emitting a command per frame during a gizmo drag.** Rejected: a hundred
history entries for one gesture, and coalescing them afterwards cannot
span the several entities a multi-selection drag touches. A drag writes
components directly for live feedback, then restores the starting values
and applies one command on release.

## Costs

- A `DestroyEntity` holds the subtree it removed for as long as it stays
  undoable, so the history is bounded rather than unlimited.
- Plan and approval modes apply and revert, so anything watching component
  changes sees the edit and its undo go past. Physics bodies and the
  spatial index are rebuilt twice and end where they started.
- `pyguara/tools`' inspector and gizmo still mutate directly. They are the
  Pygame-side debug surface and are deliberately left alone; the
  divergence is documented rather than hidden.
