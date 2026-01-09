from pyguara.graphics.pipeline.queue import RenderQueue
from pyguara.graphics.pipeline.batch import Batcher
from pyguara.graphics.components.camera import Camera2D
from pyguara.graphics.pipeline.viewport import Viewport
from pyguara.graphics.types import RenderCommand
from pyguara.common.types import Vector2


# Mocks
class MockTexture:
    def __init__(self, name):
        self.name = name


def test_queue_sorting():
    queue = RenderQueue()

    t = MockTexture("t")
    # Add unsorted
    queue.push(RenderCommand(t, Vector2(0, 0), layer=10, z_index=5))
    queue.push(RenderCommand(t, Vector2(0, 0), layer=0, z_index=0))
    queue.push(RenderCommand(t, Vector2(0, 0), layer=10, z_index=1))

    queue.sort()

    cmds = queue.commands
    # Layer 0 first
    assert cmds[0].layer == 0
    # Layer 10, Z 1
    assert cmds[1].z_index == 1
    # Layer 10, Z 5
    assert cmds[2].z_index == 5


def test_batcher_logic():
    batcher = Batcher()
    camera = Camera2D(800, 600)
    viewport = Viewport(0, 0, 800, 600)

    t1 = MockTexture("t1")
    t2 = MockTexture("t2")

    cmds = [
        RenderCommand(t1, Vector2(0, 0), 0, 0),
        RenderCommand(t1, Vector2(10, 10), 0, 0),
        RenderCommand(t2, Vector2(20, 20), 0, 0),  # Break batch
        RenderCommand(t1, Vector2(30, 30), 0, 0),  # New batch
    ]

    batches = batcher.create_batches(cmds, camera, viewport)

    assert len(batches) == 3
    assert batches[0].texture == t1
    assert len(batches[0].destinations) == 2

    assert batches[1].texture == t2
    assert len(batches[1].destinations) == 1

    assert batches[2].texture == t1
    assert len(batches[2].destinations) == 1


def test_camera_world_to_screen():
    cam = Camera2D(800, 600)  # Center is 400, 300
    cam.position = Vector2(0, 0)  # Camera at world origin

    # Point at world origin should be at screen center
    screen_pos = cam.world_to_screen(Vector2(0, 0))
    assert screen_pos == Vector2(400, 300)

    # Point at (100, 0) -> (500, 300)
    screen_pos = cam.world_to_screen(Vector2(100, 0))
    assert screen_pos == Vector2(500, 300)

    # Zoom
    cam.zoom = 2.0
    screen_pos = cam.world_to_screen(Vector2(100, 0))
    # Relative 100 * 2 = 200. Center 400. Result 600.
    assert screen_pos.x == 600


def test_viewport_aspect_ratio():
    # 100x100 window, target 2.0 (should be 100x50)
    vp = Viewport.create_best_fit(100, 100, 2.0)

    assert vp.width == 100
    assert vp.height == 50
    assert vp.y == 25  # Centered vertically (offset)

    # 100x100 window, target 0.5 (should be 50x100)
    vp = Viewport.create_best_fit(100, 100, 0.5)
    assert vp.width == 50
    assert vp.height == 100
    assert vp.x == 25  # Centered horizontally
