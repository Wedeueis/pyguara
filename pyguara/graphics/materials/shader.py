"""Shader wrapper and caching system.

This module provides a high-level wrapper around ModernGL shader programs
with automatic caching to avoid redundant compilation.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any, Optional

if TYPE_CHECKING:
    import moderngl


@dataclass(slots=True)
class Shader:
    """Wrapper around a ModernGL shader program.

    Provides a higher-level interface for managing shader uniforms
    and lifecycle.
    """

    name: str
    program: "moderngl.Program"

    # Cached uniform locations
    _uniform_cache: dict[str, Any] = field(default_factory=dict, repr=False)

    def use(self) -> None:
        """Bind this shader for rendering."""
        # ModernGL programs are automatically bound when setting uniforms
        # or when a VAO using this program is rendered
        pass

    def set_uniform(self, name: str, value: Any) -> None:
        """Set a uniform value.

        Args:
            name: The uniform name in the shader.
            value: The value to set. Type depends on the uniform:
                - float, int: scalar uniforms
                - tuple: vec2, vec3, vec4
                - bytes: raw data (matrices)
        """
        if name not in self._uniform_cache:
            try:
                self._uniform_cache[name] = self.program[name]
            except KeyError:
                # Uniform doesn't exist in shader (might be optimized out)
                return

        uniform = self._uniform_cache[name]
        if hasattr(uniform, "write"):
            # Matrix or array uniform
            if isinstance(value, bytes):
                uniform.write(value)
            else:
                uniform.value = value
        else:
            uniform.value = value

    def get_uniform(self, name: str) -> Any:
        """Get a uniform object for direct manipulation.

        Args:
            name: The uniform name.

        Returns:
            The ModernGL uniform object, or None if not found.
        """
        if name not in self._uniform_cache:
            try:
                self._uniform_cache[name] = self.program[name]
            except KeyError:
                return None
        return self._uniform_cache[name]

    def release(self) -> None:
        """Release the shader program."""
        if self.program is not None:
            self.program.release()


class ShaderCache:
    """Cache for compiled shader programs.

    Prevents redundant shader compilation by caching programs
    indexed by their source files.
    """

    def __init__(self, ctx: "moderngl.Context") -> None:
        """Initialize the shader cache.

        Args:
            ctx: The ModernGL context for compiling shaders.
        """
        self._ctx = ctx
        self._cache: dict[str, Shader] = {}

    def get_or_compile(
        self,
        name: str,
        vertex_source: str,
        fragment_source: str,
        *,
        geometry_source: Optional[str] = None,
    ) -> Shader:
        """Get a cached shader or compile a new one.

        Args:
            name: Unique identifier for this shader.
            vertex_source: GLSL vertex shader source code.
            fragment_source: GLSL fragment shader source code.
            geometry_source: Optional geometry shader source.

        Returns:
            The compiled Shader instance.
        """
        if name in self._cache:
            return self._cache[name]

        program = self._ctx.program(
            vertex_shader=vertex_source,
            fragment_shader=fragment_source,
            geometry_shader=geometry_source,
        )

        shader = Shader(name=name, program=program)
        self._cache[name] = shader
        return shader

    def get_or_load(
        self,
        name: str,
        vertex_path: Path,
        fragment_path: Path,
        *,
        geometry_path: Optional[Path] = None,
    ) -> Shader:
        """Get a cached shader or load and compile from files.

        Args:
            name: Unique identifier for this shader.
            vertex_path: Path to vertex shader file.
            fragment_path: Path to fragment shader file.
            geometry_path: Optional path to geometry shader file.

        Returns:
            The compiled Shader instance.
        """
        if name in self._cache:
            return self._cache[name]

        with open(vertex_path, "r") as f:
            vertex_source = f.read()

        with open(fragment_path, "r") as f:
            fragment_source = f.read()

        geometry_source = None
        if geometry_path is not None:
            with open(geometry_path, "r") as f:
                geometry_source = f.read()

        return self.get_or_compile(
            name, vertex_source, fragment_source, geometry_source=geometry_source
        )

    def get(self, name: str) -> Optional[Shader]:
        """Get a shader by name.

        Args:
            name: The shader identifier.

        Returns:
            The shader if found, None otherwise.
        """
        return self._cache.get(name)

    def release_all(self) -> None:
        """Release all cached shaders."""
        for shader in self._cache.values():
            shader.release()
        self._cache.clear()

    def release(self, name: str) -> None:
        """Release a specific shader.

        Args:
            name: The shader identifier.
        """
        if name in self._cache:
            self._cache[name].release()
            del self._cache[name]
