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

__all__ = ["main"]


@click.group()
@click.version_option(package_name="pyguara")
def main() -> None:
    """Provide CLI tools for the PyGuara game engine."""
    pass


main.add_command(build_command)
main.add_command(atlas_command)


if __name__ == "__main__":
    main()
