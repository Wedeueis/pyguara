"""The closed loop: open a scene, edit it, run it, look at the result.

`tools/agent_view.py` is the prior art and most of this is its lesson
generalised. It boots one of fourteen hardcoded demos, advances a fixed
number of frames and writes PNGs an agent can open. What it cannot do is
the *loop* -- edit something, run, check, undo, try again -- because it
has no edit surface and exits when it is done.

A harness binds the three pieces that already exist:

- `StudioSession`, so an edit is a command: undoable, journaled, diffable.
- `Application.begin()` / `step()`, so frames advance under the caller's
  control rather than inside `run()`.
- `agent_view`'s capture path, which is the part that took real work to
  get right and is reused rather than reimplemented.

**Determinism.** A headless application gets `FixedClock`, so every frame
is exactly one sixtieth of a second however long it really took. Two runs
of the same script therefore produce the same physics, the same tweens and
the same frames -- which is what makes "run it again and diff" an answer
rather than a coin toss.

**What a capture proves.** It reads the buffer the renderer drew into:
that proves the render *path* works -- entities queried, sprites
submitted, batches flushed. It does **not** prove a window appears on
screen. Those have already diverged in this engine, when vsync silently
promoted the display to an OpenGL surface that never presented software
blits: the captures looked perfect and the real window was blank. See
`docs/guides/agent-visual-inspection.md`.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pyguara.log import get_logger
from pyguara.studio.model.snapshot import SceneDiff, SceneSnapshot, diff_snapshots
from pyguara.studio.session import StudioSession

logger = get_logger(__name__)

DEFAULT_OUT_DIR = Path(".agent-view")
"""Where frames are written.

The same directory `tools/agent_view.py` uses, so an agent that already
knows where to look for frames does not have to learn a second place.
"""

SAMPLE_GRID = 32
"""How many samples per axis the flat-frame check takes.

