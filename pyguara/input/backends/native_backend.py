"""Input backends in the native extension: what the wgpu backend uses.

The keyboard and mouse arrive with the window (`NativeWindow`); what is
here is the rest of what SDL provided through pygame.
"""

from __future__ import annotations

from typing import Any

from pyguara import native


class NativeClipboard:
    """The desktop clipboard, through arboard.

    Implements `pyguara.ui.clipboard.Clipboard`, as `PygameClipboard` does,
    with the same promise: **no call raises.** A clipboard that cannot be
    opened -- no clipboard manager, no display -- reads as empty and
    swallows writes, because a text field is no place to surface either.
    """

    def __init__(self) -> None:
        """Open the clipboard, or remember that it cannot be."""
        self._clipboard: Any = None
        try:
            extension = native.require_extension("The native clipboard")
            self._clipboard = extension.NativeClipboard()
        except RuntimeError:
            self._clipboard = None

    def get_text(self) -> str:
        """Return the clipboard's text, or `""` when there is none to read."""
        if self._clipboard is None:
            return ""
        return str(self._clipboard.get_text())

    def set_text(self, text: str) -> None:
        """Put `text` on the clipboard; a refusal is swallowed."""
        if self._clipboard is not None:
            self._clipboard.set_text(text)
