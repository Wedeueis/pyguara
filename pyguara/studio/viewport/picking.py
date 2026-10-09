"""Working out which entity is under the cursor, or inside a marquee.

Two sources, because neither alone covers a scene:

- **Physics.** `IPhysicsEngine.point_query` is already written for this --
  its docstring says "click-picking: what is under the cursor?" -- and it
  orders results most-deeply-enclosing first, so `result[0]` is the right
  answer when shapes stack. `region_query` then `overlap_box_all` is the
  documented broad-then-exact pair for a marquee, and that docstring says
  "a marquee selection in an editor" in as many words.
- **Sprite bounds.** A sprite with no collider is invisible to all of the
  above, and most decoration is exactly that. So this module also builds
  an axis-aligned box per visible sprite from its transform and texture.

The gap this closes was real: `pyguara/tools/gizmos.py` had the only
picking code in the tree, and it compared a **world** position against a
**screen** position with no camera transform at all, against a hardcoded
32x32 box it invented rather than read. It worked in a demo whose camera
sat at the origin.

Everything here is pure geometry over the ECS -- no GL, no ImGui, no
window -- which is what lets it be tested against a real world directly.
"""

from __future__ import annotations

from dataclasses import dataclass

from pyguara.common.components import Transform
from pyguara.common.types import Rect, Vector2
from pyguara.ecs.manager import EntityManager
from pyguara.graphics.components.camera import Camera2D
from pyguara.graphics.components.sprite import Sprite
from pyguara.log import get_logger

logger = get_logger(__name__)

DEFAULT_PICK_SIZE = 16.0
"""Half-extent, in world units, for an entity with no measurable bounds.

An entity with a `Transform` and nothing else still has to be clickable --
a spawn point, a trigger marker, an empty used as a parent. A fixed box
is honest about being arbitrary, where `gizmos.py`'s identical constant
was indistinguishable from a measurement.
"""


@dataclass(frozen=True)
class Pick:
    """One entity found under a point or inside a region.

    Attributes:
        entity_id: The entity.
        bounds: Its world-space box, as picked against.
        depth: Sort key, lower is in front. Taken from the sprite's layer
            and sort order where there is one, so clicking overlapping
            sprites selects the one actually visible rather than whichever
            the ECS happened to iterate first.
    """

    entity_id: str
    bounds: Rect
    depth: int = 0


def sprite_bounds(transform: Transform, sprite: Sprite | None) -> Rect | None:
    """Return a sprite's world-space box, or None when it has no size.

    Measured from the texture rather than assumed: a 16x16 coin and a
    256x256 backdrop are both pickable at their real size. The sprite's
    own `position` is an offset from the transform, and `scale`
    multiplies both the sprite's and the transform's.

    Rotation is ignored. The box is axis-aligned, which makes a rotated
    sprite's box slightly generous -- the right trade for picking, where
    being a few pixels forgiving is a feature.

    Args:
        transform: The entity's transform.
        sprite: Its sprite, or None.

    Returns:
        The box in world coordinates, or None when there is no sprite or
        its texture has no measurable size.
    """
    if sprite is None:
        return None

    texture = getattr(sprite, "texture", None)
    width = getattr(texture, "width", 0) or 0
    height = getattr(texture, "height", 0) or 0
    if width <= 0 or height <= 0:
        return None

    scale_x = abs(transform.scale.x * sprite.scale.x)
    scale_y = abs(transform.scale.y * sprite.scale.y)
    half_width = (width * scale_x) / 2.0
    half_height = (height * scale_y) / 2.0

    centre = transform.position + sprite.position
    return Rect(
        int(centre.x - half_width),
        int(centre.y - half_height),
        int(max(1.0, half_width * 2.0)),
        int(max(1.0, half_height * 2.0)),
    )


