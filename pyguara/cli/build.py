"""Build command for creating standalone executables.

Wraps PyInstaller to package PyGuara games into distributable executables,
automatically bundling assets and engine runtime.

Usage:
    pyguara build game.py --output dist/
    pyguara build game.py --name MyGame --onefile
    pyguara build game.py --assets assets/ --icon icon.ico
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path
from typing import List, Optional

import click
import logging

logger = logging.getLogger(__name__)


def _check_pyinstaller() -> bool:
    """Check if PyInstaller is available."""
    try:
        import PyInstaller  # noqa: F401

        return True
    except ImportError:
        return False


def _find_assets_folder(project_path: Path) -> Optional[Path]:
    """Find the assets folder relative to the project."""
    candidates = ["assets", "Assets", "resources", "Resources", "data", "Data"]
    project_dir = project_path.parent if project_path.is_file() else project_path

    for candidate in candidates:
        assets_path = project_dir / candidate
        if assets_path.exists() and assets_path.is_dir():
            return assets_path

    return None


def _build_pyinstaller_args(
    entry_point: Path,
    output_dir: Path,
    name: Optional[str],
    onefile: bool,
    windowed: bool,
    icon: Optional[Path],
    assets_dirs: List[Path],
    extra_data: List[str],
    hidden_imports: List[str],
    clean: bool,
    debug: bool,
) -> List[str]:
    """Build the PyInstaller command arguments."""
    args = ["pyinstaller"]

    # Entry point
    args.append(str(entry_point))

    # Output directory
    args.extend(["--distpath", str(output_dir)])
    args.extend(["--workpath", str(output_dir / "build")])
    args.extend(["--specpath", str(output_dir)])

    # Name
    if name:
        args.extend(["--name", name])

    # Package type
    if onefile:
        args.append("--onefile")
    else:
        args.append("--onedir")

    # Windowed mode (no console)
    if windowed:
        args.append("--windowed")

    # Icon
    if icon and icon.exists():
        args.extend(["--icon", str(icon)])

    # Assets directories
    for assets_dir in assets_dirs:
        if assets_dir.exists():
            # PyInstaller data format: source:destination
            dest_name = assets_dir.name
            args.extend(["--add-data", f"{assets_dir}{_path_separator()}{dest_name}"])

    # Extra data files
    for data_spec in extra_data:
        args.extend(["--add-data", data_spec])

    # Hidden imports for PyGuara dependencies
    default_hidden_imports = [
        "pygame",
        "pygame.locals",
        "pymunk",
        "moderngl",
        "numpy",
        "PIL",
        "PIL.Image",
        "dataclasses_json",
        "msgpack",
    ]

    for hidden in default_hidden_imports + hidden_imports:
        args.extend(["--hidden-import", hidden])

    # Clean build
    if clean:
        args.append("--clean")

    # Debug mode
    if debug:
        args.append("--debug=all")

    # Suppress confirmation
    args.append("--noconfirm")

    return args


def _path_separator() -> str:
    """Return the path separator for PyInstaller --add-data."""
    return ";" if sys.platform == "win32" else ":"


@click.command()
@click.argument(
    "entry_point",
    type=click.Path(exists=True, file_okay=True, dir_okay=False, path_type=Path),
)
@click.option(
    "-o",
    "--output",
    type=click.Path(file_okay=False, dir_okay=True, path_type=Path),
    default=Path("dist"),
    help="Output directory for the build (default: dist/)",
)
@click.option(
    "-n",
    "--name",
    type=str,
    default=None,
    help="Name of the executable (default: entry point filename)",
)
@click.option(
    "--onefile/--onedir",
    default=False,
    help="Create a single executable file or a directory (default: onedir)",
)
@click.option(
    "--windowed/--console",
    default=True,
    help="Hide console window (default: windowed)",
)
@click.option(
    "--icon",
    type=click.Path(exists=True, file_okay=True, dir_okay=False, path_type=Path),
    default=None,
    help="Path to icon file (.ico on Windows, .icns on macOS)",
)
@click.option(
    "-a",
    "--assets",
    "assets_dirs",
    type=click.Path(exists=True, file_okay=False, dir_okay=True, path_type=Path),
    multiple=True,
    help="Asset directories to include (can be specified multiple times)",
)
@click.option(
    "--add-data",
    "extra_data",
    type=str,
    multiple=True,
    help="Additional data files in PyInstaller format (source:dest)",
)
@click.option(
    "--hidden-import",
    "hidden_imports",
    type=str,
    multiple=True,
    help="Additional hidden imports (can be specified multiple times)",
)
@click.option(
    "--clean",
    is_flag=True,
    default=False,
    help="Clean PyInstaller cache and build files before building",
)
@click.option(
    "--debug",
    is_flag=True,
    default=False,
    help="Enable PyInstaller debug mode",
)
@click.option(
    "--dry-run",
    is_flag=True,
    default=False,
    help="Print the PyInstaller command without executing",
)
def build(
    entry_point: Path,
    output: Path,
    name: Optional[str],
    onefile: bool,
    windowed: bool,
    icon: Optional[Path],
    assets_dirs: tuple[Path, ...],
    extra_data: tuple[str, ...],
    hidden_imports: tuple[str, ...],
    clean: bool,
    debug: bool,
    dry_run: bool,
) -> None:
    r"""Build a standalone executable from a PyGuara game.

    ENTRY_POINT is the main Python file of your game (e.g., main.py).

    Examples:
        \b
        # Basic build
        pyguara build main.py

        \b
        # Custom output and name
        pyguara build main.py --output builds/ --name MyGame

        \b
        # Single file with icon
        pyguara build main.py --onefile --icon assets/icon.ico

        \b
        # Include multiple asset directories
        pyguara build main.py -a assets/ -a levels/
    """
    # Auto-detect assets folder if none specified
    assets_list = list(assets_dirs)
    if not assets_list:
        detected_assets = _find_assets_folder(entry_point)
        if detected_assets:
            click.echo(
                f"Auto-detected assets folder: {click.style(str(detected_assets), fg='cyan')}"
            )
            assets_list.append(detected_assets)

    # Build command arguments
    args = _build_pyinstaller_args(
        entry_point=entry_point,
        output_dir=output,
        name=name,
        onefile=onefile,
        windowed=windowed,
        icon=icon,
        assets_dirs=assets_list,
        extra_data=list(extra_data),
        hidden_imports=list(hidden_imports),
        clean=clean,
        debug=debug,
    )

    if dry_run:
        click.echo(click.style("Dry run - would execute:", fg="yellow", bold=True))
        click.echo(" ".join(args))
        return

    # Check for PyInstaller (only if not dry-run)
    if not _check_pyinstaller():
        click.echo(
            click.style("Error: ", fg="red", bold=True)
            + "PyInstaller is not installed.\n"
            "Install it with: " + click.style("pip install pyinstaller", fg="cyan"),
            err=True,
        )
        raise SystemExit(1)

    # Print build configuration
    click.echo(click.style("PyGuara Build", fg="green", bold=True))
    click.echo(f"  Entry point: {click.style(str(entry_point), fg='cyan')}")
    click.echo(f"  Output: {click.style(str(output), fg='cyan')}")
    click.echo(f"  Mode: {click.style('onefile' if onefile else 'onedir', fg='cyan')}")
    if assets_list:
        click.echo(f"  Assets: {', '.join(str(a) for a in assets_list)}")
    click.echo()

    # Create output directory
    output.mkdir(parents=True, exist_ok=True)

    # Run PyInstaller
    click.echo(click.style("Running PyInstaller...", fg="yellow"))
    logger.info("Running PyInstaller with args: %s", args)

    try:
        result = subprocess.run(args, check=True)
        if result.returncode == 0:
            click.echo()
            click.echo(click.style("Build successful!", fg="green", bold=True))

            # Show output location
            exe_name = name or entry_point.stem
            if onefile:
                if sys.platform == "win32":
                    exe_path = output / f"{exe_name}.exe"
                else:
                    exe_path = output / exe_name
            else:
                exe_path = output / exe_name

            click.echo(f"Output: {click.style(str(exe_path), fg='cyan')}")

            # Clean up build artifacts
            build_dir = output / "build"
            if build_dir.exists():
                shutil.rmtree(build_dir)
                logger.debug("Cleaned up build directory")

    except subprocess.CalledProcessError as e:
        click.echo(
            click.style("Build failed!", fg="red", bold=True)
            + f" (exit code: {e.returncode})",
            err=True,
        )
        raise SystemExit(e.returncode)
    except FileNotFoundError:
        click.echo(
            click.style("Error: ", fg="red", bold=True)
            + "PyInstaller executable not found in PATH",
            err=True,
        )
        raise SystemExit(1)
