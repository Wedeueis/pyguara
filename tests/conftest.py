"""Pytest configuration and fixtures."""

import os
from collections.abc import Iterator
from typing import Any

import pytest

from pyguara.di.container import DIContainer
from pyguara.events.dispatcher import EventDispatcher

# Set in CI, where a missing graphics adapter means the environment is wrong
# rather than absent. Without it a machine with no GPU still runs the rest
# of the suite green -- but every GPU test would then skip silently on CI.
REQUIRE_GPU = os.environ.get("PYGUARA_REQUIRE_GPU") == "1"


@pytest.fixture
def wgpu_frame() -> Any:
    """Make native wgpu frames: `wgpu_frame(width, height)`, offscreen.

    Skips when no graphics adapter can be opened -- unless
    `PYGUARA_REQUIRE_GPU=1`, where that is a failure. Runs in-process:
    the separate processes wgpu tests used to need were for a ModernGL
    context in the same process, which no longer exists.
    """
    os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
    import pygame

    pygame.init()
    if pygame.display.get_surface() is None:
        pygame.display.set_mode((8, 8))
    from pyguara.graphics.backends.wgpu import GpuFrame

    try:
        GpuFrame(8, 8)
    except RuntimeError as error:
        if REQUIRE_GPU:
            pytest.fail(f"PYGUARA_REQUIRE_GPU is set and no adapter opened: {error}")
        pytest.skip(f"no graphics adapter for wgpu: {error}")
    return GpuFrame


@pytest.fixture
def imgui_ctx() -> Iterator[Any]:
    """A Dear ImGui context with no GL behind it, for the editor panels.

    ImGui's C++ core needs no OpenGL to create a context or build a frame
    -- only to *rasterise* the draw data it produces. That is what makes
    the editor's panels testable at all, and it is the seam the previous
    `pyguara/editor` lacked: every one of its panel methods early-returned
    behind a dead GL import, so 705 lines of it were never executed by a
    test or by a game.

    `renderer_has_textures` is declared because ImGui 1.92 asserts in
    `new_frame()` otherwise -- it expects a legacy backend to have uploaded
    the font atlas itself, and this fixture has no backend at all.

    Yields:
        The ImGui IO for the fresh context, already sized.
    """
    imgui = pytest.importorskip("imgui_bundle").imgui

    ctx = imgui.create_context()
    imgui.set_current_context(ctx)
    io = imgui.get_io()
    io.display_size = imgui.ImVec2(1280.0, 720.0)
    io.delta_time = 1.0 / 60.0
    io.backend_flags |= imgui.BackendFlags_.renderer_has_textures.value
    # Keeps the suite from writing an imgui.ini into the repository root.
    io.set_ini_filename("")
    try:
        yield io
    finally:
        imgui.destroy_context(ctx)


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


def pytest_addoption(parser: pytest.Parser) -> None:
    """`--update-golden`: rewrite the stored golden images from this run.

    For `tests/integration/golden.py`'s users. A golden image is the
    approved output of a render path; when an intended change moves pixels,
    rerun those tests with this flag and **look at the diff** of the images
    before committing them, as with `--snapshot-update`.
    """
    parser.addoption(
        "--update-golden",
        action="store_true",
        default=False,
        help="rewrite golden images from this run's output",
    )


@pytest.fixture
def update_golden(request: pytest.FixtureRequest) -> bool:
    """Whether this run rewrites golden images rather than checking them."""
    return bool(request.config.getoption("--update-golden"))
