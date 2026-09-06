"""Dependency injection container and scopes."""

from __future__ import annotations

import inspect
import threading
import types
from typing import (
    Any,
    Callable,
    TypeVar,
    Union,
    cast,
    get_args,
    get_origin,
    get_type_hints,
)

from pyguara.di.exceptions import (
    CircularDependencyException,
    DIException,
    ServiceNotFoundException,
)
from pyguara.di.types import ErrorHandlingStrategy, ServiceLifetime, ServiceRegistration
from pyguara.log import get_logger

logger = get_logger(__name__)

T = TypeVar("T")
TInterface = TypeVar("TInterface")
TImplementation = TypeVar("TImplementation")

_INJECTABLE_KINDS = frozenset(
    {
        inspect.Parameter.POSITIONAL_OR_KEYWORD,
        inspect.Parameter.KEYWORD_ONLY,
    }
)


class DIContainer:
    """Reflection-based dependency injection container.

    Services are registered against an interface type and constructed by
    reading their constructor's type hints. Three lifetimes are supported:
    SINGLETON (one per container), SCOPED (one per `DIScope`) and TRANSIENT
    (a fresh instance per request).

    Thread safety:
        Registration and resolution are guarded by a reentrant lock, so a
        service is constructed at most once even under contention. Cycle
        detection state is thread-local, so concurrent resolutions on
        different threads cannot see each other's partial chains.
    """

    def __init__(
        self, error_strategy: ErrorHandlingStrategy = ErrorHandlingStrategy.RAISE
    ) -> None:
        """Initialise an empty container.

        Args:
            error_strategy: What to do when dependency extraction fails.
                RAISE fails fast in development; LOG degrades gracefully.
        """
        self._services: dict[type[Any], ServiceRegistration] = {}
        self._singletons: dict[type[Any], Any] = {}
        self._lock = threading.RLock()
        self._error_strategy = error_strategy

        # Thread-local, not shared: this tracks one in-flight resolution chain.
        # A single shared list made concurrent resolutions see each other's
        # partial chains and raise CircularDependencyException at random.
        self._local = threading.local()

    @property
    def _resolution_stack(self) -> list[type[Any]]:
        """The current thread's in-flight resolution chain."""
        stack: list[type[Any]] | None = getattr(self._local, "stack", None)
        if stack is None:
            stack = []
            self._local.stack = stack
        return stack

    def register_singleton(
        self, interface: type[TInterface], implementation: type[TImplementation]
    ) -> DIContainer:
        """Register a service constructed once and shared container-wide.

        Args:
            interface: The type callers will request.
            implementation: The concrete class to construct.

        Returns:
            This container, for chaining.
        """
        return self._register_service(
            interface, implementation=implementation, lifetime=ServiceLifetime.SINGLETON
        )

    def register_transient(
        self, interface: type[TInterface], implementation: type[TImplementation]
    ) -> DIContainer:
        """Register a service constructed fresh on every request.

        Args:
            interface: The type callers will request.
            implementation: The concrete class to construct.

        Returns:
            This container, for chaining.
        """
        return self._register_service(
            interface, implementation=implementation, lifetime=ServiceLifetime.TRANSIENT
        )

    def register_scoped(
        self, interface: type[TInterface], implementation: type[TImplementation]
    ) -> DIContainer:
        """Register a service constructed once per `DIScope`.

        Args:
            interface: The type callers will request.
            implementation: The concrete class to construct.

        Returns:
            This container, for chaining.
        """
        return self._register_service(
            interface, implementation=implementation, lifetime=ServiceLifetime.SCOPED
        )

    def register_instance(
        self, interface: type[TInterface], instance: TInterface
    ) -> DIContainer:
        """Register an already-built object as the singleton for a type.

        Args:
            interface: The type callers will request.
            instance: The object to hand out.

        Returns:
            This container, for chaining.

        Raises:
            DIException: If `interface` is a `@runtime_checkable` Protocol and
                `instance` does not structurally satisfy it. Only Protocols are
                checked; concrete-class interfaces are left alone, since at
                least one registration deliberately supplies an instance that
                is not a real subclass (the Pygame `RenderGraph` stub, branched
                on by identity elsewhere). This is also the only registration
                that can validate anything up front -- the others have a class
                and no instance yet.
        """
        with self._lock:
            if getattr(interface, "_is_protocol", False) and not isinstance(
                instance, interface
            ):
                raise DIException(
                    f"Registered instance of type "
                    f"{type(instance).__name__!r} does not satisfy the "
                    f"protocol {interface.__name__!r}."
                )

            registration = ServiceRegistration(
                interface=interface,
                instance=instance,
                lifetime=ServiceLifetime.SINGLETON,
            )
            self._services[interface] = registration
            self._singletons[interface] = instance
            return self

    def is_registered(self, service_type: type[Any]) -> bool:
        """Report whether a type has a registration.

        Args:
            service_type: The type to check.

        Returns:
            True if the type can be resolved.
        """
        with self._lock:
            return service_type in self._services

    def get(self, service_type: type[T]) -> T:
        """Resolve a service, constructing it and its dependencies as needed.

        Args:
            service_type: The registered interface type to resolve.

        Returns:
            An instance of the requested service.

        Raises:
            ServiceNotFoundException: If the type was never registered.
            CircularDependencyException: If the dependency graph has a cycle.
            DIException: If a scoped service is requested without a scope.
        """
        with self._lock:
            return self._resolve_service(service_type)

    def create_scope(self) -> DIScope:
        """Create a scope for resolving scoped services.

        Returns:
            A new scope. Use it as a context manager so it disposes.
        """
        return DIScope(self)

    def _register_service(
        self,
        interface: type[TInterface],
        implementation: type[TImplementation] | None = None,
        factory: Callable[..., TInterface] | None = None,
        instance: TInterface | None = None,
        lifetime: ServiceLifetime = ServiceLifetime.TRANSIENT,
    ) -> DIContainer:
        """Record a registration and pre-compute its constructor dependencies.

        Args:
            interface: The type callers will request.
            implementation: Concrete class to construct, if any.
            factory: Callable producing the instance, if any.
            instance: Pre-built object, if any.
            lifetime: The lifecycle strategy.

        Returns:
            This container, for chaining.

        Raises:
            DIException: Unless exactly one provider is given.
        """
        with self._lock:
            providers = [implementation, factory, instance]
            if sum(p is not None for p in providers) != 1:
                raise DIException(
                    "Exactly one of implementation, factory, or instance "
                    "must be provided"
                )

            dependencies: dict[str, type[Any]] = {}
            param_defaults: set[str] = set()
            if implementation is not None:
                dependencies, param_defaults = self._extract_dependencies(
                    implementation
                )
            elif factory is not None:
                dependencies, param_defaults = self._extract_dependencies(factory)

            self._services[interface] = ServiceRegistration(
                interface=interface,
                implementation=implementation,
                factory=factory,
                instance=instance,
                lifetime=lifetime,
                dependencies=dependencies,
                param_defaults=param_defaults,
            )
            # Drop any instance cached under a previous registration; otherwise
            # re-registering a type that had already been resolved silently
            # kept handing out the old object.
            self._singletons.pop(interface, None)
            return self

    def _resolve_service(
        self, service_type: type[T], scope: DIScope | None = None
    ) -> T:
        """Resolve one service, recursing through its dependencies.

        Args:
            service_type: The interface type to resolve.
            scope: The active scope, if resolution started from one.

        Returns:
            The resolved instance.

        Raises:
            CircularDependencyException: If this type is already being built
                further up this thread's chain.
            ServiceNotFoundException: If the type was never registered.
            DIException: If a scoped service is reached without a scope.
        """
        stack = self._resolution_stack
        if service_type in stack:
            raise CircularDependencyException([*stack, service_type])

        registration = self._services.get(service_type)
        if registration is None:
            raise ServiceNotFoundException(service_type)

        stack.append(service_type)
        try:
            if registration.lifetime is ServiceLifetime.SINGLETON:
                if service_type in self._singletons:
                    return cast(T, self._singletons[service_type])
                # Deliberately scope=None: a container-lived singleton must not
                # capture a scope-lived dependency, which would outlive its
                # owner and be disposed out from under it.
                instance = self._create_instance(registration, None)
                self._singletons[service_type] = instance
                return cast(T, instance)

            if registration.lifetime is ServiceLifetime.SCOPED:
                if scope is None:
                    raise DIException(
                        f"Scoped service {service_type.__name__!r} requires an "
                        f"active scope. Either resolve it through "
                        f"DIContainer.create_scope(), or -- if it is being "
                        f"pulled in as a dependency of a singleton -- note that "
                        f"singletons are resolved without a scope on purpose, "
                        f"since a container-lived object must not capture a "
                        f"scope-lived one."
                    )
                return scope._get_scoped_service(service_type, registration)

            return cast(T, self._create_instance(registration, scope))
        finally:
            stack.pop()

    def _create_instance(
        self, registration: ServiceRegistration, scope: DIScope | None = None
    ) -> Any:
        """Construct an instance for a registration.

        Args:
            registration: The registration to build.
            scope: The active scope, if any.

        Returns:
            The constructed object.

        Raises:
            DIException: If the registration has no usable provider.
        """
        if registration.instance is not None:
            return registration.instance

        kwargs = self._resolve_dependencies(
            registration.dependencies or {},
            registration.param_defaults or set(),
            scope,
        )

        if registration.factory is not None:
            return registration.factory(**kwargs)
        if registration.implementation is not None:
            return registration.implementation(**kwargs)

        raise DIException(
            f"Registration for {registration.interface.__name__!r} has no "
            f"implementation, factory or instance."
        )

    def _resolve_dependencies(
        self,
        dependencies: dict[str, type[Any]],
        param_defaults: set[str],
        scope: DIScope | None,
    ) -> dict[str, Any]:
        """Resolve constructor arguments, skipping ones that have defaults.

        Args:
            dependencies: Parameter name to required type.
            param_defaults: Parameter names that declare a default, computed at
                registration so resolution never calls `inspect` at runtime.
            scope: The active scope, if any.

        Returns:
            Keyword arguments for the constructor. A parameter whose service is
            unregistered is omitted when it has a default, so Python supplies
            it.

        Raises:
            ServiceNotFoundException: If a dependency without a default is
                unregistered.
        """
        resolved_kwargs = {}

        for param_name, dep_type in dependencies.items():
            try:
                resolved_kwargs[param_name] = self._resolve_service(dep_type, scope)
            except ServiceNotFoundException:
                if param_name in param_defaults:
                    continue
                raise

        return resolved_kwargs

    def _extract_dependencies(
        self, target: type[Any] | Callable[..., Any]
    ) -> tuple[dict[str, type[Any]], set[str]]:
        """Read a constructor's injectable parameters, once, at registration.

        `*args` and `**kwargs` are skipped: they are not injection points, and
        treating them as such made any class declaring them unresolvable.
        `Optional[X]` and `X | None` resolve to `X`; a wider union takes its
        first non-None member.

        Args:
            target: The class or factory to inspect.

        Returns:
            A `(dependencies, param_defaults)` pair.

        Raises:
            DIException: If inspection fails and the error strategy is RAISE.
        """
        try:
            func: Any = target
            if inspect.isclass(target):
                func = getattr(target, "__init__", target)

            hints = get_type_hints(func)
            signature = inspect.signature(func)

            dependencies: dict[str, type[Any]] = {}
            param_defaults: set[str] = set()
            for param_name, param in signature.parameters.items():
                if param_name == "self" or param.kind not in _INJECTABLE_KINDS:
                    continue

                if param.default is not inspect.Parameter.empty:
                    param_defaults.add(param_name)

                if param_name not in hints:
                    continue

                param_type = hints[param_name]
                if get_origin(param_type) in (Union, types.UnionType):
                    non_none = [a for a in get_args(param_type) if a is not type(None)]
                    if non_none:
                        param_type = non_none[0]
                dependencies[param_name] = param_type

            return dependencies, param_defaults
        except Exception as error:
            target_name = getattr(target, "__name__", str(target))
            error_msg = (
                f"[DI] Dependency extraction failed for {target_name!r}: {error}. "
                f"This may cause injection failures if the service is requested."
            )

            if self._error_strategy is ErrorHandlingStrategy.IGNORE:
                return {}, set()

            logger.error(error_msg)
            if self._error_strategy is ErrorHandlingStrategy.LOG:
                return {}, set()

            raise DIException(
                f"Failed to extract dependencies from {target_name}: {error}"
            ) from error


