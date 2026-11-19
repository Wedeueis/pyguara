"""Check what docstrings and comments talk about, which ruff has no rule for.

Ruff's `D` rules hold the format. This holds the content rules of
`docs/agents/docstrings.md`: a docstring describes the code as it is, in
a bounded amount of prose.

Usage:
    uv run python tools/check_docstrings.py
    uv run python tools/check_docstrings.py --prune-baseline
    uv run python tools/check_docstrings.py --no-baseline pyguara/ai

Exit status is 1 when a finding is not in the baseline, or when a
baseline or allowlist entry matches nothing.
"""

from __future__ import annotations

import argparse
import ast
import io
import re
import sys
import tokenize
from collections.abc import Iterable, Iterator, Sequence
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
BASELINE_PATH = REPO_ROOT / "tools" / "docstring_baseline.txt"
ALLOWLIST_PATH = REPO_ROOT / "tools" / "docstring_allowlist.txt"

MAX_PROSE_LINES = 8

ALL_RULES = frozenset({"DS001", "DS002", "DS003", "DS004", "DS005", "DS006", "DS007"})

# Which rules apply under each top-level directory. A regression test may
# name its issue and tell the bug's story, so tests get length and
# emphasis only.
SCOPES: dict[str, frozenset[str]] = {
    "pyguara": ALL_RULES,
    "tests": frozenset({"DS001", "DS003"}),
}

# What a run with no paths checks: every scope, and `examples/`, whose
# only checked files are each demo's `tests/`.
DEFAULT_PATHS: tuple[Path, ...] = (*(Path(name) for name in SCOPES), Path("examples"))

# The rules that also apply to `#` comments, by top-level directory. A
# comment may explain why at any length; it may not tell the code's history,
# cite a tracker or quote a benchmark.
COMMENT_SCOPES: dict[str, frozenset[str]] = {
    "pyguara": frozenset({"DS002", "DS004", "DS005"}),
}

# A header that ends the prose. `Note:` is left out on purpose: it would
# make the prose limit optional.
_SECTION = re.compile(
    r"^\s*(Args|Arguments|Attributes|Returns|Yields|Raises|Examples?|Usage):\s*$"
)

# "used to" also means "serves to" ("the key used to load it"), so it
# counts only after a subject that makes it the past tense, or before a
# verb that the other sense never takes.
_HISTORY = re.compile(
    r"\b(?:this|it|which|that|there|things?|they) used to \w+"
    r"|(?:\b[A-Z]\w+|`[^`\n]+`) used to \w+"
    r"|\bused to (?:be|exist|take|live|cost|mean|have|silently)\b"
    r"|\bformerly\b"
    r"|\b(?:before|until) (?:this|that|the) (?:change|fix)\b"
    r"|\ban earlier version\b"
    r"|\bthe (?:old|previous|original) (?:behaviou?r|code|implementation|version)\b"
    r"|\bhistorical(?:ly)?\b"
    r"|\bturned out\b"
    r"|\bthis (?:change|fix|commit|PR)\b"
    r"|\bthis (?:module|class|function|method|file) (?:previously|originally|once)\b"
    r"|\boriginally (?:carried|held|was|were|had|lived|did)\b"
    r"|\b(?:is|are) no longer[.,:;]|\bno longer (?:holds(?=[.,:;])|true\b)"
    r"|\bwas (?:added|introduced|fixed|renamed) (?:in|by|when|after|because|for)\b"
    r"|\breproduced (?:at|in|by|with)\b"
    r"|\bhas since been\b",
)

# `(?<![\w&'"`#])` keeps hex colours (`"#000"`) and HTML entities out.
_TRACKER = re.compile(
    r"(?<![\w&'\"`#])(?<!UAX )#\d{1,5}\b(?![0-9a-fA-F])"
    r"|\bRFC-?\d+\b"
    r"|\bW\d{1,2}\b"
    r"|\bP[0-3]-\d{3}\b"
    r"|\bPR \d+\b"
)

