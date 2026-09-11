"""Graph-based layout generation: scattered points connected into a graph.

A second alternative to `bsp.py`'s space-partitioning approach to the same
problem -- "RTS map-gen and TD path-gen are others on the same algos" (#28)
applies here too: points and edges are genre-agnostic, with no "room" or
"node type" vocabulary. Placing points under a minimum-spacing or other
rule (Poisson-disc-style feature scattering, frequency/dependency rules)
is `constraint-placement`, a separate deferred algorithm family --
`scatter_points()` here is a plain uniform scatter, nothing more.
"""

from __future__ import annotations

import math
from collections.abc import Sequence

from pyguara.common.random import RandomStream
from pyguara.common.types import Rect, Vector2

Edge = tuple[int, int]


def scatter_points(bounds: Rect, count: int, rng: RandomStream) -> list[Vector2]:
    """Return `count` points uniformly distributed within `bounds`.

    No minimum-spacing guarantee -- points may land arbitrarily close
    together, even coincide. A spacing constraint belongs to
    `constraint-placement`, not this function.
    """
    return [
        Vector2(
            rng.uniform(bounds.left, bounds.right),
            rng.uniform(bounds.top, bounds.bottom),
        )
        for _ in range(count)
    ]


def build_graph(
    points: Sequence[Vector2],
    rng: RandomStream,
    extra_edge_chance: float = 0.15,
    extra_edge_max_distance: float | None = None,
) -> list[Edge]:
    """Connect `points` into a graph: a spanning tree plus a few loop edges.

    First builds a minimum spanning tree by Euclidean distance (Prim's
    algorithm), guaranteeing every point is reachable from every other --
    the shape a roguelike level graph, RTS influence graph, or TD path
    network all need. Then rolls each remaining pair independently at
    `extra_edge_chance` to add loops, optionally restricted to pairs
    within `extra_edge_max_distance` so loops stay local instead of
    cutting across the whole map.

    Args:
        points: Node positions. Order fixes each point's index (0-based)
            -- edges reference points by that index.
        rng: Seeded stream driving the loop-edge rolls. The spanning tree
            itself is deterministic given `points`' order alone.
        extra_edge_chance: Probability of keeping each non-tree pair as an
            extra edge. 0.0 returns a pure spanning tree (the fewest
            possible edges that stay connected); higher values add loops.
        extra_edge_max_distance: Only pairs at or under this distance are
            candidates for an extra edge. `None` (the default) considers
            every pair.

    Returns:
        Edges as `(i, j)` index pairs into `points`, `i < j`, spanning
        tree edges first, then any extra edges sorted by distance. Empty
        if `points` has fewer than 2 entries.
    """
    n = len(points)
    if n < 2:
        return []

    in_tree = {0}
    tree_edges: list[Edge] = []
    while len(in_tree) < n:
        best: Edge | None = None
        best_distance = math.inf
        for i in sorted(in_tree):
            for j in range(n):
                if j in in_tree:
                    continue
                distance = points[i].distance_to(points[j])
                if distance < best_distance:
                    best_distance = distance
                    best = (i, j)
        assert best is not None  # n >= 2 and in_tree != full set here
        tree_edges.append((min(best), max(best)))
        in_tree.add(best[1])

    tree_edge_set = set(tree_edges)
    candidates: list[tuple[float, Edge]] = []
    for i in range(n):
        for j in range(i + 1, n):
            edge = (i, j)
            if edge in tree_edge_set:
                continue
            distance = points[i].distance_to(points[j])
            if (
                extra_edge_max_distance is not None
                and distance > extra_edge_max_distance
            ):
                continue
            candidates.append((distance, edge))
    candidates.sort(key=lambda pair: (pair[0], pair[1]))

    extra_edges = [edge for _, edge in candidates if rng.random() < extra_edge_chance]

    return tree_edges + extra_edges
