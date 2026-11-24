"""The core Rendering System that orchestrates the pipeline."""

from bisect import bisect_right
from collections.abc import Callable, Iterable

from pyguara.common.types import Vector2
from pyguara.graphics.components.camera import Camera2D
from pyguara.graphics.pipeline.batch import Batcher
from pyguara.graphics.pipeline.queue import RenderQueue
from pyguara.graphics.pipeline.viewport import Viewport
from pyguara.graphics.protocols import IRenderer, Renderable
from pyguara.graphics.types import RenderBatch, RenderCommand

BatchSource = Callable[[Camera2D, Viewport], Iterable[RenderBatch]]
"""Builds ready-made batches for a frame, given its camera and viewport."""


class RenderSystem:
    """Manages the rendering pipeline: Sorting, Batching, and Drawing.

    Coordinates the submission of renderables, sorting by Z-index,
    batching for performance, and dispatching to the backend.
    """

    def __init__(self, backend: IRenderer):
        """Initialize with a specific backend.

        Args:
            backend: The concrete renderer implementation (e.g., PygameRenderer).
        """
        self._backend = backend
        self._queue = RenderQueue()
        self._batcher = Batcher()

        # Optimization: persistent viewport to avoid per-frame allocation
        self._default_viewport: Viewport | None = None

        # Ready-made batches, as (layer, sort group, depth, order, source).
        self._sources: list[tuple[int, int, float, int, BatchSource]] = []

    def submit(self, item: Renderable, position: Vector2 | None = None) -> None:
        """Add a renderable object to the current frame's queue.

        Args:
            item: An entity or component that complies with the Renderable protocol.
            position: World position to submit at, overriding `item.position`.
                Lets a caller combine a separate position source (e.g. an
                entity's `Transform`) without mutating `item` itself. Defaults
                to `item.position` when omitted.
        """
        # Direct access - protocol guarantees these attributes exist
        world_position = position if position is not None else item.position

        # Resolved here, not in the queue's sort key: a y-sorted command
        # carries its world Y in `z_index` so the comparison stays one
        # tuple of numbers rather than a branch per command per frame.
        # The *submitted* position is what counts -- for an entity sprite
        # that is the Transform plus the sprite's own offset, and depth has
        # to come from where the sprite is actually drawn.
        depth = world_position.y + item.sort_offset if item.y_sort else item.z_index

        # A flip is a negative scale on that axis, which every backend
        # draws as a mirror inside the same box.
        scale = item.scale
        if item.flip_x or item.flip_y:
            scale = Vector2(
                -scale.x if item.flip_x else scale.x,
                -scale.y if item.flip_y else scale.y,
            )

        self._queue.push(
            RenderCommand(
                texture=item.texture,
                world_position=world_position,
                layer=item.layer,
                z_index=depth,
                sort_group=item.sort_group,
                rotation=item.rotation,
                scale=scale,
                material=item.material,
                color=item.color,
            )
        )

    def submit_batches(
        self,
        source: BatchSource,
        layer: int,
        z_index: float = 0.0,
        sort_group: int = 0,
    ) -> None:
        """Add batches built elsewhere, drawn at a place in the sort order.

        `source` is called during `flush` with the frame's camera and
        viewport, and its batches are drawn after every sprite sorting at
        or before `(layer, sort_group, z_index)`, and before the rest.
        Batches from one source keep their order; sources at the same
        place keep their submission order.

        Args:
            source: Returns the batches, in screen coordinates.
            layer: The layer to draw them on.
            z_index: Their depth within the layer.
            sort_group: Their sort group within the layer.
        """
        self._sources.append((layer, sort_group, z_index, len(self._sources), source))

    def flush(self, camera: Camera2D, viewport: Viewport | None = None) -> None:
        """Process the frame: Sort -> Batch -> Draw.

        Draws over what the frame already holds: the frame's own clear, a
        colour the scene cleared to, or a scene beneath this one's layer.

        Args:
            camera: The active camera for the scene.
            viewport: Optional custom viewport. If None, uses full screen.
        """
        # 1. Setup Defaults (Optimized)
        if viewport is None:
            # Check if we need to (re)create the default viewport
            # We do this if it doesn't exist OR if the window size changed
            win_w, win_h = self._backend.width, self._backend.height

            if (
                self._default_viewport is None
                or self._default_viewport.width != win_w
                or self._default_viewport.height != win_h
            ):
                self._default_viewport = Viewport.create_fullscreen(win_w, win_h)

            viewport = self._default_viewport

        self._backend.set_viewport(viewport)

        # 2. Sort (Critical for Z-Index / Painter's Algorithm)
        self._queue.sort()

        # 3. Batch (Critical for Performance)
        # The batcher also handles the World->Screen coordinate transform loop
        commands = self._queue.commands
        if self._sources:
            batches = self._merge_sources(commands, camera, viewport)
        else:
            batches = self._batcher.create_batches(commands, camera, viewport)

        # 4. Execute
        self._backend.begin_frame()
        for batch in batches:
            self._backend.render_batch(batch)
        self._backend.end_frame()

        # 5. Cleanup
        # We clear the queue so it's ready for the next frame
        self._queue.clear()
        self._sources.clear()

    def _merge_sources(
        self, commands: list[RenderCommand], camera: Camera2D, viewport: Viewport
    ) -> list[RenderBatch]:
        """Batch the sorted commands with the ready-made batches between them."""
        keys = [(c.layer, c.sort_group, c.z_index) for c in commands]
        batches: list[RenderBatch] = []
        start = 0
        for layer, sort_group, z_index, _, source in sorted(
            self._sources, key=lambda entry: entry[:4]
        ):
            end = bisect_right(keys, (layer, sort_group, z_index), lo=start)
            batches += self._batcher.create_batches(
                commands[start:end], camera, viewport
            )
            batches += source(camera, viewport)
            start = end
        batches += self._batcher.create_batches(commands[start:], camera, viewport)
        return batches
