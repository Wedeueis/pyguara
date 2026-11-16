"""Tests for tools/check_docstrings.py, the docstring content check."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent


def _load() -> ModuleType:
    path = REPO_ROOT / "tools" / "check_docstrings.py"
    spec = importlib.util.spec_from_file_location("check_docstrings", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


check = _load()


def _rules(docstring: str) -> list[str]:
    return [rule for rule, _ in check.check_docstring(docstring, check.ALL_RULES)]


NINE_LINES = "\n".join(f"Line {n} of the body." for n in range(9))


@pytest.mark.parametrize(
    ("rule", "docstring"),
    [
        ("DS001", f"Summary.\n\n{NINE_LINES}"),
        ("DS002", "Summary.\n\nThis used to allocate a vector per call."),
        ("DS002", "Summary.\n\n`update()` used to only run once."),
        ("DS002", "Summary.\n\nIt was slower before the change."),
        ("DS002", "Summary.\n\nThat reason no longer holds."),
        ("DS003", "Summary.\n\nA finished child is **latched** until reset."),
        ("DS004", "Summary.\n\nFixes the re-tick (#46)."),
        ("DS004", "Summary.\n\nSee RFC-0003 for the sweep."),
        ("DS004", "Summary.\n\nThis is W16."),
        ("DS005", "Summary.\n\nTakes 54.9 ms at 20,000 sprites."),
        ("DS005", "Summary.\n\nThe native store is 3.9x faster."),
        ("DS005", "Summary.\n\nMeasured at a tenth of a recompute."),
        ("DS006", "Summary.\n\n`test_two_materials_share_a_batch` pins that."),
        ("DS007", "Summary.\n\nKept after the audit."),
        ("DS007", "Summary.\n\nMoved here from pyguara-next."),
    ],
)
def test_a_docstring_that_breaks_a_rule_is_reported(rule: str, docstring: str) -> None:
    assert _rules(docstring) == [rule]


@pytest.mark.parametrize(
    "docstring",
    [
        "Summary.",
        f"Summary.\n\n{NINE_LINES.rsplit(chr(10), 1)[0]}",
        "Summary.\n\nArgs:\n    path: The identifier used to load the resource.",
        "Summary.\n\nReturns a handle that can be used to stop it.",
        "Summary.\n\nThe entity this effect no longer applies to.",
        "Summary.\n\nRestore state previously returned by `get_state()`.",
        "Summary.\n\nArgs:\n    **kwargs: Passed on, as are **options.",
        'Summary.\n\nDefaults to "#000", or `#ff8800` when lit.',
        "Summary.\n\nSteps every 16 ms; waits 100 ms before retrying.",
        "Summary.\n\nDraws at 2x scale on a high-density display.",
        "Summary.\n\nSet `test_mode` to skip the device.",
        "Summary.\n\nWrites to the audit log. See ADR 0009.",
    ],
)
def test_reference_text_is_not_reported(docstring: str) -> None:
    assert _rules(docstring) == []


def test_sections_do_not_count_as_prose() -> None:
    args = "\n".join(f"    arg{n}: The value of argument {n}." for n in range(20))
    assert _rules(f"Summary.\n\nOne line of body.\n\nArgs:\n{args}") == []


def test_a_note_section_does_not_end_the_prose() -> None:
    assert _rules(f"Summary.\n\nNote:\n{NINE_LINES}") == ["DS001"]


def test_only_the_rules_asked_for_are_applied() -> None:
    docstring = "Summary.\n\nThis used to be **slow** (#46)."
    found = check.check_docstring(docstring, frozenset({"DS003"}))
    assert [rule for rule, _ in found] == ["DS003"]


SOURCE = '''"""Module summary, fixed in #12."""


class Batcher:
    """Group commands.

    It used to take longer.
    """

    def create(self) -> None:
        """Build the batches, **fast**."""

        def inner() -> None:
            """Measured at a millisecond."""


