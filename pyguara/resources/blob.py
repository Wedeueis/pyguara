"""Resources that are just the contents of a file.

A blob is bytes and a text resource is a decoded string, for a shader,
a fixture or any other file that should go through `ResourceManager`
(its index, cache, reference counting and hot reload) without a
backend.

A font is not one of these: it loads as a `pyguara.resources.font.Font`.
"""

from __future__ import annotations

from typing import Any

from pyguara.resources.types import Resource


class BlobResource(Resource):
    """A file's raw bytes, cached and reference-counted like anything else.

    Attributes:
        data: The file's contents.
    """

    def __init__(self, path: str, data: bytes) -> None:
        """Wrap a file's bytes.

        Args:
            path: Where it came from.
            data: Its contents.
        """
        super().__init__(path)
        self.data = data

    @property
    def native_handle(self) -> Any:
        """The bytes themselves: there is no backend object to unwrap."""
        return self.data

    @property
    def size_bytes(self) -> int:
        """Exactly the length of the data, for once.

        Returns:
            Bytes.
        """
        return len(self.data)


class TextResource(Resource):
    """A file's decoded text.

    Separate from `BlobResource` rather than a `.text` property on it,
    because the encoding is a decision made at load time and a resource
    that could be read either way would make every caller re-make it.

    Attributes:
        text: The decoded contents.
        encoding: What it was decoded with.
    """

    def __init__(self, path: str, text: str, encoding: str = "utf-8") -> None:
        """Wrap a file's text.

        Args:
            path: Where it came from.
            text: Its decoded contents.
            encoding: What it was decoded with.
        """
        super().__init__(path)
        self.text = text
        self.encoding = encoding

    @property
    def native_handle(self) -> Any:
        """The string itself: there is no backend object to unwrap."""
        return self.text

    @property
    def size_bytes(self) -> int:
        """The encoded length, not `len(text)`.

        A multi-byte character costs more than one byte, and the budget
        counts memory rather than characters.

        Returns:
            Bytes.
        """
        return len(self.text.encode(self.encoding, errors="replace"))
