"""`pyguara atlas` trims, sizes pages to fit, and spills onto more pages.

Each is checked against the pixels: a trimmed region pasted back at its
offset must rebuild the source image exactly, and every region on every
page must hold the sprite it names.
"""

from __future__ import annotations

import json
from pathlib import Path

import pygame
import pytest
from click.testing import CliRunner

from pyguara.common.types import Rect, Vector2
from pyguara.graphics.atlas import Atlas, AtlasRegion
from pyguara.resources.exceptions import InvalidMetadataError

Image = pytest.importorskip("PIL.Image")

from pyguara.cli.atlas_generator import AtlasGenerator, atlas  # noqa: E402


@pytest.fixture(scope="module")
def pygame_display():
    pygame.init()
    pygame.display.set_mode((1, 1))
    yield
    pygame.quit()


def _sprite(size: tuple[int, int], box: tuple[int, int, int, int], seed: int) -> object:
    """A transparent image with a patterned opaque block at `box`."""
    image = Image.new("RGBA", size, (0, 0, 0, 0))
    left, top, right, bottom = box
    for x in range(left, right):
        for y in range(top, bottom):
            image.putpixel((x, y), ((x * 7 + seed) % 256, (y * 13) % 256, seed, 255))
    return image


def _region_image(page: object, region: dict[str, int]) -> object:
    x, y = region["x"], region["y"]
    return page.crop((x, y, x + region["width"], y + region["height"]))


def _rebuilt(page: object, region: dict) -> object:
    """The source image, put back together from a region and its offset."""
    whole = Image.new("RGBA", tuple(region["original_size"]), (0, 0, 0, 0))
    whole.paste(_region_image(page, region), tuple(region["offset"]))
    return whole


# ===== Trimming =====


def test_trimming_keeps_the_opaque_part_and_where_it_was() -> None:
    hero = _sprite((64, 64), (5, 7, 15, 27), seed=1)
    [page], metadata = AtlasGenerator(128, padding=1, trim=True).pack_pages(
        [("hero", hero)]
    )

    region = metadata["regions"]["hero"]
    assert (region["width"], region["height"]) == (10, 20)
    assert region["offset"] == [5, 7]
    assert region["original_size"] == [64, 64]
    assert _rebuilt(page, region).tobytes() == hero.tobytes()


def test_every_trimmed_sprite_rebuilds_its_source() -> None:
    sprites = [
        (f"s{i}", _sprite((40, 30), (i, i % 5, 20 + i, 25), seed=i)) for i in range(12)
    ]
    [page], metadata = AtlasGenerator(256, padding=2, trim=True).pack_pages(sprites)

    for name, image in sprites:
        assert _rebuilt(page, metadata["regions"][name]).tobytes() == image.tobytes()


def test_a_wholly_transparent_sprite_keeps_one_pixel() -> None:
    blank = Image.new("RGBA", (32, 32), (0, 0, 0, 0))
    _, metadata = AtlasGenerator(64, trim=True).pack_pages([("blank", blank)])

    region = metadata["regions"]["blank"]
    assert (region["width"], region["height"]) == (1, 1)
    assert region["offset"] == [0, 0]
    assert region["original_size"] == [32, 32]


def test_without_trim_a_region_is_the_whole_image() -> None:
    hero = _sprite((64, 64), (5, 7, 15, 27), seed=1)
    _, metadata = AtlasGenerator(128).pack_pages([("hero", hero)])

    region = metadata["regions"]["hero"]
    assert (region["width"], region["height"]) == (64, 64)
    assert region["offset"] == [0, 0]
    assert region["page"] == 0


def test_trimming_packs_more_onto_a_page() -> None:
    sprites = [(f"s{i}", _sprite((64, 64), (24, 24, 40, 40), i)) for i in range(16)]
    untrimmed, _ = AtlasGenerator(128, padding=0).pack_pages(sprites)
    trimmed, _ = AtlasGenerator(128, padding=0, trim=True).pack_pages(sprites)
    assert (len(untrimmed), len(trimmed)) == (4, 1)


# ===== Page size =====


def test_a_page_need_not_be_square() -> None:
    [page], metadata = AtlasGenerator(128, atlas_height=64, padding=0).pack_pages(
        [("a", _sprite((60, 60), (0, 0, 60, 60), 1))]
    )
    assert page.size == (128, 64)
    assert metadata["atlas_size"] == [128, 64]

    with pytest.raises(ValueError, match="too small"):
        AtlasGenerator(128, atlas_height=64).pack_pages(
            [("tall", _sprite((10, 100), (0, 0, 10, 100), 1))]
        )


def test_tight_fit_crops_the_page_to_what_it_holds() -> None:
    sprites = [("a", _sprite((30, 20), (0, 0, 30, 20), 1))]
    [page], metadata = AtlasGenerator(512, padding=2, fit="tight").pack_pages(sprites)
    assert page.size == (34, 24)
    assert metadata["pages"][0]["size"] == [34, 24]


