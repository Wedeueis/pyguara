"""Data resource implementation for structured game assets."""

import json
from dataclasses import is_dataclass
from typing import Any, Dict, Type, TypeVar, cast

from pyguara.resources.types import Resource

T = TypeVar("T", bound="DataResource")


class DataResource(Resource):
    """
    A generic resource representing structured game data (JSON/YAML).

    This class serves as a base for specific game assets like 'ItemData',
    'EnemyData', or 'LevelConfig'. It allows these data structures to be
    managed, cached, and hot-reloaded by the ResourceManager.

    Attributes:
        data (Dict[str, Any]): The raw data dictionary loaded from disk.
    """

    def __init__(self, path: str, data: Dict[str, Any]):
        """Initialize the data resource.

        Args:
            path: The file path this resource was loaded from.
            data: The dictionary containing the parsed data.
        """
        super().__init__(path)
        self._data = data

    @property
    def native_handle(self) -> Any:
        """Return the raw data dictionary.

        Returns:
            The underlying dictionary structure.
        """
        return self._data

    def to_object(self, cls: Type[T]) -> T:
        """
        Convert the raw data into a strong-typed Dataclass instance.

        Args:
            cls: The target Dataclass type to convert into.

        Returns:
            An instance of 'cls' populated with this resource's data.

        Raises:
            TypeError: If 'cls' is not a dataclass.
        """
        if not is_dataclass(cls):
            raise TypeError(f"Target type {cls.__name__} must be a dataclass")

        # Filter data to match dataclass fields (for safety)
        valid_keys = cls.__dataclass_fields__.keys()
        filtered = {k: v for k, v in self._data.items() if k in valid_keys}

        return cast(T, cls(**filtered))

    def save(self) -> None:
        """Serialize the current data state back to disk."""
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(self._data, f, indent=4)
