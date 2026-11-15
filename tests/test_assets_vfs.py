"""`pyguara.assets`: one way to read a game's files, loose or packed."""

from __future__ import annotations

import io
import os
import threading
import zipfile
from pathlib import Path

import pytest

from pyguara import assets


@pytest.fixture(autouse=True)
def _no_packs_after():
    yield
    assets.unmount_all()


@pytest.fixture
def game(tmp_path: Path) -> Path:
    """A game folder with loose files."""
    root = tmp_path / "game"
    (root / "assets" / "sprites").mkdir(parents=True)
    (root / "assets" / "sprites" / "hero.png").write_bytes(b"loose hero")
    (root / "assets" / "data.json").write_text('{"hp": 1}', encoding="utf-8")
    return root


def _pack(path: Path, files: dict[str, bytes]) -> Path:
    with zipfile.ZipFile(path, "w") as archive:
        for name, data in files.items():
            archive.writestr(name, data)
    return path


# --------------------------------------------------------------------------- #
# Loose files: what the engine did before, unchanged                           #
# --------------------------------------------------------------------------- #


def test_loose_files_read_as_before(game: Path) -> None:
    hero = game / "assets" / "sprites" / "hero.png"
    assert assets.read_bytes(str(hero)) == b"loose hero"
    assert assets.read_text(str(game / "assets" / "data.json")) == '{"hp": 1}'
    assert assets.is_file(str(hero))
    assert assets.is_dir(str(game / "assets"))
    assert not assets.exists(str(game / "nope.png"))


def test_a_missing_file_raises_file_not_found(game: Path) -> None:
    with pytest.raises(FileNotFoundError, match="nope.png"):
        assets.read_bytes(str(game / "nope.png"))


def test_relative_paths_are_from_the_working_directory(game: Path, monkeypatch) -> None:
    monkeypatch.chdir(game)
    assert assets.read_bytes("assets/sprites/hero.png") == b"loose hero"


def test_open_gives_a_binary_file_object(game: Path) -> None:
    with assets.open(str(game / "assets" / "sprites" / "hero.png")) as handle:
        assert isinstance(handle, io.IOBase)
        assert handle.read() == b"loose hero"


# --------------------------------------------------------------------------- #
# Packs                                                                        #
# --------------------------------------------------------------------------- #


def test_a_mounted_pack_serves_paths_under_its_root(game: Path, tmp_path: Path) -> None:
    pack = _pack(
        tmp_path / "game.pak",
        {"assets/sprites/hero.png": b"packed hero", "assets/only_packed.txt": b"x"},
    )
    assets.mount_pack(pack, root=game)

    assert (
        assets.read_bytes(str(game / "assets" / "sprites" / "hero.png"))
        == b"packed hero"
    )
    assert assets.read_bytes(str(game / "assets" / "only_packed.txt")) == b"x"
    # Not in the pack: the loose file is still found.
    assert assets.read_text(str(game / "assets" / "data.json")) == '{"hp": 1}'


def test_a_pack_works_with_no_loose_files_at_all(tmp_path: Path, monkeypatch) -> None:
    root = tmp_path / "installed"
    root.mkdir()
    pack = _pack(
        tmp_path / "game.pak", {"assets/a.json": b"{}", "assets/sub/b.png": b"b"}
    )
    assets.mount_pack(pack, root=root)
    monkeypatch.chdir(root)

    assert assets.read_bytes("assets/a.json") == b"{}"
    assert assets.is_dir("assets")
    assert assets.is_dir("assets/sub")
    assert not assets.is_dir("assets/a.json")
    assert assets.is_file("assets/sub/b.png")
    # Relative in, relative out -- as walking the disk would give.
    assert assets.files_under("assets") == [
        os.path.join("assets", "a.json"),
        os.path.join("assets", "sub", "b.png"),
    ]
    assert assets.files_under("assets", recursive=False) == [
        os.path.join("assets", "a.json")
    ]
    assert assets.files_under(str(root / "assets"), recursive=False) == [
        str(root / "assets" / "a.json")
    ]


