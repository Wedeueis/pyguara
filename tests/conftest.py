"""Pytest configuration and fixtures."""

import os
from collections.abc import Iterator
from typing import Any

import pytest

from pyguara.di.container import DIContainer
from pyguara.events.dispatcher import EventDispatcher

# Set in CI, where a missing GL context means the environment is wrong
# rather than absent. Without it a machine with no GPU still runs the rest
# of the suite green, which is what keeps these tests cheap to live with --
# but it also let every GL test in this repository skip silently on CI.
REQUIRE_GL = os.environ.get("PYGUARA_REQUIRE_GL") == "1"


@pytest.fixture(scope="session")
def gl_ctx() -> Iterator[Any]:
    """A standalone ModernGL context, shared by every test that needs GL.

    Standalone rather than SDL: no window, no display, no swap semantics.
    `tools/agent_view.py --gl` uses SDL's offscreen driver instead, but
    that exists to capture what a *demo* draws, which is a different job.

    **Nothing is configured on it.** `ModernGLRenderer` applies the blend
    mode it needs when it is constructed, so a test drawing through the
    renderer gets the same state the engine runs with. A test drawing
    without one -- the UI renderer, a raw pass -- sets up what it needs
    itself, and should not assume it inherited it from a neighbour.

    Yields:
        The ModernGL context.
    """
    moderngl = pytest.importorskip("moderngl")

    # The default backend is GLX on Linux and wants a display; EGL does
    # not, which is what makes this work on a headless runner.
    failures = []
    for kwargs in ({}, {"backend": "egl"}):
        try:
            ctx = moderngl.create_standalone_context(**kwargs)
            break
        except Exception as exc:  # pragma: no cover - depends on the machine
            failures.append(f"{kwargs or 'default'}: {exc}")
    else:  # pragma: no cover - depends on the machine
        detail = "; ".join(failures)
        if REQUIRE_GL:
            pytest.fail(
                "PYGUARA_REQUIRE_GL is set and no standalone GL context could "
                f"be created, so the GL suite would have skipped silently. {detail}"
            )
        pytest.skip(f"no standalone GL context available: {detail}")

    try:
        yield ctx
    finally:
        ctx.release()


@pytest.fixture
def isolated_gl_ctx(gl_ctx: Any) -> Iterator[Any]:
    """A standalone GL context of one test's own, then the shared one back.

    For a test that needs to change context-global state -- the blend mode,
    say -- and so cannot use the session-scoped `gl_ctx` without leaking
    into every later GL test.

    **Do not create a standalone context by hand for this.** Creating one
    makes it current, and releasing it leaves *no* context current, not the
    one that was current before. The shared `gl_ctx` is then still a live
    Python object whose every GL call fails: `cannot create renderbuffer`,
    from a fixture that looks entirely unrelated. That is what this fixture
    exists to prevent -- it re-asserts `gl_ctx` afterwards.

    It went unnoticed because it depends on collection order. While the
    only module with a private context happened to run *before* every other
    GL module, `gl_ctx` did not exist yet when those contexts came and
    went, so it was created afterwards and was current. Adding a GL test
    file that sorts earlier in the directory was enough to break 28 tests
    across seven modules that nothing had touched.

    Yields:
        A fresh standalone context, released when the test ends.
    """
    moderngl = pytest.importorskip("moderngl")
    try:
        ctx = moderngl.create_standalone_context()
    except Exception as exc:  # pragma: no cover - depends on the machine
        pytest.skip(f"no standalone GL context available: {exc}")
    try:
        yield ctx
    finally:
        ctx.release()
        # moderngl offers no public "make current" other than the
        # context-manager protocol, and nothing here wants to exit it: the
        # shared context is session-scoped, and every later GL test expects
        # to find it current.
        gl_ctx.__enter__()


# Define fake classes for Pygame types to satisfy dataclasses and inheritance
class MockColor:
    """Mock for pygame.Color."""

    def __init__(self, r=0, g=0, b=0, a=255):
        """Initialize color."""
        self.r, self.g, self.b, self.a = r, g, b, a

    def __iter__(self):
        """Allow iteration."""
        return iter((self.r, self.g, self.b, self.a))

    def normalize(self):
        """Return normalized color."""
        return (self.r / 255, self.g / 255, self.b / 255, self.a / 255)


class MockRect:
    """Mock for pygame.Rect."""

    def __init__(self, x=0, y=0, w=0, h=0):
        """Initialize rect."""
        self.x, self.y, self.w, self.h = x, y, w, h
        self.width, self.height = w, h
        self.centerx = x + w // 2
        self.centery = y + h // 2

    def collidepoint(self, x, y):
        """Mock collision check."""
        return True


@pytest.fixture
def container():
    """Provide a DI container."""
    return DIContainer()


@pytest.fixture
def event_dispatcher():
    """Provide an event dispatcher."""
    return EventDispatcher()
