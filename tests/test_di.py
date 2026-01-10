import pytest
from typing import Protocol, TYPE_CHECKING
from pyguara.di.exceptions import (
    ServiceNotFoundException,
    CircularDependencyException,
    DIException,
)

if TYPE_CHECKING:
    from pyguara.di.container import DIContainer


class IService(Protocol):
    def do_work(self) -> str: ...


class ServiceImpl:
    def do_work(self) -> str:
        return "work"


class ServiceWithDep:
    def __init__(self, service: IService):
        self.service = service


class CircularA:
    def __init__(self, b: "CircularB"):
        pass


class CircularB:
    def __init__(self, a: "CircularA"):
        pass


class DisposableService:
    def __init__(self) -> None:
        self.disposed = False

    def dispose(self) -> None:
        self.disposed = True


def test_singleton_registration(container: DIContainer) -> None:
    container.register_singleton(IService, ServiceImpl)  # type: ignore[type-abstract]

    s1 = container.get(IService)  # type: ignore[type-abstract]
    s2 = container.get(IService)  # type: ignore[type-abstract]

    assert isinstance(s1, ServiceImpl)
    assert s1 is s2  # Same instance


def test_transient_registration(container: DIContainer) -> None:
    container.register_transient(IService, ServiceImpl)  # type: ignore[type-abstract]

    s1 = container.get(IService)  # type: ignore[type-abstract]
    s2 = container.get(IService)  # type: ignore[type-abstract]

    assert isinstance(s1, ServiceImpl)
    assert s1 is not s2  # Different instances


def test_dependency_resolution(container: DIContainer) -> None:
    container.register_singleton(IService, ServiceImpl)  # type: ignore[type-abstract]
    container.register_transient(ServiceWithDep, ServiceWithDep)

    dependent = container.get(ServiceWithDep)
    assert isinstance(dependent.service, ServiceImpl)


def test_scoped_resolution(container: DIContainer) -> None:
    """Test scoped service resolution within different scopes."""
    container.register_scoped(IService, ServiceImpl)  # type: ignore[type-abstract]

    # Scoped services require an active scope
    with pytest.raises(DIException):
        container.get(IService)  # type: ignore[type-abstract]

    # Within a scope, the same instance is returned
    with container.create_scope() as scope:
        s1 = scope.get(IService)  # type: ignore[type-abstract]
        s2 = scope.get(IService)  # type: ignore[type-abstract]
        assert isinstance(s1, ServiceImpl)
        assert s1 is s2  # Same instance within scope

    # Different scope returns different instance
    with container.create_scope() as scope2:
        s3 = scope2.get(IService)  # type: ignore[type-abstract]
        assert isinstance(s3, ServiceImpl)
        assert s1 is not s3  # Different instance in different scope


def test_circular_dependency(container: DIContainer) -> None:
    container.register_transient(CircularA, CircularA)
    container.register_transient(CircularB, CircularB)

    with pytest.raises(CircularDependencyException):
        container.get(CircularA)


def test_service_not_found(container: DIContainer) -> None:
    with pytest.raises(ServiceNotFoundException):
        container.get(str)  # Random type


def test_scope_disposal(container: DIContainer) -> None:
    """Test that scoped services are properly disposed when scope ends."""
    container.register_scoped(DisposableService, DisposableService)

    scope = container.create_scope()
    service = scope.get(DisposableService)

    assert not service.disposed
    scope.dispose()
    assert service.disposed


def test_scope_resolves_singleton_correctly(container: DIContainer) -> None:
    """Test that singletons resolved via scope return the global instance."""
    container.register_singleton(IService, ServiceImpl)  # type: ignore[type-abstract]

    # Get singleton from container
    singleton_instance = container.get(IService)  # type: ignore[type-abstract]

    # Get same singleton from scope
    with container.create_scope() as scope:
        scoped_singleton = scope.get(IService)  # type: ignore[type-abstract]
        assert scoped_singleton is singleton_instance  # Same global instance

    # Get from another scope - still same instance
    with container.create_scope() as scope2:
        another_scoped_singleton = scope2.get(IService)  # type: ignore[type-abstract]
        assert another_scoped_singleton is singleton_instance


def test_scope_resolves_transient_correctly(container: DIContainer) -> None:
    """Test that transients resolved via scope create new instances."""
    container.register_transient(IService, ServiceImpl)  # type: ignore[type-abstract]

    with container.create_scope() as scope:
        t1 = scope.get(IService)  # type: ignore[type-abstract]
        t2 = scope.get(IService)  # type: ignore[type-abstract]
        assert isinstance(t1, ServiceImpl)
        assert isinstance(t2, ServiceImpl)
        assert t1 is not t2  # Transients always create new instances


def test_scope_mixed_lifetimes(container: DIContainer) -> None:
    """Test resolving services with mixed lifetimes from a scope."""
    # Setup different lifetimes
    container.register_singleton(IService, ServiceImpl)  # type: ignore[type-abstract]

    class ScopedService:
        def __init__(self, service: IService):
            self.service = service

    container.register_scoped(ScopedService, ScopedService)

    # Get singleton outside scope
    singleton = container.get(IService)  # type: ignore[type-abstract]

    # Resolve scoped service that depends on singleton
    with container.create_scope() as scope:
        scoped = scope.get(ScopedService)
        assert scoped.service is singleton  # Scoped service gets global singleton

        # Verify scoped service is reused within scope
        scoped2 = scope.get(ScopedService)
        assert scoped2 is scoped


def test_scope_context_manager_cleanup(container: DIContainer) -> None:
    """Test that scope automatically disposes resources when used as context manager."""
    container.register_scoped(DisposableService, DisposableService)

    service = None
    with container.create_scope() as scope:
        service = scope.get(DisposableService)
        assert not service.disposed

    # After exiting context, service should be disposed
    assert service.disposed
