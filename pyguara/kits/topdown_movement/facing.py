"""Choosing an animation clip from a facing direction.

Every game this engine targets is top-down, and every top-down character
has N actions times 4 or 8 facings. Today that means registering
`walk_down`, `walk_up`, `walk_left`, `walk_right` as flat clips and
writing the same selection system by hand in each game -- including the
two details everyone gets wrong the first time: that a *stopped*
character must keep facing where it last faced rather than snapping to a
default, and that screen Y grows downward, so a negative Y velocity is
"up".

A kit rather than core: 8-way facing is a genre's vocabulary, and nothing
in `pyguara.graphics` should know what "down" means.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from enum import Enum

from pyguara.common.types import Vector2
from pyguara.ecs.component import BaseComponent


class Facing(Enum):
    """The eight compass directions a top-down character can face.

    Ordered clockwise from `DOWN`, which is the direction a character
    faces at rest in every top-down game: towards the player.
    """

    DOWN = "down"
    DOWN_LEFT = "down_left"
    LEFT = "left"
    UP_LEFT = "up_left"
    UP = "up"
    UP_RIGHT = "up_right"
    RIGHT = "right"
    DOWN_RIGHT = "down_right"


_EIGHT_WAY: tuple[Facing, ...] = (
    Facing.RIGHT,
    Facing.DOWN_RIGHT,
    Facing.DOWN,
    Facing.DOWN_LEFT,
    Facing.LEFT,
    Facing.UP_LEFT,
    Facing.UP,
    Facing.UP_RIGHT,
)
"""Facings by 45-degree sector, starting at +X and turning towards +Y."""

_FOUR_WAY: tuple[Facing, ...] = (
    Facing.RIGHT,
    Facing.DOWN,
    Facing.LEFT,
    Facing.UP,
)
"""Facings by 90-degree sector, same starting point and direction."""

_DIAGONAL_FALLBACK: dict[Facing, Facing] = {
    Facing.DOWN_LEFT: Facing.LEFT,
    Facing.UP_LEFT: Facing.LEFT,
    Facing.DOWN_RIGHT: Facing.RIGHT,
    Facing.UP_RIGHT: Facing.RIGHT,
}
"""Which cardinal a diagonal borrows from when no diagonal clip exists.

Left and right rather than up and down: a four-direction sprite set reads
as sideways-facing on a diagonal far more convincingly than as
facing-away, because the silhouette of a profile view is closer to a
three-quarter view than a back view is.
"""


def facing_from_vector(direction: Vector2, ways: int = 8) -> Facing | None:
    """Pick the facing a direction vector points at.

    Screen Y grows **downward**, so a negative Y is up. That is the detail
    that makes a hand-written version of this face backwards for a week
    before anyone notices.

    Args:
        direction: Any non-zero vector -- a velocity, an aim, a knockback.
            Its length is ignored.
        ways: 8 for diagonals, 4 for cardinals only.

    Returns:
        The facing, or None for a zero vector. None rather than a default,
        because a stopped character must keep facing where it last faced:
        snapping to `DOWN` on every halt is the other classic bug.

    Raises:
        ValueError: If `ways` is neither 4 nor 8.
    """
    if ways not in (4, 8):
        raise ValueError(f"ways must be 4 or 8, got {ways}.")

    if direction.x == 0 and direction.y == 0:
        return None

    sectors = _EIGHT_WAY if ways == 8 else _FOUR_WAY
    # atan2(y, x) with screen-down Y already gives an angle that turns from
    # +X towards +Y, matching the sector tables.
    angle = math.degrees(math.atan2(direction.y, direction.x)) % 360.0
    span = 360.0 / len(sectors)
    index = int((angle + span / 2) // span) % len(sectors)
    return sectors[index]


@dataclass
class DirectionalClipSet:
    """Clip names keyed by `(action, facing)`, with sensible fallbacks.

    The naming convention is the common one -- `"walk_down"`,
    `"attack_up_left"` -- so `for_action()` can usually derive the name
    and a game only lists the exceptions.

    Attributes:
        actions: The actions this set covers, e.g. `("idle", "walk")`.
        ways: 4 or 8. A 4-way set maps a diagonal onto its left/right
            cardinal.
        overrides: `(action, facing)` to clip name, for the cases the
            convention does not cover -- a shared `idle_down` used for
            every facing, say.
        separator: Between action and facing in a derived name.
    """

    actions: tuple[str, ...]
    ways: int = 8
    overrides: dict[tuple[str, Facing], str] = field(default_factory=dict)
    separator: str = "_"

    def __post_init__(self) -> None:
        """Validate the direction count.

        Raises:
            ValueError: If `ways` is neither 4 nor 8.
        """
        if self.ways not in (4, 8):
            raise ValueError(f"ways must be 4 or 8, got {self.ways}.")

    def resolve_facing(self, facing: Facing) -> Facing:
        """Map a facing onto one this set actually has clips for.

        Args:
            facing: Any facing.

        Returns:
            The same facing for an 8-way set, or its left/right cardinal
            for a 4-way one.
        """
        if self.ways == 8:
            return facing
        return _DIAGONAL_FALLBACK.get(facing, facing)

    def clip_name(self, action: str, facing: Facing) -> str:
        """Return the clip name for an action and a facing.

        Args:
            action: One of `actions` -- not checked, so a game can ask for
                an action it registered later.
            facing: The facing, resolved against `ways` first.

        Returns:
            An override if one exists, else
            `f"{action}{separator}{facing.value}"`.
        """
        resolved = self.resolve_facing(facing)
        override = self.overrides.get((action, resolved))
        if override is not None:
            return override
        return f"{action}{self.separator}{resolved.value}"

    def every_clip_name(self) -> list[str]:
        """Every name this set can produce, for a registration loop.

        Returns:
            One name per action per facing the set covers, deduplicated
            and in a stable order -- overrides collapse several facings
            onto one name, and registering a clip twice is a waste rather
            than an error.
        """
        facings = _EIGHT_WAY if self.ways == 8 else _FOUR_WAY
        seen: dict[str, None] = {}
        for action in self.actions:
            for facing in facings:
                seen[self.clip_name(action, facing)] = None
        return list(seen)


class DirectionalAnimator(BaseComponent):
    """The facing a character is currently showing, and the set to pick from.

    Pure data, like every component: `DirectionalAnimationSystem` reads the
    velocity, updates `facing`, and plays the clip.

    `facing` persists through a stop, which is the whole reason it is
    stored rather than recomputed: a character that has halted is still
    facing somewhere.
    """

    def __init__(
        self,
        clips: DirectionalClipSet,
        action: str = "idle",
        facing: Facing = Facing.DOWN,
    ) -> None:
        """Create the component.

        Args:
            clips: The clip set to resolve names against.
            action: The action to play, set by game code -- "idle",
                "walk", "attack". The system never changes it; only the
                facing is its business.
            facing: Where the character faces to begin with.
        """
        super().__init__()
        self.clips = clips
        self.action = action
        self.facing = facing