# A measured figure has a decimal point or is a speed-up; a contract
# ("waits 100 ms") is a round number and is allowed.
_MEASUREMENT = re.compile(
    r"\b\d+\.\d+\s?(?:ms|us|µs|ns|fps)\b"
    r"|\b\d+(?:\.\d+)?x (?:faster|slower|as fast|as slow|quicker)"
    r"|\b\d+(?:\.\d+)?x to \d"
    r"|\bmeasured (?:at|on|against)\b",
    re.IGNORECASE,
)

_BOLD = re.compile(r"(?<![`*\w])\*\*[^\s*`](?:[^*\n]*[^\s*])?\*\*(?![\w*])")

_TEST_NAME = re.compile(r"\btest_[a-z0-9]+_[a-z0-9_]+\b")

_PROCESS = re.compile(
    r"\b(the audit(?! (?:log|trail|record))|audit (?:finding|item|remediation)|remediation"
    r"|pyguara-next|the fork\b|the user's call|the owner's call"
    r"|the roadmap|workstream \d|the (?:columnar |native )?spike)\b",
    re.IGNORECASE,
)

_MESSAGES = {
    "DS001": f"more than {MAX_PROSE_LINES} lines of prose before the first section",
    "DS002": "describes what the code used to do",
    "DS003": "bold emphasis",
    "DS004": "issue, RFC or work-item number",
    "DS005": "benchmark figure",
    "DS006": "names a test",
    "DS007": "refers to the project's process",
}

_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("DS002", _HISTORY),
    ("DS003", _BOLD),
    ("DS004", _TRACKER),
    ("DS005", _MEASUREMENT),
    ("DS006", _TEST_NAME),
    ("DS007", _PROCESS),
)


@dataclass(frozen=True, slots=True)
class Finding:
    """One rule broken by one docstring.

    Attributes:
        rule: The rule code, `DS001` to `DS007`.
        path: The file, relative to the repository root, with `/`.
        qualname: The dotted name of the documented object, or
            `<module>`.
        line: The line the docstring starts on.
        detail: The text that matched, or the line count for `DS001`.
    """

    rule: str
    path: str
    qualname: str
    line: int
    detail: str

    @property
    def key(self) -> str:
        """The identity a baseline entry stores, which has no line number."""
        return f"{self.rule} {self.path} {self.qualname}"


def prose_line_count(docstring: str) -> int:
    """Count the non-blank lines between the summary and the first section."""
    count = 0
    for index, line in enumerate(docstring.splitlines()):
        if _SECTION.match(line):
            break
        if index and line.strip():
            count += 1
    return count


def check_docstring(docstring: str, rules: frozenset[str]) -> list[tuple[str, str]]:
    """Apply the rules to one docstring.

    Args:
        docstring: The docstring's text, as `ast.get_docstring` returns it.
        rules: The rule codes to apply.

    Returns:
        A `(rule, detail)` pair per broken rule, in rule order.
    """
    found: list[tuple[str, str]] = []
    if "DS001" in rules:
        prose = prose_line_count(docstring)
        if prose > MAX_PROSE_LINES:
            found.append(("DS001", f"{prose} lines"))
    for rule, pattern in _PATTERNS:
        if rule in rules:
            match = pattern.search(docstring)
            if match:
                found.append((rule, match.group(0)))
    return found


def _documented_nodes(
    tree: ast.Module,
) -> Iterator[tuple[str, ast.AST]]:
    """Yield every node that can carry a docstring, with its dotted name."""
    yield "<module>", tree
    stack: list[tuple[str, ast.AST]] = [("", tree)]
    while stack:
        prefix, parent = stack.pop()
        for child in ast.iter_child_nodes(parent):
            if isinstance(child, ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef):
                name = f"{prefix}{child.name}"
                yield name, child
                stack.append((f"{name}.", child))
            else:
                stack.append((prefix, child))


