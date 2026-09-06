"""Error-handling types shared across engine subsystems.

Kept at the top level, importing nothing from the engine, so any subsystem can
depend on it without creating a cycle -- `di` in particular must not import
`events`, and `events` must not import `log`.
"""

from enum import Enum


class ErrorHandlingStrategy(Enum):
    """What a subsystem does when user-supplied code raises.

    Used by `EventDispatcher` for handlers and filters, and by `DIContainer`
    for constructor introspection. A single definition, because two enums with
    the same members are not interchangeable: comparing one subsystem's RAISE
    against another's silently evaluates false.

    Attributes:
        LOG: Log the error and carry on. Graceful degradation in production.
        RAISE: Log the error and re-raise it. Fail fast in development, and
            the default everywhere.
        IGNORE: Swallow the error silently. Tests and narrow edge cases only.

    Example:
        ```python
        from pyguara.errors import ErrorHandlingStrategy

        dispatcher = EventDispatcher(error_strategy=ErrorHandlingStrategy.LOG)
        container = DIContainer(error_strategy=ErrorHandlingStrategy.LOG)
        ```
    """

    LOG = "log"
    RAISE = "raise"
    IGNORE = "ignore"
