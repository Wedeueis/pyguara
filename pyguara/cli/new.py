"""`pyguara new`: a project that runs.

Writes a package with one scene, an entry point built on `pyguara.run()`,
a `pyproject.toml`, an assets folder and the agent instruction files.
"""

from __future__ import annotations

import keyword
import re
import sys
from pathlib import Path

import click

import pyguara
from pyguara.cli.studio import instructions_command

_PYPROJECT = """\
[project]
name = "{distribution}"
version = "0.1.0"
description = "A game built on the PyGuara engine."
requires-python = ">=3.12"
dependencies = ["pyguara>={engine_version}"]

[project.scripts]
{distribution} = "{package}.__main__:main"

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["{package}"]
"""

_INIT = '''\
"""{title}, a game built on the PyGuara engine."""
'''

_MAIN = '''\
"""The entry point: `python -m {package}`."""

import pyguara
from pyguara.config.types import GameConfig

from {package}.scenes import MainScene


def configure(config: GameConfig) -> None:
    """Name the window and size it, before it is created."""
    config.display.title = "{title}"
    config.display.screen_width = 1280
    config.display.screen_height = 720


def main() -> None:
    """Run the game until its window closes."""
    pyguara.run(MainScene, configure=configure)


if __name__ == "__main__":
    main()
'''

_SCENES = '''\
"""The game's scenes."""

from dataclasses import dataclass

from pyguara.common.components import Transform
from pyguara.common.types import Color, Rect, Vector2
from pyguara.ecs.component import BaseComponent
from pyguara.graphics.protocols import IRenderer, UIRenderer
from pyguara.scene.base import Scene

BACKGROUND = Color(20, 24, 32)
BOX = Color(240, 180, 60)
BOX_SIZE = 32
BOX_SPEED = 240.0
TRACK_LENGTH = 1280.0


@dataclass(slots=True)
class Velocity(BaseComponent):
    """Pixels per second. Components are data; the scene moves them."""

    value: Vector2 = Vector2(0, 0)


class MainScene(Scene):
    """One box crossing the window, to show the loop is running."""

    def on_enter(self) -> None:
        """Create the box."""
        box = self.entity_manager.create_entity()
        box.add_component(Transform(position=Vector2(0, 344)))
        box.add_component(Velocity(Vector2(BOX_SPEED, 0)))

    def fixed_update(self, fixed_dt: float) -> None:
        """Move everything that has a velocity, at the fixed rate."""
        for entity in self.entity_manager.get_entities_with(Transform, Velocity):
            transform = entity.get_component(Transform)
            position = transform.position + (
                entity.get_component(Velocity).value * fixed_dt
            )
            transform.position = Vector2(position.x % TRACK_LENGTH, position.y)
            self.entity_manager.notify_component_changed(entity.id, Transform)

    def update(self, dt: float) -> None:
        """Nothing runs at the display rate yet."""

    def render(self, world_renderer: IRenderer, ui_renderer: UIRenderer) -> None:
        """Draw every entity as a box."""
        world_renderer.clear(BACKGROUND)
        for entity in self.entity_manager.get_entities_with(Transform):
            position = entity.get_component(Transform).position
            world_renderer.draw_rect(
                Rect(int(position.x), int(position.y), BOX_SIZE, BOX_SIZE), BOX
            )

    def on_exit(self) -> None:
        """Nothing to release."""
'''

_README = """\
# {title}

A game built on the [PyGuara](https://pypi.org/project/pyguara/) engine.

```bash
python -m {package}
```

- `{package}/__main__.py` is the entry point: the window's title and size,
  and the first scene.
- `{package}/scenes.py` holds the scenes.
- `assets/` is for textures, sounds, fonts and data.
- `AGENTS.md` tells a coding agent how the engine is used. Regenerate it
  with `pyguara studio instructions` after the project changes.
"""

_GITIGNORE = """\
__pycache__/
*.py[cod]
.venv/
dist/
build/
logs/
saves/
"""

_NAME = re.compile(r"[A-Za-z][A-Za-z0-9_-]*")


def package_name(name: str) -> str:
    """Turn a project name into the name of its Python package.

    Args:
        name: The project name as typed.

    Returns:
        The name in lower case with hyphens as underscores.

    Raises:
        click.BadParameter: If the result could not be imported, or would
            shadow the engine or a standard library module.
    """
    if not _NAME.fullmatch(name):
        raise click.BadParameter(
            f"{name!r} is not a usable project name. Start with a letter and "
            "use only letters, digits, hyphens and underscores."
        )
    package = name.lower().replace("-", "_")
    if keyword.iskeyword(package):
        raise click.BadParameter(f"{package!r} is a Python keyword.")
    if package == "pyguara" or package in sys.stdlib_module_names:
        raise click.BadParameter(
            f"A package named {package!r} would shadow the module of the same "
            "name, and nothing that imports it would work."
        )
    return package


def scaffold(directory: Path, name: str) -> list[Path]:
    """Write a new project's files into `directory`.

    Args:
        directory: Where the project goes. Created if missing.
        name: The project name; see `package_name`.

    Returns:
        The files written, in the order they were written.

    Raises:
        click.BadParameter: If `name` is not usable.
        click.ClickException: If `directory` exists and is not empty.
    """
    package = package_name(name)
    if directory.exists() and any(directory.iterdir()):
        raise click.ClickException(
            f"{directory} exists and is not empty. Choose another name, or "
            "remove it first."
        )

    values = {
        "package": package,
        "distribution": package.replace("_", "-"),
        "title": name.replace("-", " ").replace("_", " ").title(),
        "engine_version": pyguara.__version__,
    }
    files = {
        "pyproject.toml": _PYPROJECT,
        "README.md": _README,
        ".gitignore": _GITIGNORE,
        "assets/.gitkeep": "",
        f"{package}/__init__.py": _INIT,
        f"{package}/__main__.py": _MAIN,
        f"{package}/scenes.py": _SCENES,
    }

    written: list[Path] = []
    for relative, template in files.items():
        path = directory / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(template.format(**values), encoding="utf-8")
        written.append(path)
    return written


@click.command("new")
@click.argument("name")
@click.option(
    "--directory",
    type=click.Path(file_okay=False, path_type=Path),
    default=None,
    help="Where to create the project. Defaults to ./NAME.",
)
@click.option(
    "--no-instructions",
    is_flag=True,
    help="Skip AGENTS.md and the per-tool files that import it.",
)
@click.pass_context
def new(
    context: click.Context, name: str, directory: Path | None, no_instructions: bool
) -> None:
    """Create a project that runs: one scene, an entry point, an assets folder.

    Args:
        context: The Click context, used to run `studio instructions`.
        name: The project name. Its package is the name in lower case with
            hyphens as underscores.
        directory: Where to create it. Defaults to a folder named `name`.
        no_instructions: Skip the agent instruction files.
    """
    target = (directory if directory is not None else Path(name)).resolve()
    package = package_name(name)

    for path in scaffold(target, name):
        click.echo(f"wrote {path.relative_to(target)}")

    if not no_instructions:
        context.invoke(
            instructions_command,
            project=target,
            check=False,
            dry_run=False,
            no_shims=False,
            summary=None,
        )

    click.echo(f"\nCreated {name} in {target}. Run it with:")
    click.echo(f"\n    cd {target}\n    python -m {package}")
