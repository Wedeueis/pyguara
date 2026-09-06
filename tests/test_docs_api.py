"""Guards that the documentation describes an API that actually exists.

`docs/core/logging.md` once documented `pyguara.log.config.setup_logging()` --
a module and a function that have never existed in this tree. Every code
sample on the page raised ModuleNotFoundError, and nothing caught it, because
documentation is never executed.

These tests extract `pyguara...` imports and dotted references out of the
Markdown under `docs/` and check they resolve. They are deliberately shallow:
the point is to catch a symbol that has been renamed or never existed, not to
type-check the samples.
"""

from __future__ import annotations

import ast
import importlib
import re
from pathlib import Path

import pytest

DOCS_DIR = Path(__file__).resolve().parent.parent / "docs"

# Illustrative names in the style guide, standing in for "your subsystem".
# They are meant not to resolve.
PLACEHOLDER_PREFIXES = ("pyguara.subsystem",)

_CODE_FENCE = re.compile(r"```(?:python|py)\n(.*?)```", re.DOTALL)
# Inline references like `pyguara.log.config.setup_logging()` in prose.
_INLINE_DOTTED = re.compile(r"`(pyguara(?:\.[A-Za-z_][A-Za-z0-9_]*)+)`")


def _markdown_files() -> list[Path]:
    return sorted(DOCS_DIR.rglob("*.md"))


def _python_blocks(text: str) -> list[str]:
    return _CODE_FENCE.findall(text)


def _imports_in(source: str) -> list[tuple[str, tuple[str, ...]]]:
    """Return (module, names) for every pyguara import in a snippet."""
    try:
        tree = ast.parse(source)
    except SyntaxError:
        # Samples are often fragments (`...` bodies, elided lines). A fragment
        # that will not parse cannot be checked, and is not itself a failure.
        return []

    found: list[tuple[str, tuple[str, ...]]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and (node.module or "").startswith(
            "pyguara"
        ):
            found.append((node.module or "", tuple(a.name for a in node.names)))
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.startswith("pyguara"):
                    found.append((alias.name, ()))
    return found


@pytest.mark.parametrize("path", _markdown_files(), ids=lambda p: p.name)
def test_documented_imports_resolve(path: Path) -> None:
    """Every `from pyguara... import X` in the docs must actually import."""
    failures: list[str] = []

    for block in _python_blocks(path.read_text(encoding="utf-8")):
        for module_name, names in _imports_in(block):
            if module_name.startswith(PLACEHOLDER_PREFIXES):
                continue
            try:
                module = importlib.import_module(module_name)
            except ImportError as error:
                failures.append(f"{module_name}: {error}")
                continue
            for name in names:
                if name == "*":
                    continue
                if not hasattr(module, name):
                    failures.append(f"{module_name} has no attribute {name!r}")

    assert not failures, f"{path.relative_to(DOCS_DIR.parent)}:\n  " + "\n  ".join(
        failures
    )


@pytest.mark.parametrize("path", _markdown_files(), ids=lambda p: p.name)
def test_inline_dotted_references_resolve(path: Path) -> None:
    """Backticked `pyguara.a.b.c` references in prose must resolve too.

    This is what would have caught `pyguara.log.config.setup_logging`.
    """
    failures: list[str] = []

    for dotted in set(_INLINE_DOTTED.findall(path.read_text(encoding="utf-8"))):
        if dotted.startswith(PLACEHOLDER_PREFIXES):
            continue
        parts = dotted.split(".")
        # Walk as far as the import system allows, then attribute-access.
        module = None
        index = len(parts)
        while index > 0:
            try:
                module = importlib.import_module(".".join(parts[:index]))
                break
            except ImportError:
                index -= 1
        if module is None:
            failures.append(f"{dotted}: no importable module in that path")
            continue

        target = module
        for attribute in parts[index:]:
            if not hasattr(target, attribute):
                failures.append(f"{dotted}: {attribute!r} not found")
                break
            target = getattr(target, attribute)

    assert not failures, f"{path.relative_to(DOCS_DIR.parent)}:\n  " + "\n  ".join(
        failures
    )
