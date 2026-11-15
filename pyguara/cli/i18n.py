"""`pyguara i18n`: tools for a game's locale files."""

from __future__ import annotations

from pathlib import Path

import click

from pyguara.i18n.check import check_directory


@click.group()
def i18n() -> None:
    """Work with a game's locale files (`locales/<locale>.json`)."""


@i18n.command()
@click.argument(
    "directory",
    type=click.Path(exists=True, file_okay=False, path_type=Path),
)
@click.option("--source", default="en", show_default=True, help="The source locale.")
@click.option(
    "--require-reviewed",
    is_flag=True,
    help="Fail on a translation not yet reviewed by a native speaker. For "
    "release builds.",
)
def check(directory: Path, source: str, require_reviewed: bool) -> None:
    """Check every locale in DIRECTORY against the source's strings."""
    report = check_directory(directory, source=source)
    for error in report.errors:
        click.echo(f"error: {error}")
    for warning in report.warnings:
        click.echo(f"warning: {warning}")
    click.echo(
        f"{len(report.locales)} locales, {len(report.errors)} errors, "
        f"{len(report.warnings)} warnings"
    )
    if report.errors or (require_reviewed and report.warnings):
        raise SystemExit(1)
