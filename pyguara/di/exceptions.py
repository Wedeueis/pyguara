"""Custom exceptions for the Dependency Injection system."""

from typing import List, Type


class DIException(Exception):
    """Base exception for all dependency injection errors."""


class CircularDependencyException(DIException):
    """Raised when the container detects a cycle in dependencies."""

    def __init__(self, dependency_chain: List[Type]) -> None:
        """Initialize the exception with the problematic chain.

        Args:
            dependency_chain: List of classes involved in the cycle.
        """
        self.dependency_chain = dependency_chain
        chain_str = " -> ".join([cls.__name__ for cls in dependency_chain])
        super().__init__(f"Circular dependency detected: {chain_str}")


class ServiceNotFoundException(DIException):
    """Raised when requesting a service that has not been registered."""

    def __init__(self, service_type: Type) -> None:
        """Initialize the exception.

        Args:
            service_type: The class type that could not be found.
        """
        super().__init__(f"Service not registered: {service_type.__name__}")
