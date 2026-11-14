"""Open a window on the wgpu backend and say what a frame costs.

    uv run python tools/wgpu_probe.py
    uv run python tools/wgpu_probe.py --shapes 4000 --vsync

Prints which adapter and API wgpu chose, whether it is drawing straight to
the window or copying each frame to it, and the cost of a frame split into
its three parts. Then draws the same frame with pygame's software renderer
for comparison.

**Run this on the machine the game will ship on.** The figures are the
driver's, not the engine's: on WSL, wgpu has only OpenGL translated to
Direct3D 12 and a frame costs about 10 ms whatever is in it, while pygame's
software fill costs under 2 ms. That says nothing about DX12 on Windows
itself, which is the number that decides whether this backend is used.
"""

from __future__ import annotations

import argparse
import time

import pygame

from pyguara import native
from pyguara.graphics.backends.wgpu.window import native_window

WIDTH, HEIGHT = 1280, 720


def mean_ms(samples: list[float]) -> float:
    """Mean of the samples after warm-up, in milliseconds."""
    kept = samples[20:]
    return sum(kept) / len(kept) * 1000


def main() -> None:
    """Run the probe."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--shapes", type=int, default=400)
    parser.add_argument("--frames", type=int, default=300)
    parser.add_argument("--vsync", action="store_true")
    arguments = parser.parse_args()

    pygame.init()
    screen = pygame.display.set_mode((WIDTH, HEIGHT))
    pygame.display.set_caption("pyguara wgpu probe")
    extension = native.require_extension("tools/wgpu_probe.py")
    handle = native_window()
    print(f"SDL driver: {pygame.display.get_driver()}; native window: {handle}")
    if handle is None:
        gpu = extension.NativeGpu(WIDTH, HEIGHT)
    else:
        gpu = extension.NativeGpu.for_window(*handle, WIDTH, HEIGHT, arguments.vsync)
    print(f"adapter: {gpu.adapter}; drawing to the window: {gpu.has_surface}")

    push: list[float] = []
    render: list[float] = []
    present: list[float] = []
    for frame in range(arguments.frames):
        pygame.event.pump()
        start = time.perf_counter()
        gpu.clear(18, 20, 30, 255)
        for index in range(arguments.shapes):
            gpu.rect(
                (index * 37 + frame * 3) % (WIDTH - 20),
                (index * 53) % (HEIGHT - 20),
                18, 18, 255, 120 + index % 100, 40, 255,
            )  # fmt: skip
        pushed = time.perf_counter()
        gpu.end_frame()
        rendered = time.perf_counter()
        if gpu.has_surface:
            gpu.present()
        else:
            image = pygame.image.frombuffer(gpu.read_pixels(), (WIDTH, HEIGHT), "RGBA")
            screen.blit(image, (0, 0))
            pygame.display.flip()
        shown = time.perf_counter()
        push.append(pushed - start)
        render.append(rendered - pushed)
        present.append(shown - rendered)
    total = mean_ms(push) + mean_ms(render) + mean_ms(present)
    print(
        f"wgpu, {arguments.shapes} rectangles at {WIDTH}x{HEIGHT}: "
        f"{total:.2f} ms a frame = push {mean_ms(push):.2f} + "
        f"render {mean_ms(render):.2f} + present {mean_ms(present):.2f}"
    )

    software: list[float] = []
    for frame in range(min(arguments.frames, 120)):
        pygame.event.pump()
        start = time.perf_counter()
        screen.fill((18, 20, 30))
        for index in range(arguments.shapes):
            pygame.draw.rect(
                screen,
                (255, 120 + index % 100, 40),
                (
                    (index * 37 + frame * 3) % (WIDTH - 20),
                    (index * 53) % (HEIGHT - 20),
                    18,
                    18,
                ),
            )
        pygame.display.flip()
        software.append(time.perf_counter() - start)
    print(f"pygame software, the same frame: {mean_ms(software):.2f} ms")
    pygame.quit()


if __name__ == "__main__":
    main()