def _comment_blocks(source: str) -> Iterator[tuple[int, str]]:
    """Yield each comment block as its first line number and its joined text.

    Consecutive whole-line comments form one block, so a phrase that wraps
    across two lines is still found. A trailing comment is a block of its
    own.
    """
    lines = source.splitlines()
    start = 0
    last = 0
    parts: list[str] = []
    for token in tokenize.generate_tokens(io.StringIO(source).readline):
        if token.type != tokenize.COMMENT:
            continue
        number = token.start[0]
        whole_line = lines[number - 1].lstrip().startswith("#")
        text = token.string.lstrip("#").strip()
        if parts and whole_line and number == last + 1:
            parts.append(text)
        else:
            if parts:
                yield start, " ".join(parts)
            start, parts = number, [text]
        last = number if whole_line else -1
    if parts:
        yield start, " ".join(parts)


def _enclosing(spans: list[tuple[int, int, str]], line: int) -> str:
    """Return the dotted name of the innermost definition around a line."""
    best = "<module>"
    size = 0
    for first, final, qualname in spans:
        if first <= line <= final and (not size or final - first < size):
            best, size = qualname, final - first
    return best


def check_source(
    source: str,
    path: str,
    rules: frozenset[str],
    comment_rules: frozenset[str] = frozenset(),
) -> list[Finding]:
    """Check every docstring, and optionally every comment, in one module.

    A finding in a comment is named after the definition around it, with
    `#comment` appended.

    Args:
        source: The module's text.
        path: The path to report, relative to the repository root.
        rules: The rule codes to apply to docstrings.
        comment_rules: The rule codes to apply to comments.

    Returns:
        The findings, in the order they appear in the file.
    """
    tree = ast.parse(source)
    findings: list[Finding] = []
    spans: list[tuple[int, int, str]] = []
    for qualname, node in _documented_nodes(tree):
        assert isinstance(
            node, ast.Module | ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef
        )
        if not isinstance(node, ast.Module):
            spans.append((node.lineno, node.end_lineno or node.lineno, qualname))
        docstring = ast.get_docstring(node)
        if not docstring:
            continue
        line = node.body[0].lineno
        for rule, detail in check_docstring(docstring, rules):
            findings.append(Finding(rule, path, qualname, line, detail))
    if comment_rules:
        for line, text in _comment_blocks(source):
            name = f"{_enclosing(spans, line)}#comment"
            for rule, detail in check_docstring(text, comment_rules):
                findings.append(Finding(rule, path, name, line, detail))
    findings.sort(key=lambda finding: (finding.line, finding.rule))
    return findings


def _rules_for(relative: Path) -> frozenset[str]:
    """Return the rules that apply to a path.

    By its top-level directory, except that a `tests` folder anywhere
    below it, such as a demo's own tests, is held to the rules for tests.
    """
    if relative.parts[0] in SCOPES:
        return SCOPES[relative.parts[0]]
    if "tests" in relative.parts[1:-1]:
        return SCOPES["tests"]
    return frozenset()


def check_paths(paths: Iterable[Path], root: Path = REPO_ROOT) -> list[Finding]:
    """Check every Python file under the given files and directories.

    Args:
        paths: Files or directories, absolute or relative to `root`.
        root: The directory that scopes and reported paths are relative to.

    Returns:
        The findings, sorted by path and line.
    """
    findings: list[Finding] = []
    for start in paths:
        absolute = start if start.is_absolute() else root / start
        files = [absolute] if absolute.is_file() else sorted(absolute.rglob("*.py"))
        for file in files:
            relative = file.relative_to(root)
            rules = _rules_for(relative)
            comment_rules = COMMENT_SCOPES.get(relative.parts[0], frozenset())
            if rules or comment_rules:
                findings.extend(
                    check_source(
                        file.read_text(encoding="utf-8"),
                        relative.as_posix(),
                        rules,
                        comment_rules,
                    )
                )
    findings.sort(key=lambda finding: (finding.path, finding.line, finding.rule))
    return findings


