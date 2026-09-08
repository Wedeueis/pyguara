"""Generic A* pathfinding algorithm implementation."""

import heapq
from itertools import count

from pyguara.ai.pathfinding.core import Graph, Heuristic, Node


class AStarPathfinder:
    """Generic A* solver for any graph type."""

    def find_path(
        self, graph: Graph[Node], start: Node, goal: Node, heuristic: Heuristic[Node]
    ) -> list[Node] | None:
        """
        Calculate the shortest path from start to goal.

        Optimized to reduce heap operations.
        """
        # The monotonic tie-breaker is load-bearing, not cosmetic: on a
        # priority tie heapq compares the next tuple element, and Node is only
        # bound to Hashable -- an arbitrary graph node need not be
        # order-comparable, so (priority, node) tuples raise TypeError. The
        # counter is always distinct, so the node is never compared.
        counter = count()
        frontier: list[tuple[float, int, Node]] = []
        heapq.heappush(frontier, (0.0, next(counter), start))

        came_from: dict[Node, Node | None] = {start: None}
        cost_so_far: dict[Node, float] = {start: 0.0}

        while frontier:
            _, _, current = heapq.heappop(frontier)

            if current == goal:
                break

            for next_node in graph.get_neighbors(current):
                new_cost = cost_so_far[current] + graph.cost(current, next_node)

                if next_node not in cost_so_far or new_cost < cost_so_far[next_node]:
                    cost_so_far[next_node] = new_cost
                    priority = new_cost + heuristic.estimate(next_node, goal)
                    heapq.heappush(frontier, (priority, next(counter), next_node))
                    came_from[next_node] = current

        return self._reconstruct_path(came_from, start, goal)

    def _reconstruct_path(
        self, came_from: dict[Node, Node | None], start: Node, goal: Node
    ) -> list[Node] | None:
        """Rebuild the path from the came_from map."""
        if goal not in came_from:
            return None

        current: Node | None = goal
        path = []

        while current is not None:
            path.append(current)
            current = came_from[current]

        path.reverse()
        return path
