#!/usr/bin/env python3
"""Cut `guara_falcao`'s layout sheet into per-frame PNGs with alpha.

The sheet (`assets/textures/pyguara_platformer_spritesheet.jpg`) is a
**contact sheet**, not an atlas: the strips are labelled, the frames sit
at whatever offsets the layout wanted, and it is a JPEG -- no alpha, and
a grey backdrop that compression has smeared into a cloud of nearby
greys. None of that can be sliced at load time without baking a table of
magic offsets into the game and keying a lossy background every frame.

So it is done once, here, and the result is checked in. The demo loads
ordinary PNGs and knows nothing about contact sheets.

What this does, per frame:

1. **Crop** the box from `FRAMES`, measured off the sheet rather than
   guessed -- see `--measure`, which re-derives them by finding the
   saturated blobs, and prints what it found so a re-exported sheet can
   be checked against the table below.
2. **Key** the grey backdrop to transparency, with a tolerance wide
   enough for the JPEG noise, then erode the edge by one pixel. Keying
   alone leaves a grey halo where compression blurred the boundary; the
   erode is what stops the character having a dirty outline against the
   Cerrado's warm palette.
3. **Despeckle**: drop any blob under a hundredth of the character.
   The boxes are measured off the sheet and occasionally clip a fleck of
   the strip next door, which otherwise ships as a mote hanging in the
   air beside the guará.
4. **Place** it on one canvas shared by every frame -- centred
   horizontally, bottom-aligned -- so the animation does not jitter and
   two clips of different heights still draw the same size.

Run it from the repository root:

    uv run python tools/slice_spritesheet.py
    uv run python tools/slice_spritesheet.py --measure   # re-derive boxes
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
from PIL import Image

SHEET = Path("assets/textures/pyguara_platformer_spritesheet.jpg")
OUT_DIR = Path("games/guara_falcao/assets/textures")

BACKDROP = (124, 124, 124)
"""The sheet's flat grey, sampled from an empty corner."""

KEY_TOLERANCE = 30
"""How far a pixel may sit from `BACKDROP` and still count as backdrop.
Wide, because JPEG smears a flat colour into a cloud around it; the
character art is saturated enough that nothing of it falls inside."""

Box = tuple[int, int, int, int]
"""`(x, y, width, height)` on the sheet."""

PAD = 8
"""Pixels of slack added around every box before cropping.

The boxes were measured by finding *saturated* pixels, which under-reads
a frame's true extent wherever its edge is desaturated -- a falcão's
grey-blue wingtip, a guará's cream tail. Cropping to the measured box
alone clipped those. Padding is free: the key drops the extra backdrop,
and the frame is re-cropped to its own alpha afterwards. The strips sit
about forty pixels apart, so eight never reaches the frame next door."""

FRAMES: dict[str, tuple[Box, ...]] = {
    # The guará, left column of the sheet, top to bottom.
    #
    # The Idle strip has four frames and they are not one pose: the first
    # has no backpack, the second has the pack but no falcão, and only
    # the last two carry both. Looping all four would strobe the gear on
    # and off, so the clip is the last two -- which also means the falcão
    # rides on the guará's back while it stands and flies when it moves,
    # a read the sheet's own "Perching Idle" strip already implies.
    "guara_idle": (
        (456, 58, 165, 144),
        (662, 58, 164, 144),
    ),
    "guara_run": (
        (24, 289, 201, 127),
        (244, 289, 190, 126),
        (458, 289, 203, 126),
        (678, 289, 192, 127),
    ),
    # "Jump Up" is the two-frame leap; "Jump" the single airborne pose
    # beside it. They share a band on the sheet and a clip here: the
    # whole thing is one push off the ground.
    "guara_jump": (
        (29, 496, 178, 148),
        (254, 490, 164, 162),
        (467, 517, 159, 140),
    ),
    # Likewise "Fall Down" (two) and "Land" (one).
    "guara_fall": (
        (29, 754, 186, 135),
        (273, 720, 157, 164),
    ),
    "guara_land": ((461, 763, 179, 148),),
    "guara_hit": (
        (34, 967, 172, 125),
        (270, 945, 148, 148),
        (476, 943, 124, 151),
    ),
    # The falcão, from the sheet's "Fly Run" strip. Only the flying one:
    # the perched falcão is already drawn into the guará's own idle
    # frames, so the companion rides while the guará stands and takes off
    # when it moves -- which is the whole animation, and it is free.
    "falcao_fly": (
        (929, 524, 91, 70),
        (1068, 522, 92, 72),
        (1206, 530, 114, 62),
        (1369, 523, 115, 68),
    ),
}

