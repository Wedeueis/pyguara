"""The clipboard, as something `pyguara.ui` can reach without pygame.

`pyguara/ui` may not import a backend, so a widget takes a `Clipboard`
and the application decides which one.

The default is `InMemoryClipboard`, which is process-local and cannot
fail: copying between two fields works, and copying from another
program does not. `pyguara.input.backends.NativeClipboard` (wgpu) and
`pyguara.input.backends.PygameClipboard` (pygame) are the system ones.
"""

from typing import Protocol, runtime_checkable

__all__ = ["Clipboard", "InMemoryClipboard"]


@runtime_checkable
class Clipboard(Protocol):
    """Somewhere to put cut text and take pasted text from."""

    def get_text(self) -> str:
        """Return the clipboard's current text.

        Returns:
            The text, or `""` when the clipboard is empty or holds
            something that is not text. Never None: a paste of nothing
            should insert nothing, not raise.
        """
        ...

    def set_text(self, text: str) -> None:
        """Replace the clipboard's contents.

        Args:
            text: The text to put there.
        """
        ...


class InMemoryClipboard:
    """A clipboard that never leaves the process.

    What a `TextInput` gets unless it is given something better. Copy and
    paste work between fields in the same game; nothing is shared with
    the rest of the desktop.
    """

    def __init__(self, text: str = "") -> None:
        """Start holding `text`.

        Args:
            text: Initial contents.
        """
        self._text = text

    def get_text(self) -> str:
        """Return the stored text."""
        return self._text

    def set_text(self, text: str) -> None:
        """Replace the stored text.

        Args:
            text: The new contents.
        """
        self._text = text
