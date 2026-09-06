"""Core abstractions for pathfinding protocols."""

from collections.abc import Hashable, Iterator
from typing import Protocol, TypeVar, runtime_checkable

# Generic type for a Node (invariant for Graphs as they produce and consume)
Node = TypeVar("Node", bound=Hashable)

# Contravariant type for Heuristics (they only consume nodes)
NodeContra = TypeVar("NodeContra", bound=Hashable, contravariant=True)


@runtime_checkable
class Graph(Protocol[Node]):
    """Interface for a navigation graph."""

    def get_neighbors(self, node: Node) -> Iterator[Node]:
        """Yield the neighbors of the given node."""
        ...

    def cost(self, from_node: Node, to_node: Node) -> float:
        """Calculate the movement cost between two adjacent nodes."""
        ...


@runtime_checkable
class Heuristic(Protocol[NodeContra]):
    """Interface for heuristic functions."""

    def estimate(self, current: NodeContra, goal: NodeContra) -> float:
        """Estimate the remaining cost to the goal (h_score)."""
        ...
