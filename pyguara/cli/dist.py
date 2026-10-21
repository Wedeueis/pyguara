"""Store distribution templates for a built game.

`pyguara build` produces an executable. Getting that executable in front
of players is a per-store job whose conventions are easy to get subtly
wrong and hard to notice afterwards -- a Steam build that lets a customer
bypass the client, an itch.io upload no player is ever offered because its
channel name does not name a platform. Both ship successfully and both
are broken for somebody.

This module writes the scripts rather than running them. Uploading needs
`steamcmd` or `butler`, a store account and, for Steam, a Steam Guard
code; none of that belongs inside a game engine, and a command that
wrapped it would be a thin shell around credentials it cannot hold. So
every command here generates files, prints what to run, and stops.

Usage:
    pyguara dist icons logo.png --out build/icons
    pyguara dist steam --app-id 480 --depot-id 481 --content dist/MyGame
    pyguara dist itch --target studio/my-game --content dist/MyGame
"""

from __future__ import annotations

import os
import stat
from pathlib import Path

import click

from pyguara.log import get_logger

logger = get_logger(__name__)


# Windows picks the size it wants out of a single `.ico`, so one file has
# to carry all of them: 256 for the Explorer tile, 16 for the title bar.
# Pillow writes every size listed that is not larger than the source.
_ICO_SIZES = [(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]

# itch.io reads the *channel name* to decide which platform an upload is
# for, and an upload with no platform tag is offered to nobody. These are
# the substrings butler recognises.
# https://itch.io/docs/butler/pushing.html
_ITCH_PLATFORM_TOKENS = {
    "windows": ("win", "windows"),
    "macos": ("mac", "osx"),
    "linux": ("linux",),
    "android": ("android",),
}

_STEAM_APPID_FILE = "steam_appid.txt"


def _relative_or_absolute(target: Path, start: Path) -> str:
    """Return `target` relative to `start`, or absolute if it cannot be.

    The generated scripts resolve their paths against the directory they
    live in, so a relative path keeps the whole folder movable and
    commitable -- which matters, because these files end up in a
    repository and then in CI. `relpath` raises across Windows drive
    letters, and an absolute path is the only correct answer there.

    Args:
        target: The path to express.
        start: The directory the result is relative to.

    Returns:
        The path as it should appear in a generated script.
    """
    try:
        return os.path.relpath(target.resolve(), start.resolve())
    except ValueError:  # different drives on Windows
        return str(target.resolve())


def write_icons(source: Path, out_dir: Path) -> dict[str, Path]:
    """Write one source image out as every platform's icon format.

    PyInstaller does not convert: it wants `.ico` on Windows and `.icns`
    on macOS and fails or warns on anything else, which is why a project
    with a single `logo.png` cannot be built for Windows without this
    step. Pillow is already a core dependency, so no new one is needed.

    Args:
        source: The image to convert. Square and at least 256x256 is
            what every target wants; smaller is accepted and produces
            fewer `.ico` sizes.
        out_dir: Directory to write `icon.ico`, `icon.icns` and
            `icon.png` into. Created if absent.

    Returns:
        A mapping of platform name ("windows", "macos", "linux") to the
        icon written for it.

    Raises:
        click.ClickException: If the source cannot be opened as an image.
    """
    from PIL import Image, UnidentifiedImageError

    out_dir.mkdir(parents=True, exist_ok=True)

    try:
        image = Image.open(source)
    except (UnidentifiedImageError, OSError) as error:
        raise click.ClickException(
            f"{source} could not be read as an image: {error}"
        ) from error

    # RGBA throughout: an `.ico` from a palette image loses its alpha and
    # a game icon with a white box around it is the usual symptom.
    icon = image.convert("RGBA")

    if icon.width != icon.height:
        logger.warning(
            "%s is %dx%d, not square. Every store stretches a non-square "
            "icon differently; crop it first if the result looks wrong.",
            source,
            icon.width,
            icon.height,
        )

    ico_path = out_dir / "icon.ico"
    icns_path = out_dir / "icon.icns"
    png_path = out_dir / "icon.png"

    sizes = [size for size in _ICO_SIZES if size[0] <= icon.width]
    icon.save(ico_path, format="ICO", sizes=sizes or [(icon.width, icon.height)])
    icon.save(icns_path, format="ICNS")
    icon.save(png_path, format="PNG")

    return {"windows": ico_path, "macos": icns_path, "linux": png_path}


def _app_build_vdf(
    app_id: str,
    depot_id: str,
    description: str,
    content_root: str,
    build_output: str,
    branch: str,
    preview: bool,
) -> str:
    """Return the `app_build_<appid>.vdf` Steam content-builder script.

    Keys and casing follow Valve's own example at
    https://partner.steamgames.com/doc/sdk/uploading.
    """
    return f"""\
// Steam content-builder app build script, generated by `pyguara dist steam`.
//
// Run it with the SDK's builder:
//   steamcmd +login <user> +run_app_build <abs path to this file> +quit
//
// Paths below are relative to this file's directory.
"AppBuild"
{{
\t"AppID"\t\t"{app_id}"
\t"Desc"\t\t"{description}"

\t// 1 uploads and validates without making the build available. Valve
\t// recommends it for a first run: a wrong ContentRoot produces a
\t// perfectly successful build of the wrong files.
\t"Preview"\t"{1 if preview else 0}"

\t// The branch to set live afterwards. Empty means "do not set live",
\t// which is the only safe default -- naming "default" here would ship
\t// to every customer the moment the upload finished.
\t"SetLive"\t"{branch}"

\t"ContentRoot"\t"{content_root}"
\t"BuildOutput"\t"{build_output}"

\t"Depots"
\t{{
\t\t"{depot_id}"\t"depot_build_{depot_id}.vdf"
\t}}
}}
"""


def _depot_build_vdf(depot_id: str, content_root: str) -> str:
    """Return the `depot_build_<depotid>.vdf` script.

    One deliberate inclusion: `steam_appid.txt` is excluded explicitly.
    See `_steam_readme` for why that file must never reach a depot.

    The root key is `DepotBuildConfig`, which is what the SDK's bundled
    sample scripts and every working upload pipeline use. Valve's
    documentation page spells it `DepotBuild` instead. The conflict is
    real and unresolved here, so it is named in the generated README
    rather than papered over.
    """
    return f"""\
// Steam depot build script, generated by `pyguara dist steam`.
"DepotBuildConfig"
{{
\t"DepotID"\t"{depot_id}"
\t"ContentRoot"\t"{content_root}"

\t"FileMapping"
\t{{
\t\t"LocalPath"\t"*"
\t\t"DepotPath"\t"."
\t\t"recursive"\t"1"
\t}}

\t// Never ship this: it overrides the App ID Steam supplies and makes
\t// SteamAPI_RestartAppIfNecessary return false, so a customer who
\t// launches the executable directly bypasses the Steam client.
\t"FileExclusion"\t"{_STEAM_APPID_FILE}"

\t// Debug symbols are large and are not for players.
\t"FileExclusion"\t"*.pdb"
}}
"""


def _steam_upload_script(app_id: str, posix: bool) -> str:
    """Return a runnable wrapper around `steamcmd +run_app_build`."""
    script = f"app_build_{app_id}.vdf"
    if posix:
        return f"""\
#!/usr/bin/env bash
# Generated by `pyguara dist steam`. Uploads the depot described by
# scripts/{script}.
#
# STEAM_USERNAME must be a build account, and the first interactive login
# on this machine has to answer Steam Guard before any of this works
# unattended.
set -euo pipefail

: "${{STEAM_USERNAME:?set STEAM_USERNAME to your Steam build account}}"
here="$(cd "$(dirname "${{BASH_SOURCE[0]}}")" && pwd)"

steamcmd \\
\t+login "$STEAM_USERNAME" \\
\t+run_app_build "$here/scripts/{script}" \\
\t+quit
"""
    return f"""\
@echo off
REM Generated by `pyguara dist steam`. Uploads the depot described by
REM scripts\\{script}.
REM
REM STEAM_USERNAME must be a build account, and the first interactive
REM login on this machine has to answer Steam Guard before any of this
REM works unattended.
if "%STEAM_USERNAME%"=="" (
\techo set STEAM_USERNAME to your Steam build account
\texit /b 1
)

steamcmd.exe +login "%STEAM_USERNAME%" ^
\t+run_app_build "%~dp0scripts\\{script}" ^
\t+quit
"""


def _steam_readme(app_id: str, depot_id: str, content: str) -> str:
    """Return the README that goes beside the generated scripts."""
    return f"""\
# Steam upload for app {app_id}

Generated by `pyguara dist steam`. Four files:

| file | what it is |
| --- | --- |
| `scripts/app_build_{app_id}.vdf` | the build: which depots, which branch |
| `scripts/depot_build_{depot_id}.vdf` | the depot: which files go in it |
| `upload.sh` / `upload.bat` | `steamcmd +run_app_build` around the above |
| `dev/{_STEAM_APPID_FILE}` | **development only** -- see below |

The content root is `{content}`, relative to `scripts/`.

## Before the first upload

1. Get the Steamworks SDK and put `steamcmd` on your `PATH` (the builder
   lives in `sdk/tools/ContentBuilder`).
2. Log in interactively once on the machine that will upload, so Steam
   Guard is satisfied: `steamcmd +login <build account>`. Unattended CI
   fails at this step otherwise, and it is the single most common reason
   a store pipeline does not work.
3. Leave `Preview` at `1` for the first run and read the output. A wrong
   `ContentRoot` produces a completely successful build of the wrong
   files, and the only sign is the file list.
4. `SetLive` is empty on purpose. Set a **branch name** when you want the
   upload to go live, never `default` from a script.

## `{_STEAM_APPID_FILE}` must not reach the depot

It is written to `dev/` rather than into the content root, and the depot
script also excludes it by name. Both, because it matters twice over:

- It **overrides the App ID** Steam supplies to the running game.
- It makes `SteamAPI_RestartAppIfNecessary` **return false**, which is how
  the game gets re-launched through the client. Ship it, and a customer
  who runs the executable directly plays with no Steam client attached --
  no overlay, no achievements, no cloud saves, and no error.

Copy it next to your executable while testing locally, and keep it out of
anything you upload.

## One thing to check against your SDK

The depot script's root key is `DepotBuildConfig`, which is what the
SDK's bundled sample scripts use. Valve's documentation page spells the
same block `DepotBuild`. If `steamcmd` rejects the file, diff it against
the samples in `sdk/tools/ContentBuilder/scripts` and trust those.
"""


def _itch_platform_of(channel: str) -> str | None:
    """Return the platform a channel name implies, or None."""
    lowered = channel.lower()
    for platform, tokens in _ITCH_PLATFORM_TOKENS.items():
        if any(token in lowered for token in tokens):
            return platform
    return None


def _default_itch_channel() -> str:
    """Return a channel name for the host platform."""
    import sys

    if sys.platform.startswith("win"):
        return "windows"
    if sys.platform == "darwin":
        return "osx"
    return "linux"


def _itch_push_script(target: str, channel: str, content: str, version: str) -> str:
    """Return a runnable `butler push` wrapper."""
    version_flag = f" \\\n\t--userversion {version}" if version else ""
    return f"""\
#!/usr/bin/env bash
# Generated by `pyguara dist itch`. Uploads to {target}:{channel}.
#
# `butler login` once on this machine first, or set BUTLER_API_KEY in the
# environment (which is what CI wants).
set -euo pipefail

here="$(cd "$(dirname "${{BASH_SOURCE[0]}}")" && pwd)"

butler push "$here/{content}" "{target}:{channel}"{version_flag}
"""


def _write(path: Path, text: str, *, executable: bool = False) -> None:
    """Write `text` to `path`, creating parents, and log it."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    if executable:
        path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    logger.info("wrote %s", path)


@click.group()
def dist() -> None:
    """Generate store distribution templates for a built game.

    Writes scripts; never uploads. See `pyguara dist steam --help`.
    """


@dist.command("icons")
@click.argument(
    "source",
    type=click.Path(exists=True, file_okay=True, dir_okay=False, path_type=Path),
)
@click.option(
    "-o",
    "--out",
    type=click.Path(file_okay=False, dir_okay=True, path_type=Path),
    default=Path("build/icons"),
    help="Directory for the generated icons (default: build/icons/)",
)
def icons_command(source: Path, out: Path) -> None:
    """Convert SOURCE into every platform's icon format.

    Writes `icon.ico` (Windows, multi-size), `icon.icns` (macOS) and
    `icon.png` (Linux). Pass the matching one to `pyguara build --icon`.
    """
    written = write_icons(source, out)
    for platform, path in written.items():
        click.echo(f"{platform:8} {path}")


@dist.command("steam")
@click.option("--app-id", required=True, help="Steam App ID, as digits")
@click.option("--depot-id", required=True, help="Steam Depot ID, as digits")
@click.option(
    "--content",
    required=True,
    type=click.Path(exists=True, file_okay=False, dir_okay=True, path_type=Path),
    help="The built game directory to upload (a `pyguara build` output)",
)
@click.option(
    "-o",
    "--out",
    type=click.Path(file_okay=False, dir_okay=True, path_type=Path),
    default=Path("dist/steam"),
    help="Where to write the scripts (default: dist/steam/)",
)
@click.option(
    "--build-output",
    type=click.Path(file_okay=False, dir_okay=True, path_type=Path),
    default=None,
    help="steamcmd's own log and chunk directory (default: <out>/output)",
)
@click.option(
    "--description",
    default="",
    help="Build description shown in Steamworks (default: a generated one)",
)
@click.option(
    "--branch",
    default="",
    help="Branch to set live after a successful upload (default: none)",
)
@click.option(
    "--preview/--no-preview",
    default=True,
    help="Validate without publishing the build (default: preview)",
)
def steam_command(
    app_id: str,
    depot_id: str,
    content: Path,
    out: Path,
    build_output: Path | None,
    description: str,
    branch: str,
    preview: bool,
) -> None:
    """Write a Steam content-builder script set for a built game.

    Generates the app and depot VDFs, an upload wrapper for both shells,
    a README with the manual steps, and the development-only
    `steam_appid.txt` -- outside the content root, because shipping it
    lets a customer bypass the Steam client.
    """
    for name, value in (("--app-id", app_id), ("--depot-id", depot_id)):
        if not value.isdigit():
            raise click.ClickException(
                f"{name} must be digits; got {value!r}. Steamworks shows "
                f"both on the app's Depots page."
            )

    scripts = out / "scripts"
    output = build_output if build_output is not None else out / "output"
    content_root = _relative_or_absolute(content, scripts)

    _write(
        scripts / f"app_build_{app_id}.vdf",
        _app_build_vdf(
            app_id=app_id,
            depot_id=depot_id,
            description=description or f"PyGuara build of {content.name}",
            content_root=content_root,
            build_output=_relative_or_absolute(output, scripts),
            branch=branch,
            preview=preview,
        ),
    )
    _write(
        scripts / f"depot_build_{depot_id}.vdf",
        _depot_build_vdf(depot_id, content_root),
    )
    _write(out / "upload.sh", _steam_upload_script(app_id, posix=True), executable=True)
    _write(out / "upload.bat", _steam_upload_script(app_id, posix=False))
    _write(out / "dev" / _STEAM_APPID_FILE, f"{app_id}\n")
    _write(out / "README.md", _steam_readme(app_id, depot_id, content_root))

    click.echo(f"Steam scripts written to {out}")
    if preview:
        click.echo(
            "Preview is on, so the first upload validates without "
            "publishing. Read the file list it prints."
        )
    if branch:
        click.echo(f"SetLive is {branch!r} -- this upload will go live on it.")


@dist.command("itch")
@click.option(
    "--target",
    required=True,
    help="The itch.io target as user/game, e.g. studio/my-game",
)
@click.option(
    "--content",
    required=True,
    type=click.Path(exists=True, file_okay=False, dir_okay=True, path_type=Path),
    help="The built game directory to upload (a `pyguara build` output)",
)
@click.option(
    "--channel",
    default=None,
    help="butler channel (default: the host platform's name)",
)
@click.option("--version", default="", help="Value for butler --userversion")
@click.option(
    "-o",
    "--out",
    type=click.Path(file_okay=False, dir_okay=True, path_type=Path),
    default=Path("dist/itch"),
    help="Where to write the push script (default: dist/itch/)",
)
def itch_command(
    target: str,
    content: Path,
    channel: str | None,
    version: str,
    out: Path,
) -> None:
    """Write a `butler push` script for a built game.

    The channel name is not cosmetic: itch.io reads it to decide which
    platform the upload is for, and one that names no platform is
    offered to nobody. This refuses such a name rather than generating a
    script that uploads successfully into the void.
    """
    if target.count("/") != 1 or not all(part for part in target.split("/")):
        raise click.ClickException(
            f"--target must be user/game; got {target!r}. It is the last "
            f"two segments of the game's itch.io URL."
        )

    channel = channel or _default_itch_channel()
    platform = _itch_platform_of(channel)
    if platform is None:
        recognised = ", ".join(
            sorted(
                token for tokens in _ITCH_PLATFORM_TOKENS.values() for token in tokens
            )
        )
        raise click.ClickException(
            f"the channel {channel!r} names no platform, so itch.io would "
            f"tag the upload for none and offer it to nobody. Include one "
            f"of: {recognised}. Several is fine -- `win-linux-stable`."
        )

    script = out / "push.sh"
    _write(
        script,
        _itch_push_script(
            target=target,
            channel=channel,
            content=_relative_or_absolute(content, out),
            version=version,
        ),
        executable=True,
    )
    click.echo(f"itch.io push script written to {script}")
    click.echo(f"channel {channel!r} -> tagged for {platform}")
