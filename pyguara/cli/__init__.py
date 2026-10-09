"""Command line interface for PyGuara game engine.

Provides offline tools for asset processing, project management, and building
standalone executables.

Usage:
    pyguara --help
    pyguara build --help
    pyguara atlas --help
"""

import click

# Alias on import: a bare ``from ... import build`` would rebind the
# ``pyguara.cli.build`` *module* attribute to the command object, so
# ``import pyguara.cli.build`` would hand back a Click Command instead of the
# module. Keep the submodules reachable by dotted path.
from pyguara.cli.atlas_generator import atlas as atlas_command
from pyguara.cli.build import build as build_command
from pyguara.cli.studio import studio as studio_command

__all__ = ["main"]


@click.group()
@click.version_option(package_name="pyguara")
def main() -> None:
    """Provide CLI tools for the PyGuara game engine."""
    pass


main.add_command(build_command)
main.add_command(atlas_command)
main.add_command(studio_command)

# No `if __name__ == "__main__"` here: inside a package's `__init__`,
# `__name__` is `pyguara.cli` and the block could never run. `__main__.py`
# beside this file is what makes `python -m pyguara.cli` work.