def fallback_bounds(
    transform: Transform, half_extent: float = DEFAULT_PICK_SIZE
) -> Rect:
    """Return a fixed box around `transform`, for an entity with no sprite.

    Args:
        transform: The entity's transform.
        half_extent: Half the box's side, in world units.

    Returns:
        The box in world coordinates.
    """
    scale = max(abs(transform.scale.x), abs(transform.scale.y), 0.01)
    extent = half_extent * scale
    return Rect(
        int(transform.position.x - extent),
        int(transform.position.y - extent),
        int(max(1.0, extent * 2.0)),
        int(max(1.0, extent * 2.0)),
    )


def _depth_of(sprite: Sprite | None) -> int:
    """Return a sort key for a sprite, lower being in front.

    Negated layer and sort order, so the sprite drawn last -- the one a
    user can actually see -- sorts first and wins a click.

    Args:
        sprite: The sprite, or None.

    Returns:
        The sort key.
    """
    if sprite is None:
        # Behind every sprite: an invisible marker should not win a click
        # against the thing drawn on top of it.
        return 1
    return -((sprite.sort_group * 1_000_000) + (sprite.layer * 1000) + sprite.z_index)


def iter_pickable(world: EntityManager) -> list[Pick]:
    """Return every entity that can be picked, with its world box.

    Args:
        world: The world to read.

    Returns:
        One `Pick` per entity with a `Transform`, front-most first.
        Disabled entities and invisible sprites are excluded -- clicking
        something that is not on screen is never what was meant.
    """
    picks: list[Pick] = []
    for entity in world.get_entities_with(Transform):
        if not world.is_entity_enabled(entity.id):
            continue

        transform = entity.get_component(Transform)
        sprite = entity.get_component(Sprite) if entity.has_component(Sprite) else None
        if sprite is not None and not sprite.visible:
            continue

        bounds = sprite_bounds(transform, sprite) or fallback_bounds(transform)
        picks.append(Pick(entity_id=entity.id, bounds=bounds, depth=_depth_of(sprite)))

    # Entity id breaks the tie, so two sprites on the same layer always
    # pick the same way -- a viewport whose selection depended on ECS
    # iteration order would be maddening to use.
    picks.sort(key=lambda pick: (pick.depth, pick.entity_id))
    return picks


def pick_at(
    world: EntityManager, world_point: Vector2, *, physics: object | None = None
) -> Pick | None:
    """Return the front-most entity at `world_point`.

    Physics is consulted first when available: a collider is a deliberate
    statement about an entity's extent, where a sprite box is inferred
    from its image. Its result is then resolved against the sprite pass so
    the caller always gets bounds to draw a selection box with.

    Args:
        world: The world to read.
        world_point: Where to look, in world coordinates.
        physics: An `IPhysicsEngine`, or None to use sprite bounds only.

    Returns:
        The entity under the point, or None.
    """
    if physics is not None:
        entity_id = _physics_point_pick(physics, world_point)
        if entity_id is not None:
            for pick in iter_pickable(world):
                if pick.entity_id == entity_id:
                    return pick
            # Picked something with a body but no transform to measure.
            return Pick(
                entity_id=entity_id,
                bounds=Rect(int(world_point.x), int(world_point.y), 1, 1),
            )

    for pick in iter_pickable(world):
        if _contains(pick.bounds, world_point):
            return pick
    return None


def pick_in_region(
    world: EntityManager, region: Rect, *, require_full_containment: bool = False
) -> list[Pick]:
    """Return every entity overlapping `region`, front-most first.

    Args:
        world: The world to read.
        region: The marquee, in world coordinates.
        require_full_containment: Select only entities entirely inside the
            marquee. The two conventions both exist in real editors --
            touch-select is quicker, enclose-select is precise -- so the
            caller chooses rather than this module guessing.

    Returns:
        The matching picks.
    """
    matches: list[Pick] = []
    for pick in iter_pickable(world):
        if require_full_containment:
            if _contains_rect(region, pick.bounds):
                matches.append(pick)
        elif _overlaps(region, pick.bounds):
            matches.append(pick)
    return matches


