"""Loaders for files the engine does not need to interpret."""

from __future__ import annotations

from pyguara import assets
from pyguara.resources.blob import BlobResource, TextResource
from pyguara.resources.types import Resource

# Shader stages, as every GLSL toolchain names them, plus the catch-all.
SHADER_EXTENSIONS = (".vert", ".frag", ".geom", ".comp", ".glsl")

# Deliberately *not* ".txt" or ".md": a game's prose is content a game
# loads on purpose, and claiming those extensions engine-wide would make
# the choice for it. A game that wants them registers this loader itself
# with the extensions it means.
TEXT_EXTENSIONS = SHADER_EXTENSIONS

# Nothing image-, audio- or data-shaped: those have loaders that know what
# the bytes mean, and a blob loader claiming ".png" would quietly win the
# registration race and hand a texture request a pile of bytes. Fonts have
# their own loader too, `pyguara.resources.font.FontLoader`.
BLOB_EXTENSIONS = (".bin", ".dat")


class BlobLoader:
    """Reads a file as bytes, interpreting nothing.

    What a binary fixture or a packed table needs to get into
    the cache. The bytes are the resource; turning them into something
    useful is the caller's business.
    """

    def __init__(self, extensions: tuple[str, ...] = BLOB_EXTENSIONS) -> None:
        """Choose which extensions this loader claims.

        Args:
            extensions: Lowercase extensions including the dot.
        """
        self._extensions = list(extensions)

    @property
    def supported_extensions(self) -> list[str]:
        """The extensions this loader claims."""
        return list(self._extensions)

    def load(self, path: str) -> Resource:
        """Read the file's bytes.

        Args:
            path: The full path to the file.

        Returns:
            The wrapped bytes.

        Raises:
            FileNotFoundError: If the path does not exist.
            OSError: If the file is unreadable.
        """
        return BlobResource(path, assets.read_bytes(path))


class TextLoader:
    """Reads a file as decoded text.

    Registered for shader stages by default, which is the engine's own use
    for it: a `.vert` is a string the backend compiles, and the only
    reason it was outside the resource system is that nobody wrote this.
    """

    def __init__(
        self,
        extensions: tuple[str, ...] = TEXT_EXTENSIONS,
        encoding: str = "utf-8",
    ) -> None:
        """Choose which extensions this loader claims, and how to decode.

        Args:
            extensions: Lowercase extensions including the dot.
            encoding: Text encoding.
        """
        self._extensions = list(extensions)
        self._encoding = encoding

    @property
    def supported_extensions(self) -> list[str]:
        """The extensions this loader claims."""
        return list(self._extensions)

    def load(self, path: str) -> Resource:
        """Read and decode the file.

        Args:
            path: The full path to the file.

        Returns:
            The decoded text.

        Raises:
            FileNotFoundError: If the path does not exist.
            UnicodeDecodeError: If the file is not valid in this encoding.
                Raised rather than replaced: a shader that silently loses a
                character fails to compile with a message about the wrong
                line.
        """
        return TextResource(
            path, assets.read_text(path, self._encoding), self._encoding
        )
