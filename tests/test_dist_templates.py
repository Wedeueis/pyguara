"""The store distribution templates, and the two traps they exist for.

Both failures these guard against are **silent and remote**: the upload
succeeds, the store accepts it, and the damage shows up on a player's
machine. That is why they are asserted here rather than left to a
reviewer's eye on a generated file nobody re-reads.

1. `steam_appid.txt` reaching a depot. It overrides the App ID Steam
   supplies and makes `SteamAPI_RestartAppIfNecessary` return false, so a
   customer who launches the executable directly plays with no client
   attached -- no overlay, no achievements, no cloud saves, no error.
2. An itch.io channel name that names no platform. itch.io reads the
   channel to decide what an upload *is*; one that matches none of its
   tokens is tagged for nothing and offered to nobody.
"""

from __future__ import annotations

from pathlib import Path

import click
import pytest
from click.testing import CliRunner
from PIL import Image

from pyguara.cli import main
from pyguara.cli.dist import (
    _ITCH_PLATFORM_TOKENS,
    _STEAM_APPID_FILE,
    _default_itch_channel,
    _itch_platform_of,
    write_icons,
)


@pytest.fixture
def built_game(tmp_path: Path) -> Path:
    """A stand-in for a `pyguara build` output directory."""
    content = tmp_path / "MyGame"
    content.mkdir()
    (content / "MyGame").write_text("not really an executable")
    return content


@pytest.fixture
def source_icon(tmp_path: Path) -> Path:
    """A square source image big enough for every `.ico` size."""
    path = tmp_path / "logo.png"
    Image.new("RGBA", (512, 512), (200, 60, 30, 255)).save(path)
    return path


