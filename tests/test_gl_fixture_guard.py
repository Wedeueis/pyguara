"""The shared GL fixture must not skip silently where GL is mandatory.

Every GL test in this repository skipped on CI for as long as CI had no
Mesa installed, and a skip reads as a pass: the pixel suites proved things
locally and nothing in the pipeline. `PYGUARA_REQUIRE_GL` is what turns
that into a failure, so it needs a test of its own -- it is precisely the
kind of guard that is never exercised until the day it matters.

The fixture body is called directly here, since the point is what it does
when no context can be created, which is not a state this machine can be
put into.
"""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Any

import pytest

from tests import conftest


def _no_context(*args: Any, **kwargs: Any) -> Any:
    raise RuntimeError("no display and no EGL")


@pytest.fixture
def without_gl(monkeypatch: pytest.MonkeyPatch) -> None:
    """Make every context-creation attempt fail."""
    moderngl = pytest.importorskip("moderngl")
    monkeypatch.setattr(moderngl, "create_standalone_context", _no_context)


def test_it_skips_when_gl_is_merely_absent(
    without_gl: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A laptop with no GPU still runs the rest of the suite green."""
    monkeypatch.setattr(conftest, "REQUIRE_GL", False)

    with pytest.raises(pytest.skip.Exception, match="no standalone GL context"):
        next(conftest.gl_ctx.__wrapped__())  # type: ignore[attr-defined]


def test_it_fails_when_gl_is_required(
    without_gl: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(conftest, "REQUIRE_GL", True)

    with pytest.raises(pytest.fail.Exception, match="would have skipped silently"):
        next(conftest.gl_ctx.__wrapped__())  # type: ignore[attr-defined]


def test_the_failure_names_what_went_wrong(
    without_gl: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Both attempts are reported, so a broken runner is diagnosable."""
    monkeypatch.setattr(conftest, "REQUIRE_GL", True)

    with pytest.raises(pytest.fail.Exception) as excinfo:
        next(conftest.gl_ctx.__wrapped__())  # type: ignore[attr-defined]

    message = str(excinfo.value)
    assert "default" in message and "egl" in message
    assert "no display and no EGL" in message


def test_the_backend_fallback_is_tried_before_giving_up(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """EGL is reached when the default backend fails.

    The default backend is GLX on Linux and wants a display. CI has none,
    so the default attempt raises there and only the EGL one succeeds --
    the branch that matters most is the one this machine, which has a
    working GLX, can never take on its own.
    """
    moderngl = pytest.importorskip("moderngl")
    attempts: list[dict[str, Any]] = []
    sentinel = object()

    def _egl_only(*args: Any, **kwargs: Any) -> Any:
        attempts.append(kwargs)
        if kwargs.get("backend") != "egl":
            raise RuntimeError("(standalone) XOpenDisplay: cannot open display")
        return sentinel

    monkeypatch.setattr(moderngl, "create_standalone_context", _egl_only)

    assert conftest.create_standalone_context() is sentinel
    assert attempts == [{}, {"backend": "egl"}]


def _calls_moderngl_directly(path: Path) -> bool:
    """Whether `path` calls `moderngl.create_standalone_context(...)`.

    Args:
        path: A test module to parse.

    Returns:
        True if the bare call appears as an actual call expression.
    """
    tree = ast.parse(path.read_text())
    return any(
        isinstance(node.func, ast.Attribute)
        and node.func.attr == "create_standalone_context"
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id == "moderngl"
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
    )


def test_no_test_builds_a_context_without_that_fallback() -> None:
    """No test may call `moderngl.create_standalone_context` itself.

    The bare call picks the default backend only. It works on any machine
    with a display and fails on CI with `XOpenDisplay: cannot open
    display`, so a test that rolls its own context either dies or skips
    there for a reason unrelated to what it tests -- which is how
    `test_gl_blend_state.py`'s five tests came to run on developer machines
    and nowhere else. `conftest.create_standalone_context()` is the only
    way in.

    Checked by parsing the sources: an import-time or runtime check would
    only fire on the machines that already work. Parsed rather than
    grepped, so that naming the call in a docstring -- as this very test
    does -- is not an offence.
    """
    tests_root = Path(__file__).parent
    offenders = sorted(
        str(path.relative_to(tests_root))
        for path in tests_root.rglob("test_*.py")
        if _calls_moderngl_directly(path)
    )

    assert offenders == [], (
        f"{offenders} build a GL context directly; call "
        "conftest.create_standalone_context() instead, which falls back to "
        "EGL on a headless runner"
    )