def read_keys(path: Path, *, need_reason: bool = False) -> set[str]:
    """Read finding keys from a baseline or allowlist file.

    Blank lines and lines starting with `#` are skipped.

    Args:
        path: The file to read. A missing file is an empty set.
        need_reason: Whether each entry must end in `# reason`.

    Returns:
        The keys, each `RULE path qualname`.

    Raises:
        ValueError: If a line is not three fields, or lacks a reason when
            one is needed.
    """
    keys: set[str] = set()
    if not path.exists():
        return keys
    for number, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        entry, _, reason = raw.partition("  # ")
        entry = entry.strip()
        if not entry or entry.startswith("#"):
            continue
        if len(entry.split(" ")) != 3:
            raise ValueError(f"{path.name}:{number}: expected 'RULE path qualname'")
        if need_reason and not reason.strip():
            raise ValueError(f"{path.name}:{number}: needs '  # reason' after it")
        keys.add(entry)
    return keys


_BASELINE_HEADER = """\
# Findings that existed when this directory came under tools/check_docstrings.py.
# This file only shrinks: fix a docstring, then run
#     uv run python tools/check_docstrings.py --prune-baseline
# Never add a line by hand. A real exception goes in docstring_allowlist.txt.
"""


def write_baseline(path: Path, keys: Iterable[str]) -> None:
    """Write the baseline file, one sorted key per line."""
    ordered = sorted(keys, key=lambda key: (key.split(" ")[1:], key))
    path.write_text(
        _BASELINE_HEADER + "".join(f"{key}\n" for key in ordered), encoding="utf-8"
    )


def main(argv: Sequence[str] | None = None) -> int:
    """Run the check from the command line.

    Args:
        argv: The arguments, or None for `sys.argv[1:]`.

    Returns:
        The process exit status: 0 when clean, 1 otherwise.
    """
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument("paths", nargs="*", type=Path, help="default: every scope")
    parser.add_argument(
        "--no-baseline", action="store_true", help="report baselined findings too"
    )
    group = parser.add_mutually_exclusive_group()
    group.add_argument(
        "--prune-baseline",
        action="store_true",
        help="drop baseline entries that no longer occur",
    )
    group.add_argument(
        "--write-baseline",
        action="store_true",
        help="record every current finding; for creating the file only",
    )
    args = parser.parse_args(argv)

    whole_tree = not args.paths
    paths = args.paths or list(DEFAULT_PATHS)
    try:
        allowed = read_keys(ALLOWLIST_PATH, need_reason=True)
        baseline = set() if args.no_baseline else read_keys(BASELINE_PATH)
    except ValueError as error:
        print(error, file=sys.stderr)
        return 1

    findings = check_paths(paths)
    current = {finding.key for finding in findings}

    if args.write_baseline:
        write_baseline(BASELINE_PATH, current - allowed)
        print(f"Wrote {len(current - allowed)} entries to {BASELINE_PATH.name}.")
        return 0
    if args.prune_baseline:
        kept = baseline & current
        write_baseline(BASELINE_PATH, kept)
        print(f"Removed {len(baseline) - len(kept)} entries; {len(kept)} remain.")
        baseline = kept

    failed = False
    for finding in findings:
        if finding.key in allowed or finding.key in baseline:
            continue
        failed = True
        print(
            f"{finding.path}:{finding.line}: {finding.rule} "
            f"{_MESSAGES[finding.rule]}: {finding.detail!r} ({finding.qualname})"
        )

    # A stale entry is only knowable when the whole tree was checked.
    if whole_tree and not args.no_baseline:
        for name, keys in (
            (BASELINE_PATH.name, baseline),
            (ALLOWLIST_PATH.name, allowed),
        ):
            for key in sorted(keys - current):
                failed = True
                print(f"{name}: '{key}' matches nothing; remove it")

    if failed:
        print("\nThe rules are in docs/agents/docstrings.md.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
