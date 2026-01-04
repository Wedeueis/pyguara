"""Type definitions for the Event System."""

from typing import Callable, TypeVar, Optional

# We use a Forward Reference because Event is defined in protocols.py
E_contra = TypeVar("E_contra", contravariant=True)

# A Handler is a callable that takes an Event and returns nothing.
EventHandler = Callable[[E_contra], Optional[bool]]