def test_power_of_two_fit_rounds_up_but_never_past_the_limit() -> None:
    sprites = [("a", _sprite((30, 20), (0, 0, 30, 20), 1))]
    [page], _ = AtlasGenerator(512, padding=2, fit="pot").pack_pages(sprites)
    assert page.size == (64, 32)

    wide = [("w", _sprite((100, 4), (0, 0, 100, 4), 1))]
    [page], _ = AtlasGenerator(120, padding=0, fit="pot").pack_pages(wide)
    assert page.size == (120, 4)


@pytest.mark.parametrize(
    "kwargs",
    [{"atlas_size": 0}, {"atlas_height": -1}, {"padding": -1}, {"fit": "snug"}],
)
def test_a_bad_setting_is_refused(kwargs: dict) -> None:
    with pytest.raises(ValueError):
        AtlasGenerator(**kwargs)


# ===== Pages =====


def _six() -> list[tuple[str, object]]:
    return [(f"s{i}", _sprite((60, 60), (0, 0, 60, 60), i)) for i in range(6)]


def test_sprites_that_overflow_go_on_the_next_page() -> None:
    sprites = _six()
    pages, metadata = AtlasGenerator(128, padding=0).pack_pages(sprites)

    assert len(pages) == 2
    assert len(metadata["pages"]) == 2
    on_page = [r["page"] for r in metadata["regions"].values()]
    assert sorted(on_page) == [0, 0, 0, 0, 1, 1]
    for name, image in sprites:
        region = metadata["regions"][name]
        held = _region_image(pages[region["page"]], region)
        assert held.tobytes() == image.tobytes()


def test_regions_on_one_page_never_overlap() -> None:
    sprites = [
        (f"s{i}", _sprite((10 + i * 3, 50 - i * 2), (0, 0, 10 + i * 3, 50 - i * 2), i))
        for i in range(20)
    ]
    _, metadata = AtlasGenerator(100, padding=1).pack_pages(sprites)

    rects = [
        (r["page"], Rect(r["x"], r["y"], r["width"], r["height"]))
        for r in metadata["regions"].values()
    ]
    for index, (page, rect) in enumerate(rects):
        assert rect.x + rect.width <= 100 and rect.y + rect.height <= 100
        for other_page, other in rects[index + 1 :]:
            if page == other_page:
                assert not rect.colliderect(other)


def test_pack_asks_for_metadata_when_one_page_is_not_enough() -> None:
    with pytest.raises(ValueError, match="need 2.*-m"):
        AtlasGenerator(128, padding=0).pack(_six())


def test_the_layout_does_not_depend_on_input_order() -> None:
    sprites = _six()
    _, forward = AtlasGenerator(128, padding=0).pack_pages(sprites)
    _, backward = AtlasGenerator(128, padding=0).pack_pages(sprites[::-1])
    assert forward == backward


# ===== Writing and reading back =====


def _folder(tmp_path: Path, sprites: list[tuple[str, object]]) -> Path:
    folder = tmp_path / "sprites"
    folder.mkdir()
    for name, image in sprites:
        image.save(folder / f"{name}.png")
    return folder


def test_generate_writes_each_page_and_names_it(tmp_path: Path) -> None:
    folder = _folder(tmp_path, _six())
    out = tmp_path / "out" / "atlas.png"
    meta = tmp_path / "out" / "atlas.json"

    AtlasGenerator(128, padding=0).generate(folder, out, meta)

    metadata = json.loads(meta.read_text("utf-8"))
    assert [p["image"] for p in metadata["pages"]] == ["atlas.png", "atlas_1.png"]
    assert out.is_file() and (out.parent / "atlas_1.png").is_file()


def test_without_metadata_several_pages_are_refused(tmp_path: Path) -> None:
    folder = _folder(tmp_path, _six())
    with pytest.raises(ValueError, match="-m"):
        AtlasGenerator(128, padding=0).generate(folder, tmp_path / "atlas.png")
    assert not (tmp_path / "atlas.png").exists()


def test_rerunning_into_the_sprite_folder_ingests_no_page(tmp_path: Path) -> None:
    folder = _folder(tmp_path, _six())
    out, meta = folder / "atlas.png", folder / "atlas.json"

    AtlasGenerator(128, padding=0).generate(folder, out, meta)
    AtlasGenerator(128, padding=0).generate(folder, out, meta)

    metadata = json.loads(meta.read_text("utf-8"))
    assert sorted(metadata["regions"]) == [f"s{i}" for i in range(6)]


def test_a_page_no_longer_needed_is_removed(tmp_path: Path) -> None:
    folder = _folder(tmp_path, _six())
    out, meta = folder / "atlas.png", folder / "atlas.json"
    AtlasGenerator(128, padding=0).generate(folder, out, meta)
    assert (folder / "atlas_1.png").is_file()

    AtlasGenerator(256, padding=0).generate(folder, out, meta)

    assert not (folder / "atlas_1.png").exists()
    AtlasGenerator(256, padding=0).generate(folder, out, meta)
    assert len(json.loads(meta.read_text("utf-8"))["regions"]) == 6