`agent_view.is_blank`'s figure. A full scan of a 1280x720 frame is nearly
a million `get_at` calls in Python, and a thousand samples finds a flat
frame just as reliably.
"""


@dataclass(frozen=True)
class Capture:
    """One frame written to disk.

    Attributes:
        path: Where it was written.
        width: Its width in pixels.
        height: Its height in pixels.
        blank: Whether the composed frame is a single flat colour -- the
            usual way a capture silently tells you nothing.
        world_flat: Whether the *world* buffer alone is flat, or None when
            there is no separate one. Reported apart from `blank` because
            a composed frame carries the UI too, so a dead world render
            path still leaves a HUD on screen and the frame is never flat.
            This is the check that catches it.
    """

    path: Path
    width: int
    height: int
    blank: bool
    world_flat: bool | None = None

    def to_dict(self) -> dict[str, Any]:
        """Return the JSON-serializable form.

        Returns:
            The capture as a plain dict.
        """
        data: dict[str, Any] = {
            "path": str(self.path),
            "width": self.width,
            "height": self.height,
            "blank": self.blank,
        }
        if self.world_flat is not None:
            data["world_flat"] = self.world_flat
        return data


class StudioHarness:
    """Drives an application frame by frame, with a session over its world."""

    def __init__(
        self,
        application: Any,
        session: StudioSession,
        *,
        out_dir: Path | None = None,
    ) -> None:
        """Wrap a started application.

        Args:
            application: An `Application` that `begin()` has been called
                on. Not `run()`: this harness owns the frame loop.
            session: A session over the active scene's world.
            out_dir: Where to write frames.
        """
        self._application = application
        self._session = session
        self._out_dir = out_dir or DEFAULT_OUT_DIR
        self._frame = 0
        self._baseline: SceneSnapshot | None = None

    @property
    def session(self) -> StudioSession:
        """The session over the running scene."""
        return self._session

    @property
    def application(self) -> Any:
        """The application being driven."""
        return self._application

    @property
    def frame(self) -> int:
        """How many frames have been stepped."""
        return self._frame

    @property
    def out_dir(self) -> Path:
        """Where frames are written."""
        return self._out_dir

    def step(self, frames: int = 1) -> int:
        """Advance the loop.

        Args:
            frames: How many frames to run.

        Returns:
            How many actually ran -- fewer when the application stopped,
            which a caller should check rather than assume.

        Raises:
            ValueError: If `frames` is negative.
        """
        if frames < 0:
            raise ValueError(f"frames must not be negative, got {frames}")

        ran = 0
        for _ in range(frames):
            if not self._application.step():
                break
            ran += 1
            self._frame += 1
        return ran

    # ----------------------------------------------------------------
    # Looking
    # ----------------------------------------------------------------

    def capture(self, name: str | None = None) -> Capture | None:
        """Write the current frame to a PNG and report what is in it.

        Args:
            name: The file name, without an extension. Defaults to the
                frame number, zero-padded so a directory listing sorts in
                order.

        Returns:
            The capture, or None when there is nothing to read -- a
            headless backend with no surface and no framebuffer.
        """
        image = self._compose()
        if image is None:
            logger.warning(
                "Nothing to capture: this backend exposes neither a display "
                "surface nor a framebuffer."
            )
            return None

        self._out_dir.mkdir(parents=True, exist_ok=True)
        path = self._out_dir / f"{name or f'frame_{self._frame:04d}'}.png"
        image.save(path)

        world = self._world_image()
        width, height = image.get_size()
        return Capture(
            path=path,
            width=width,
            height=height,
            blank=is_flat(image),
            world_flat=None if world is None else is_flat(world),
        )

    def _compose(self) -> RgbaImage | None:
        """Return the composed frame, UI included, or None.

        The wgpu window renders into the device's own target, so the frame
        is read back from the GPU. The pygame backend draws onto its display
        surface, which is read instead -- the only branch that touches
        pygame, and only because that backend is pygame.

        Returns:
            The frame, or None.
        """
        from pyguara.graphics.window import Window

        try:
            backend = self._application.container.get(Window).backend
        except Exception:  # noqa: BLE001 - no window registered: fall through
            backend = None
        read_pixels = getattr(backend, "read_pixels", None)
        if read_pixels is not None:
            return RgbaImage(*read_pixels())
        framebuffer = self._framebuffer(self._final_source())
        if framebuffer is not None:
            return _read_buffer(framebuffer)
        return _display_surface()

    def _world_image(self) -> RgbaImage | None:
        """Return the world buffer alone, before any UI, or None.

        Returns:
            The image, or None when there is no separate world buffer.
        """
        if self._final_source() == "world":
            # The composed frame already is the world buffer, so a second
            # read would say the same thing twice.
            return None
        framebuffer = self._framebuffer("world")
        return None if framebuffer is None else _read_buffer(framebuffer)

    def _final_source(self) -> str:
        """Return the name of the buffer the finished frame is composed in.

        Returns:
            `FinalPass.input_fbo_name`, or `"world"` when there is no
            final pass -- which is what the offscreen capture tooling
            runs with.
        """
        graph = self._graph()
        if graph is None:
            return "world"
        final_pass = graph.get_pass("final")
        if final_pass is None:
            return "world"
        name = getattr(final_pass, "input_fbo_name", "world")
        return str(name)

    def _framebuffer(self, name: str) -> Any:
        """Return a named framebuffer from the render graph, or None.

        Args:
            name: The buffer's name.

        Returns:
            The framebuffer, or None.
        """
        graph = self._graph()
        if graph is None:
            return None
        manager = getattr(graph, "fbo_manager", None)
        if manager is None:
            return None
        return manager.get(name)

    def _graph(self) -> Any:
        """Return the real render graph, or None on a backend without one.

        Returns:
            The graph, or None -- the Pygame backend registers a stub
            under the same key, and a headless one registers nothing.
        """
        try:
            from pyguara.graphics.pipeline.graph import RenderGraph

            graph = self._application.container.get(RenderGraph)
        except Exception:
            return None
        return graph if isinstance(graph, RenderGraph) else None

    # ----------------------------------------------------------------
    # Checking
    # ----------------------------------------------------------------

    def mark(self) -> SceneSnapshot:
        """Record the world now, as the baseline for `changes()`.

        Returns:
            The snapshot taken.
        """
        self._baseline = self._session.snapshot()
        return self._baseline

    def changes(self) -> SceneDiff:
        """Return what has changed since `mark()`.

        The "check" half of edit-run-check. Without a baseline, the
        comparison is against the world as it is, which is empty by
        construction -- so one is taken on first use rather than
        returning something misleading.

        Returns:
            The difference.
        """
        if self._baseline is None:
            self.mark()
        assert self._baseline is not None
        return diff_snapshots(self._baseline, self._session.snapshot())

    def close(self) -> None:
        """Shut the application down.

        Safe to call more than once -- `Application.shutdown()` is
        idempotent.
        """
        self._application.shutdown()


def is_flat(surface: Any) -> bool:
    """Report whether a frame is a single flat colour.

    A blank frame is the usual way a capture silently tells you nothing,
    so it is worth flagging rather than leaving for a reader to notice.

    Sampled on a grid rather than scanned: a full pass over a 1280x720
    frame is nearly a million `get_at` calls in Python, and a thousand
    samples finds a flat frame just as reliably.

    Args:
        surface: The captured frame.

    Returns:
        True if every sampled pixel is identical. A zero-sized surface
        counts as flat.
    """
    width, height = surface.get_size()
    if width == 0 or height == 0:
        return True

    step_x = max(1, width // SAMPLE_GRID)
    step_y = max(1, height // SAMPLE_GRID)
    first = surface.get_at((0, 0))
    for y in range(0, height, step_y):
        for x in range(0, width, step_x):
            if surface.get_at((x, y)) != first:
                return False
    return True


class RgbaImage:
    """A captured frame: RGBA bytes, top row first.

    Answers `get_size()` and `get_at()`, the two calls `is_flat` makes, so
    a pygame surface and this are interchangeable there.
    """

    def __init__(self, pixels: bytes, width: int, height: int) -> None:
        """Hold a frame.

        Args:
            pixels: `width * height * 4` bytes.
            width: Width in pixels.
            height: Height in pixels.
        """
        self.pixels = bytes(pixels)
        self.width = width
        self.height = height

    def get_size(self) -> tuple[int, int]:
        """Return `(width, height)`."""
        return self.width, self.height

    def get_at(self, at: tuple[int, int]) -> tuple[int, int, int, int]:
        """Return the RGBA of one pixel."""
        start = (at[1] * self.width + at[0]) * 4
        red, green, blue, alpha = self.pixels[start : start + 4]
        return red, green, blue, alpha

    def save(self, path: Path) -> None:
        """Write the frame as a PNG.

        Through the native extension where it is built, so a wgpu game's
        capture loads no pygame; through pygame where it is not.
        """
        from pyguara import native

        try:
            extension = native.require_extension("PNG capture")
        except RuntimeError:
            extension = None
        if extension is not None:
            extension.encode_png(str(path), self.pixels, self.width, self.height)
            return
        import pygame

        image = pygame.image.frombuffer(self.pixels, self.get_size(), "RGBA")
        pygame.image.save(image, str(path))


def _read_buffer(framebuffer: Any) -> RgbaImage:
    """Read a render-graph buffer, which is top row first on wgpu."""
    return RgbaImage(framebuffer.read_rgba(), framebuffer.width, framebuffer.height)


def _display_surface() -> RgbaImage | None:
    """Read the pygame backend's display surface, or None if it has none."""
    import pygame

    surface = pygame.display.get_surface()
    if surface is None:
        return None
    width, height = surface.get_size()
    return RgbaImage(pygame.image.tobytes(surface, "RGBA"), width, height)


