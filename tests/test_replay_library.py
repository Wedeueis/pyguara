"""`ReplayLibrary`: a game's replays by name, in one folder."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from pyguara.replay import ReplayData, ReplayLibrary, ReplayMetadata
from pyguara.replay.types import InputFrame


def _replay(seed: int = 7, frames: int = 3) -> ReplayData:
    return ReplayData(
        metadata=ReplayMetadata(version=3, seed=seed, frame_count=frames),
        frames=[
            InputFrame(frame_id=i, timestamp=i / 60, delta_time=1 / 60)
            for i in range(frames)
        ],
    )


@pytest.fixture
def library(tmp_path: Path) -> ReplayLibrary:
    return ReplayLibrary(tmp_path / "replays")


def test_an_empty_library_has_nothing_and_writes_nothing(
    library: ReplayLibrary,
) -> None:
    assert library.entries() == []
    assert not library.directory.exists()


def test_a_saved_replay_loads_back_by_name(library: ReplayLibrary) -> None:
    path = library.save(_replay(seed=11), "boss rush")

    assert path == library.directory / "boss rush.replay.gz"
    loaded = library.load("boss rush")
    assert loaded.metadata.seed == 11
    assert len(loaded.frames) == 3


def test_entries_are_newest_first_with_their_metadata(library: ReplayLibrary) -> None:
    older = library.save(_replay(seed=1), "first")
    library.save(_replay(seed=2), "second")
    os.utime(older, (1_000_000, 1_000_000))

    entries = library.entries()

    assert [e.name for e in entries] == ["second", "first"]
    assert [e.metadata.seed for e in entries if e.metadata] == [2, 1]
    assert library.names() == ["second", "first"]


def test_a_damaged_replay_is_listed_as_damaged_not_left_out(
    library: ReplayLibrary,
) -> None:
    library.save(_replay(), "good")
    (library.directory / "broken.replay.gz").write_bytes(b"not gzip")
    (library.directory / "notes.txt").write_text("not a replay")

    entries = {e.name: e for e in library.entries()}

    assert set(entries) == {"good", "broken"}
    assert entries["broken"].metadata is None
    with pytest.raises(ValueError, match="cannot be read"):
        library.load("broken")


def test_an_uncompressed_replay_saved_elsewhere_is_found_too(
    library: ReplayLibrary,
) -> None:
    library.directory.mkdir(parents=True)
    from pyguara.replay import save_replay

    assert save_replay(_replay(seed=5), str(library.directory / "plain.replay"), False)

    assert library.names() == ["plain"]
    assert library.load("plain").metadata.seed == 5
    library.rename("plain", "renamed")
    assert (library.directory / "renamed.replay").is_file()


def test_a_taken_name_is_refused_unless_overwriting(library: ReplayLibrary) -> None:
    library.save(_replay(seed=1), "run")

    with pytest.raises(FileExistsError, match="run"):
        library.save(_replay(seed=2), "run")
    library.save(_replay(seed=2), "run", overwrite=True)
    assert library.load("run").metadata.seed == 2


def test_rename_and_delete(library: ReplayLibrary) -> None:
    library.save(_replay(), "a")
    library.save(_replay(), "b")

    with pytest.raises(FileExistsError):
        library.rename("a", "b")
    library.rename("a", "c")
    assert sorted(library.names()) == ["b", "c"]

    library.delete("c")
    assert library.names() == ["b"]
    with pytest.raises(FileNotFoundError):
        library.delete("c")
    with pytest.raises(FileNotFoundError):
        library.load("c")


@pytest.mark.parametrize(
    "name",
    ["", "../escape", "a/b", "a\\b", "C:thing", "x" * 101, " padded", "dot.", "CON"],
)
def test_a_name_that_is_not_a_plain_file_name_is_refused(
    library: ReplayLibrary, name: str
) -> None:
    with pytest.raises(ValueError):
        library.save(_replay(), name)
    with pytest.raises(ValueError):
        library.path_of(name)
    assert not library.directory.exists()


def test_a_name_in_any_script_is_fine(library: ReplayLibrary) -> None:
    library.save(_replay(), "Босс 一 ação")
    assert library.names() == ["Босс 一 ação"]


def test_the_games_library_is_in_its_data_directory(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    import platformdirs

    monkeypatch.setattr(
        platformdirs,
        "user_data_dir",
        lambda name, author, roaming: str(tmp_path / name),
    )
    assert (
        ReplayLibrary.for_game("Reclaimer").directory
        == tmp_path / "Reclaimer" / "replays"
    )
