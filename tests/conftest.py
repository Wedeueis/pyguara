"""Pytest configuration and fixtures."""

import gc
import os
import sys
from collections.abc import Iterator
from typing import Any

import pytest

from pyguara.di.container import DIContainer
from pyguara.events.dispatcher import EventDispatcher

# No test opens a real wgpu window unless it asks for one: the variable is
# inherited by every subprocess a test starts, too. A test that wants a
# window opens `NativeWindow` itself (`test_wgpu_window.py`).
os.environ.setdefault("PYGUARA_WINDOW", "offscreen")

# Set in CI, where a missing graphics adapter means the environment is wrong
# rather than absent. Without it a machine with no GPU still runs the rest
# of the suite green -- but every GPU test would then skip silently on CI.
REQUIRE_GPU = os.environ.get("PYGUARA_REQUIRE_GPU") == "1"

# How many wgpu devices a test may leave alive before the next one starts.
# Each `NativeGpu` owns an instance, an adapter and a device, and a driver
# can segfault past its cap instead of refusing: Mesa's GL-on-D3D12 under
# WSLg does at the tenth. An application a test never shut down keeps its
# device until a full garbage collection, which may not come for many
# tests, so test order alone decided whether the cap was reached.
_LIVE_DEVICE_BUDGET = 4


def _live_devices() -> int:
    """The process's live `NativeGpu` count.

    Read from the extension only if something has imported it: until then no
    device can exist, and looking it up here would load it.
    """
    extension = sys.modules.get("pyguara.pyguara_core_rs")
    if extension is None:
        return 0
    return int(extension.NativeGpu.live_devices())


@pytest.fixture(autouse=True)
def _restore_ui_theme() -> Iterator[None]:
    """Put the global UI theme back after each test.

    A game installs its own theme, as it should, so a test that runs one
    (the demo render tests do) leaves it behind: `cerrado_dusk` turns on
    shadows, and the next test's button draws one more rectangle. Serially
    the next test was never a UI one; under xdist it can be.
    """
    theme = sys.modules.get("pyguara.ui.theme")
    previous = theme.get_theme() if theme is not None else None
    yield
    theme = sys.modules.get("pyguara.ui.theme")
    if theme is None:
        return
    theme.set_theme(previous if previous is not None else theme.UITheme())


@pytest.fixture(autouse=True)
def _free_leaked_gpu_devices() -> Iterator[None]:
    """Collect garbage after a test that leaves too many devices alive.

    Only then: a full collection after each of eight thousand tests would
    cost minutes, and almost no test touches the GPU.
    """
    yield
    if _live_devices() > _LIVE_DEVICE_BUDGET:
        gc.collect()


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

    ImGui's core needs no GPU to create a context or build a frame, only
    to rasterise the draw data, so panels can be tested without one.

    `renderer_has_textures` is declared because ImGui asserts in
    `new_frame()` otherwise: with no backend, nothing uploads the font
    atlas.

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
    rerun those tests with this flag and look at the diff of the images
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
