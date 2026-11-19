"""The foundation packages import nothing above them.

`ecs`, `di`, `events`, `common`, `log` and `errors` are what every other
package is built on. If one of them imports a subsystem, the subsystem
can no longer be tested, replaced or loaded without the whole engine.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

PACKAGE = Path(__file__).resolve().parent.parent / "pyguara"

FOUNDATION = frozenset({"ecs", "di", "events", "common", "log", "errors"})

# Below the foundation: the extension and its loader import nothing of ours.
ALLOWED = FOUNDATION | {"native", "pyguara_core_rs"}


def _sources() -> list[Path]:
    files: list[Path] = []
    for name in sorted(FOUNDATION):
        target = PACKAGE / name
        files.extend(
            sorted(target.rglob("*.py"))
            if target.is_dir()
            else [target.with_suffix(".py")]
        )
    return files


def _imported_subpackages(source: Path) -> set[str]:
    """Return each `pyguara.<name>` the file imports, including inside functions."""
    found: set[str] = set()
    for node in ast.walk(ast.parse(source.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            modules = [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            if node.module == "pyguara":
                modules = [f"pyguara.{alias.name}" for alias in node.names]
            else:
                modules = [node.module]
        else:
            continue
        for module in modules:
            parts = module.split(".")
            if parts[0] == "pyguara" and len(parts) > 1:
                found.add(parts[1])
    return found


@pytest.mark.parametrize(
    "source", _sources(), ids=lambda p: str(p.relative_to(PACKAGE))
)
def test_a_foundation_module_imports_only_the_foundation(source: Path) -> None:
    upward = _imported_subpackages(source) - ALLOWED
    assert not upward, (
        f"pyguara/{source.relative_to(PACKAGE)} imports "
        f"{', '.join(f'pyguara.{name}' for name in sorted(upward))}, above the "
        "foundation. Move the dependency up, or pass it in."
    )


def test_the_check_sees_every_foundation_package() -> None:
    covered = {p.relative_to(PACKAGE).parts[0].removesuffix(".py") for p in _sources()}
    assert covered == FOUNDATION
