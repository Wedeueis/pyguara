# Docstrings

A docstring says what the thing does and how to call it, as true of the
code today. It is reference text for someone who has never seen the
project's history.

`make lint` checks this page's rules: ruff holds the format, and
`tools/check_docstrings.py` holds the content, of docstrings and of
comments.

## The shape

```python
def find_path(self, start: Vector2, goal: Vector2) -> list[Vector2]:
    """Return the shortest walkable path between two world positions.

    The path runs through cell centres and includes both ends. Diagonal
    steps are never taken between two blocked cells.

    Args:
        start: Where the path begins, in world units.
        goal: Where it ends, in world units.

    Returns:
        The waypoints in order, or an empty list when no path exists.

    Raises:
        ValueError: If either position is outside the grid.
    """
```

1. **Summary line**: one sentence on the same line as the opening
   quotes, ending in a full stop. Imperative for a function ("Return
   the..."); a noun phrase for a class or module.
2. **Body**: optional, **at most 8 lines of prose**. What a caller
   cannot see from the signature: units, ordering, what is mutated, what
   is cached, what is not thread-safe.
3. **Sections**, Google style, in this order: `Args:`, `Returns:` or
   `Yields:`, `Raises:`, `Example:`. A dataclass or component lists its
   fields under `Attributes:`.
4. **`Raises:` lists what the function raises**, and nothing it does
   not.
5. **A section is not required** where the summary already says it. A
   typed function with one obvious argument needs no `Args:`.
6. **A private helper** (`_name`) needs one line, or none when its name
   says it.

Studio shows the first line of a component's docstring, and of each
enum member's, in `component_schema`. The summary has to make sense
alone.

## What does not belong

| Not in a docstring | Rule | Where it goes |
| --- | --- | --- |
| More than 8 lines of prose before the first section | `DS001` | A page under `docs/`, linked in one line |
| What the code used to do, or the bug behind a change | `DS002` | The regression test's docstring; the commit message |
| `**Bold**` emphasis | `DS003` | Nowhere. Put the important sentence first |
| An issue, PR, RFC or work-item number | `DS004` | The commit message and the PR |
| A benchmark figure | `DS005` | `docs/guides/performance.md` |
| The name of a test | `DS006` | Nowhere. The test finds the code, not the reverse |
| The project's process: an audit, a spike, the fork, who decided | `DS007` | The ADR, if the decision still binds |

Also not in a docstring, though no rule can check it: an argument for
why the design is right. If the decision still constrains the code, it
is an ADR, and the docstring may name it ("See ADR 0009").

**A constraint that binds the next editor stays**, stated as a rule and
without its story.

```python
# No: the story.
"""...
Grouping used to be by identity, which split a deserialised material
into its own batch (#212). It is by id now, and
`test_two_materials_with_the_same_id_stay_in_one_batch` pins that.
"""

# Yes: the rule.
"""...
Grouping is by `material_id`, not identity, so a copied or deserialised
material batches with its original.
"""
```

## Where the rules apply

| Directory | Format (ruff `D`, Google convention) | Docstring content | Comment content |
| --- | --- | --- | --- |
| `pyguara/` | Yes | `DS001` to `DS007` | `DS002`, `DS004`, `DS005` |
| `tests/` | No | `DS001` and `DS003`. A regression test may name its issue and tell the bug's story, briefly | No |
| `examples/`, `tools/` | No | No | No |

## Comments

A `#` comment in `pyguara/` may explain why the code is the way it is, at
whatever length that takes. It follows three of the rules above: it does
not say what the code used to do (`DS002`), cite an issue or work item
(`DS004`) or quote a benchmark figure (`DS005`). Consecutive comment lines
are read as one block.

A finding in a comment is reported under the definition around it, with
`#comment` after the name.

## Running the check

```bash
uv run python tools/check_docstrings.py              # what CI runs
uv run python tools/check_docstrings.py pyguara/ai   # one directory
```

A finding prints as `path:line: DS00n message: 'matched text' (name)`.

There is no baseline: every docstring and comment in scope meets the rules,
and a new finding fails the check. The check can still read a
`tools/docstring_baseline.txt`, for the day its scope grows to a directory
with existing findings; `--write-baseline` creates one and
`--prune-baseline` shrinks it.

### When a rule is wrong

The content rules are patterns, and a pattern can match something the
rule is not about: `16.67 ms` in the contract of a frame clock, for
one. Reword the docstring if that costs nothing. Otherwise add the
entry to `tools/docstring_allowlist.txt` with a reason after it.