def _manager():
    from pyguara.graphics.backends.pygame.loaders import PygameImageLoader
    from pyguara.resources.manager import ResourceManager

    manager = ResourceManager()
    manager.register_loader(PygameImageLoader())
    return manager


def test_load_atlas_reads_every_page_and_offset(
    tmp_path: Path, pygame_display: None
) -> None:
    sprites = _six()
    sprites[5] = ("s5", _sprite((60, 60), (10, 20, 30, 50), 5))
    folder = _folder(tmp_path, sprites)
    out, meta = tmp_path / "atlas.png", tmp_path / "atlas.json"
    AtlasGenerator(128, padding=0, trim=True).generate(folder, out, meta)

    loaded = _manager().load_atlas(str(out), str(meta))

    assert len(loaded.pages) == 2
    assert loaded.texture is loaded.pages[0]
    for name in loaded.list_regions():
        region = loaded.get_region(name)
        assert region is not None
        assert loaded.texture_of(name) is loaded.pages[region.page]
    trimmed = loaded.get_region("s5")
    assert trimmed is not None and trimmed.trimmed
    assert trimmed.offset == (10, 20)
    assert trimmed.original_size == (60, 60)


def _write(tmp_path: Path, metadata: dict) -> tuple[str, str]:
    page = tmp_path / "atlas.png"
    Image.new("RGBA", (16, 16)).save(page)
    meta = tmp_path / "atlas.json"
    meta.write_text(json.dumps(metadata), "utf-8")
    return str(page), str(meta)


_REGION = {"x": 0, "y": 0, "width": 4, "height": 4, "original_size": [4, 4]}


@pytest.mark.parametrize("image", ["../elsewhere.png", "sub/page.png", "..", "", 7])
def test_load_atlas_refuses_a_page_outside_its_folder(
    tmp_path: Path, pygame_display: None, image: object
) -> None:
    page, meta = _write(
        tmp_path,
        {"pages": [{"image": "atlas.png"}, {"image": image}], "regions": {}},
    )
    with pytest.raises(InvalidMetadataError, match="beside the atlas"):
        _manager().load_atlas(page, meta)


def test_load_atlas_refuses_a_region_on_a_missing_page(
    tmp_path: Path, pygame_display: None
) -> None:
    page, meta = _write(tmp_path, {"regions": {"a": {**_REGION, "page": 1}}})
    with pytest.raises(InvalidMetadataError, match="page 1"):
        _manager().load_atlas(page, meta)


def test_load_atlas_refuses_a_malformed_offset(
    tmp_path: Path, pygame_display: None
) -> None:
    page, meta = _write(tmp_path, {"regions": {"a": {**_REGION, "offset": [1]}}})
    with pytest.raises(InvalidMetadataError, match="invalid data"):
        _manager().load_atlas(page, meta)


# ===== The runtime region =====


def test_center_offset_puts_a_trimmed_region_where_the_image_was() -> None:
    region = AtlasRegion("hero", Rect(0, 0, 10, 20), (64, 64), offset=(5, 7))
    assert region.trimmed
    # Region centre in the source: (5 + 5, 7 + 10); source centre (32, 32).
    assert region.center_offset == Vector2(-22.0, -15.0)

    whole = AtlasRegion("whole", Rect(0, 0, 64, 64), (64, 64))
    assert not whole.trimmed
    assert whole.center_offset == Vector2(0.0, 0.0)


def test_an_atlas_refuses_a_region_on_a_page_it_lacks() -> None:
    texture = object()
    region = AtlasRegion("a", Rect(0, 0, 1, 1), (1, 1), page=2)
    with pytest.raises(ValueError, match="page 2"):
        Atlas(texture, {"a": region})  # type: ignore[arg-type]


# ===== The command =====


def test_the_command_takes_a_non_square_size(tmp_path: Path) -> None:
    folder = _folder(tmp_path, _six())
    out, meta = tmp_path / "atlas.png", tmp_path / "atlas.json"

    result = CliRunner().invoke(
        atlas,
        [
            "-i",
            str(folder),
            "-o",
            str(out),
            "-m",
            str(meta),
            "-s",
            "256x128",
            "-p",
            "0",
            "--trim",
            "--fit",
            "pot",
        ],
    )

    assert result.exit_code == 0, result.output
    metadata = json.loads(meta.read_text("utf-8"))
    assert metadata["pages"][0]["size"][0] <= 256
    assert metadata["pages"][0]["size"][1] <= 128


@pytest.mark.parametrize("size", ["big", "0", "256x0", "x"])
def test_the_command_refuses_a_bad_size(tmp_path: Path, size: str) -> None:
    folder = _folder(tmp_path, _six())
    result = CliRunner().invoke(
        atlas, ["-i", str(folder), "-o", str(tmp_path / "a.png"), "-s", size]
    )
    assert result.exit_code == 2
    assert "--size" in result.output
