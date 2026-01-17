"""Resource loading exceptions."""


class ResourceError(Exception):
    """Base exception for all resource-related errors."""

    pass


class ResourceLoadError(ResourceError):
    """Raised when a resource fails to load.

    Attributes:
        path: The path to the resource that failed to load.
        reason: A human-readable reason for the failure.
    """

    def __init__(self, path: str, reason: str) -> None:
        """Initialize the error.

        Args:
            path: The path to the resource that failed to load.
            reason: A human-readable reason for the failure.
        """
        self.path = path
        self.reason = reason
        super().__init__(f"Failed to load resource '{path}': {reason}")


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