def _physics_point_pick(physics: object, world_point: Vector2) -> str | None:
    """Ask the physics engine what is under a point.

    Args:
        physics: Something with a `point_query`.
        world_point: Where to look.

    Returns:
        The front-most entity id as a string, or None. `point_query`
        returns ids ordered most-deeply-enclosing first, so the first
        result is the best pick when shapes stack.
    """
    query = getattr(physics, "point_query", None)
    if query is None:
        return None
    try:
        hits = query(world_point)
    except Exception as exc:
        # A physics engine that cannot answer must not break picking;
        # sprite bounds still work.
        logger.debug(f"point_query failed, falling back to sprite bounds: {exc}")
        return None
    if not hits:
        return None
    return str(hits[0])


def _contains(bounds: Rect, point: Vector2) -> bool:
    """Whether `bounds` contains `point`, edges included.

    Args:
        bounds: The box.
        point: The point to test.

    Returns:
        True when the point is inside.
    """
    return (
        bounds.x <= point.x <= bounds.x + bounds.width
        and bounds.y <= point.y <= bounds.y + bounds.height
    )


def _overlaps(first: Rect, second: Rect) -> bool:
    """Whether two boxes share any area, touching edges included.

    Args:
        first: One box.
        second: The other.

    Returns:
        True when they overlap.
    """
    return not (
        first.x + first.width < second.x
        or second.x + second.width < first.x
        or first.y + first.height < second.y
        or second.y + second.height < first.y
    )


def _contains_rect(outer: Rect, inner: Rect) -> bool:
    """Whether `outer` fully contains `inner`.

    Args:
        outer: The containing box.
        inner: The box to test.

    Returns:
        True when `inner` is entirely inside `outer`.
    """
    return (
        outer.x <= inner.x
        and outer.y <= inner.y
        and inner.x + inner.width <= outer.x + outer.width
        and inner.y + inner.height <= outer.y + outer.height
    )


def marquee_rect(start: Vector2, end: Vector2) -> Rect:
    """Return the box between two drag corners, in any drag direction.

    Args:
        start: Where the drag began.
        end: Where it is now.

    Returns:
        A normalised box. Dragging up-and-left is as valid as
        down-and-right, and a `Rect` with negative width contains nothing.
    """
    left = min(start.x, end.x)
    top = min(start.y, end.y)
    return Rect(
        int(left),
        int(top),
        int(max(1.0, abs(end.x - start.x))),
        int(max(1.0, abs(end.y - start.y))),
    )


def screen_to_world(
    camera: Camera2D, panel_point: Vector2, panel: Rect, target: Rect
) -> Vector2:
    """Map a point in a viewport panel to world coordinates.

    Two mappings, composed. A Studio viewport shows a framebuffer rendered
    at the game's resolution, scaled into whatever size the panel happens
    to be, so a click has to be scaled back to framebuffer space before
    the camera can be asked about it. Skipping that step is how a viewport
    picks correctly only when the panel is exactly the render size.

    Args:
        camera: The camera the frame was rendered with.
        panel_point: The cursor, relative to the panel's content origin.
        panel: The panel's content area.
        target: The framebuffer's size, as rendered.

    Returns:
        The world position under the cursor.
    """
    if panel.width <= 0 or panel.height <= 0:
        return camera.screen_to_world(panel_point)

    scale_x = target.width / panel.width
    scale_y = target.height / panel.height
    in_target = Vector2(panel_point.x * scale_x, panel_point.y * scale_y)
    return camera.screen_to_world(in_target, target)


def world_to_panel(
    camera: Camera2D, world_point: Vector2, panel: Rect, target: Rect
) -> Vector2:
    """Map a world position to a point in a viewport panel.

    The inverse of `screen_to_world`, for drawing a selection box or a
    gizmo over the image. The two must agree exactly, or a handle is drawn
    where it cannot be grabbed.

    Args:
        camera: The camera the frame was rendered with.
        world_point: The world position.
        panel: The panel's content area.
        target: The framebuffer's size, as rendered.

    Returns:
        The position relative to the panel's content origin.
    """
    in_target = camera.world_to_screen(world_point, target)
    if target.width <= 0 or target.height <= 0:
        return in_target

    scale_x = panel.width / target.width
    scale_y = panel.height / target.height
    return Vector2(in_target.x * scale_x, in_target.y * scale_y)
