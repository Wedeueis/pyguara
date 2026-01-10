"""Core container and scope logic."""

from __future__ import annotations

import inspect
import threading
from typing import (
    Any,
    Callable,
    Dict,
    List,
    Optional,
    Type,
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
from pyguara.di.types import ServiceLifetime, ServiceRegistration, ErrorHandlingStrategy

T = TypeVar("T")
TInterface = TypeVar("TInterface")
TImplementation = TypeVar("TImplementation")


class DIContainer:
    """Lightweight dependency injection container with lifecycle management."""

    def __init__(
        self, error_strategy: ErrorHandlingStrategy = ErrorHandlingStrategy.RAISE
    ) -> None:
        """Initialize an empty container.

        Args:
            error_strategy: How to handle errors during dependency resolution.
                Defaults to RAISE for fail-fast behavior in development.
                Use LOG for production graceful degradation.
        """
        self._services: Dict[Type[Any], ServiceRegistration] = {}
        self._singletons: Dict[Type[Any], Any] = {}
        self._lock = threading.RLock()
        self._resolution_stack: List[Type] = []
        self._error_strategy = error_strategy

    def register_singleton(
        self, interface: Type[TInterface], implementation: Type[TImplementation]
    ) -> DIContainer:
        """Register a service as a singleton (shared instance)."""
        return self._register_service(
            interface, implementation=implementation, lifetime=ServiceLifetime.SINGLETON
        )

    def register_transient(
        self, interface: Type[TInterface], implementation: Type[TImplementation]
    ) -> DIContainer:
        """Register a service as transient (fresh instance every time)."""
        return self._register_service(
            interface, implementation=implementation, lifetime=ServiceLifetime.TRANSIENT
        )

    def register_scoped(
        self, interface: Type[TInterface], implementation: Type[TImplementation]
    ) -> DIContainer:
        """Register a service as scoped (shared within a scope)."""
        return self._register_service(
            interface, implementation=implementation, lifetime=ServiceLifetime.SCOPED
        )

    def register_instance(
        self, interface: Type[TInterface], instance: TInterface
    ) -> DIContainer:
        """Register an existing object as a singleton."""
        with self._lock:
            registration = ServiceRegistration(
                interface=interface,
                instance=instance,
                lifetime=ServiceLifetime.SINGLETON,
            )
            self._services[interface] = registration
            self._singletons[interface] = instance
            return self

    def get(self, service_type: Type[T]) -> T:
        """Resolve and retrieve an instance of the requested service."""
        with self._lock:
            return self._resolve_service(service_type)

    def create_scope(self) -> DIScope:
        """Create a new resource scope."""
        return DIScope(self)

    def _register_service(
        self,
        interface: Type[TInterface],
        implementation: Optional[Type[TImplementation]] = None,
        factory: Optional[Callable[..., TInterface]] = None,
        instance: Optional[TInterface] = None,
        lifetime: ServiceLifetime = ServiceLifetime.TRANSIENT,
    ) -> DIContainer:
        with self._lock:
            providers = [implementation, factory, instance]
            if sum(p is not None for p in providers) != 1:
                raise DIException(
                    "Exactly one of implementation, factory, or instance must be provided"
                )

            dependencies: Dict[str, Type] = {}
            if implementation:
                dependencies = self._extract_dependencies(implementation)
            elif factory:
                dependencies = self._extract_dependencies(factory)

            registration = ServiceRegistration(
                interface=interface,
                implementation=implementation,
                factory=factory,
                instance=instance,
                lifetime=lifetime,
                dependencies=dependencies,
            )

            self._services[interface] = registration
            return self

    def _resolve_service(
        self, service_type: Type[T], scope: Optional[DIScope] = None
    ) -> T:
        # 1. Cycle Detection
        if service_type in self._resolution_stack:
            raise CircularDependencyException(self._resolution_stack + [service_type])

        # 2. Lookup
        if service_type not in self._services:
            raise ServiceNotFoundException(service_type)

        registration = self._services[service_type]

        # 3. Strategy Execution
        if registration.lifetime == ServiceLifetime.SINGLETON:
            if service_type in self._singletons:
                return cast(T, self._singletons[service_type])

            self._resolution_stack.append(service_type)
            try:
                instance = self._create_instance(registration, scope)
                self._singletons[service_type] = instance
                return cast(T, instance)
            finally:
                self._resolution_stack.pop()

        elif registration.lifetime == ServiceLifetime.SCOPED:
            if scope is None:
                raise DIException(
                    f"Scoped service {service_type.__name__} requires an active scope"
                )
            return scope._get_scoped_service(service_type, registration)

        else:  # TRANSIENT
            self._resolution_stack.append(service_type)
            try:
                return cast(T, self._create_instance(registration, scope))
            finally:
                self._resolution_stack.pop()

    def _create_instance(
        self, registration: ServiceRegistration, scope: Optional[DIScope] = None
    ) -> Any:
        if registration.instance is not None:
            return registration.instance

        target = registration.implementation or registration.factory
        if target is None:
            raise DIException("Invalid registration state")

        kwargs = self._resolve_dependencies(
            registration.dependencies or {}, target, scope
        )

        if registration.factory:
            return registration.factory(**kwargs)

        if registration.implementation:
            return registration.implementation(**kwargs)

    def _resolve_dependencies(
        self,
        dependencies: Dict[str, Type],
        target: Union[Type, Callable],
        scope: Optional[DIScope],
    ) -> Dict[str, Any]:
        """Resolve dependencies recursively, respecting default arguments."""
        resolved_kwargs = {}

        # FIX: Use inspect.signature directly. It handles classes and functions automatically.
        # This avoids unsafe access to 'target.__init__'.
        try:
            sig = inspect.signature(target)
        except ValueError:
            # Fallback if signature fails (unlikely for classes/functions)
            sig = inspect.Signature()

        for param_name, dep_type in dependencies.items():
            try:
                instance = self._resolve_service(dep_type, scope)
                resolved_kwargs[param_name] = instance
            except ServiceNotFoundException:
                # Fallback: check if the parameter has a default value
                param = sig.parameters.get(param_name)
                if param and param.default != inspect.Parameter.empty:
                    continue  # Let Python use the default
                raise

        return resolved_kwargs

    def _extract_dependencies(self, target: Union[Type, Callable]) -> Dict[str, Type]:
        """Extract type hints using typing.get_type_hints."""
        try:
            # We still need explicit check here for get_type_hints
            # But we wrap it safely or assume inspect.isclass handles it.
            func = target
            if inspect.isclass(target):
                # Safe access for Class types
                func = getattr(target, "__init__", target)

            hints = get_type_hints(func)
            sig = inspect.signature(func)

            dependencies = {}
            for param_name, _ in sig.parameters.items():
                if param_name == "self":
                    continue

                if param_name in hints:
                    param_type = hints[param_name]
                    if get_origin(param_type) is Union:
                        args = get_args(param_type)
                        valid_args = [arg for arg in args if arg is not type(None)]
                        if valid_args:
                            param_type = valid_args[0]

                    dependencies[param_name] = param_type
            return dependencies
        except Exception as e:
            # Handle error based on configured strategy
            target_name = getattr(target, "__name__", str(target))
            error_msg = (
                f"[DI] Dependency extraction failed for '{target_name}': {e}. "
                f"This may cause injection failures if the service is requested."
            )

            if self._error_strategy == ErrorHandlingStrategy.IGNORE:
                # Silently ignore (not recommended)
                return {}
            elif self._error_strategy == ErrorHandlingStrategy.LOG:
                # Log and return empty dict (graceful degradation)
                print(error_msg)
                return {}
            else:  # ErrorHandlingStrategy.RAISE
                # Log and re-raise
                print(error_msg)
                raise DIException(
                    f"Failed to extract dependencies from {target_name}: {e}"
                ) from e


class DIScope:
    """Service scope for managing scoped lifetimes and cleanup.

    Scopes are used to manage the lifetime of scoped services. Services
    registered as scoped will have one instance per scope, shared across
    all requests within that scope.

    Example:
        >>> container = DIContainer()
        >>> container.register_scoped(IDatabase, DatabaseConnection)
        >>>
        >>> with container.create_scope() as scope:
        ...     db1 = scope.get(IDatabase)  # Creates new instance
        ...     db2 = scope.get(IDatabase)  # Returns same instance
        ...     assert db1 is db2
        >>> # Scope disposed, resources cleaned up
    """

    def __init__(self, container: DIContainer) -> None:
        """Initialize a new scope."""
        self._container = container
        self._scoped_services: Dict[Type[Any], Any] = {}
        self._disposed = False
        self._disposables: List[Any] = []
        self._lock = threading.RLock()

    def get(self, service_type: Type[T]) -> T:
        """Resolve and retrieve a service instance within this scope.

        This is the primary public API for resolving services within a scope.
        Scoped services will be shared within this scope, while singletons
        will return the global instance, and transients will create new instances.

        Args:
            service_type: The type of service to resolve.

        Returns:
            An instance of the requested service.

        Raises:
            ServiceNotFoundException: If the service is not registered.
            CircularDependencyException: If a circular dependency is detected.
            DIException: If attempting to resolve a scoped service without a scope.

        Example:
            >>> container = DIContainer()
            >>> container.register_scoped(ILogger, FileLogger)
            >>> container.register_singleton(IConfig, AppConfig)
            >>>
            >>> with container.create_scope() as scope:
            ...     logger = scope.get(ILogger)  # Scoped instance
            ...     config = scope.get(IConfig)  # Singleton instance
        """
        return self._container._resolve_service(service_type, scope=self)

    def _get_scoped_service(
        self, service_type: Type[T], registration: ServiceRegistration
    ) -> T:
        with self._lock:
            if service_type in self._scoped_services:
                return cast(T, self._scoped_services[service_type])

            instance = self._container._create_instance(registration, self)
            self._scoped_services[service_type] = instance

            if hasattr(instance, "dispose") or hasattr(instance, "close"):
                self._disposables.append(instance)

            return cast(T, instance)

    def dispose(self) -> None:
        """Cleanup all resources tracked by this scope."""
        with self._lock:
            if self._disposed:
                return

            for disposable in reversed(self._disposables):
                try:
                    if hasattr(disposable, "dispose"):
                        disposable.dispose()
                    elif hasattr(disposable, "close"):
                        disposable.close()
                except Exception:
                    pass

            self._scoped_services.clear()
            self._disposables.clear()
            self._disposed = True

    def __enter__(self) -> DIScope:
        """Enter the context manager, returning this scope."""
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Exit the context manager, disposing resources."""
        self.dispose()
