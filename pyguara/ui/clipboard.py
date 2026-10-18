"""The clipboard, as something `pyguara.ui` can reach without pygame.

Cut, copy and paste need somewhere to put the text, and the only real
clipboard is the one the windowing system owns -- which here is SDL,
reached through pygame. `pyguara/ui` may not import a backend, so the
widget takes a `Clipboard` and the application decides which one.

The default is deliberately **not** the system clipboard. A widget
constructed as `TextInput(position)` gets `InMemoryClipboard`, which is
process-local: copy in one field and paste into another and it works,
copy from the browser and it does not. That is a smaller promise than a
`TextInput` silently reaching into the OS clipboard the moment it is
constructed -- and a test, a headless run and a tool with no window all
need a clipboard that cannot fail.

`pyguara.input.backends.pygame_backend.PygameClipboard` is the real one.
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
