# Finding and fixing defects

How work on the engine is checked, whoever does it. The rules in
`AGENTS.md` say *what* must hold; this page says how to find out whether
it does.

## Probe before you fix

Reproduce a suspected defect with a throwaway script or test **before**
changing any code, and keep the probe as the regression test.

Reading is not enough. Nearly every significant defect found in this
engine looked correct on a read-through and was obvious under a probe. A
fix made without one fixes what you think the defect is, and you cannot
tell whether it fixed what it is.

## Judge the tests, not just the count

Before adding tests to a subsystem, decide what the existing ones are
worth: which are load-bearing and which only look like coverage. The
smells that have hidden real bugs here:

- **Uniform setup.** Every test builds its subject the same way, so a
  second way of building it goes untested. One query-cache suite always
  used `create_entity()`, and an `add_entity()` bug survived. A config
  suite always mocked the filesystem, so no round-trip bug could surface.
  Every DI test was single-threaded, so a missing lock survived. Ask how
  the subject is *constructed*, not only what is asserted.
- **Assertions on private state.** `obj._internal[...]` instead of the
  public getter breaks the test on a refactor and misses the bug the
  getter has.
- **Tautological asserts.** `assert x is not None` on something that
  cannot be None, or "did not raise" as the only check.
- **Fixtures that mock away the unit under test.**

Then add or rewrite tests to close the gap the judgement names.

## Guards that return a wrong answer

A check that avoids a crash by substituting a plausible value is worse
than the crash. `safe_zoom = 0.001` put coordinates six orders of
magnitude out; `ratio ... else 0` gave a 450 px viewport for a 0 px
window; `scale or Vector2(1, 1)` silently turned a requested zero scale
into one. Raise instead, naming what was wrong.

Grep for them: `if x != 0 else`, `or 1`, `or Vector2(`, a bare
`except: pass`, and `except Exception` that returns a default.

## Check that documented API exists

Pages under `docs/` have described functions that never existed.
`tests/test_docs_api.py` imports every `from pyguara... import X` it finds
in the docs, but it cannot check prose; when you touch a page, run what
it shows.

## Gaps are not defects

A subsystem can be correct and still lack what a shipped game will reach
for. Name each gap with a rough size and one disposition:

- **in the change**: small and squarely in the subsystem being worked on;
- **a new issue**: coherent, sizeable, or needing a product decision;
- **parked**: noted, and revisited when a later piece of work forces it.

This is not licence to widen a change. For anything non-trivial the
default is an issue.

## Verify the commit, not the working tree

A working tree can pass with changes the commit does not contain. For a
change that matters, check the commit itself:

```bash
git worktree add --detach /tmp/check <sha>
cd /tmp/check && uv sync --all-extras && uv run pytest
```

With several commits on a branch, each must pass alone (`AGENTS.md`).

## Where the method came from

The subsystem audit of September 2026 and the engine-remediation effort
after it were run this way. Their records are archived under the tag
`archive/pre-alpha-history`:

```bash
git show archive/pre-alpha-history:REFACTOR_STATE.md
git show archive/pre-alpha-history:.scratch/engine-remediation/map.md
```