def clean() -> None:
    """Do nothing."""
'''


def test_findings_name_the_object_and_the_docstring_line() -> None:
    findings = check.check_source(SOURCE, "pyguara/x.py", check.ALL_RULES)
    assert [(f.rule, f.qualname, f.line) for f in findings] == [
        ("DS004", "<module>", 1),
        ("DS002", "Batcher", 5),
        ("DS003", "Batcher.create", 11),
        ("DS005", "Batcher.create.inner", 14),
    ]
    assert findings[1].key == "DS002 pyguara/x.py Batcher"


def test_a_key_does_not_move_when_lines_do() -> None:
    before = check.check_source(SOURCE, "pyguara/x.py", check.ALL_RULES)
    after = check.check_source("\n\n\n" + SOURCE, "pyguara/x.py", check.ALL_RULES)
    assert [f.key for f in before] == [f.key for f in after]
    assert [f.line for f in before] != [f.line for f in after]


def _tree(tmp_path: Path) -> Path:
    (tmp_path / "pyguara").mkdir()
    (tmp_path / "tests").mkdir()
    (tmp_path / "games").mkdir()
    story = '"""Summary.\n\nThis used to be **slow** (#46).\n"""\n'
    for name in ("pyguara", "tests", "games"):
        (tmp_path / name / "mod.py").write_text(story, encoding="utf-8")
    return tmp_path


def test_tests_get_length_and_emphasis_only_and_games_nothing(tmp_path: Path) -> None:
    root = _tree(tmp_path)
    findings = check.check_paths([Path("pyguara"), Path("tests"), Path("games")], root)
    assert [(f.path, f.rule) for f in findings] == [
        ("pyguara/mod.py", "DS002"),
        ("pyguara/mod.py", "DS003"),
        ("pyguara/mod.py", "DS004"),
        ("tests/mod.py", "DS003"),
    ]


@pytest.fixture
def project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    root = _tree(tmp_path)
    (root / "tools").mkdir()
    monkeypatch.setattr(check, "REPO_ROOT", root)
    monkeypatch.setattr(check, "BASELINE_PATH", root / "tools" / "baseline.txt")
    monkeypatch.setattr(check, "ALLOWLIST_PATH", root / "tools" / "allowlist.txt")
    monkeypatch.setattr(
        check, "check_paths", lambda paths, _r=root, _f=check.check_paths: _f(paths, _r)
    )
    return root


def test_a_new_finding_fails(project: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert check.main([]) == 1
    out = capsys.readouterr().out
    assert "pyguara/mod.py:1: DS004" in out
    assert "'#46'" in out


def test_a_baselined_finding_passes_and_a_new_one_still_fails(
    project: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert check.main(["--write-baseline"]) == 0
    assert check.main([]) == 0

    (project / "pyguara" / "new.py").write_text(
        '"""Summary, **loudly**."""\n', encoding="utf-8"
    )
    capsys.readouterr()
    assert check.main([]) == 1
    out = capsys.readouterr().out
    assert "pyguara/new.py:1: DS003" in out
    assert "mod.py" not in out


def test_a_fixed_docstring_left_in_the_baseline_fails_until_pruned(
    project: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    check.main(["--write-baseline"])
    (project / "pyguara" / "mod.py").write_text('"""Summary."""\n', encoding="utf-8")
    capsys.readouterr()

    assert check.main([]) == 1
    assert "matches nothing; remove it" in capsys.readouterr().out

    assert check.main(["--prune-baseline"]) == 0
    assert check.read_keys(check.BASELINE_PATH) == {"DS003 tests/mod.py <module>"}
    assert check.main([]) == 0


def test_pruning_never_adds_an_entry(project: Path) -> None:
    check.write_baseline(check.BASELINE_PATH, [])
    assert check.main(["--prune-baseline"]) == 1
    assert check.read_keys(check.BASELINE_PATH) == set()


def test_checking_one_directory_does_not_call_the_rest_stale(project: Path) -> None:
    check.main(["--write-baseline"])
    assert check.main(["pyguara"]) == 0


def test_an_allowlist_entry_needs_a_reason(
    project: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    check.ALLOWLIST_PATH.write_text("DS004 pyguara/mod.py <module>\n", encoding="utf-8")
    assert check.main([]) == 1
    assert "needs '  # reason'" in capsys.readouterr().err


def test_an_allowlisted_finding_passes_and_a_stale_entry_fails(
    project: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    check.main(["--write-baseline"])
    kept = check.read_keys(check.BASELINE_PATH) - {"DS004 pyguara/mod.py <module>"}
    check.write_baseline(check.BASELINE_PATH, kept)
    assert check.main([]) == 1

    check.ALLOWLIST_PATH.write_text(
        "DS004 pyguara/mod.py <module>  # '#46' is a colour index here\n",
        encoding="utf-8",
    )
    assert check.main([]) == 0

    check.ALLOWLIST_PATH.write_text(
        "DS004 pyguara/gone.py <module>  # no such file\n", encoding="utf-8"
    )
    capsys.readouterr()
    assert check.main([]) == 1
    assert "allowlist.txt: 'DS004 pyguara/gone.py <module>'" in capsys.readouterr().out


def test_the_repository_passes_its_own_check() -> None:
    findings = check.check_paths([Path(name) for name in check.SCOPES], REPO_ROOT)
    current = {finding.key for finding in findings}
    baseline = check.read_keys(REPO_ROOT / "tools" / "docstring_baseline.txt")
    allowed = check.read_keys(
        REPO_ROOT / "tools" / "docstring_allowlist.txt", need_reason=True
    )
    assert current - baseline - allowed == set()
    assert (baseline | allowed) - current == set()


COMMENTED = '''"""Module summary."""

