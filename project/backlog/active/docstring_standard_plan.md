# Docstrings: one standard, checked in CI

**Status: done on 2026-11-16**, in six pull requests (#434, #441 to #444,
and the one that deletes the baseline). The outcome is at the end.

Written 2026-11-15, measured against `main` at `015a89d` with ruff
0.14.10. Answers finding 4 of phase 6 in `engine_completion_roadmap.md`
("about half the non-blank lines in `pyguara/` are docstrings and
comments").

## What the measurement says

`pyguara/` has 77,550 non-blank lines in 423 files. 34,947 of them are
docstring lines and 4,116 are comments: 50% of the package.

| | Count |
| --- | --- |
| Docstrings | 4,876 (423 modules, 763 classes, 3,690 functions) |
| Median length | 4 lines; 90th percentile 12; longest 52 |
| Public functions with no docstring | 55 |
| Functions with a Google section (`Args:`, `Returns:`, ...) | 2,032 of 3,690 |
| One-line function docstrings | 1,361 |

**The format is already close to Google style.** Switching ruff's
convention from `pep257` to `google` reports 188 findings, all of one
rule (D212, the summary starts on the line after the quotes), and all
fixed by `ruff check --fix`.

**The problem is content, and it is concentrated.** 437 docstrings, 9%
of the total, carry at least one of the following. Everything else is
ordinary reference text.

| What the docstring contains | Docstrings | Example |
| --- | --- | --- |
| More than 8 lines of prose before the first section | 272 | `Batcher` (`graphics/pipeline/batch.py`): 52 lines, five paragraphs on optimisations already made |
| History wording ("used to", "before this change", "no longer", "reproduced") | 131 | `StateMachine.add_transition`: "Transitions used to exist only as..." |
| Bold emphasis (`**...**`) | 158 | `ParallelNode`: "A child that has finished is **latched**" |
| An issue, RFC or work-item number (`#46`, `W16`) | 44 | `ParallelNode`: "(#46, reproduced at 60/60 before this change)" |
| A measured number (`54.9 ms`, `3.9x`) | 27 | `Batcher`: "it used to take 54.9 ms" |
| The name of a test | 13 | `Batcher`: "`test_destinations_are_the_camera_transform_exactly` asserts that" |
| Process words (audit, spike, the fork, the plan) | 12 | |

The worst packages by share of flagged docstrings are `systems` (22%),
`application` (19%), `events` (12%), `scripting` (10%) and `ecs` (10%).
By count they are `studio`, `graphics` and `kits`.

**Cleaning these will not halve the volume.** Capping prose at 8 lines
removes about 1,700 of 25,700 docstring text lines; capping at 5 removes
about 3,000. Most docstring lines are `Args:` and `Attributes:` sections
on 3,700 functions, which is what Google style asks for. Whether to trim
those too is decision 3 below.

Outside the package: `tests/` has 4,441 docstrings (317 with a marker),
`games/` and `tools/` 1,656 (81). None of the three is under any
docstring rule today (#267).

## The standard

A docstring says what the thing does and how to call it, as true of the
code today. It is reference text for someone who has never seen the
history.

1. **Summary line**: one sentence, imperative for a function ("Return
   the..."), on the same line as the opening quotes, ending in a full
   stop.
2. **Body**: optional, at most 8 lines of prose. Behaviour a caller
   cannot see from the signature: units, ordering, what is mutated, what
   is cached, what is not thread-safe.
3. **Sections**, Google style, in this order: `Args:`, `Returns:` (or
   `Yields:`), `Raises:`, `Example:`. `Attributes:` on a dataclass or
   component.
4. **`Raises:` lists what the function raises**, and nothing it does not.
5. **Private helpers** (`_name`) need one line, or none when the name
   says it.
6. **Not in a docstring:**
   - what the code used to do, or the bug that led to it;
   - issue, PR, RFC or work-item numbers;
   - benchmark numbers;
   - the names of the tests that cover it;
   - who decided something and when;
   - `**bold**` or other Markdown emphasis;
   - an argument for why the design is right.

A constraint that still binds the next editor stays, stated as a rule
and without its story: "Group by `material_id`, not identity: a
deserialised material keeps its id."

### Where the removed text goes

| Content | Home |
| --- | --- |
| A measurement | `docs/guides/performance.md` (most are already there) |
| Why a design was chosen over another | The ADR, if one exists; otherwise deleted |
| The bug a change fixed | The regression test's docstring, and the commit that is already in `git log` |
| What changed between versions | `CHANGELOG.md` |
| Anything else | Deleted |

### Before and after

`Batcher`, 52 lines today, becomes:

```python
class Batcher:
    """Group sorted render commands into draw batches.

    Consecutive commands sharing a texture and a material become one
    batch. Rotation, scale, tint and source rect are optional parallel
    columns, filled only from the first command that needs one.

    Grouping is by `material_id`, not object identity, so a copied or
    deserialised material batches with its original.
    """
```

The four optimisations, their timings and the removed `_static_batches`
dict are in `docs/guides/performance.md` and the commit history.

## The CI check

Two layers, both in the existing `Code Quality` job through `make lint`.

### 1. Ruff: format and truthfulness

| Change | Findings today | Fix |
| --- | --- | --- |
| `convention = "google"` | 188 (D212) | Automatic |
| `DOC502`: a documented exception is not raised | 100 | **Not enabled**, see below |
| `DOC202`, `DOC403`: a documented return or yield does not exist | 2 | **Not enabled**: both are functions that return an iterator |
| `DOC501`: a raised exception is not documented | 59 | Done in D2 |

**`DOC502` was a mistake in the first version of this plan**, which
called its 100 findings "docstrings that say something false". Read one
by one in D2, nearly all document an exception a callee raises:
`SceneNotReadyError` from a scene accessor, `OSError` from a file read,
`EditError` from a command helper. Ruff sees only a `raise` in the
function's own body, so the rule would delete true contracts. It stays
off.

The `DOC` rules are preview rules in ruff 0.14.10; the config already
enables preview rules one at a time (`explicit-preview-rules`), so they
are added by code.

Not recommended: `DOC201` (every returning function needs `Returns:`).
It reports 366 findings and the fix adds lines such as "Returns: The
width." to functions whose summary already says so.

### 2. `tools/check_docstrings.py`: content

Ruff has no rule for what a docstring talks about. A small AST script,
standard library only, with one rule per row of the table above:

| Rule | Fails on | `pyguara/` | `tests/` |
| --- | --- | --- | --- |
| `DS001` | More than 8 prose lines before the first section | 271 | 110 |
| `DS002` | What the code used to do, from a fixed list of phrasings | 50 | -- |
| `DS003` | `**bold**` | 157 | 59 |
| `DS004` | `#123`, `RFC-0003`, `W16`, `P0-001` | 50 | -- |
| `DS005` | A figure with a decimal and `ms`, `us`, `ns` or `fps`; `Nx faster`; "measured at" | 22 | -- |
| `DS006` | An identifier of the form `test_a_b` | 12 | -- |
| `DS007` | The audit, the fork, the spike, the roadmap, whose call it was | 1 | -- |

These are the baseline as D1 wrote it: 732 entries over 369 docstrings
in `pyguara/` and 137 in `tests/`. They differ from the first table,
which came from a looser scan: "used to" also means "serves to" ("the
key used to load it"), and round figures such as "waits 100 ms" are
contracts, so both rules were narrowed until they stopped flagging
reference text.

- Output is `path:line: DS00n message`, as ruff's is.
- **The baseline**, `tools/docstring_baseline.txt`, lists the findings
  that existed when the check landed, by rule, path and dotted name, so
  an entry survives a line moving. The check fails on any finding not
  in it, and on any entry that no longer occurs, so the file only
  shrinks. It is deleted when empty.
- **The allowlist**, `tools/docstring_allowlist.txt`, takes the same
  entry with a reason after it, for a pattern matching something its
  rule is not about. It is empty.
- `tests/test_check_docstrings.py` covers each rule both ways, and
  runs the check on the repository, so `pytest` fails on a new finding
  as `make lint` does.

## Rollout

| PR | What | Size |
| --- | --- | --- |
| **D1** (done, #434) | The standard as `docs/agents/docstrings.md`, one line in `AGENTS.md` pointing at it; `convention = "google"` and the D212 autofix; `tools/check_docstrings.py` with its baseline; wired into `make lint` | M |
| **D2** (#441) | `DOC501` enabled: 41 functions gained a `Raises:` entry. Click commands and Studio's operation handlers are exempt | S |
| **D3** (#442) | The 341 flagged docstrings in `pyguara/` outside the core, one commit per group of packages | L |
| **D4** (#443) | The 28 in `ecs`, `di` and `events`, as their own PR | S |
| **D5** (#444) | `tests/`: 110 docstrings over the length limit rewritten, bold stripped from 63 | M |
| **D6** (this PR) | Baseline deleted; `DS002`, `DS004` and `DS005` applied to comments in `pyguara/`, and the 16 comment blocks that broke them rewritten | S |

Every cleanup PR changes docstrings and nothing else. Each one proves it
with a comparison of every touched module's AST, docstrings stripped,
before and after: identical means no code changed.

`ecs`, `di` and `events` come last and as their own PR, since
`AGENTS.md` asks before changing them even when the change is text.

### What reads a docstring at run time

Checked, so a rewrite does not break them:

- `studio/model/schema.py` shows the **first line** of a component's and
  an enum member's docstring in `component_schema`. Summary lines must
  stay meaningful on their own.
- `persistence/migration.py` uses a migration function's docstring as
  its description when none is given.
- `tests/test_system_step_naming.py` reads system docstrings for the
  fixed and variable step wording (ADR 0005).
- The Click commands in `pyguara/cli/` print theirs as `--help`.

## Decisions

The owner took all five recommendations on 2026-11-15.

1. **The prose cap is 8 lines.** 12 would have flagged 138 docstrings
   in `pyguara/` and 5 would have flagged 522.
2. **Comments get `DS002`, `DS004` and `DS005` in D9**, after the
   docstrings. 4,116 comment lines carry the same habits, and
   `pyproject.toml` has 147 more.
3. **`Args:` is neither required nor forbidden** on a function whose
   summary already says it. Requiring it adds lines to 531 public
   functions; forbidding a redundant one cannot be checked.
4. **`tests/` gets `DS001` and `DS003` only.** A regression test may
   name its issue. `games/` and `tools/` wait for #267.
5. **`DOC501` is enabled in D2**: an exception a caller can meet is
   part of the contract.

## Outcome

Measured on `pyguara/` after the last PR, against the first table:

| | Before | After |
| --- | --- | --- |
| Docstring lines | 34,947 | 32,185 |
| Non-blank lines | 77,550 | 75,033 |
| Docstrings and comments, as a share of the package | 50.4% | 48.3% |
| Longest docstring | 52 lines | 32 lines |
| Docstrings over 20 lines | 104 | 32 |
| Findings from the content check | 563 in 369 docstrings | 0 |

The share moved two points, as the first section said it would: most
docstring lines are `Args:` and `Attributes:` sections, which the standard
keeps. What changed is what the prose says.

Left open:

- `games/` and `tools/` are under no docstring rule (#267).
- The comments in `pyproject.toml` have the same habits and no check.
- `DS001` is not applied to comments, by decision 2: a comment may be as
  long as its explanation needs.
- The content rules are patterns. They miss history told in other words,
  and a reviewer still has to read a new docstring.
