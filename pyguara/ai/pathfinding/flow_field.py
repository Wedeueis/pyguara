"""Multi-source Dijkstra cost maps and flow fields.

`dijkstra_map` answers "how far is every reachable node from the nearest of
these goals" in one sweep -- the substrate a horde of enemies, units
converging on a rally point, or a tower's targeting all want without each
running its own A* search. `flow_field` turns that cost map into a
per-node "which neighbor gets me closer" lookup, so an agent following it
does one dict lookup a tick instead of a search.

Generic over any `Graph[Node]`, exactly like `AStarPathfinder` -- a grid is
the common case, but nothing here assumes one.
"""

from __future__ import annotations

import heapq
from collections.abc import Iterable
from itertools import count

from pyguara.ai.pathfinding.core import Graph, Node


def dijkstra_map(
    graph: Graph[Node], goals: Iterable[Node], max_cost: float | None = None
) -> dict[Node, float]:
    """Return the cost from every reachable node to its nearest goal.

    A multi-source Dijkstra sweep seeded with every goal at cost 0, rather
    than one single-source search per goal -- the same total work either
    way, but one sweep instead of `len(goals)` of them.

    Args:
        graph: The graph to search.
        goals: Nodes to measure distance to. Each is seeded at cost 0.
        max_cost: Stop expanding past this cost, if given. A node only
            reachable at a higher cost is left out of the result entirely
            rather than included at some inflated value -- useful for
            capping the search to "everything within N of a rally point"
            when the far side of a large map is irrelevant this tick.

    Returns:
        Every reached node's cost to its nearest goal, including the goals
        themselves at 0.
    """
    counter = count()
    frontier: list[tuple[float, int, Node]] = []
    cost_so_far: dict[Node, float] = {}

    for goal in goals:
        cost_so_far[goal] = 0.0
        heapq.heappush(frontier, (0.0, next(counter), goal))

    while frontier:
        cost, _, current = heapq.heappop(frontier)
        if cost > cost_so_far[current]:
            continue  # a cheaper route to `current` was already processed

        for next_node in graph.get_neighbors(current):
            new_cost = cost + graph.cost(current, next_node)
            if max_cost is not None and new_cost > max_cost:
                continue
            if next_node not in cost_so_far or new_cost < cost_so_far[next_node]:
                cost_so_far[next_node] = new_cost
                heapq.heappush(frontier, (new_cost, next(counter), next_node))

    return cost_so_far


def flow_field(
    graph: Graph[Node], cost_map: dict[Node, float]
) -> dict[Node, Node | None]:
    """Return each node's steepest-descent neighbor toward its nearest goal.

    Args:
        graph: The same graph `cost_map` was computed over.
        cost_map: A `dijkstra_map()` result.

    Returns:
        For every node in `cost_map`, the neighbor with the lowest cost, if
        any neighbor is cheaper than the node itself -- following it one
        step at a time reaches a goal along a shortest path. `None` when no
        neighbor is cheaper: the node is already a goal, or is a local
        minimum a `max_cost` cutoff left stranded short of a true goal.
    """
    result: dict[Node, Node | None] = {}
    for node, node_cost in cost_map.items():
        best_neighbor: Node | None = None
        best_cost = node_cost
        for neighbor in graph.get_neighbors(node):
            neighbor_cost = cost_map.get(neighbor)
            if neighbor_cost is not None and neighbor_cost < best_cost:
                best_cost = neighbor_cost
                best_neighbor = neighbor
        result[node] = best_neighbor
    return result
