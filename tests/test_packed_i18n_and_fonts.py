"""Locale files and fallback fonts load from a mounted pack.

A game built with `pyguara build --pack` ships its `locales/` and its CJK
faces inside the pack, and nothing loose. These tests mount a pack over a
folder that holds neither, so a loader that went to the disk finds nothing.
"""

from __future__ import annotations

import json
import os
import shutil
from collections.abc import Iterator
from pathlib import Path

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

import pygame
import pytest

from pyguara import assets
from pyguara.cli.pack import bake_pack
from pyguara.graphics import fonts
from pyguara.i18n import Translator
from pyguara.i18n.check import check_directory

try:
    from pyguara import pyguara_core_rs as extension
except ImportError:  # pragma: no cover - the wheel always ships it
    extension = None

CJK = Path(__file__).parent / "fixtures" / "fonts" / "PyguaraTestCJK.ttf"


@pytest.fixture
def game(tmp_path: Path) -> Iterator[Path]:
    """A game folder whose `locales/` and `fonts/` exist only in its pack."""
    source = tmp_path / "source"
    (source / "locales").mkdir(parents=True)
    (source / "fonts").mkdir()
    for code, title in (("en", "Reclaimer"), ("ja", "リクレイマー")):
        (source / "locales" / f"{code}.json").write_text(
            json.dumps({"title": title}, ensure_ascii=False), encoding="utf-8"
        )
    shutil.copy(CJK, source / "fonts" / CJK.name)
    root = tmp_path / "game"
    root.mkdir()
    bake_pack([source / "locales", source / "fonts"], root / "Game.pak")
    shutil.rmtree(source)
    assets.mount_pack(root / "Game.pak", root=root)
    yield root
    assets.unmount_all()
    fonts.set_fallback_fonts([])


def test_the_translator_loads_a_packed_locales_folder(game: Path) -> None:
    assert not (game / "locales").exists()

    tr = Translator.from_directory(game / "locales", locale="ja")

    assert tr.available == ("en", "ja")
    assert tr("title") == "リクレイマー"


def test_the_check_reads_a_packed_locales_folder(game: Path) -> None:
    report = check_directory(game / "locales")

    assert report.locales == ["en", "ja"]
    assert report.errors == []


def test_a_packed_fallback_face_is_accepted(game: Path) -> None:
    face = game / "fonts" / CJK.name
    assert not face.exists()

    fonts.set_fallback_fonts([face])

    assert fonts.fallback_fonts() == (face,)
    assert fonts.fallback_font_data(face) == CJK.read_bytes()


@pytest.mark.skipif(extension is None, reason="extension not built")
def test_both_renderers_draw_from_a_packed_fallback_face(game: Path) -> None:
    from pyguara.graphics.backends.pygame.fallback_font import FallbackFont

    fonts.set_fallback_fonts([game / "fonts" / CJK.name])

    assert len(fonts.native_fallback_faces()) == 1
    assert fonts.faces_for("A一") == [0, 1]
    pygame.init()
    try:
        runs = FallbackFont(32).runs("A一")
        assert [text for _, text in runs] == ["A", "一"]
        assert runs[0][0] is not runs[1][0]
    finally:
        pygame.quit()
