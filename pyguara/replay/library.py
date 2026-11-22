"""A folder of named replays: list, save, load, rename and delete them.

For a game's replay menu. Each replay is one file, named after the replay,
in the folder the library was opened on: `<name>.replay.gz`. A name is a
file name, so it is refused if it could reach outside the folder.

Example:
    library = ReplayLibrary.for_game("Reclaimer")
    library.save(app.stop_recording(), "boss rush")
    for entry in library.entries():
        print(entry.name, entry.metadata.duration if entry.metadata else "damaged")
    app.load_replay(str(library.path_of("boss rush")))
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from pyguara.replay.serializer import ReplaySerializer
from pyguara.replay.types import ReplayData, ReplayMetadata

__all__ = ["ReplayEntry", "ReplayLibrary"]

_SUFFIX = ReplaySerializer.COMPRESSED_EXTENSION
_PLAIN_SUFFIX = ReplaySerializer.EXTENSION
# Characters no file system objects to, so a name saves the same everywhere.
_FORBIDDEN = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
_RESERVED = frozenset(
    {"con", "prn", "aux", "nul"}
    | {f"com{i}" for i in range(1, 10)}
    | {f"lpt{i}" for i in range(1, 10)}
)
_MAX_NAME = 100


@dataclass(frozen=True)
class ReplayEntry:
    """One replay in a library.

    Attributes:
        name: Its name in the library.
        path: Its file.
        metadata: What it records, or None if the file cannot be read: a
            menu shows that as damaged rather than leaving it out.
        modified: When the file was last written, in seconds since the epoch.
    """

    name: str
    path: Path
    metadata: ReplayMetadata | None
    modified: float


class ReplayLibrary:
    """Named replays in one folder."""

    def __init__(self, directory: Path) -> None:
        """Open a library on `directory`, which is created on the first save.

        Args:
            directory: The folder the replays live in.
        """
        self.directory = Path(directory)
        self._serializer = ReplaySerializer()

    @classmethod
    def for_game(cls, app_name: str, app_author: str | None = None) -> ReplayLibrary:
        """Open the library in the player's data directory, under `replays/`.

        Args:
            app_name: The game's name, as the crash reporter is given it.
            app_author: Vendor name, used only on Windows.
        """
        import platformdirs

        base = platformdirs.user_data_dir(app_name, app_author, roaming=False)
        return cls(Path(base) / "replays")

    def entries(self) -> list[ReplayEntry]:
        """Every replay, newest first, damaged ones included."""
        if not self.directory.is_dir():
            return []
        found: list[ReplayEntry] = []
        for path in self.directory.iterdir():
            name = _name_of(path)
            if name is None or not path.is_file():
                continue
            raw = self._serializer.get_metadata(str(path))
            metadata = ReplayMetadata.from_dict(raw) if raw is not None else None
            found.append(ReplayEntry(name, path, metadata, path.stat().st_mtime))
        found.sort(key=lambda entry: (-entry.modified, entry.name))
        return found

    def names(self) -> list[str]:
        """Every replay's name, newest first."""
        return [entry.name for entry in self.entries()]

    def path_of(self, name: str) -> Path:
        """Return the file a replay of this name is, or would be, saved in.

        Raises:
            ValueError: If the name cannot be a file name in this folder.
        """
        check_name(name)
        plain = self.directory / f"{name}{_PLAIN_SUFFIX}"
        if plain.is_file() and not (self.directory / f"{name}{_SUFFIX}").is_file():
            return plain
        return self.directory / f"{name}{_SUFFIX}"

    def save(self, data: ReplayData, name: str, *, overwrite: bool = False) -> Path:
        """Save a replay under `name`, compressed.

        Args:
            data: The replay, as `Application.stop_recording()` returns it.
            name: Its name in the library.
            overwrite: Replace a replay already called `name`.

        Returns:
            The file written.

        Raises:
            ValueError: If the name cannot be a file name.
            FileExistsError: If `name` is taken and `overwrite` is False.
            OSError: If the file cannot be written.
        """
        check_name(name)
        if not overwrite and self.exists(name):
            raise FileExistsError(f"there is already a replay called {name!r}")
        self.directory.mkdir(parents=True, exist_ok=True)
        path = self.directory / f"{name}{_SUFFIX}"
        if not self._serializer.save(data, str(path), compress=True):
            raise OSError(f"could not write the replay {name!r} to {path}")
        (self.directory / f"{name}{_PLAIN_SUFFIX}").unlink(missing_ok=True)
        return path

    def load(self, name: str) -> ReplayData:
        """Read a replay by name.

        Raises:
            ValueError: If the name cannot be a file name, or the file is
                damaged or from a newer engine.
            FileNotFoundError: If there is no replay of that name.
        """
        path = self._existing(name)
        data = self._serializer.load(str(path))
        if data is None:
            raise ValueError(f"the replay {name!r} cannot be read ({path})")
        return data

    def exists(self, name: str) -> bool:
        """Whether a replay of this name is in the library."""
        return self.path_of(name).is_file()

    def rename(self, name: str, new_name: str) -> Path:
        """Give a replay another name, keeping its file as it is.

        Returns:
            The renamed file.

        Raises:
            ValueError: If either name cannot be a file name.
            FileNotFoundError: If there is no replay called `name`.
            FileExistsError: If `new_name` is taken.
        """
        path = self._existing(name)
        check_name(new_name)
        if new_name == name:
            return path
        if self.exists(new_name) and new_name.casefold() != name.casefold():
            raise FileExistsError(f"there is already a replay called {new_name!r}")
        target = self.directory / f"{new_name}{_name_suffix(path)}"
        return path.rename(target)

    def delete(self, name: str) -> None:
        """Delete a replay.

        Raises:
            ValueError: If the name cannot be a file name.
            FileNotFoundError: If there is no replay of that name.
        """
        self._existing(name).unlink()

    def _existing(self, name: str) -> Path:
        path = self.path_of(name)
        if not path.is_file():
            raise FileNotFoundError(f"there is no replay called {name!r}")
        return path


def check_name(name: str) -> None:
    """Refuse a name that is not a plain file name on every platform.

    Raises:
        ValueError: If it is empty, too long, has a character a file system
            forbids, starts or ends with a space or a dot, or is a name
            Windows reserves.
    """
    if not name or len(name) > _MAX_NAME:
        raise ValueError(f"a replay name must be 1 to {_MAX_NAME} characters")
    if _FORBIDDEN.search(name):
        raise ValueError(f'a replay name cannot contain any of <>:"/\\|?* : {name!r}')
    if name != name.strip(" .") or name.casefold() in _RESERVED:
        raise ValueError(f"{name!r} cannot be a file name on every platform")


def _name_suffix(path: Path) -> str:
    return _SUFFIX if path.name.endswith(_SUFFIX) else _PLAIN_SUFFIX


def _name_of(path: Path) -> str | None:
    for suffix in (_SUFFIX, _PLAIN_SUFFIX):
        if path.name.endswith(suffix) and len(path.name) > len(suffix):
            return path.name[: -len(suffix)]
    return None
