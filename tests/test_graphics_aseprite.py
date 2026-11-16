"""An Aseprite sprite sheet export becomes textures and clips.

The files are built here in the shape Aseprite writes them: a strip of
frames and the JSON beside it, in both of its layouts.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from PIL import Image

from pyguara.graphics.aseprite import AsepriteFormatError, load_aseprite, split_path
from pyguara.graphics.backends.pygame.types import PygameTextureFactory
from pyguara.graphics.components.animation import PlaybackMode

SIZE = 8
COLOURS = [(255, 0, 0, 255), (0, 255, 0, 255), (0, 0, 255, 255), (255, 255, 0, 255)]
DURATIONS = [100, 100, 250, 50]


@pytest.fixture
def factory() -> PygameTextureFactory:
    return PygameTextureFactory()


def _strip(path: Path) -> None:
    """Four solid frames side by side, each its own colour."""
    image = Image.new("RGBA", (SIZE * len(COLOURS), SIZE))
    for index, colour in enumerate(COLOURS):
        image.paste(colour, (index * SIZE, 0, (index + 1) * SIZE, SIZE))
    image.save(path)


def _frame(index: int) -> dict[str, Any]:
    return {
        "filename": f"hero {index}.aseprite",
        "frame": {"x": index * SIZE, "y": 0, "w": SIZE, "h": SIZE},
        "rotated": False,
        "trimmed": False,
        "spriteSourceSize": {"x": 0, "y": 0, "w": SIZE, "h": SIZE},
        "sourceSize": {"w": SIZE, "h": SIZE},
        "duration": DURATIONS[index],
    }


def _export(
    folder: Path,
    tags: list[dict[str, Any]] | None = None,
    *,
    as_hash: bool = False,
    frames: list[dict[str, Any]] | None = None,
    image: str = "hero.png",
) -> str:
    """Write the image and JSON; return the JSON's path."""
    _strip(folder / "hero.png")
    listed = frames if frames is not None else [_frame(i) for i in range(4)]
    document = {
        "frames": {entry["filename"]: entry for entry in listed} if as_hash else listed,
        "meta": {
            "app": "https://www.aseprite.org/",
            "image": image,
            "format": "RGBA8888",
            "size": {"w": SIZE * 4, "h": SIZE},
            "scale": "1",
            "frameTags": tags or [],
        },
    }
    path = folder / "hero.json"
    path.write_text(json.dumps(document), encoding="utf-8")
    return str(path)


def _colour(texture: Any, at: tuple[int, int] = (1, 1)) -> tuple[int, ...]:
    return tuple(texture.native_handle.get_at(at))


class TestFrames:
    @pytest.mark.parametrize("as_hash", [False, True])
    def test_both_json_layouts_give_the_frames_in_order(
        self, tmp_path: Path, factory: PygameTextureFactory, as_hash: bool
    ) -> None:
        sheet = load_aseprite(_export(tmp_path, as_hash=as_hash), factory)

        assert [_colour(frame) for frame in sheet.frames] == COLOURS
        assert sheet.durations == (0.1, 0.1, 0.25, 0.05)

    def test_a_trimmed_frame_is_put_back_on_the_sprites_canvas(
        self, tmp_path: Path, factory: PygameTextureFactory
    ) -> None:
        trimmed = _frame(1)
        trimmed["frame"] = {"x": SIZE, "y": 0, "w": 4, "h": 4}
        trimmed["trimmed"] = True
        trimmed["spriteSourceSize"] = {"x": 3, "y": 2, "w": 4, "h": 4}

        sheet = load_aseprite(_export(tmp_path, frames=[trimmed]), factory)

        (frame,) = sheet.frames
        assert (frame.width, frame.height) == (SIZE, SIZE)
        assert _colour(frame, (3, 2)) == COLOURS[1]
        assert _colour(frame, (6, 5)) == COLOURS[1]
        assert _colour(frame, (2, 2))[3] == 0, "outside the trim is transparent"
        assert _colour(frame, (7, 6))[3] == 0

    def test_the_image_is_found_beside_the_json_whatever_path_was_exported(
        self, tmp_path: Path, factory: PygameTextureFactory
    ) -> None:
        path = _export(tmp_path, image="C:\\Users\\artist\\art\\hero.png")

        assert len(load_aseprite(path, factory).frames) == 4

    def test_an_image_can_be_named_outright(
        self, tmp_path: Path, factory: PygameTextureFactory
    ) -> None:
        path = _export(tmp_path, image="")
        _strip(tmp_path / "other.png")

        sheet = load_aseprite(path, factory, image_path=str(tmp_path / "other.png"))

        assert len(sheet.frames) == 4