class TestIcons:
    def test_it_writes_one_icon_per_platform(
        self, source_icon: Path, tmp_path: Path
    ) -> None:
        """PyInstaller converts nothing: Windows needs `.ico` or it fails."""
        written = write_icons(source_icon, tmp_path / "icons")

        assert written["windows"].suffix == ".ico"
        assert written["macos"].suffix == ".icns"
        assert written["linux"].suffix == ".png"
        for path in written.values():
            assert path.is_file()

    def test_the_ico_carries_every_size(
        self, source_icon: Path, tmp_path: Path
    ) -> None:
        """Windows picks a size out of the file; one entry is not enough.

        A single 256px entry renders as a blurry title bar icon and a
        blurry taskbar one, which is the usual symptom of a `.ico`
        written by something that only had one size to give.
        """
        written = write_icons(source_icon, tmp_path / "icons")

        with Image.open(written["windows"]) as icon:
            sizes = {size[0] for size in icon.ico.sizes()}

        assert {16, 32, 48, 256} <= sizes

    def test_a_small_source_writes_only_the_sizes_it_has(self, tmp_path: Path) -> None:
        """Upscaling a 32px logo to 256 looks worse than not offering it."""
        small = tmp_path / "small.png"
        Image.new("RGBA", (32, 32), (0, 0, 0, 255)).save(small)

        written = write_icons(small, tmp_path / "icons")

        with Image.open(written["windows"]) as icon:
            sizes = {size[0] for size in icon.ico.sizes()}

        assert sizes <= {16, 32}

    def test_a_non_square_source_is_converted_but_warned_about(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Declining would be worse: every store stretches it anyway."""
        oblong = tmp_path / "oblong.png"
        Image.new("RGBA", (512, 256), (0, 0, 0, 255)).save(oblong)

        with caplog.at_level("WARNING"):
            written = write_icons(oblong, tmp_path / "icons")

        assert written["windows"].is_file()
        assert "not square" in caplog.text

    def test_something_that_is_not_an_image_is_refused(self, tmp_path: Path) -> None:
        """Named, rather than a stack trace from inside Pillow."""
        text = tmp_path / "notanicon.png"
        text.write_text("this is not a png")

        with pytest.raises(click.ClickException, match="could not be read"):
            write_icons(text, tmp_path / "icons")


class TestSteamScripts:
    def _generate(self, content: Path, out: Path, *extra: str) -> None:
        result = CliRunner().invoke(
            main,
            [
                "dist",
                "steam",
                "--app-id",
                "480",
                "--depot-id",
                "481",
                "--content",
                str(content),
                "--out",
                str(out),
                *extra,
            ],
        )
        assert result.exit_code == 0, result.output

    def test_it_writes_the_whole_script_set(
        self, built_game: Path, tmp_path: Path
    ) -> None:
        out = tmp_path / "steam"
        self._generate(built_game, out)

        assert (out / "scripts" / "app_build_480.vdf").is_file()
        assert (out / "scripts" / "depot_build_481.vdf").is_file()
        assert (out / "upload.sh").is_file()
        assert (out / "upload.bat").is_file()
        assert (out / "README.md").is_file()

    def test_the_app_script_points_at_the_depot_script(
        self, built_game: Path, tmp_path: Path
    ) -> None:
        """A build that lists no depot uploads nothing, successfully."""
        out = tmp_path / "steam"
        self._generate(built_game, out)

        app = (out / "scripts" / "app_build_480.vdf").read_text()

        assert '"AppID"' in app
        assert '"480"' in app
        assert "depot_build_481.vdf" in app

    def test_both_scripts_agree_on_the_content_root(
        self, built_game: Path, tmp_path: Path
    ) -> None:
        """Two roots that disagree upload a subset and report success."""
        out = tmp_path / "steam"
        self._generate(built_game, out)

        app = (out / "scripts" / "app_build_480.vdf").read_text()
        depot = (out / "scripts" / "depot_build_481.vdf").read_text()
        root = str(Path("..") / ".." / built_game.name)

        assert f'"ContentRoot"\t"{root}"' in app
        assert f'"ContentRoot"\t"{root}"' in depot

    def test_the_appid_file_is_kept_out_of_the_depot(
        self, built_game: Path, tmp_path: Path
    ) -> None:
        """The first trap, guarded twice over.

        `steam_appid.txt` is a development aid that bypasses the Steam
        client, so it is written *outside* the content root and the depot
        script also excludes it by name. Either alone would do; both,
        because someone will copy it next to the executable to test
        locally and then upload that directory.
        """
        out = tmp_path / "steam"
        self._generate(built_game, out)

        assert (out / "dev" / _STEAM_APPID_FILE).read_text().strip() == "480"
        assert not (built_game / _STEAM_APPID_FILE).exists()

        depot = (out / "scripts" / "depot_build_481.vdf").read_text()
        assert f'"FileExclusion"\t"{_STEAM_APPID_FILE}"' in depot

    def test_it_does_not_go_live_unless_asked(
        self, built_game: Path, tmp_path: Path
    ) -> None:
        """`SetLive` naming a branch publishes the moment it finishes."""
        out = tmp_path / "steam"
        self._generate(built_game, out)

        app = (out / "scripts" / "app_build_480.vdf").read_text()

        assert '"SetLive"\t""' in app
        assert '"Preview"\t"1"' in app

    def test_a_branch_and_no_preview_are_passed_through(
        self, built_game: Path, tmp_path: Path
    ) -> None:
        out = tmp_path / "steam"
        self._generate(built_game, out, "--branch", "beta", "--no-preview")

        app = (out / "scripts" / "app_build_480.vdf").read_text()

        assert '"SetLive"\t"beta"' in app
        assert '"Preview"\t"0"' in app

    @pytest.mark.parametrize(
        ("flag", "value"),
        [("--app-id", "my-game"), ("--depot-id", "481a")],
    )
    def test_an_id_that_is_not_digits_is_refused(
        self, built_game: Path, tmp_path: Path, flag: str, value: str
    ) -> None:
        """Steamworks IDs are numeric; a name here fails inside steamcmd."""
        args = [
            "dist",
            "steam",
            "--app-id",
            "480",
            "--depot-id",
            "481",
            "--content",
            str(built_game),
            "--out",
            str(tmp_path / "steam"),
        ]
        args[args.index(flag) + 1] = value

        result = CliRunner().invoke(main, args)

        assert result.exit_code != 0
        assert "must be digits" in result.output


class TestItchScript:
    def _invoke(self, content: Path, out: Path, *extra: str):
        return CliRunner().invoke(
            main,
            [
                "dist",
                "itch",
                "--target",
                "studio/my-game",
                "--content",
                str(content),
                "--out",
                str(out),
                *extra,
            ],
        )

    def test_it_writes_a_push_script(self, built_game: Path, tmp_path: Path) -> None:
        out = tmp_path / "itch"
        result = self._invoke(built_game, out, "--channel", "windows")

        assert result.exit_code == 0, result.output
        script = (out / "push.sh").read_text()
        assert "butler push" in script
        assert "studio/my-game:windows" in script

    def test_the_version_reaches_butler(self, built_game: Path, tmp_path: Path) -> None:
        out = tmp_path / "itch"
        self._invoke(built_game, out, "--channel", "linux", "--version", "0.4.1")

        assert "--userversion 0.4.1" in (out / "push.sh").read_text()

    def test_a_channel_naming_no_platform_is_refused(
        self, built_game: Path, tmp_path: Path
    ) -> None:
        """The second trap: itch.io tags from the channel name alone.

        `release-candidate` is a perfectly sensible-looking channel that
        names no platform, so the upload would be tagged for none and
        offered to no player -- while butler reports success.
        """
        result = self._invoke(
            built_game, tmp_path / "itch", "--channel", "release-candidate"
        )

        assert result.exit_code != 0
        assert "names no platform" in result.output
        # The convention here: an error names the alternative.
        assert "win" in result.output
        assert "linux" in result.output

    def test_a_target_that_is_not_user_slash_game_is_refused(
        self, built_game: Path, tmp_path: Path
    ) -> None:
        result = CliRunner().invoke(
            main,
            [
                "dist",
                "itch",
                "--target",
                "my-game",
                "--content",
                str(built_game),
                "--out",
                str(tmp_path / "itch"),
            ],
        )

        assert result.exit_code != 0
        assert "user/game" in result.output

    @pytest.mark.parametrize(
        ("channel", "platform"),
        [
            ("windows", "windows"),
            ("win64-beta", "windows"),
            ("osx-universal", "macos"),
            ("mac", "macos"),
            ("linux-stable", "linux"),
            ("android", "android"),
        ],
    )
    def test_the_platform_is_read_out_of_the_channel_name(
        self, channel: str, platform: str
    ) -> None:
        assert _itch_platform_of(channel) == platform

    def test_a_multi_platform_channel_is_accepted(self) -> None:
        """butler's own documented example is `win-linux-mac-stable`."""
        assert _itch_platform_of("win-linux-mac-stable") is not None

    def test_the_host_default_names_a_platform(self) -> None:
        """Otherwise the default channel would hit the refusal above."""
        assert _itch_platform_of(_default_itch_channel()) is not None

    def test_every_token_the_error_offers_actually_works(self) -> None:
        """An error that names an alternative has to mean it."""
        for tokens in _ITCH_PLATFORM_TOKENS.values():
            for token in tokens:
                assert _itch_platform_of(token) is not None


def test_the_group_is_registered_on_the_cli() -> None:
    """A command nothing reaches is the same as a command that is absent."""
    result = CliRunner().invoke(main, ["dist", "--help"])

    assert result.exit_code == 0
    for subcommand in ("icons", "itch", "steam"):
        assert subcommand in result.output
