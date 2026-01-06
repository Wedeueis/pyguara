"""Generic A* pathfinding algorithm implementation."""

import heapq
from typing import Dict, List, Optional, Tuple

from pyguara.ai.pathfinding.core import Graph, Heuristic, Node


class AStarPathfinder:
    """Generic A* solver for any graph type."""

    def find_path(
        self, graph: Graph[Node], start: Node, goal: Node, heuristic: Heuristic[Node]
    ) -> Optional[List[Node]]:
        """
        Calculate the shortest path from start to goal.

        Optimized to reduce heap operations.
        """
        frontier: List[Tuple[float, Node]] = []
        heapq.heappush(frontier, (0, start))

        came_from: Dict[Node, Optional[Node]] = {start: None}
        cost_so_far: Dict[Node, float] = {start: 0.0}

        while frontier:
            _, current = heapq.heappop(frontier)

            if current == goal:
                break

            for next_node in graph.get_neighbors(current):
                new_cost = cost_so_far[current] + graph.cost(current, next_node)

                if next_node not in cost_so_far or new_cost < cost_so_far[next_node]:
                    cost_so_far[next_node] = new_cost
                    priority = new_cost + heuristic.estimate(next_node, goal)
                    heapq.heappush(frontier, (priority, next_node))
                    came_from[next_node] = current

        return self._reconstruct_path(came_from, start, goal)

    def _reconstruct_path(
        self, came_from: Dict[Node, Optional[Node]], start: Node, goal: Node
    ) -> Optional[List[Node]]:
        """Rebuild the path from the came_from map."""
        if goal not in came_from:
            return None

        current: Optional[Node] = goal
        path = []

        while current is not None:
            path.append(current)
            current = came_from[current]

        path.reverse()
        return path
