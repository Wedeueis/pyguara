"""`pyguara sounds`: build placeholder sound effects from a recipe file."""

from __future__ import annotations

import json
from pathlib import Path

import click

from pyguara.audio.placeholder import DEFAULT_SEED, RecipeError, build_placeholders


@click.command()
@click.argument(
    "recipes",
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
)
@click.argument(
    "out_dir",
    type=click.Path(file_okay=False, path_type=Path),
)
@click.option(
    "--seed",
    type=int,
    default=DEFAULT_SEED,
    show_default=True,
    help="Shared by every sound; change it to reroll their noise.",
)
def sounds(recipes: Path, out_dir: Path, seed: int) -> None:
    """Build placeholder sounds from RECIPES (JSON) into OUT_DIR, one .wav each.

    RECIPES maps each sound's name to its recipe: a tree of tones, noise and
    envelopes. See `pyguara.audio.placeholder` for the format. Every recipe is
    checked before anything is written.

    For example: pyguara sounds data/sounds.json assets/audio/
    """
    try:
        data = json.loads(recipes.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise click.ClickException(f"{recipes}: not valid JSON: {error}") from error
    if not isinstance(data, dict):
        raise click.ClickException(
            f"{recipes}: expected an object mapping sound names to recipes."
        )
    try:
        written = build_placeholders(data, out_dir, seed=seed)
    except RecipeError as error:
        raise click.ClickException(f"{recipes}: {error}") from error
    for path in written:
        click.echo(f"wrote {path}")
