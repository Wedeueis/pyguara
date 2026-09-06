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


# -- Lifetime boundaries: singletons must not capture scoped services --


class ScopedResource:
    def __init__(self) -> None:
        self.disposed = False

    def dispose(self) -> None:
        self.disposed = True


class SingletonNeedingScope:
    def __init__(self, resource: ScopedResource) -> None:
        self.resource = resource


def test_a_singleton_cannot_capture_a_scoped_dependency(container) -> None:
    """A container-lived object holding a scope-lived one is the classic
    captive-dependency bug: the scope disposes its instance and the singleton
    keeps handing out the dead object forever. Singletons are therefore built
    with no scope, so the attempt fails loudly instead."""
    container.register_scoped(ScopedResource, ScopedResource)
    container.register_singleton(SingletonNeedingScope, SingletonNeedingScope)

    with container.create_scope() as scope:
        with pytest.raises(DIException, match="requires an active scope"):
            scope.get(SingletonNeedingScope)


def test_the_captive_dependency_error_explains_the_singleton_case(container) -> None:
    container.register_scoped(ScopedResource, ScopedResource)
    container.register_singleton(SingletonNeedingScope, SingletonNeedingScope)

    with container.create_scope() as scope:
        with pytest.raises(DIException) as excinfo:
            scope.get(SingletonNeedingScope)

    assert "singleton" in str(excinfo.value).lower()


def test_a_transient_may_still_take_a_scoped_dependency(container) -> None:
    """Transients live no longer than the call that asked for them, so they
    are free to depend on scoped services."""

    class TransientUser:
        def __init__(self, resource: ScopedResource) -> None:
            self.resource = resource

    container.register_scoped(ScopedResource, ScopedResource)
    container.register_transient(TransientUser, TransientUser)

    with container.create_scope() as scope:
        assert scope.get(TransientUser).resource is scope.get(ScopedResource)


def test_a_scoped_service_may_depend_on_a_singleton(container) -> None:
    class Config:
        pass

    class ScopedUser:
        def __init__(self, config: Config) -> None:
            self.config = config

    container.register_singleton(Config, Config)
    container.register_scoped(ScopedUser, ScopedUser)

    with container.create_scope() as scope:
        assert scope.get(ScopedUser).config is container.get(Config)


# -- Scope disposal --


def test_a_disposed_scope_refuses_to_resolve(container) -> None:
    """Resolving after disposal produced instances that would never be
    cleaned up -- the scope had already emptied its disposables list."""
    container.register_scoped(ScopedResource, ScopedResource)
    scope = container.create_scope()
    scope.dispose()

    with pytest.raises(DIException, match="disposed"):
        scope.get(ScopedResource)


def test_disposing_twice_is_a_noop(container) -> None:
    class CountingDispose:
        def __init__(self) -> None:
            self.calls = 0

        def dispose(self) -> None:
            self.calls += 1

    container.register_scoped(CountingDispose, CountingDispose)
    scope = container.create_scope()
    instance = scope.get(CountingDispose)

    scope.dispose()
    scope.dispose()

    assert instance.calls == 1


def test_a_failing_dispose_does_not_abort_the_rest(container) -> None:
    """dispose() swallowed every exception with a bare `except: pass`, so a
    broken teardown was invisible. It is logged now, and the remaining
    services are still disposed."""

    class FailingDispose:
        def dispose(self) -> None:
            raise RuntimeError("cleanup failed")

    class WorkingDispose:
        def __init__(self, other: FailingDispose) -> None:
            self.disposed = False

        def dispose(self) -> None:
            self.disposed = True

    container.register_scoped(FailingDispose, FailingDispose)
    container.register_scoped(WorkingDispose, WorkingDispose)

    with container.create_scope() as scope:
        working = scope.get(WorkingDispose)

    assert working.disposed


def test_a_failing_dispose_is_logged(container, caplog) -> None:
    import logging

    class FailingDispose:
        def dispose(self) -> None:
            raise RuntimeError("cleanup failed")

    container.register_scoped(FailingDispose, FailingDispose)
    with caplog.at_level(logging.ERROR):
        with container.create_scope() as scope:
            scope.get(FailingDispose)

    assert "Error disposing" in caplog.text


def test_close_is_used_when_dispose_is_absent(container) -> None:
    class Closeable:
        def __init__(self) -> None:
            self.closed = False

        def close(self) -> None:
            self.closed = True

    container.register_scoped(Closeable, Closeable)
    with container.create_scope() as scope:
        instance = scope.get(Closeable)

    assert instance.closed


def test_disposed_flag_is_observable(container) -> None:
    scope = container.create_scope()
    assert scope.disposed is False
    scope.dispose()
    assert scope.disposed is True


# -- Re-registration --


def test_re_registering_replaces_an_already_resolved_singleton(container) -> None:
    """The registration dict was overwritten but the cached instance was not,
    so a re-registered singleton silently kept handing out the old object."""

    class Original:
        pass

    class Replacement:
        pass

    container.register_singleton(Original, Original)
    first = container.get(Original)

    container.register_singleton(Original, Replacement)
    second = container.get(Original)

    assert isinstance(first, Original)
    assert isinstance(second, Replacement)


