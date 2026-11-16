"""Turn a UI polygon into triangles for the GPU.

The wgpu UI renderer draws a polygon as one native `mesh` step: its
fill triangulated by ear clipping, its outline as one ring of mitred
quads, so a translucent outline is blended once at its corners.

Vertices are placed on pixel centres, where pygame's own edges run, so
the two renderers agree inside a polygon and differ slightly along its
edges.
"""

from __future__ import annotations

import math
import struct

Point = tuple[float, float]

MITER_LIMIT = 4.0
"""How far a corner's miter may reach, in half-widths, before it is cut.

A sharp corner's miter grows without bound -- at 10 degrees it is eleven
half-widths long -- and draws a spike. Past the limit the corner is
bevelled instead."""


def _signed_area(points: list[Point]) -> float:
    total = 0.0
    for i, (x1, y1) in enumerate(points):
        x2, y2 = points[(i + 1) % len(points)]
        total += x1 * y2 - x2 * y1
    return total / 2.0


def _cross(o: Point, a: Point, b: Point) -> float:
    return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])


def _inside(p: Point, a: Point, b: Point, c: Point) -> bool:
    """Whether `p` is in triangle `abc` (positively wound), edges included."""
    return _cross(a, b, p) >= 0 and _cross(b, c, p) >= 0 and _cross(c, a, p) >= 0


def _without_repeats(points: list[Point]) -> list[Point]:
    out: list[Point] = []
    for point in points:
        if not out or point != out[-1]:
            out.append(point)
    if len(out) > 1 and out[0] == out[-1]:
        out.pop()
    return out


def triangulate(points: list[Point]) -> list[tuple[int, int, int]]:
    """Split a polygon into triangles by ear clipping.

    Handles any simple polygon, convex or not, in either winding. A
    self-intersecting one has no ears to clip once it tangles, so the
    remainder is fanned from its first corner -- what a convex polygon
    would get anyway.

    Args:
        points: The corners, in order.

    Returns:
        Triangles as indices into `points`.
    """
    count = len(points)
    if count < 3:
        return []
    order = list(range(count))
    if _signed_area(points) < 0:
        # Ears are found on a positively wound ring; only consistency matters.
        order.reverse()
    triangles: list[tuple[int, int, int]] = []
    guard = 0
    while len(order) > 3 and guard < count * count:
        guard += 1
        clipped = False
        size = len(order)
        for k in range(size):
            i, j, m = order[k - 1], order[k], order[(k + 1) % size]
            a, b, c = points[i], points[j], points[m]
            if _cross(a, b, c) <= 0:
                continue  # reflex or flat: not an ear
            if any(
                _inside(points[other], a, b, c)
                for other in order
                if other not in (i, j, m) and points[other] not in (a, b, c)
            ):
                continue
            triangles.append((i, j, m))
            del order[k]
            clipped = True
            break
        if not clipped:
            break
    # Whatever is left: three corners, or a tangle that had no ear.
    triangles.extend(
        (order[0], order[k], order[k + 1]) for k in range(1, len(order) - 1)
    )
    return triangles


def _normal(a: Point, b: Point) -> Point:
    dx, dy = b[0] - a[0], b[1] - a[1]
    length = math.hypot(dx, dy) or 1.0
    return -dy / length, dx / length


def outline_ring(
    points: list[Point], width: float
) -> tuple[list[Point], list[tuple[int, int, int]]]:
    """Build a closed outline `width` thick, centred on the polygon's edges.

    Each corner gets an inner and an outer point along its miter, cut back
    to `MITER_LIMIT` at a sharp corner, and consecutive corners are joined
    by two triangles. The ring does not overlap itself at its corners.

    Args:
        points: The corners, in order.
        width: The thickness in pixels.

    Returns:
        `(vertices, triangles)`.
    """
    ring = _without_repeats(points)
    count = len(ring)
    if count < 2 or width <= 0:
        return [], []
    half = width / 2.0
    vertices: list[Point] = []
    for i in range(count):
        before, here, after = ring[i - 1], ring[i], ring[(i + 1) % count]
        n1, n2 = _normal(before, here), _normal(here, after)
        mx, my = n1[0] + n2[0], n1[1] + n2[1]
        length = math.hypot(mx, my)
        if length < 1e-9:
            # The edge doubles back: offset along the incoming normal.
            mx, my, scale = n1[0], n1[1], half
        else:
            mx, my = mx / length, my / length
            cosine = mx * n1[0] + my * n1[1]
            scale = min(half / max(cosine, 1e-9), half * MITER_LIMIT)
        vertices.append((here[0] + mx * scale, here[1] + my * scale))
        vertices.append((here[0] - mx * scale, here[1] - my * scale))
    triangles: list[tuple[int, int, int]] = []
    for i in range(count):
        j = (i + 1) % count
        outer_i, inner_i, outer_j, inner_j = 2 * i, 2 * i + 1, 2 * j, 2 * j + 1
        triangles.append((outer_i, outer_j, inner_i))
        triangles.append((inner_i, outer_j, inner_j))
    return vertices, triangles


_VERTEX = struct.Struct("<ffffBBBB")


def polygon_mesh(
    points: list[tuple[int, int]],
    width: int,
    color: tuple[int, int, int, int],
) -> tuple[bytes, bytes, int]:
    """Build the `NativeGpu.mesh` buffers for a filled or outlined polygon.

    Args:
        points: The corners, in pixels.
        width: 0 fills; more draws a closed outline that thick.
        color: RGBA.

    Returns:
        `(vertices, indices, index count)`: 20-byte vertices (position,
        uv, colour) and u32 indices, as the mesh step reads them.
    """
    # Pixel centres: pygame's edges run through them.
    corners = [(x + 0.5, y + 0.5) for x, y in points]
    if width <= 0:
        vertices, triangles = corners, triangulate(corners)
    else:
        vertices, triangles = outline_ring(corners, float(width))
    red, green, blue, alpha = color
    vertex_bytes = b"".join(
        _VERTEX.pack(x, y, 0.5, 0.5, red, green, blue, alpha) for x, y in vertices
    )
    flat = [index for triangle in triangles for index in triangle]
    return vertex_bytes, struct.pack(f"<{len(flat)}I", *flat), len(flat)