CANVASES: dict[str, tuple[str, ...]] = {
    "guara": (
        "guara_idle",
        "guara_run",
        "guara_jump",
        "guara_fall",
        "guara_land",
        "guara_hit",
    ),
    "falcao": ("falcao_fly",),
}
"""Which clips share one output size. Every frame of every clip in a group
lands on the same canvas, so a state change never resizes the character."""


def _sheet() -> Image.Image:
    if not SHEET.exists():
        sys.exit(f"sheet not found: {SHEET} (run from the repository root)")
    return Image.open(SHEET).convert("RGB")


def _keyed(crop: Image.Image) -> Image.Image:
    """`crop` with the backdrop knocked out, edge eroded by a pixel.

    The backdrop is removed by **flooding in from the border**, not by
    keying every grey pixel in the frame. The difference is the guará's
    backpack: it is a desaturated blue-grey whose mid-tones sit inside
    any tolerance wide enough for the JPEG noise, so a plain key punched
    holes straight through it. Grey that the outside cannot reach is part
    of the character.

    Args:
        crop: One frame, straight off the sheet.

    Returns:
        The same frame, RGBA, with the backdrop transparent.
    """
    pixels = np.asarray(crop).astype(np.int16)
    backdrop = np.abs(pixels - np.array(BACKDROP)).max(axis=2) <= KEY_TOLERANCE
    solid = ~_flood_from_border(backdrop)

    # Erode: drop any kept pixel that touches a dropped one. JPEG blurs
    # the boundary into intermediate greys, and those survive the key as
    # a halo that reads as a dirty outline over the demo's warm palette.
    padded = np.pad(solid, 1, constant_values=False)
    neighbours = np.ones_like(solid, dtype=bool)
    for dy in (0, 1, 2):
        for dx in (0, 1, 2):
            neighbours &= padded[dy : dy + solid.shape[0], dx : dx + solid.shape[1]]
    solid = solid & neighbours
    solid = _despeckle(solid)

    rgba = np.dstack([pixels.astype(np.uint8), (solid * 255).astype(np.uint8)])
    return Image.fromarray(rgba, "RGBA")


MIN_BLOB = 0.01
"""Smallest connected blob kept, as a fraction of the frame's opaque
pixels. The crop boxes are measured off the sheet and occasionally clip
a fleck of the strip next door; at a hundredth of the character it is a
dust mote hanging in the air, and it survives every other step."""


def _despeckle(solid: np.ndarray) -> np.ndarray:
    """`solid` with every blob smaller than `MIN_BLOB` dropped.

    Args:
        solid: True where the frame is opaque.

    Returns:
        The same mask, minus the flecks.
    """
    floor = solid.sum() * MIN_BLOB
    kept = np.zeros_like(solid)
    remaining = solid.copy()
    while remaining.any():
        seed = np.zeros_like(solid)
        first = np.argwhere(remaining)[0]
        seed[first[0], first[1]] = True
        blob = _grow(seed, remaining)
        if blob.sum() >= floor:
            kept |= blob
        remaining &= ~blob
    return kept


def _grow(seed: np.ndarray, within: np.ndarray) -> np.ndarray:
    """Flood `seed` through `within`, 4-connected, to a fixed point."""
    reached = seed & within
    while True:
        grown = reached.copy()
        grown[1:, :] |= reached[:-1, :]
        grown[:-1, :] |= reached[1:, :]
        grown[:, 1:] |= reached[:, :-1]
        grown[:, :-1] |= reached[:, 1:]
        grown &= within
        if np.array_equal(grown, reached):
            return reached
        reached = grown


def _flood_from_border(candidate: np.ndarray) -> np.ndarray:
    """Which of `candidate`'s cells the frame's border can reach.

    A 4-connected flood from every border cell at once.

    Args:
        candidate: True where a pixel *could* be backdrop.

    Returns:
        True where it is: connected to the outside.
    """
    border = np.zeros_like(candidate)
    border[0, :] = border[-1, :] = True
    border[:, 0] = border[:, -1] = True
    return _grow(border & candidate, candidate)


