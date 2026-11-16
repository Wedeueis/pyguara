"""Import a sprite sheet exported from Aseprite.

Aseprite's "Export Sprite Sheet" writes an image and a JSON file. The JSON
lists each frame's rectangle and duration, and the tags an artist drew over
the timeline. `load_aseprite()` turns that pair into textures and one
`AnimationClip` per tag, with each frame held for the time the artist gave it.

Read through `pyguara.assets`, so both files load from a pack as well.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Any

from PIL import Image

from pyguara import assets
from pyguara.graphics.components.animation import AnimationClip, PlaybackMode
from pyguara.graphics.protocols import TextureFactory
from pyguara.resources.types import Texture

_REVERSED = {"reverse", "pingpong_reverse"}
_PING_PONG = {"pingpong", "pingpong_reverse"}
_DIRECTIONS = {"forward"} | _REVERSED | _PING_PONG


class AsepriteFormatError(ValueError):
    """The JSON is not a sprite sheet export this importer can read."""


@dataclass(frozen=True)
class AsepriteSheet:
    """What one Aseprite export holds.

    Attributes:
        frames: Every frame of the timeline, in order, each the size of the
            sprite's canvas.
        durations: Seconds each frame is held, one per frame.
        clips: One clip per tag, by the tag's name. A file with no tags has
            a single looping clip of every frame, named after the file.
    """

    frames: tuple[Texture, ...]
    durations: tuple[float, ...]
    clips: dict[str, AnimationClip]

    def clip(self, name: str) -> AnimationClip:
        """Return the clip for the tag called `name`.

        Args:
            name: The tag's name as written in Aseprite.

        Returns:
            The clip.

        Raises:
            KeyError: If there is no such tag; the message lists the ones
                there are.
        """
        try:
            return self.clips[name]
        except KeyError:
            raise KeyError(
                f"No tag named {name!r}. This sheet has: {sorted(self.clips)}"
            ) from None


def load_aseprite(
    json_path: str,
    factory: TextureFactory,
    *,
    image_path: str | None = None,
) -> AsepriteSheet:
    """Load an Aseprite sprite sheet export as textures and clips.

    Reads both of the JSON layouts Aseprite writes, "Array" and "Hash". A
    frame exported with "Trim" is put back on a canvas of the sprite's own
    size, so the frames of a clip stay aligned with each other.

    Args:
        json_path: The exported JSON file.
        factory: Makes the backend's textures.
        image_path: The exported image. Defaults to the file the JSON
            names, looked for beside the JSON.

    Returns:
        The sheet's frames, their durations and its clips.

    Raises:
        AsepriteFormatError: If the JSON is not an Aseprite export, a frame
            is rotated or lies outside the image, or a tag cannot be
            played as it is written.
    """
    try:
        document = json.loads(assets.read_text(json_path))
    except json.JSONDecodeError as error:
        raise AsepriteFormatError(f"{json_path} is not valid JSON: {error}") from error
    if not isinstance(document, dict) or "frames" not in document:
        raise AsepriteFormatError(
            f"{json_path} has no 'frames'. Export it from Aseprite with "
            "File > Export Sprite Sheet and the JSON Data option ticked."
        )
    meta = document.get("meta") or {}

    if image_path is None:
        named = meta.get("image")
        if not named:
            raise AsepriteFormatError(
                f"{json_path} does not name its image; pass image_path."
            )
        # Only the file name: Aseprite may write the absolute path of the
        # machine that exported it.
        file_name = PurePosixPath(str(named).replace("\\", "/")).name
        image_path = str(PurePosixPath(json_path).parent / file_name)

    with Image.open(assets.open(image_path)) as opened:
        image = opened.convert("RGBA")

    records = document["frames"]
    entries = list(records.values()) if isinstance(records, dict) else list(records)
    if not entries:
        raise AsepriteFormatError(f"{json_path} lists no frames.")

    frames = tuple(
        _frame_texture(image, entry, index, image_path, json_path, factory)
        for index, entry in enumerate(entries)
    )
    durations = tuple(
        _duration(entry, index, json_path) for index, entry in enumerate(entries)
    )

    tags = meta.get("frameTags") or []
    if tags:
        clips = {
            str(tag.get("name")): _tag_clip(tag, frames, durations, json_path)
            for tag in tags
        }
    else:
        name = PurePosixPath(json_path).stem
        clips = {name: _clip(name, frames, durations, PlaybackMode.LOOP, 1)}

    return AsepriteSheet(frames, durations, clips)


def _frame_texture(
    image: Image.Image,
    entry: Any,
    index: int,
    image_path: str,
    json_path: str,
    factory: TextureFactory,
) -> Texture:
    """Cut one frame out of the sheet, on a canvas of the sprite's size.

    Raises:
        AsepriteFormatError: If the frame has no rectangle, is rotated, or
            lies outside the image.
    """
    try:
        rect = entry["frame"]
        x, y, width, height = (int(rect[key]) for key in ("x", "y", "w", "h"))
    except (KeyError, TypeError, ValueError) as error:
        raise AsepriteFormatError(
            f"{json_path}: frame {index} has no usable 'frame' rectangle."
        ) from error
    if entry.get("rotated"):
        raise AsepriteFormatError(
            f"{json_path}: frame {index} is rotated in the sheet, which this "
            "importer does not undo. Export without rotation."
        )
    if (
        width <= 0
        or height <= 0
        or x < 0
        or y < 0
        or x + width > image.width
        or y + height > image.height
    ):
        raise AsepriteFormatError(
            f"{json_path}: frame {index} is {width}x{height} at ({x}, {y}), "
            f"which is outside the {image.width}x{image.height} image "
            f"{image_path}. The JSON and the image are from different exports."
        )

    cut = image.crop((x, y, x + width, y + height))

    source = entry.get("sourceSize") or {}
    placed = entry.get("spriteSourceSize") or {}
    full_width = int(source.get("w", width))
    full_height = int(source.get("h", height))
    if (full_width, full_height) != (width, height):
        canvas = Image.new("RGBA", (full_width, full_height), (0, 0, 0, 0))
        canvas.paste(cut, (int(placed.get("x", 0)), int(placed.get("y", 0))))
        cut = canvas

    return factory.create_from_bytes(
        f"{image_path}#{index}", cut.tobytes("raw", "RGBA"), cut.width, cut.height
    )


def _duration(entry: Any, index: int, json_path: str) -> float:
    """Return one frame's duration in seconds.

    Raises:
        AsepriteFormatError: If the duration is missing or not positive.
    """
    milliseconds = entry.get("duration")
    if not isinstance(milliseconds, (int, float)) or milliseconds <= 0:
        raise AsepriteFormatError(
            f"{json_path}: frame {index} has duration {milliseconds!r}; it "
            "must be a positive number of milliseconds."
        )
    return milliseconds / 1000.0


def _tag_clip(
    tag: Any,
    frames: tuple[Texture, ...],
    durations: tuple[float, ...],
    json_path: str,
) -> AnimationClip:
    """Build the clip one tag describes.

    Raises:
        AsepriteFormatError: If the tag's range, direction or repeat count
            cannot be read, or it is a ping-pong with a repeat count.
    """
    name = str(tag.get("name"))
    try:
        first, last = int(tag["from"]), int(tag["to"])
    except (KeyError, TypeError, ValueError) as error:
        raise AsepriteFormatError(
            f"{json_path}: tag {name!r} has no usable 'from' and 'to'."
        ) from error
    if not 0 <= first <= last < len(frames):
        raise AsepriteFormatError(
            f"{json_path}: tag {name!r} covers frames {first} to {last}, but "
            f"the sheet has {len(frames)}."
        )

    direction = str(tag.get("direction", "forward"))
    if direction not in _DIRECTIONS:
        raise AsepriteFormatError(
            f"{json_path}: tag {name!r} has direction {direction!r}; expected "
            f"one of {sorted(_DIRECTIONS)}."
        )

    tag_frames = frames[first : last + 1]
    tag_durations = durations[first : last + 1]
    if direction in _REVERSED:
        tag_frames = tag_frames[::-1]
        tag_durations = tag_durations[::-1]

    # Aseprite writes the repeat count as a string, and leaves it out (or
    # writes 0) for a tag that loops forever.
    try:
        repeat = int(tag.get("repeat") or 0)
    except (TypeError, ValueError) as error:
        raise AsepriteFormatError(
            f"{json_path}: tag {name!r} has repeat {tag.get('repeat')!r}."
        ) from error

    if direction in _PING_PONG:
        if repeat:
            raise AsepriteFormatError(
                f"{json_path}: tag {name!r} is a ping-pong that repeats "
                f"{repeat} times. The engine plays a ping-pong forever or a "
                "forward loop a number of times, not both. Clear the tag's "
                "repeat count, or change its direction."
            )
        return _clip(name, tag_frames, tag_durations, PlaybackMode.PING_PONG, 1)
    if repeat:
        return _clip(name, tag_frames, tag_durations, PlaybackMode.LOOP_TIMES, repeat)
    return _clip(name, tag_frames, tag_durations, PlaybackMode.LOOP, 1)


def _clip(
    name: str,
    frames: tuple[Texture, ...],
    durations: tuple[float, ...],
    mode: PlaybackMode,
    loop_count: int,
) -> AnimationClip:
    """Build a clip, using a plain frame rate when every frame is as long."""
    uniform = all(duration == durations[0] for duration in durations)
    return AnimationClip(
        name=name,
        frames=list(frames),
        frame_rate=len(durations) / sum(durations),
        mode=mode,
        loop_count=loop_count,
        frame_durations=None if uniform else durations,
    )