def test_listing_merges_pack_and_loose_files_once(game: Path, tmp_path: Path) -> None:
    pack = _pack(
        tmp_path / "game.pak",
        {"assets/sprites/hero.png": b"p", "assets/sprites/foe.png": b"p"},
    )
    assets.mount_pack(pack, root=game)
    found = assets.files_under(str(game / "assets" / "sprites"))
    assert sorted(Path(p).name for p in found) == ["foe.png", "hero.png"]


def test_a_path_outside_the_root_is_not_looked_up_in_the_pack(
    game: Path, tmp_path: Path
) -> None:
    elsewhere = tmp_path / "elsewhere.txt"
    elsewhere.write_bytes(b"disk")
    pack = _pack(tmp_path / "game.pak", {"elsewhere.txt": b"pack"})
    assets.mount_pack(pack, root=game)
    assert assets.read_bytes(str(elsewhere)) == b"disk"


def test_dot_dot_cannot_climb_out_of_the_root(game: Path, tmp_path: Path) -> None:
    pack = _pack(tmp_path / "game.pak", {"assets/x.txt": b"in"})
    assets.mount_pack(pack, root=game)
    sneaky = str(game / "assets" / ".." / "assets" / "x.txt")
    assert assets.read_bytes(sneaky) == b"in"  # normalised, still inside


def test_the_last_mounted_pack_wins(game: Path, tmp_path: Path) -> None:
    base = _pack(
        tmp_path / "base.pak", {"assets/a.txt": b"base", "assets/b.txt": b"base"}
    )
    patch = _pack(tmp_path / "patch.pak", {"assets/a.txt": b"patch"})
    assets.mount_pack(base, root=game)
    assets.mount_pack(patch, root=game)
    assert assets.read_bytes(str(game / "assets" / "a.txt")) == b"patch"
    assert assets.read_bytes(str(game / "assets" / "b.txt")) == b"base"
    assert assets.mounted_packs() == (patch, base)


def test_a_stamp_changes_when_a_loose_file_does(game: Path) -> None:
    path = game / "assets" / "data.json"
    before = assets.stamp(str(path))
    path.write_text('{"hp": 22}', encoding="utf-8")
    import os

    os.utime(path, (1, 1))
    assert assets.stamp(str(path)) != before
    assert assets.stamp(str(game / "nope")) is None


def test_a_packed_file_has_a_fixed_stamp(game: Path, tmp_path: Path) -> None:
    pack = _pack(tmp_path / "game.pak", {"assets/a.txt": b"x"})
    assets.mount_pack(pack, root=game)
    stamp = assets.stamp(str(game / "assets" / "a.txt"))
    assert stamp is not None
    assert assets.stamp(str(game / "assets" / "a.txt")) == stamp


def test_a_file_that_is_not_a_pack_is_refused_by_name(tmp_path: Path) -> None:
    bogus = tmp_path / "bogus.pak"
    bogus.write_bytes(b"not a zip")
    with pytest.raises(ValueError, match="bogus.pak"):
        assets.mount_pack(bogus, root=tmp_path)


def test_unmount_closes_the_pack(game: Path, tmp_path: Path) -> None:
    pack = _pack(tmp_path / "game.pak", {"assets/a.txt": b"x"})
    assets.mount_pack(pack, root=game)
    assets.unmount_all()
    assert assets.mounted_packs() == ()
    pack.unlink()  # Windows refuses this while the pack is open


def test_reads_from_many_threads_are_safe(game: Path, tmp_path: Path) -> None:
    files = {f"assets/f{i}.bin": bytes([i]) * 4096 for i in range(32)}
    pack = _pack(tmp_path / "game.pak", files)
    assets.mount_pack(pack, root=game)
    errors: list[BaseException] = []

    def read_all() -> None:
        try:
            for i in range(32):
                for _ in range(10):
                    data = assets.read_bytes(str(game / "assets" / f"f{i}.bin"))
                    assert data == bytes([i]) * 4096
        except BaseException as error:  # noqa: BLE001 - reported below
            errors.append(error)

    threads = [threading.Thread(target=read_all) for _ in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert errors == []