def _padded(box: Box, sheet_size: tuple[int, int]) -> tuple[int, int, int, int]:
    """`box` grown by `PAD` on every side, clamped to the sheet.

    Args:
        box: The measured `(x, y, width, height)`.
        sheet_size: The sheet's `(width, height)`.

    Returns:
        A `(left, top, right, bottom)` crop box.
    """
    x, y, width, height = box
    sheet_width, sheet_height = sheet_size
    return (
        max(0, x - PAD),
        max(0, y - PAD),
        min(sheet_width, x + width + PAD),
        min(sheet_height, y + height + PAD),
    )


def _tight(frame: Image.Image) -> tuple[int, int, int, int]:
    """The box of `frame`'s opaque pixels, or the whole frame if none."""
    alpha = np.asarray(frame)[:, :, 3]
    rows = np.where(alpha.any(1))[0]
    cols = np.where(alpha.any(0))[0]
    if not len(rows) or not len(cols):
        return (0, 0, frame.width, frame.height)
    return (cols[0], rows[0], cols[-1] + 1, rows[-1] + 1)


def slice_sheet(out_dir: Path) -> list[Path]:
    """Cut every clip in `FRAMES` and write the PNGs.

    Args:
        out_dir: Where the frames land, one `<clip>_<index>.png` each.

    Returns:
        The files written, in the order they were cut.
    """
    sheet = _sheet()
    out_dir.mkdir(parents=True, exist_ok=True)

    keyed: dict[str, list[Image.Image]] = {}
    for clip, boxes in FRAMES.items():
        keyed[clip] = [_keyed(sheet.crop(_padded(box, sheet.size))) for box in boxes]

    written = []
    for group, clips in CANVASES.items():
        tights = {
            clip: [_tight(frame) for frame in keyed[clip]]
            for clip in clips
            if clip in keyed
        }
        width = max(x1 - x0 for boxes in tights.values() for (x0, _, x1, _) in boxes)
        height = max(y1 - y0 for boxes in tights.values() for (_, y0, _, y1) in boxes)
        print(f"{group}: canvas {width}x{height}")

        for clip in clips:
            if clip not in keyed:
                continue
            for index, (frame, tight) in enumerate(
                zip(keyed[clip], tights[clip], strict=True)
            ):
                left, top, right, bottom = tight
                cut = frame.crop((left, top, right, bottom))
                canvas = Image.new("RGBA", (width, height), (0, 0, 0, 0))
                # Centred, and standing on the bottom edge: a clip that is
                # a few pixels shorter must not float.
                canvas.paste(cut, ((width - cut.width) // 2, height - cut.height), cut)
                path = out_dir / f"{clip}_{index}.png"
                canvas.save(path)
                written.append(path)
    return written


def measure() -> None:
    """Re-derive the frame boxes from the sheet and print them.

    What `FRAMES` was built from. Run it against a re-exported sheet to
    see whether the table above still describes it.
    """
    art = np.asarray(_sheet()).astype(np.int16)
    saturated = (art.max(2) - art.min(2)) > 30

    def runs(profile: np.ndarray, floor: int) -> list[tuple[int, int]]:
        found, inside, start = [], False, 0
        for index, value in enumerate(profile):
            if value > floor and not inside:
                start, inside = index, True
            elif value <= floor and inside:
                inside = False
                if index - start > 12:
                    found.append((start, index))
        if inside:
            found.append((start, len(profile)))
        return found

    region = saturated[:1130, :880]
    for y0, y1 in runs(region.sum(1), 6):
        band = region[y0:y1]
        boxes = []
        for x0, x1 in runs(band.sum(0), 3):
            rows = np.where(band[:, x0:x1].any(1))[0]
            boxes.append((x0, y0 + rows[0], x1 - x0, rows[-1] - rows[0] + 1))
        print(f"band y={y0}..{y1}: {boxes}")


def main() -> None:
    """Slice the sheet, or measure it."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--measure",
        action="store_true",
        help="re-derive the frame boxes from the sheet and print them",
    )
    parser.add_argument("--out", type=Path, default=OUT_DIR, help="output directory")
    args = parser.parse_args()

    if args.measure:
        measure()
        return
    written = slice_sheet(args.out)
    print(f"wrote {len(written)} frames to {args.out}")


if __name__ == "__main__":
    main()
