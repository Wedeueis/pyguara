"""Command line interface for PyGuara game engine.

Provides offline tools for asset processing, project management, and building
standalone executables.

Usage:
    pyguara --help
    pyguara build --help
    pyguara atlas --help
"""

import click

from pyguara.cli.build import build
from pyguara.cli.atlas_generator import atlas


@click.group()
@click.version_option(package_name="pyguara")
def main() -> None:
    """Provide CLI tools for the PyGuara game engine."""
    pass


main.add_command(build)
main.add_command(atlas)


if __name__ == "__main__":
    main()
