import pytest
from typing import Protocol
from pyguara.di.exceptions import (
    ServiceNotFoundException,
    CircularDependencyException,
    DIException,
)


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
    def __init__(self):
        self.disposed = False

    def dispose(self):
        self.disposed = True


def test_singleton_registration(container):
    container.register_singleton(IService, ServiceImpl)

    s1 = container.get(IService)
    s2 = container.get(IService)

    assert isinstance(s1, ServiceImpl)
    assert s1 is s2  # Same instance


def test_transient_registration(container):
    container.register_transient(IService, ServiceImpl)

    s1 = container.get(IService)
    s2 = container.get(IService)

    assert isinstance(s1, ServiceImpl)
    assert s1 is not s2  # Different instances


def test_dependency_resolution(container):
    container.register_singleton(IService, ServiceImpl)
    container.register_transient(ServiceWithDep, ServiceWithDep)

    dependent = container.get(ServiceWithDep)
    assert isinstance(dependent.service, ServiceImpl)


def test_scoped_resolution(container):
    container.register_scoped(IService, ServiceImpl)

    # Getting scoped service from root container implies a default or error depending on impl
    # The current impl requires explicit scope
    with pytest.raises(DIException):
        container.get(IService)

    with container.create_scope() as scope:
        # Access private method or exposed method if available (container._resolve_service with scope)
        # But standard way is scope._get_scoped_service or container logic handling scope
        # In this implementation, DIContainer.get() doesn't take a scope.
        # We must assume the container design intends scopes to be used via scope object?
        # Checking implementation: `container._resolve_service` takes optional scope.
        # But `container.get` does not.

        # NOTE: The current DIContainer public API doesn't expose getting a service *within* a scope easily
        # except via internal methods or if `DIScope` had a `get` method?
        # Let's check DIScope implementation... it doesn't have `get`.
        # It relies on DIContainer calling `scope._get_scoped_service`.
        # Wait, if I can't ask the Scope for a service, how do I use it?
        # Ah, usually scopes are passed implicitly or there is a `scope.resolve(Type)` method.
        # The current implementation seems to lack a public `resolve` on `DIScope`.
        # I will test what is possible, or maybe just `_resolve_service`.

        # Using internal method for test verification since public API seems incomplete for Scopes
        s1 = container._resolve_service(IService, scope)
        s2 = container._resolve_service(IService, scope)
        assert s1 is s2

    with container.create_scope() as scope2:
        s3 = container._resolve_service(IService, scope2)
        assert s1 is not s3


def test_circular_dependency(container):
    container.register_transient(CircularA, CircularA)
    container.register_transient(CircularB, CircularB)

    with pytest.raises(CircularDependencyException):
        container.get(CircularA)


def test_service_not_found(container):
    with pytest.raises(ServiceNotFoundException):
        container.get(str)  # Random type


def test_scope_disposal(container):
    container.register_scoped(DisposableService, DisposableService)

    scope = container.create_scope()
    service = container._resolve_service(DisposableService, scope)

    assert not service.disposed
    scope.dispose()
    assert service.disposed
