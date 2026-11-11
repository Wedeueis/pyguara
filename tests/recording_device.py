"""A `GraphicsDevice` that records what passes and effects ask of it.

For unit tests of a pass's plumbing -- which shader, which buffers, which
uniforms -- with no GPU. What the shader then draws is the business of the
integration tests that run it on both backends.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from pyguara.graphics.pipeline.device import GraphicsDevice


@dataclass
class Run:
    """One `run` or `draw_instanced` call."""

    shader: Any
    inputs: dict[str, Any]
    uniforms: dict[str, Any]
    output: Any
    blend: str


class RecordingDevice(GraphicsDevice):
    """Remembers every call, in order, and draws nothing."""

    def __init__(self) -> None:
        self.runs: list[Run] = []
        self.clears: list[tuple[Any, tuple[float, ...]]] = []

    @property
    def ctx(self) -> None:
        return None

    def create_target(
        self, name: str, width: int, height: int, *, samples: int, dtype: str
    ) -> Any:
        from unittest.mock import MagicMock

        buffer = MagicMock()
        buffer.name, buffer.width, buffer.height, buffer.dtype = (
            name,
            width,
            height,
            dtype,
        )
        return buffer

    def run(
        self,
        shader: Any,
        inputs: Any,
        uniforms: Any,
        output: Any,
        *,
        blend: Any = "alpha",
        viewport: Any = None,
        clear: Any = None,
    ) -> None:
        shader.pack(uniforms)  # A missing or malformed uniform fails here.
        self.runs.append(Run(shader, dict(inputs), dict(uniforms), output, blend))

    def draw_instanced(
        self,
        shader: Any,
        data: bytes,
        count: int,
        uniforms: Any,
        output: Any,
        *,
        blend: Any = "alpha",
    ) -> None:
        shader.pack(uniforms)
        self.runs.append(
            Run(shader, {"data": data, "count": count}, dict(uniforms), output, blend)
        )

    def clear(self, buffer: Any, rgba: tuple[float, float, float, float]) -> None:
        self.clears.append((buffer, rgba))

    @property
    def last(self) -> Run:
        """The most recent call."""
        return self.runs[-1]
