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
        import pygame

        surface = self._compose()
        if surface is None:
            logger.warning(
                "Nothing to capture: this backend exposes neither a display "
                "surface nor a framebuffer."
            )
            return None

        self._out_dir.mkdir(parents=True, exist_ok=True)
        path = self._out_dir / f"{name or f'frame_{self._frame:04d}'}.png"
        pygame.image.save(surface, str(path))

        world = self._world_surface()
        width, height = surface.get_size()
        return Capture(
            path=path,
            width=width,
            height=height,
            blank=is_flat(surface),
            world_flat=None if world is None else is_flat(world),
        )

    def _compose(self) -> Any:
        """Return the composed frame as a pygame surface, or None.

        `agent_view`'s logic, and its reasoning: the pygame backends draw
        into the display surface, so reading it back is the whole job. A
        ModernGL backend does not -- under an `OPENGL` display,
        `get_surface()` hands back a surface the GPU never touched -- so
        the offscreen buffer the final pass blits from is read instead.
        The default framebuffer is no use: after the swap it is an
        undefined back buffer, and before it reads back as solid zeros
        under the offscreen driver.

        Returns:
            The surface, or None.
        """
        import pygame

        framebuffer = self._framebuffer(self._final_source())
        if framebuffer is not None:
            return _to_surface(framebuffer)
        return pygame.display.get_surface()

    def _world_surface(self) -> Any:
        """Return the world buffer alone, before any UI, or None.

        Returns:
            The surface, or None when there is no separate world buffer.
        """
        if self._final_source() == "world":
            # The composed frame already is the world buffer, so a second
            # read would say the same thing twice.
            return None
        framebuffer = self._framebuffer("world")
        return None if framebuffer is None else _to_surface(framebuffer)

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


def _to_surface(framebuffer: Any) -> Any:
    """Read a framebuffer into a pygame surface, the right way up.

    Args:
        framebuffer: A `Framebuffer` from the render graph.

    Returns:
        The surface.
    """
    import pygame

    size = (framebuffer.width, framebuffer.height)
    frame = pygame.image.frombuffer(framebuffer.fbo.read(components=3), size, "RGB")
    # GL's origin is bottom-left and pygame's is top-left.
    return pygame.transform.flip(frame, False, True)


def open_headless(
    scene_factory: Any,
    *,
    project_root: Path | None = None,
    out_dir: Path | None = None,
    container_factory: Any = None,
    gl: bool = False,
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
    along. The driver choice matters too: `dummy` has no OpenGL
    whatsoever, so a ModernGL scene cannot create its context under it and
    needs `offscreen` instead, which is what `gl` selects.

    Args:
        scene_factory: Called with the event dispatcher, returns the
            `Scene` to run.
        project_root: The project directory, for `project_overview`.
        out_dir: Where to write frames.
        container_factory: Returns a configured container, for a game
            with its own bootstrap. Demos in this repository expose
            `configure_game_container()` for exactly this. Defaults to
            `create_application()`'s container.
        gl: Use the `offscreen` driver, which provides a real GL context,
            instead of `dummy`. Required for a ModernGL scene.
        seed: Seed the engine's `RandomService` with this, so two runs
            draw the same numbers. None leaves whatever the bootstrap
            chose, which is a fresh seed per run.
        fixed_clock: Advance every frame by exactly one sixtieth of a
            second rather than by wall-clock time.

    Returns:
        The harness, with the scene active and no frame stepped yet.
    """
    _force_headless_drivers(gl=gl)

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

    The non-headless bootstrap registers `PygameClock`, which measures
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


def _force_headless_drivers(*, gl: bool = False) -> None:
    """Point SDL at drivers that need no display.

    `setdefault`, so a caller or a test module that has already chosen
    keeps their choice -- changing it after pygame has initialised its
    video subsystem would not take effect anyway.

    Args:
        gl: Prefer `offscreen`, which provides a real GL context
            headlessly. `dummy` has no OpenGL at all ("OpenGL support is
            either not configured in SDL or not available in current SDL
            video driver"), so a ModernGL scene cannot create its context
            under it.
    """
    os.environ.setdefault("SDL_VIDEODRIVER", "offscreen" if gl else "dummy")
    os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
    os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")
