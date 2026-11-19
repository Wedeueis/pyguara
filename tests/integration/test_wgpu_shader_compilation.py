"""Every shader the engine ships compiles on wgpu.

A WGSL error is a runtime error: nothing compiles a shader until a frame
first draws with it, and a pass a game uses rarely -- a boss's storm, a
material on one sprite -- would fail only then, mid-game. So each is
compiled here, as the device compiles it.

Found by walking the modules for shader constants rather than by a list,
so a new effect is covered the moment it exists.
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path
from typing import Any

import pytest

import pyguara
from pyguara.graphics.pipeline.device import (
    FullscreenShader,
    InstancedShader,
    SpriteShader,
)
from tools.demo_list import DEMO_ROOT, EXAMPLES_DIR


def _modules() -> list[str]:
    """Every module under `pyguara.graphics` and the demos, by file.

    Files rather than `pkgutil.walk_packages`, which does not descend into
    a directory with no `__init__.py` -- and `graphics/pipeline` and
    `graphics/backends` have none, so the walk silently missed every pass.
    """
    engine = Path(pyguara.__file__).resolve().parent.parent
    names = []
    for root, folder in (
        (engine, engine / "pyguara" / "graphics"),
        (DEMO_ROOT, EXAMPLES_DIR),
    ):
        for path in sorted(folder.rglob("*.py")):
            relative = path.relative_to(root).with_suffix("")
            names.append(".".join(relative.parts))
    if str(DEMO_ROOT) not in sys.path:
        sys.path.insert(0, str(DEMO_ROOT))
    return names


def _shaders() -> dict[str, Any]:
    found: dict[str, Any] = {}
    for name in _modules():
        try:
            loaded = importlib.import_module(name)
        except Exception:  # a script, or an optional dependency
            continue
        for attr, value in vars(loaded).items():
            if isinstance(value, (FullscreenShader, InstancedShader, SpriteShader)):
                found.setdefault(f"{name}.{attr}", value)
    return found


SHADERS = _shaders()


def test_the_walk_finds_the_engine_shaders() -> None:
    """Not an empty parametrisation passing on nothing."""
    names = {name.rsplit(".", 1)[1] for name in SHADERS}
    assert {"COMPOSITE", "BLIT", "LIGHTS", "STORM", "HEAT_HAZE", "SHAPES"} <= names


@pytest.mark.integration
@pytest.mark.parametrize("name", sorted(SHADERS))
def test_the_shader_compiles(name: str, wgpu_frame: Any) -> None:
    shader = SHADERS[name]
    gpu = wgpu_frame(8, 8).gpu
    if isinstance(shader, SpriteShader):
        gpu.create_material(shader.wgsl_source(), shader.uniform_bytes, shader.texture)
    elif isinstance(shader, InstancedShader):
        gpu.create_effect(
            shader.wgsl_source(), 0, shader.uniform_bytes, list(shader.floats)
        )
    else:
        gpu.create_effect(
            shader.wgsl_source(), len(shader.inputs), shader.uniform_bytes
        )
