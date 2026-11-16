"""One way to read a game's files, whether they are loose or packed.

`pyguara build` can bake the assets into one pack (a ZIP), which is
mounted at run time over the folder it was made from. Every engine
loader reads through this module. A pack holds paths relative to its
`root`, and a path is looked up in a pack only if it lies under that
root, so the same paths work loose or packed. The last mounted pack is
consulted first, then the earlier ones, then the disk. Packs are
read-only.

Example:
    from pyguara import assets

    assets.mount_pack("Reclaimer.pak", root=game_dir)
    assets.read_bytes(game_dir / "assets/sprites/hero.png")   # the pack
    assets.read_bytes("saves/slot1.save")                     # the disk
"""

from __future__ import annotations

import builtins
import io
import os
import sys
import threading
import zipfile
from pathlib import Path
from typing import BinaryIO

__all__ = [
    "exists",
    "files_under",
    "in_pack",
    "is_dir",
    "is_file",
    "mount_pack",
    "mounted_packs",
    "open",
    "read_bytes",
    "read_text",
    "stamp",
    "unmount_all",
]

PathLike = str | os.PathLike[str]


class _Pack:
    """A mounted ZIP: its entries, by path relative to `root`."""

    def __init__(self, path: Path, root: Path) -> None:
        self.path = path
        self.root = _normal(root)
        try:
            self._zip = zipfile.ZipFile(path)
        except (OSError, zipfile.BadZipFile) as error:
            raise ValueError(f"{path} is not an asset pack: {error}") from error
        self._lock = threading.Lock()
        self._files = {
            info.filename.rstrip("/"): info
            for info in self._zip.infolist()
            if not info.is_dir()
        }
        directories: set[str] = set()
        for name in self._files:
            parts = name.split("/")[:-1]
            for depth in range(1, len(parts) + 1):
                directories.add("/".join(parts[:depth]))
        self._directories = directories
        # One stamp per pack: its contents do not change while mounted.
        self._stamp = ("pack", str(path), os.stat(path).st_mtime_ns)

    def key(self, path: str) -> str | None:
        """Return the entry name for `path`, or None outside the root."""
        try:
            relative = os.path.relpath(path, self.root)
        except ValueError:  # another drive, on Windows
            return None
        if relative == "." or relative.startswith(".."):
            return "" if relative == "." else None
        return relative.replace(os.sep, "/")

    def has_file(self, key: str) -> bool:
        return key in self._files

    def has_dir(self, key: str) -> bool:
        return key == "" or key in self._directories

    def read(self, key: str) -> bytes:
        with self._lock:
            return self._zip.read(self._files[key])

    def stamp(self) -> tuple[str, str, int]:
        return self._stamp

    def files(self, key: str, recursive: bool) -> list[str]:
        prefix = f"{key}/" if key else ""
        found = []
        for name in self._files:
            if not name.startswith(prefix):
                continue
            rest = name[len(prefix) :]
            if recursive or "/" not in rest:
                found.append(os.path.join(self.root, *name.split("/")))
        return found

    def close(self) -> None:
        with self._lock:
            self._zip.close()


_packs: list[_Pack] = []
_packs_lock = threading.Lock()


def _normal(path: PathLike) -> str:
    """Return `path` absolute and normalised, without resolving symlinks."""
    text = os.fspath(path)
    if not os.path.isabs(text):
        text = os.path.join(os.getcwd(), text)
    return os.path.normpath(text)


_bundled_checked = threading.Event()


def _mount_bundled() -> None:
    """Mount the packs a frozen game was built with, once.

    `pyguara build --pack` puts `<name>.pak` at the root of the bundle,
    which is also where `--add-data` would have put the loose folders and
    where the game's own code lives. Done on the first read rather than at
    startup, so a game that reads its data before building the application
    still finds it.
    """
    if _bundled_checked.is_set():
        return
    with _packs_lock:
        if _bundled_checked.is_set():
            return
        _bundled_checked.set()
        if not getattr(sys, "frozen", False):
            return
        bundle = Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
        for pack_path in sorted(bundle.glob("*.pak")):
            _packs.append(_Pack(pack_path, bundle))


def _reset_bundled_for_tests() -> None:
    """Let the next read look for bundled packs again."""
    _bundled_checked.clear()


def _find(path: PathLike) -> tuple[_Pack, str] | None:
    _mount_bundled()
    absolute = _normal(path)
    for pack in reversed(_packs):
        key = pack.key(absolute)
        if key and pack.has_file(key):
            return pack, key
    return None


