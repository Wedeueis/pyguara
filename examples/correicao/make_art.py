"""Draw Correição's sprites and write them as PNG files.

    uv run python -m examples.correicao.make_art

The art is drawn here, pixel by pixel, rather than painted, so the demo
ships nothing it did not make. Writing PNG needs only `zlib` and `struct`,
which keeps this script free of any image library.
"""

from __future__ import annotations

import math
import struct
import zlib
from pathlib import Path

Pixel = tuple[int, int, int, int]
Image = list[list[Pixel]]

ASSETS = Path(__file__).resolve().parent / "assets"
CLEAR: Pixel = (0, 0, 0, 0)


def blank(width: int, height: int) -> Image:
    """Return a fully transparent image."""
    return [[CLEAR] * width for _ in range(height)]


def put(image: Image, x: int, y: int, color: Pixel) -> None:
    """Set one pixel, ignoring any outside the image."""
    if 0 <= y < len(image) and 0 <= x < len(image[0]):
        image[y][x] = color


def ellipse(
    image: Image, cx: float, cy: float, rx: float, ry: float, color: Pixel
) -> None:
    """Fill an axis-aligned ellipse."""
    for y in range(len(image)):
        for x in range(len(image[0])):
            if ((x + 0.5 - cx) / rx) ** 2 + ((y + 0.5 - cy) / ry) ** 2 <= 1.0:
                image[y][x] = color


def write_png(path: Path, image: Image) -> None:
    """Write `image` as an 8-bit RGBA PNG."""
    height, width = len(image), len(image[0])
    raw = b"".join(b"\x00" + bytes(c for px in row for c in px) for row in image)

    def chunk(kind: bytes, data: bytes) -> bytes:
        body = kind + data
        return struct.pack(">I", len(data)) + body + struct.pack(">I", zlib.crc32(body))

    header = struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)
    path.write_bytes(
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", header)
        + chunk(b"IDAT", zlib.compress(raw, 9))
        + chunk(b"IEND", b"")
    )


def ant(frame: int) -> Image:
    """An army ant seen from above, head to the right; `frame` swaps the legs."""
    body: Pixel = (120, 38, 22, 255)
    dark: Pixel = (70, 20, 12, 255)
    image = blank(16, 12)
    ellipse(image, 3.5, 6, 3.0, 2.4, body)  # gaster
    ellipse(image, 8, 6, 1.8, 1.4, body)  # thorax
    ellipse(image, 12, 6, 2.2, 2.0, dark)  # head
    put(image, 14, 4, dark)  # mandibles
    put(image, 15, 3, dark)
    put(image, 14, 8, dark)
    put(image, 15, 9, dark)
    lean = 1 if frame else -1
    for i, x in enumerate((6, 8, 10)):
        sway = lean if i % 2 == 0 else -lean
        for side in (-1, 1):
            put(image, x, 6 + 2 * side, dark)
            put(image, x + sway, 6 + 3 * side, dark)
            put(image, x + 2 * sway, 6 + 4 * side, dark)
    return image


def calango(frame: int) -> Image:
    """A striped lizard from above, head to the right; `frame` curls the tail."""
    green: Pixel = (92, 156, 64, 255)
    stripe: Pixel = (232, 214, 120, 255)
    dark: Pixel = (40, 74, 30, 255)
    image = blank(32, 20)
    ellipse(image, 16, 10, 7, 4, green)
    ellipse(image, 25, 10, 3.6, 3.0, green)
    for x in range(11, 22):
        put(image, x, 9, stripe)
        put(image, x, 11, stripe)
    put(image, 27, 9, dark)
    put(image, 27, 11, dark)
    bend = 1.5 if frame else -1.5
    for step in range(10):
        x = 9 - step
        y = 10 + bend * math.sin(step / 3.0)
        put(image, x, round(y), green)
        if step < 5:
            put(image, x, round(y) + 1, green)
    for index, (x, side) in enumerate(((12, -1), (12, 1), (20, -1), (20, 1))):
        reach = 1 if (index + frame) % 2 else -1
        for step in range(3):
            put(image, x + reach * step, 10 + side * (4 + step), dark)
    return image


def tuft() -> Image:
    """A clump of dry caatinga grass."""
    blade: Pixel = (170, 150, 80, 255)
    image = blank(12, 10)
    for x0, lean in ((3, -1), (5, 0), (7, 1), (9, 1), (6, -1)):
        for step in range(7):
            put(image, x0 + (lean * step) // 3, 9 - step, blade)
    return image


def stone() -> Image:
    """A pale stone with a shadow."""
    image = blank(12, 9)
    ellipse(image, 6.5, 5.5, 5, 3, (90, 80, 70, 255))
    ellipse(image, 6, 4.5, 4.5, 2.8, (176, 166, 150, 255))
    return image


SPRITES = {
    "ant_0": ant(0),
    "ant_1": ant(1),
    "calango_0": calango(0),
    "calango_1": calango(1),
    "tuft": tuft(),
    "stone": stone(),
}


def main() -> None:
    """Write every sprite under `assets/`."""
    ASSETS.mkdir(exist_ok=True)
    for name, image in SPRITES.items():
        write_png(ASSETS / f"{name}.png", image)


if __name__ == "__main__":
    main()
