"""
Interface definition for Resource Loaders.

This module uses Python Protocols to define the Strategy Pattern for
loading files. Any class that implements this protocol can be registered
into the ResourceManager.
"""

from typing import Protocol, runtime_checkable

from .meta import AssetMeta
from .types import Resource


@runtime_checkable
class IResourceLoader(Protocol):
    """A Protocol that defines how to load a specific file format from disk."""

    @property
    def supported_extensions(self) -> list[str]:
        """
        A list of file extensions that this loader can handle.

        Example:
            return ['.png', '.jpg', '.jpeg']

        Returns:
            List[str]: Lowercase extensions including the dot.
        """
        ...

    def load(self, path: str) -> Resource:
        """
        Read the file at the given path and returns a concrete Resource instance.

        Args:
            path (str): The full path to the file.

        Returns:
            Resource: The loaded and wrapped resource (e.g., PygameTexture).

        Raises:
            FileNotFoundError: If the path does not exist.
            IOError: If the file is corrupted or unreadable.
        """
        ...


@runtime_checkable
class IMetaAwareLoader(IResourceLoader, Protocol):
    """Extended loader protocol that supports asset metadata.

    Loaders implementing this protocol can apply import settings from
    `.meta` files during loading.
    """

    def load_with_meta(self, path: str, meta: AssetMeta | None) -> Resource:
        """
        Load a resource with optional metadata settings.

        If meta is None, uses default settings. Otherwise applies the
        settings from the meta object.

        Args:
            path: The full path to the file.
            meta: Optional metadata with import settings.

        Returns:
            Resource: The loaded resource with meta settings applied.
        """
        ...


@runtime_checkable
class ITwoPhaseLoader(IResourceLoader, Protocol):
    """A loader that separates file decode from device upload.

    The split exists because the two halves have different constraints.
    Decoding a file is CPU work on bytes; creating a GPU texture touches a
    GL context that belongs to the main thread. `ResourceManager` can
    therefore run `decode()` on a worker and must run `upload()` on the
    thread that owns the context.

    **`threaded_decode` is a claim about the GIL, and it is measured, not
    guessed.** A worker thread only helps if `decode()` spends its time in
    code that releases the GIL. `pygame-ce` decodes images in SDL with it
    released and scales ~3x on four threads; `json` parses with it held and
    runs *0.71x* threaded -- slower than inline, because the contention is
    real and the parallelism is not. See "Resource loading, and the GIL" in
    `docs/guides/performance.md`.

    So the flag defaults to `False`: a loader that has not been measured is
    run on the main thread, where it is merely slow rather than slow *and*
    fighting the frame for the GIL.
    """

    threaded_decode: bool
    """True only if `decode()` releases the GIL for most of its work."""

    def decode(self, path: str, meta: AssetMeta | None) -> object:
        """Read and decode the file, touching no device state.

        Must be safe to call off the main thread when `threaded_decode` is
        True. Anything that needs a GL context, a display surface, or any
        other main-thread-only resource belongs in `upload()`.

        Args:
            path: The full path to the file.
            meta: Optional metadata with import settings.

        Returns:
            Whatever `upload()` needs -- this loader's own intermediate
            form, opaque to the manager.

        Raises:
            FileNotFoundError: If the path does not exist.
            OSError: If the file is unreadable.
        """
        ...

    def upload(self, path: str, decoded: object, meta: AssetMeta | None) -> Resource:
        """Turn a decoded payload into a Resource, on the main thread.

        Args:
            path: The full path to the file, for error messages.
            decoded: Exactly what this loader's `decode()` returned.
            meta: Optional metadata with import settings.

        Returns:
            The finished resource.
        """
        ...