class TestClips:
    def test_a_tag_becomes_a_clip_of_its_frames(
        self, tmp_path: Path, factory: PygameTextureFactory
    ) -> None:
        tags = [
            {"name": "idle", "from": 0, "to": 1, "direction": "forward"},
            {"name": "attack", "from": 2, "to": 3, "direction": "forward"},
        ]

        sheet = load_aseprite(_export(tmp_path, tags), factory)

        assert sorted(sheet.clips) == ["attack", "idle"]
        idle, attack = sheet.clip("idle"), sheet.clip("attack")
        assert [_colour(frame) for frame in idle.frames] == COLOURS[0:2]
        assert [_colour(frame) for frame in attack.frames] == COLOURS[2:4]
        assert idle.playback_mode is PlaybackMode.LOOP

    def test_frames_of_one_length_play_at_a_plain_frame_rate(
        self, tmp_path: Path, factory: PygameTextureFactory
    ) -> None:
        tags = [{"name": "idle", "from": 0, "to": 1, "direction": "forward"}]

        idle = load_aseprite(_export(tmp_path, tags), factory).clip("idle")

        assert idle.frame_durations is None
        assert idle.frame_rate == pytest.approx(10.0)

    def test_frames_of_different_lengths_keep_each_duration(
        self, tmp_path: Path, factory: PygameTextureFactory
    ) -> None:
        tags = [{"name": "attack", "from": 1, "to": 3, "direction": "forward"}]

        attack = load_aseprite(_export(tmp_path, tags), factory).clip("attack")

        assert attack.frame_durations == (0.1, 0.25, 0.05)

    def test_a_reversed_tag_reverses_frames_and_durations_together(
        self, tmp_path: Path, factory: PygameTextureFactory
    ) -> None:
        tags = [{"name": "back", "from": 1, "to": 3, "direction": "reverse"}]

        back = load_aseprite(_export(tmp_path, tags), factory).clip("back")

        assert [_colour(frame) for frame in back.frames] == COLOURS[3:0:-1]
        assert back.frame_durations == (0.05, 0.25, 0.1)

    @pytest.mark.parametrize(
        ("direction", "first"), [("pingpong", 0), ("pingpong_reverse", 1)]
    )
    def test_a_ping_pong_tag_plays_back_and_forth(
        self,
        tmp_path: Path,
        factory: PygameTextureFactory,
        direction: str,
        first: int,
    ) -> None:
        tags = [{"name": "bob", "from": 0, "to": 1, "direction": direction}]

        bob = load_aseprite(_export(tmp_path, tags), factory).clip("bob")

        assert bob.playback_mode is PlaybackMode.PING_PONG
        assert _colour(bob.frames[0]) == COLOURS[first]

    def test_a_repeat_count_plays_that_many_times(
        self, tmp_path: Path, factory: PygameTextureFactory
    ) -> None:
        tags = [
            {"name": "hit", "from": 0, "to": 1, "direction": "forward", "repeat": "2"}
        ]

        hit = load_aseprite(_export(tmp_path, tags), factory).clip("hit")

        assert hit.playback_mode is PlaybackMode.LOOP_TIMES
        assert hit.loop_count == 2

    def test_a_file_with_no_tags_has_one_clip_of_everything(
        self, tmp_path: Path, factory: PygameTextureFactory
    ) -> None:
        sheet = load_aseprite(_export(tmp_path), factory)

        assert list(sheet.clips) == ["hero"]
        assert len(sheet.clip("hero").frames) == 4

    def test_asking_for_a_missing_tag_lists_the_ones_there_are(
        self, tmp_path: Path, factory: PygameTextureFactory
    ) -> None:
        tags = [{"name": "idle", "from": 0, "to": 1, "direction": "forward"}]
        sheet = load_aseprite(_export(tmp_path, tags), factory)

        with pytest.raises(KeyError, match="idle"):
            sheet.clip("walk")


