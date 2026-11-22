"""The Windows version resource: what an `.exe`'s Details tab shows.

PyInstaller takes it as a text file holding a `VSVersionInfo(...)`
expression, which it evaluates. Every string is written with `repr()`,
so a name or copyright line is always a literal, never code.

Windows applies it only; PyInstaller ignores it elsewhere with a warning.
"""

from __future__ import annotations

import re
import tomllib
from dataclasses import dataclass
from pathlib import Path

__all__ = ["VersionInfo", "numeric_version", "project_version", "render"]

_RELEASE = re.compile(r"^\s*v?(\d+)(?:\.(\d+))?(?:\.(\d+))?(?:\.(\d+))?")
_WORD = 0xFFFF


@dataclass(frozen=True)
class VersionInfo:
    """What a built game says about itself.

    Attributes:
        product: The game's name, also its description and file name.
        version: The version as written, such as `1.2.0rc1`.
        company: Who makes it, or None to leave the field out.
        copyright: The copyright line, or None to leave it out.
    """

    product: str
    version: str
    company: str | None = None
    copyright: str | None = None


def numeric_version(version: str) -> tuple[int, int, int, int]:
    """Return the four numbers Windows stores, from a version string.

    The release numbers only: `1.2.0rc1` is `(1, 2, 0, 0)`; the string
    itself keeps the suffix.

    Raises:
        ValueError: If the string does not start with a number, or a part
            does not fit in the 16 bits Windows gives it.
    """
    match = _RELEASE.match(version)
    if match is None:
        raise ValueError(
            f"version {version!r} does not start with a number, as 1.2.3 does"
        )
    parts = tuple(int(part) if part else 0 for part in match.groups())
    if any(part > _WORD for part in parts):
        raise ValueError(f"version {version!r} has a part above {_WORD}")
    return parts[0], parts[1], parts[2], parts[3]


def project_version(start: Path) -> str | None:
    """Return `[project].version` from the nearest `pyproject.toml` above `start`.

    The search stops at the first `pyproject.toml`. None when it has no
    static version, or there is no such file.
    """
    for directory in [start, *start.parents]:
        candidate = directory / "pyproject.toml"
        if candidate.is_file():
            with candidate.open("rb") as file:
                data = tomllib.load(file)
            version = data.get("project", {}).get("version")
            return version if isinstance(version, str) else None
    return None


def render(info: VersionInfo) -> str:
    """Return the version file PyInstaller's `--version-file` reads.

    Raises:
        ValueError: If the version is not one Windows can store.
    """
    numbers = numeric_version(info.version)
    strings = [
        ("CompanyName", info.company),
        ("FileDescription", info.product),
        ("FileVersion", info.version),
        ("InternalName", info.product),
        ("LegalCopyright", info.copyright),
        ("OriginalFilename", f"{info.product}.exe"),
        ("ProductName", info.product),
        ("ProductVersion", info.version),
    ]
    table = ",\n".join(
        f"          StringStruct({key!r}, {value!r})"
        for key, value in strings
        if value is not None
    )
    # 0x040904B0: US English, Unicode -- the table every tool reads first.
    return f"""\
VSVersionInfo(
  ffi=FixedFileInfo(
    filevers={numbers!r},
    prodvers={numbers!r},
    mask=0x3F,
    flags=0x0,
    OS=0x40004,
    fileType=0x1,
    subtype=0x0,
    date=(0, 0),
  ),
  kids=[
    StringFileInfo([
      StringTable(
        '040904B0',
        [
{table},
        ],
      ),
    ]),
    VarFileInfo([VarStruct('Translation', [1033, 1200])]),
  ],
)
"""
