"""Core abstractions for pathfinding protocols."""

from typing import Protocol, Iterator, TypeVar, Hashable

# Generic type for a Node (invariant for Graphs as they produce and consume)
Node = TypeVar("Node", bound=Hashable)

# Contravariant type for Heuristics (they only consume nodes)
NodeContra = TypeVar("NodeContra", bound=Hashable, contravariant=True)


class Graph(Protocol[Node]):
    """Interface for a navigation graph."""

    def get_neighbors(self, node: Node) -> Iterator[Node]:
        """Yield the neighbors of the given node."""
        ...

    def cost(self, from_node: Node, to_node: Node) -> float:
        """Calculate the movement cost between two adjacent nodes."""
        ...


class Heuristic(Protocol[NodeContra]):
    """Interface for heuristic functions."""

    def estimate(self, current: NodeContra, goal: NodeContra) -> float:
        """Estimate the remaining cost to the goal (h_score)."""
        ...