def test_re_registering_replaces_a_registered_instance(container) -> None:
    class Thing:
        pass

    first, second = Thing(), Thing()
    container.register_instance(Thing, first)
    container.register_singleton(Thing, Thing)

    assert container.get(Thing) is not first
    assert container.get(Thing) is not second


def test_is_registered(container) -> None:
    class Known:
        pass

    class Unknown:
        pass

    container.register_singleton(Known, Known)
    assert container.is_registered(Known)
    assert not container.is_registered(Unknown)


# -- Constructor signature handling --


def test_varargs_are_not_treated_as_injection_points(container) -> None:
    """`*args: int` was read as a dependency named "args" of type int, so any
    class declaring varargs failed to resolve with ServiceNotFoundException."""

    class Varargs:
        def __init__(self, *args: int, **kwargs: str) -> None:
            self.built = True

    container.register_transient(Varargs, Varargs)

    assert container._services[Varargs].dependencies == {}
    assert container.get(Varargs).built


def test_varargs_alongside_a_real_dependency(container) -> None:
    class Dep:
        pass

    class Mixed:
        def __init__(self, dep: Dep, *args: int) -> None:
            self.dep = dep

    container.register_singleton(Dep, Dep)
    container.register_transient(Mixed, Mixed)

    assert container.get(Mixed).dep is container.get(Dep)


def test_an_unregistered_dependency_with_a_default_is_skipped(container) -> None:
    class Missing:
        pass

    class HasDefault:
        def __init__(self, missing: Missing | None = None) -> None:
            self.missing = missing

    container.register_transient(HasDefault, HasDefault)

    assert container.get(HasDefault).missing is None


def test_an_unregistered_dependency_without_a_default_raises(container) -> None:
    class Missing:
        pass

    class NeedsIt:
        def __init__(self, missing: Missing) -> None: ...

    container.register_transient(NeedsIt, NeedsIt)

    with pytest.raises(ServiceNotFoundException):
        container.get(NeedsIt)


def test_a_class_with_no_constructor_resolves(container) -> None:
    class Bare:
        pass

    container.register_singleton(Bare, Bare)
    assert isinstance(container.get(Bare), Bare)


def test_a_factory_registration_receives_injected_arguments(container) -> None:
    class Dep:
        pass

    class Product:
        def __init__(self, dep: Dep) -> None:
            self.dep = dep

    def build(dep: Dep) -> Product:
        return Product(dep)

    container.register_singleton(Dep, Dep)
    container._register_service(Product, factory=build)

    assert container.get(Product).dep is container.get(Dep)


def test_registering_two_providers_at_once_is_rejected(container) -> None:
    class Thing:
        pass

    with pytest.raises(DIException, match="Exactly one"):
        container._register_service(Thing, implementation=Thing, instance=Thing())


# -- Thread safety --


def test_concurrent_scoped_resolution_does_not_report_false_cycles(container) -> None:
    """DIScope.get() resolved without taking the container lock, so parallel
    resolutions shared one mutable cycle-detection stack and saw each other's
    partial chains. With a slow constructor this reported a circular
    dependency on roughly 90% of resolutions.
    """
    import threading
    import time

    class Slow:
        def __init__(self) -> None:
            time.sleep(0.002)

    class Root:
        def __init__(self, slow: Slow) -> None: ...

    container.register_transient(Slow, Slow)
    container.register_transient(Root, Root)

    errors: list[Exception] = []

    def worker() -> None:
        for _ in range(10):
            try:
                with container.create_scope() as scope:
                    scope.get(Root)
            except Exception as exc:  # noqa: BLE001
                errors.append(exc)

    threads = [threading.Thread(target=worker) for _ in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert errors == []


def test_a_singleton_is_constructed_once_under_contention(container) -> None:
    import threading
    import time

    class SlowSingleton:
        instances = 0

        def __init__(self) -> None:
            time.sleep(0.002)
            SlowSingleton.instances += 1

    container.register_singleton(SlowSingleton, SlowSingleton)
    resolved = []

    def worker() -> None:
        resolved.append(container.get(SlowSingleton))

    threads = [threading.Thread(target=worker) for _ in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert SlowSingleton.instances == 1
    assert len({id(r) for r in resolved}) == 1


def test_cycle_detection_state_does_not_leak_between_threads(container) -> None:
    """The resolution stack is thread-local, so one thread's in-flight chain is
    invisible to another even without the lock held."""
    import threading

    class Leaf:
        pass

    container.register_transient(Leaf, Leaf)
    stacks: list[list] = []

    def worker() -> None:
        container.get(Leaf)
        stacks.append(container._resolution_stack)

    threads = [threading.Thread(target=worker) for _ in range(4)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert all(s == [] for s in stacks)
    assert len({id(s) for s in stacks}) == 4


def test_the_resolution_stack_is_unwound_after_a_failed_resolution(container) -> None:
    class Missing:
        pass

    class NeedsIt:
        def __init__(self, missing: Missing) -> None: ...

    container.register_transient(NeedsIt, NeedsIt)

    with pytest.raises(ServiceNotFoundException):
        container.get(NeedsIt)

    assert container._resolution_stack == []
    container.register_singleton(Missing, Missing)
    assert container.get(NeedsIt) is not None
