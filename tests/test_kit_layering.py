"""Core never imports a kit.

`pyguara.kits` states the rule: core is genre-agnostic and never
imports from it. A violation looks like an ordinary import, so this
check fails the build on one.

The source is parsed, not grepped: a docstring that names
`pyguara.kits` is not an import.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

PYGUARA = Path(__file__).resolve().parent.parent / "pyguara"
KITS = PYGUARA / "kits"

CORE_MODULES = sorted(p for p in PYGUARA.rglob("*.py") if KITS not in p.parents)


def _kit_imports(path: Path) -> list[str]:
    """Every `pyguara.kits...` module imported by `path`.

    Args:
        path: A module to parse.

    Returns:
        The imported kit module names, in source order.
    """
    found: list[str] = []
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.ImportFrom):
            if node.module and node.module.startswith("pyguara.kits"):
                found.append(node.module)
        elif isinstance(node, ast.Import):
            found.extend(
                alias.name
                for alias in node.names
                if alias.name.startswith("pyguara.kits")
            )
    return found


@pytest.mark.parametrize(
    "module", CORE_MODULES, ids=lambda p: str(p.relative_to(PYGUARA))
)
def test_a_core_module_does_not_import_a_kit(module: Path) -> None:
    imported = _kit_imports(module)

    assert imported == [], (
        f"{module.relative_to(PYGUARA)} imports {imported}. Core is "
        "genre-agnostic: a kit depends on core, never the reverse. Move the "
        "code that needs the kit into the kit, as #132 did with the "
        "platformer's debug probes."
    )


def test_the_scan_actually_found_the_core_modules() -> None:
    """A wrong path would make every test above pass vacuously."""
    assert len(CORE_MODULES) > 100
    assert not any(KITS in p.parents for p in CORE_MODULES)
