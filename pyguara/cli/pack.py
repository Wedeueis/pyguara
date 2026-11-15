"""Baking asset folders into one pack, for `pyguara build --pack`.

A pack is a ZIP whose entries are the folders' files, each under its
folder's own name -- `assets/sprites/hero.png` -- which is where PyInstaller's
`--add-data` would have put the loose file in the bundle. A frozen game
mounts it with the bundle as its root (`pyguara.assets`), so every path the
game's code builds finds the packed file.

Reproducible: entries are sorted and carry a fixed timestamp, so the same
folders bake to the same bytes.
"""

from __future__ import annotations

import zipfile
from dataclasses import dataclass
from pathlib import Path

__all__ = ["PackReport", "bake_pack"]

# Already compressed: deflating them again costs time and saves nothing.
_STORED = frozenset(
    {
        ".png", ".jpg", ".jpeg", ".webp", ".gif",
        ".ogg", ".mp3", ".flac", ".opus",
        ".zip", ".pak", ".gz", ".woff", ".woff2",
    }
)  # fmt: skip
_SKIPPED_DIRS = frozenset({"__pycache__", ".git", ".svn"})
_FIXED_TIME = (1980, 1, 1, 0, 0, 0)


@dataclass(frozen=True)
class PackReport:
    """What a bake wrote.

    Attributes:
        path: The pack.
        files: How many files it holds.
        source_bytes: Their total size before compression.
        packed_bytes: The pack's size.
    """

    path: Path
    files: int
    source_bytes: int
    packed_bytes: int


def bake_pack(folders: list[Path], destination: Path) -> PackReport:
    """Write the files under `folders` into one pack.

    Hidden files (`.DS_Store`) and `__pycache__` are left out; everything else
    is kept, `.meta` sidecars included.

    Args:
        folders: The asset folders. Each becomes a top-level folder of the
            pack under its own name.
        destination: The pack to write; replaced if it exists.

    Returns:
        What was written.

    Raises:
        ValueError: If two folders share a name, which would put two trees
            at one path.
    """
    names = [folder.name for folder in folders]
    clashes = sorted({name for name in names if names.count(name) > 1})
    if clashes:
        raise ValueError(
            f"two asset folders are both named {', '.join(clashes)}; in the "
            "pack, as in the bundle, they would land at one path"
        )
    destination.parent.mkdir(parents=True, exist_ok=True)
    entries: list[tuple[str, Path]] = []
    for folder in folders:
        for path in sorted(folder.rglob("*")):
            relative = path.relative_to(folder)
            if not path.is_file():
                continue
            if any(part in _SKIPPED_DIRS for part in relative.parts):
                continue
            if any(part.startswith(".") for part in relative.parts):
                continue
            entries.append((f"{folder.name}/{relative.as_posix()}", path))

    source_bytes = 0
    with zipfile.ZipFile(destination, "w") as archive:
        for name, path in sorted(entries):
            data = path.read_bytes()
            source_bytes += len(data)
            info = zipfile.ZipInfo(name, date_time=_FIXED_TIME)
            info.external_attr = 0o644 << 16
            info.compress_type = (
                zipfile.ZIP_STORED
                if path.suffix.lower() in _STORED
                else zipfile.ZIP_DEFLATED
            )
            archive.writestr(info, data)
    return PackReport(
        path=destination,
        files=len(entries),
        source_bytes=source_bytes,
        packed_bytes=destination.stat().st_size,
    )