def open_headless(
    scene_factory: Any,
    *,
    project_root: Path | None = None,
    out_dir: Path | None = None,
    container_factory: Any = None,
    seed: int | None = 0,
    fixed_clock: bool = True,
) -> StudioHarness:
    """Boot an application with no visible window and open a harness on it.

    **Headless here means "no window", not "the headless backend".** The
    distinction is load-bearing: `create_headless_application()` registers
    no texture loader at all, so any scene that loads an image dies with
    `No loader registered for extension: .png` before it finishes
    entering. A real demo is almost entirely images.

    So this boots the *normal* bootstrap under an SDL driver that needs no
    display -- the same arrangement `tools/agent_view.py` has used all
    along. `dummy` is enough for every backend: wgpu renders offscreen
    and needs no GL context from SDL.

    Args:
        scene_factory: Called with the event dispatcher, returns the
            `Scene` to run.
        project_root: The project directory, for `project_overview`.
        out_dir: Where to write frames.
        container_factory: Returns a configured container, for a game
            with its own bootstrap. Demos in this repository expose
            `configure_game_container()` for exactly this. Defaults to
            `create_application()`'s container.
        seed: Seed the engine's `RandomService` with this, so two runs
            draw the same numbers. None leaves whatever the bootstrap
            chose, which is a fresh seed per run.
        fixed_clock: Advance every frame by exactly one sixtieth of a
            second rather than by wall-clock time.

    Returns:
        The harness, with the scene active and no frame stepped yet.
    """
    _force_headless_drivers()

    from pyguara.application.application import Application
    from pyguara.events.dispatcher import EventDispatcher
    from pyguara.prefabs.registry import ComponentRegistry

    if container_factory is not None:
        container = container_factory()
    else:
        from pyguara.application.bootstrap import create_container

        container = create_container()

    # Both replacements happen *before* `container.get(Application)`,
    # because `Application.__init__` resolves the clock eagerly and would
    # otherwise keep the wall-clock one it was handed.
    if fixed_clock:
        _install_fixed_clock(container)
    if seed is not None:
        _seed_random(container, seed)

    application = container.get(Application)

    scene = scene_factory(container.get(EventDispatcher))
    application.begin(scene)

    session = StudioSession(
        scene.entity_manager,
        scene_name=scene.name,
        project_root=(project_root or Path.cwd()).resolve(),
        component_registry=container.get(ComponentRegistry),
    )
    harness = StudioHarness(application, session, out_dir=out_dir)
    # So `run_frames` and `capture_frame` work over this session.
    session.attach_harness(harness)
    return harness