class DIScope:
    """A resolution context owning one instance of each scoped service.

    Scoped services are created once per scope and disposed when it closes.
    Singletons and transients resolve as usual through the container.

    Use it as a context manager so disposal always runs:

    ```python
    container.register_scoped(IDatabase, DatabaseConnection)

    with container.create_scope() as scope:
        db = scope.get(IDatabase)
        assert scope.get(IDatabase) is db
    # scope disposed; db.dispose() called
    ```
    """

    def __init__(self, container: DIContainer) -> None:
        """Initialise an empty scope.

        Args:
            container: The container this scope resolves against.
        """
        self._container = container
        self._scoped_services: dict[type[Any], Any] = {}
        self._disposed = False
        self._disposables: list[Any] = []
        self._lock = threading.RLock()

    @property
    def disposed(self) -> bool:
        """Whether this scope has been disposed."""
        return self._disposed

    def get(self, service_type: type[T]) -> T:
        """Resolve a service within this scope.

        Args:
            service_type: The registered interface type to resolve.

        Returns:
            An instance. Scoped services are shared within this scope;
            singletons come from the container; transients are fresh.

        Raises:
            DIException: If this scope has already been disposed. Anything
                created afterwards would never be cleaned up.
            ServiceNotFoundException: If the service is not registered.
            CircularDependencyException: If the dependency graph has a cycle.
        """
        if self._disposed:
            raise DIException(
                "Cannot resolve from a disposed DIScope; anything created now "
                "would never be disposed. Create a new scope instead."
            )
        # Take the container lock, as DIContainer.get() does. Without it,
        # resolutions through a scope raced registry and singleton access.
        with self._container._lock:
            return self._container._resolve_service(service_type, scope=self)

    def dispose(self) -> None:
        """Dispose every scoped service this scope created, newest first.

        Calls `dispose()` if present, otherwise `close()`. A failure is logged
        and the remaining objects are still disposed. Calling this twice is a
        no-op.
        """
        with self._lock:
            if self._disposed:
                return
            # Set first: a disposal callback that reaches back into this scope
            # gets the clear "disposed" error rather than a half-torn-down one.
            self._disposed = True

            for disposable in reversed(self._disposables):
                try:
                    if hasattr(disposable, "dispose"):
                        disposable.dispose()
                    elif hasattr(disposable, "close"):
                        disposable.close()
                except Exception:
                    logger.error(
                        f"Error disposing {type(disposable).__name__!r} in "
                        f"DIScope; continuing with the remaining services.",
                        exc_info=True,
                    )

            self._scoped_services.clear()
            self._disposables.clear()

    def _get_scoped_service(
        self, service_type: type[T], registration: ServiceRegistration
    ) -> T:
        """Return this scope's instance of a service, creating it if needed.

        Args:
            service_type: The interface being resolved.
            registration: Its registration.

        Returns:
            The scope-local instance.
        """
        with self._lock:
            if service_type in self._scoped_services:
                return cast(T, self._scoped_services[service_type])

            instance = self._container._create_instance(registration, self)
            self._scoped_services[service_type] = instance

            if hasattr(instance, "dispose") or hasattr(instance, "close"):
                self._disposables.append(instance)

            return cast(T, instance)

    def __enter__(self) -> DIScope:
        """Enter the context manager.

        Returns:
            This scope.
        """
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Leave the context manager, disposing the scope."""
        self.dispose()