class TestRefusals:
    def _load(self, tmp_path: Path, **kwargs: Any) -> None:
        load_aseprite(_export(tmp_path, **kwargs), PygameTextureFactory())

    def test_json_that_is_not_an_export(self, tmp_path: Path) -> None:
        path = tmp_path / "data.json"
        path.write_text('{"hello": 1}', encoding="utf-8")

        with pytest.raises(AsepriteFormatError, match="Export Sprite Sheet"):
            load_aseprite(str(path), PygameTextureFactory())

    def test_a_frame_outside_the_image(self, tmp_path: Path) -> None:
        outside = _frame(0)
        outside["frame"]["x"] = SIZE * 4

        with pytest.raises(AsepriteFormatError, match="different exports"):
            self._load(tmp_path, frames=[outside])

    def test_a_rotated_frame(self, tmp_path: Path) -> None:
        rotated = _frame(0)
        rotated["rotated"] = True

        with pytest.raises(AsepriteFormatError, match="rotated"):
            self._load(tmp_path, frames=[rotated])

    def test_a_frame_with_no_duration(self, tmp_path: Path) -> None:
        untimed = _frame(0)
        untimed["duration"] = 0

        with pytest.raises(AsepriteFormatError, match="duration"):
            self._load(tmp_path, frames=[untimed])

    def test_a_tag_past_the_last_frame(self, tmp_path: Path) -> None:
        tags = [{"name": "run", "from": 2, "to": 9, "direction": "forward"}]

        with pytest.raises(AsepriteFormatError, match="'run' covers frames 2 to 9"):
            self._load(tmp_path, tags=tags)

    def test_a_direction_it_does_not_know(self, tmp_path: Path) -> None:
        tags = [{"name": "run", "from": 0, "to": 1, "direction": "sideways"}]

        with pytest.raises(AsepriteFormatError, match="sideways"):
            self._load(tmp_path, tags=tags)

    def test_a_ping_pong_with_a_repeat_count(self, tmp_path: Path) -> None:
        tags = [
            {"name": "bob", "from": 0, "to": 1, "direction": "pingpong", "repeat": "3"}
        ]

        with pytest.raises(AsepriteFormatError, match="ping-pong that repeats"):
            self._load(tmp_path, tags=tags)


class TestPaths:
    """The image is looked for beside the JSON, on any platform's paths."""

    WINDOWS = "/\\"

    def test_a_windows_path_keeps_its_folder(self) -> None:
        folder, name = split_path("C:\\art\\heroes\\hero.json", self.WINDOWS)

        assert (folder, name) == ("C:\\art\\heroes\\", "hero.json")

    def test_a_pack_path_on_windows_keeps_its_forward_slashes(self) -> None:
        assert split_path("sprites/hero.json", self.WINDOWS) == (
            "sprites/",
            "hero.json",
        )

    def test_a_bare_file_name_has_no_folder(self) -> None:
        assert split_path("hero.json") == ("", "hero.json")

    def test_a_backslash_is_part_of_a_posix_file_name(self) -> None:
        assert split_path("art/odd\\name.json", "/") == ("art/", "odd\\name.json")

    def test_the_default_separators_are_the_platforms(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from pyguara.graphics import aseprite

        monkeypatch.setattr(aseprite.os, "sep", "\\")
        monkeypatch.setattr(aseprite.os, "altsep", "/")

        assert split_path("C:\\art\\hero.json") == ("C:\\art\\", "hero.json")
