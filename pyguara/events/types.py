"""Type definitions for the event system."""

from collections.abc import Callable
from typing import TypeVar

# We use a Forward Reference because Event is defined in protocols.py
from pyguara.errors import ErrorHandlingStrategy

E_contra = TypeVar("E_contra", contravariant=True)

# A Handler is a callable that takes an Event and returns nothing.
EventHandler = Callable[[E_contra], bool | None]


# Re-exported so `from pyguara.events.types import ErrorHandlingStrategy` keeps
# working. The definition lives in pyguara.errors because DIContainer needs the
# same enum and must not import this package.
__all__ = ["ErrorHandlingStrategy", "EventHandler"]
