"""Loader strategies for data files."""

import json
from typing import List

from pyguara.resources.loader import IResourceLoader
from pyguara.resources.data import DataResource
from pyguara.resources.types import Resource


class JsonLoader(IResourceLoader):
    """
    Loader strategy for parsing JSON files into DataResources.

    Implements the IResourceLoader protocol.
    """

    @property
    def supported_extensions(self) -> List[str]:
        """Return supported extensions."""
        return [".json", ".manifest", ".config"]

    def load(self, path: str) -> Resource:
        """
        Read a JSON file and return a DataResource.

        Args:
            path: The full path to the file.

        Returns:
            DataResource: A resource wrapping the parsed JSON dict.

        Raises:
            FileNotFoundError: If the file does not exist.
            json.JSONDecodeError: If the file contains invalid JSON.
        """
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)

        return DataResource(path, data)
