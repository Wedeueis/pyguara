import pytest
from typing import Protocol, runtime_checkable
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


def test_singleton_registration(container) -> None:
    container.register_singleton(IService, ServiceImpl)

    s1 = container.get(IService)
    s2 = container.get(IService)

    assert isinstance(s1, ServiceImpl)
    assert s1 is s2  # Same instance


def test_transient_registration(container) -> None:
    container.register_transient(IService, ServiceImpl)

    s1 = container.get(IService)
    s2 = container.get(IService)

    assert isinstance(s1, ServiceImpl)
    assert s1 is not s2  # Different instances


@runtime_checkable
class ICheckedService(Protocol):
    """A @runtime_checkable protocol, distinct from IService, scoped to the
    register_instance() runtime safety check tests (wayfinder ticket 33)."""

    def do_work(self) -> str: ...


class WrongImpl:
    """Missing do_work() entirely -- does not structurally satisfy ICheckedService."""

    def unrelated(self) -> None:
        pass


def test_register_instance_rejects_structurally_mismatched_protocol(container) -> None:
    """register_instance() must reject an instance that doesn't structurally
    satisfy a @runtime_checkable protocol interface."""
    with pytest.raises(DIException):
        container.register_instance(ICheckedService, WrongImpl())


def test_register_instance_accepts_structurally_matching_protocol(container) -> None:
    """No false positive: a real match still registers and resolves."""
    container.register_instance(ICheckedService, ServiceImpl())

    assert container.get(ICheckedService).do_work() == "work"


def test_register_instance_does_not_check_non_protocol_interfaces(container) -> None:
    """Concrete-class interfaces are never isinstance-checked -- at least one
    real caller (BOOT-1's Pygame RenderGraph stub, application.py) deliberately
    registers an instance that is *not* a real subclass of its interface,
    branched on by identity elsewhere rather than treated as a genuine one."""

    class Base:
        pass

    class Unrelated:
        pass

    container.register_instance(Base, Unrelated())  # must not raise

    assert isinstance(container.get(Base), Unrelated)


def test_dependency_resolution(container) -> None:
    container.register_singleton(IService, ServiceImpl)
    container.register_transient(ServiceWithDep, ServiceWithDep)

    dependent = container.get(ServiceWithDep)
    assert isinstance(dependent.service, ServiceImpl)


def test_scoped_resolution(container) -> None:
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


def test_circular_dependency(container) -> None:
    container.register_transient(CircularA, CircularA)
    container.register_transient(CircularB, CircularB)

    with pytest.raises(CircularDependencyException):
        container.get(CircularA)


def test_service_not_found(container) -> None:
    with pytest.raises(ServiceNotFoundException):
        container.get(str)  # Random type


def test_scope_disposal(container) -> None:
    container.register_scoped(DisposableService, DisposableService)

    scope = container.create_scope()
    service = container._resolve_service(DisposableService, scope)

    assert not service.disposed
    scope.dispose()
    assert service.disposed


def test_error_handling_strategy_raise_on_dependency_extraction():
    """Test that RAISE strategy raises exceptions during dependency extraction."""
    from pyguara.di.container import DIContainer
    from pyguara.di.types import ErrorHandlingStrategy

    container = DIContainer(error_strategy=ErrorHandlingStrategy.RAISE)

    # Create a class with problematic dependency hints that will fail extraction
    class ProblematicService:
        def __init__(self, dep: "NonExistent"):  # type: ignore[name-defined]  # noqa: F821
            self.dep = dep

    # Should raise when trying to register with broken dependencies
    with pytest.raises(DIException):
        container.register_transient(ProblematicService, ProblematicService)


def test_error_handling_strategy_log_on_dependency_extraction():
    """Test that LOG strategy logs and continues with dependency extraction failures."""
    from pyguara.di.container import DIContainer
    from pyguara.di.types import ErrorHandlingStrategy
    from unittest.mock import patch
    from io import StringIO

    container = DIContainer(error_strategy=ErrorHandlingStrategy.LOG)

    # Create a class with problematic dependency hints
    class ProblematicService:
        def __init__(self, dep: "NonExistent"):  # type: ignore[name-defined]  # noqa: F821
            self.dep = dep

    # Capture print output
    captured_output = StringIO()
    with patch("sys.stdout", captured_output):
        # Should log warning but not raise
        container.register_transient(ProblematicService, ProblematicService)

    # The service should be registered but with empty dependencies
    assert ProblematicService in container._services


def test_error_handling_strategy_ignore_on_dependency_extraction():
    """Test that IGNORE strategy silently ignores dependency extraction failures."""
    from pyguara.di.container import DIContainer
    from pyguara.di.types import ErrorHandlingStrategy

    container = DIContainer(error_strategy=ErrorHandlingStrategy.IGNORE)

    # Create a class with problematic dependency hints
    class ProblematicService:
        def __init__(self, dep: "NonExistent"):  # type: ignore[name-defined]  # noqa: F821
            self.dep = dep

    # Should silently ignore the error
    container.register_transient(ProblematicService, ProblematicService)

    # The service should be registered but with empty dependencies
    assert ProblematicService in container._services


def test_pep604_union_dependency_resolves(container) -> None:
    """A required `X | None` parameter (PEP 604 union) must unwrap to X, not fall through."""
    container.register_singleton(IService, ServiceImpl)

    class ServiceWithPipeUnionDep:
        def __init__(self, service: IService | None):
            self.service = service

    container.register_transient(ServiceWithPipeUnionDep, ServiceWithPipeUnionDep)

    dependent = container.get(ServiceWithPipeUnionDep)
    assert isinstance(dependent.service, ServiceImpl)


class ScopedCircularA:
    def __init__(self, b: "ScopedCircularB"):
        pass


class ScopedCircularB:
    def __init__(self, a: "ScopedCircularA"):
        pass


def test_circular_dependency_detected_for_scoped_services(container) -> None:
    """A circular SCOPED dependency must raise CircularDependencyException,
    not overflow the Python call stack with a RecursionError."""
    container.register_scoped(ScopedCircularA, ScopedCircularA)
    container.register_scoped(ScopedCircularB, ScopedCircularB)

    with container.create_scope() as scope:
        with pytest.raises(CircularDependencyException):
            container._resolve_service(ScopedCircularA, scope)


def test_default_error_strategy_is_raise():
    """Test that the default error strategy is RAISE for fail-fast behavior."""
    from pyguara.di.container import DIContainer
    from pyguara.di.types import ErrorHandlingStrategy

    container = DIContainer()

    assert container._error_strategy == ErrorHandlingStrategy.RAISE