def _install_fixed_clock(container: Any) -> None:
    """Make every frame exactly one sixtieth of a second.

    The non-headless bootstrap registers a wall clock (`PygameClock` or
    `WallClock`, by backend), which measures
    wall-clock time -- so two runs of the same script step different
    amounts of simulated time and produce different results. That is the
    right behaviour for a game and useless for "run it again and diff".

    Only the *headless backend* gets `FixedClock` by default, and that
    backend registers no texture loader, so a real scene cannot use it.
    Hence this: the real backend's rendering with the headless backend's
    clock.

    Args:
        container: The container to replace the clock in.
    """
    from pyguara.application.clock import Clock, FixedClock

    container.register_instance(Clock, FixedClock())


def _seed_random(container: Any, seed: int) -> None:
    """Replace the engine's random service with a seeded one.

    Without it, anything drawing from `RandomService` -- particle jitter,
    an AI's choice of target, a spawn table -- diverges between runs even
    with a fixed clock.

    Args:
        container: The container to replace the service in.
        seed: The root seed.
    """
    from pyguara.random.service import RandomService

    container.register_instance(RandomService, RandomService(root_seed=seed))


def _force_headless_drivers() -> None:
    """Point SDL at drivers that need no display.

    `setdefault`, so a caller or a test module that has already chosen
    keeps their choice -- changing it after pygame has initialised its
    video subsystem would not take effect anyway.
    """
    os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
    os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
    os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")