# A module comment. This used to be a
# dict keyed on id (#324).


class Batcher:
    """Group commands."""

    def create(self) -> None:
        """Build the batches."""
        x = 1  # took 54.9 ms before
        # Sized against the bottom strip, which is 16 px high. The entity
        # no longer holds the component here, and the index is
        # UAX #14 compliant.
        return None
'''

COMMENT_RULES = frozenset({"DS002", "DS004", "DS005"})


def test_a_comment_block_is_read_as_one_and_named_after_its_definition() -> None:
    findings = check.check_source(
        COMMENTED, "pyguara/x.py", check.ALL_RULES, COMMENT_RULES
    )
    assert [(f.rule, f.qualname, f.line) for f in findings] == [
        ("DS002", "<module>#comment", 3),
        ("DS004", "<module>#comment", 3),
        ("DS005", "Batcher.create#comment", 12),
    ]


def test_comments_are_not_checked_unless_asked() -> None:
    assert check.check_source(COMMENTED, "pyguara/x.py", check.ALL_RULES) == []


def test_a_comment_has_no_length_limit_and_may_use_emphasis() -> None:
    long_comment = "\n".join(
        f"# Line {n} of a **long** explanation." for n in range(30)
    )
    assert (
        check.check_source(
            long_comment + "\n", "pyguara/x.py", check.ALL_RULES, COMMENT_RULES
        )
        == []
    )


def test_only_the_engine_package_has_its_comments_checked(tmp_path: Path) -> None:
    for name in ("pyguara", "tests"):
        (tmp_path / name).mkdir()
        (tmp_path / name / "mod.py").write_text(
            "x = 1  # this used to be 2 (#46)\n", encoding="utf-8"
        )
    findings = check.check_paths([Path("pyguara"), Path("tests")], tmp_path)
    assert [(f.path, f.rule) for f in findings] == [
        ("pyguara/mod.py", "DS002"),
        ("pyguara/mod.py", "DS004"),
    ]


def test_there_is_no_baseline_left() -> None:
    assert not (REPO_ROOT / "tools" / "docstring_baseline.txt").exists()
