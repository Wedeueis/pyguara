"""Resource loading exceptions."""


class ResourceError(Exception):
    """Base exception for all resource-related errors."""

    pass


class ResourceLoadError(ResourceError):
    """Raised when a resource fails to load.

    Carries the resolved path *and*, when they differ, the name the caller
    asked for. A game asks for `"hero.png"` and the index resolves it to
    somewhere under `assets/`; a bare `FileNotFoundError` from the loader
    names neither clearly, which is the whole difficulty of debugging a
    missing asset.

    Attributes:
        path: The resolved filesystem path that failed to load.
        reason: A human-readable reason for the failure.
        name: The name or path the caller originally passed, if it differed
            from `path`. None when the caller already gave a real path.
    """

    def __init__(self, path: str, reason: str, name: str | None = None) -> None:
        """Initialize the error.

        Args:
            path: The resolved path to the resource that failed to load.
            reason: A human-readable reason for the failure.
            name: The name the caller asked for, when it differs from
                `path`.
        """
        self.path = path
        self.reason = reason
        self.name = name if name != path else None

        if self.name is None:
            message = f"Failed to load resource '{path}': {reason}"
        else:
            message = (
                f"Failed to load resource '{self.name}' "
                f"(resolved to '{path}'): {reason}"
            )
        super().__init__(message)


class InvalidMetadataError(ResourceError):
    """Raised when resource metadata is malformed or invalid.

    This exception provides detailed information about JSON parsing
    errors including the filename and line/column information when
    available.

    Attributes:
        path: The path to the metadata file.
        reason: A human-readable reason for the failure.
        line: The line number where the error occurred (if available).
        column: The column number where the error occurred (if available).
    """

    def __init__(
        self,
        path: str,
        reason: str,
        line: int | None = None,
        column: int | None = None,
    ) -> None:
        """Initialize the error.

        Args:
            path: The path to the metadata file.
            reason: A human-readable reason for the failure.
            line: The line number where the error occurred (if available).
            column: The column number where the error occurred (if available).
        """
        self.path = path
        self.reason = reason
        self.line = line
        self.column = column

        location = ""
        if line is not None:
            location = f" (line {line}"
            if column is not None:
                location += f", column {column}"
            location += ")"

        super().__init__(f"Invalid metadata in '{path}'{location}: {reason}")