def mount_pack(path: PathLike, *, root: PathLike) -> None:
    """Serve the files in a pack as if they were under `root`.

    Args:
        path: The `.pak` file `pyguara build` made (a ZIP).
        root: The folder the pack's paths are relative to -- the one it was
            baked from, which at run time is where the game's code lives.

    Raises:
        FileNotFoundError: If the pack does not exist.
        ValueError: If it is not a pack.
    """
    pack_path = Path(path)
    if not pack_path.is_file():
        raise FileNotFoundError(f"asset pack {pack_path} does not exist")
    pack = _Pack(pack_path, Path(root))
    with _packs_lock:
        _packs.append(pack)


def mounted_packs() -> tuple[Path, ...]:
    """Return the mounted packs' files, the one consulted first first."""
    _mount_bundled()
    return tuple(pack.path for pack in reversed(_packs))


def unmount_all() -> None:
    """Close and forget every pack. Reads go to disk again."""
    with _packs_lock:
        for pack in _packs:
            pack.close()
        _packs.clear()


def read_bytes(path: PathLike) -> bytes:
    """Return a file's contents, from a pack if one has it, else from disk.

    Raises:
        FileNotFoundError: If neither has it.
        IsADirectoryError: If the path is a directory.
    """
    found = _find(path)
    if found is not None:
        pack, key = found
        return pack.read(key)
    try:
        with builtins.open(os.fspath(path), "rb") as handle:
            return handle.read()
    except IsADirectoryError:
        raise
    except FileNotFoundError:
        raise FileNotFoundError(f"no such asset: {os.fspath(path)}") from None


def read_text(path: PathLike, encoding: str = "utf-8") -> str:
    """Return a file's contents as text; UTF-8 unless told otherwise.

    Newlines are translated as a text-mode `open()` would, so a file packed
    on Windows reads the same as it did loose.
    """
    text = read_bytes(path).decode(encoding)
    return text.replace("\r\n", "\n").replace("\r", "\n")


def open(path: PathLike) -> BinaryIO:  # noqa: A001 - mirrors the built-in
    """Return a file's contents as a readable binary file object.

    For an API that wants a file rather than bytes, such as
    `pygame.image.load`. The whole file is read; assets are small enough.
    """
    return io.BytesIO(read_bytes(path))


def in_pack(path: PathLike) -> bool:
    """Whether a mounted pack serves `path` (so it is not read from disk).

    For an API that streams a loose file itself and should keep doing so,
    such as pygame's music player.
    """
    return _find(path) is not None


def is_file(path: PathLike) -> bool:
    """Whether a pack or the disk has a file at `path`."""
    return _find(path) is not None or os.path.isfile(os.fspath(path))


def is_dir(path: PathLike) -> bool:
    """Whether a pack or the disk has a folder at `path`."""
    _mount_bundled()
    absolute = _normal(path)
    for pack in _packs:
        key = pack.key(absolute)
        if key is not None and pack.has_dir(key):
            return True
    return os.path.isdir(os.fspath(path))


def exists(path: PathLike) -> bool:
    """Whether `path` is a file or a folder, packed or on disk."""
    return is_file(path) or is_dir(path)


def stamp(path: PathLike) -> object | None:
    """Return a value that changes when the file does, or None if it is absent.

    A loose file's modification time; a packed file's pack, which does not
    change while it is mounted. For caches that must notice an edit.
    """
    found = _find(path)
    if found is not None:
        return found[0].stamp()
    try:
        return ("disk", os.stat(os.fspath(path)).st_mtime_ns)
    except OSError:
        return None


def files_under(directory: PathLike, *, recursive: bool = True) -> list[str]:
    """List the files under a folder, packed and loose, each once.

    Packed files are listed as the paths they would have on disk, so a path
    from this list reads back through `read_bytes`: absolute when
    `directory` is, relative to the working directory when it is relative,
    as a walk of the disk would give. Sorted.

    Args:
        directory: The folder.
        recursive: Include subfolders.
    """
    _mount_bundled()
    absolute = _normal(directory)
    found: set[str] = set()
    for pack in _packs:
        key = pack.key(absolute)
        if key is not None and pack.has_dir(key):
            found.update(pack.files(key, recursive))
    base = os.fspath(directory)
    if os.path.isdir(base):
        if recursive:
            for folder, _, names in os.walk(base):
                found.update(_normal(os.path.join(folder, name)) for name in names)
        else:
            for name in os.listdir(base):
                candidate = os.path.join(base, name)
                if os.path.isfile(candidate):
                    found.add(_normal(candidate))
    if not os.path.isabs(base):
        here = os.getcwd()
        return sorted(os.path.relpath(path, here) for path in found)
    return sorted(found)
