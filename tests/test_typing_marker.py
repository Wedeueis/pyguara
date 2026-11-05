"""PyGuara's types have to reach the games built on it."""

from __future__ import annotations

from pathlib import Path

import pyguara


def test_the_package_declares_that_it_has_types() -> None:
    """Without this, mypy in a game treats every engine type as Any, and checks nothing."""
    assert (Path(pyguara.__file__).parent / "py.typed").is_file()
