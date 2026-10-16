"""Tweening an entity's own properties, ticked by the engine.

Before this, tweening one property was about forty lines of boilerplate
per effect: hold a reference, own a `TweenManager`, tick it in a system
you wrote, read `current_value`, write it back every frame. The worked
example was `games/true_coral/systems.py`'s `BlockMoveSystem`, and every
game that wanted damage numbers floating up, a pickup magnetising, or a
chest lid lerping wrote it again.

    tween_property(entity, "transform.position", to=target, duration=0.3,
                   easing=EasingType.EASE_OUT_QUAD)

`TweenSystem` does the rest. It is a **scene** system rather than a
DI-registered global, which #37 suggested: an app-wide manager outlives
the scene whose entities it animates, and goes on writing to components of
entities that no longer exist. That is the same leak #55 fixed for
coroutines, and a scene-owned system cannot have it -- the scene's
`SystemManager.cleanup()` takes the tweens with it.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from pyguara.animation.easing import EasingType
from pyguara.animation.timeline import Animatable
from pyguara.animation.tween import Tween
from pyguara.common.components import Transform
from pyguara.ecs.component import BaseComponent
from pyguara.ecs.entity import Entity
from pyguara.ecs.manager import EntityManager
from pyguara.log import get_logger
from pyguara.physics.components import RigidBody

logger = get_logger(__name__)


class PropertyPathError(Exception):
    """Raised when a property path does not resolve on an entity."""


@dataclass
class Binding:
    """One tween, plus where to write its value.

    Attributes:
        animatable: The tween (or timeline) driving the value.
        apply: Writes a value to the destination. A closure rather than an
            `(object, attribute)` pair because the destination may be a
            read-only property, or a slotted value type that can only be
            replaced on its parent -- the same reason
            `tools.tweakable.TweakableLeaf` carries one.
        path: The path this binding was created from, for messages and for
            `stop_property()`.
        interpolated: The `Transform` this binding switched into visual
            interpolation, or None if it did not. Set only when the binding
            drives `transform.position` on a transform that was not already
            interpolating, so `TweenSystem` can put it back when the tween
            ends and never clears a flag something else owns.
    """

    animatable: Animatable
    apply: Callable[[Any], None]
    path: str = ""
    interpolated: Transform | None = None


class Tweener(BaseComponent):
    """Holds the tweens running against one entity's properties.

    Attached automatically by `tween_property()`; a game rarely constructs
    one. Pure data, like every component: `TweenSystem` is what ticks it.
    """

    def __init__(self) -> None:
        """Start with no bindings."""
        super().__init__()
        self.bindings: list[Binding] = []


@dataclass
class TweenTarget:
    """A resolved destination: what to read now, and how to write later.

    Attributes:
        current: The value the property holds right now, which becomes the
            tween's start point.
        apply: Writes a new value back.
        container: The object holding the final attribute, and
        attribute: its name -- together enough to recognise *what* is being
            tweened without re-parsing the path. `_interpolate_position_tween`
            uses them to spot a `Transform.position` tween.
    """

    current: Any
    apply: Callable[[Any], None]
    container: Any = None
    attribute: str = ""


def resolve_property(entity: Entity, path: str) -> TweenTarget:
    """Resolve a dotted path against an entity into a readable destination.

    The first segment names a component the way `entity.transform` does;
    the rest walk attributes from there, so `"transform.position"`,
    `"sprite.color"` and `"sprite.color.a"` all work.

    The write goes through the *last* container, replacing the final
    attribute rather than mutating it. That is the only approach that
    works for a value type: `Vector2` wraps an immutable `pymunk.Vec2d`
    and `Color`'s channels are clamped on construction, so neither can be
    changed in place.

    Args:
        entity: The entity to resolve against.
        path: Dotted path, e.g. `"transform.position"`.

    Returns:
        The destination.

    Raises:
        PropertyPathError: If the path is empty, has no attribute part, or
            names something the entity does not have. Raised rather than
            logged: a typo'd path means the effect silently never happens,
            and a tween that quietly does nothing is worse to debug than
            one that refuses to start.
    """
    segments = path.split(".")
    if len(segments) < 2 or not all(segments):
        raise PropertyPathError(
            f"Property path {path!r} needs at least a component and an "
            f"attribute, e.g. 'transform.position'."
        )

    try:
        container: Any = getattr(entity, segments[0])
    except AttributeError as error:
        raise PropertyPathError(
            f"Entity {entity.id} has no component {segments[0]!r} for path "
            f"{path!r}. Add the component before tweening it."
        ) from error

    for segment in segments[1:-1]:
        try:
            container = getattr(container, segment)
        except AttributeError as error:
            raise PropertyPathError(
                f"Property path {path!r} does not resolve: "
                f"{type(container).__name__} has no {segment!r}."
            ) from error

    final = segments[-1]
    if not hasattr(container, final):
        raise PropertyPathError(
            f"Property path {path!r} does not resolve: "
            f"{type(container).__name__} has no {final!r}."
        )

    held = container
    return TweenTarget(
        current=getattr(container, final),
        apply=lambda value: setattr(held, final, value),
        container=held,
        attribute=final,
    )


def _interpolate_position_tween(target: TweenTarget) -> Transform | None:
    """Switch a position-driving tween's transform into visual interpolation.

    `TweenSystem` runs on the **fixed** step, so a tween moves a position 60
    times a second however fast the display is. For a physics body that is
    already handled: `PhysicsSystem` sets `Transform.interpolate`, the scene
    manager snapshots `previous_position` before each tick, and the render
    path lerps between the two. A tween on an entity with no `RigidBody`
    had none of that, so on a 120 or 144 Hz display the sprite held still
    for two or three frames and then jumped -- the judder
    `render_position`'s own docstring describes.

    Opting the transform in is the fix that keeps the fixed step. Moving
    the tick to `variable_update` would also look smooth and would cost
    two things worth more: the ordering guarantee documented at
    `scene/base.py:120-123` (a tween driving a position must be applied
    before steering, AI or the scene's update reads it this tick), and
    reproducibility -- a framerate-dependent tween does not replay, which
    is the thing `RandomService` seeding was just fixed to protect.

    Mirrors `PhysicsSystem`'s own opt-in, including seeding
    `previous_position`: without it the first rendered frame lerps from
    whatever the field happened to hold.

    Args:
        target: The resolved destination.

    Returns:
        The transform that was switched on, so the caller can put it back
        later -- or None if this is not a position tween, or the transform
        was interpolating already and is therefore not ours to restore.
    """
    container = target.container
    if not isinstance(container, Transform) or target.attribute != "position":
        return None
    if container.interpolate:
        return None

    container.interpolate = True
    container.previous_position = container.position
    return container


def tween_property(
    entity: Entity,
    path: str,
    to: Any,
    duration: float,
    easing: EasingType = EasingType.LINEAR,
    *,
    delay: float = 0.0,
    loops: int = 0,
    yoyo: bool = False,
    on_complete: Callable[[], None] | None = None,
    replace: bool = True,
) -> Tween:
    """Tween one of an entity's properties from its current value to `to`.

    The start point is read from the property itself, so a call interrupting
    an earlier tween of the same path begins from wherever it had got to --
    which is what makes a knockback retargeted mid-flight look continuous
    rather than snapping back.

    Args:
        entity: The entity to animate.
        path: Dotted path, e.g. `"transform.position"`.
        to: The destination value, of the property's own type.
        duration: Seconds.
        easing: Which curve.
        delay: Seconds to wait before moving.
        loops: 0 once, -1 forever, N extra repeats.
        yoyo: Alternate direction each loop.
        on_complete: Called once when the tween finishes.
        replace: Stop any tween already running on this exact path first.
            On by default, because two tweens writing the same property
            every frame is never what anyone wanted: the last writer wins
            and the result depends on binding order.

    Returns:
        The `Tween`, for `pause()`, `stop()` or inspection.

    Raises:
        PropertyPathError: If `path` does not resolve.
    """
    target = resolve_property(entity, path)

    if not entity.has_component(Tweener):
        entity.add_component(Tweener())
    tweener = entity.get_component(Tweener)

    if replace:
        stop_property(entity, path)

    tween = Tween(
        start_value=target.current,
        end_value=to,
        duration=duration,
        easing=easing,
        delay=delay,
        loops=loops,
        yoyo=yoyo,
        on_complete=on_complete,
    )
    tween.start()
    tweener.bindings.append(
        Binding(
            animatable=tween,
            apply=target.apply,
            path=path,
            interpolated=_interpolate_position_tween(target),
        )
    )
    return tween


def bind_tween(
    entity: Entity, path: str, animatable: Animatable, *, replace: bool = True
) -> Binding:
    """Drive an entity property from a tween or timeline you built yourself.

    The escape hatch from `tween_property`'s single-tween shape: a timeline
    whose value feeds a property, or a tween configured in ways the helper
    does not expose.

    Args:
        entity: The entity to animate.
        path: Dotted path to write to.
        animatable: Something with `update(dt) -> bool` and a
            `current_value`. A `Timeline` has no value of its own, so it
            only makes sense here when it is driving callbacks rather than
            a property.
        replace: Stop anything already bound to this path.

    Returns:
        The binding, for `Tweener.bindings` bookkeeping.

    Raises:
        PropertyPathError: If `path` does not resolve.
    """
    target = resolve_property(entity, path)
    if not entity.has_component(Tweener):
        entity.add_component(Tweener())
    tweener = entity.get_component(Tweener)
    if replace:
        stop_property(entity, path)
    binding = Binding(animatable=animatable, apply=target.apply, path=path)
    tweener.bindings.append(binding)
    return binding


def stop_property(entity: Entity, path: str) -> int:
    """Stop every tween writing to one property, leaving its value as-is.

    Args:
        entity: The entity.
        path: The path to stop.

    Returns:
        How many bindings were removed.
    """
    if not entity.has_component(Tweener):
        return 0
    tweener = entity.get_component(Tweener)
    doomed = [b for b in tweener.bindings if b.path == path]
    for binding in doomed:
        binding.animatable.stop()
        tweener.bindings.remove(binding)
    return len(doomed)


def stop_tweens(entity: Entity) -> int:
    """Stop every tween on an entity.

    What a death or a scene change wants, and cheaper than removing the
    component: the entity keeps its (now empty) `Tweener` and the next
    `tween_property()` does not have to re-add one.

    Args:
        entity: The entity.

    Returns:
        How many bindings were removed.
    """
    if not entity.has_component(Tweener):
        return 0
    tweener = entity.get_component(Tweener)
    count = len(tweener.bindings)
    for binding in tweener.bindings:
        binding.animatable.stop()
    tweener.bindings.clear()
    return count


class TweenSystem:
    """Advances every entity's `Tweener` bindings and writes their values.

    Registered on each scene's own `SystemManager`, in the engine priority
    band, so it runs before the scene's own update sees the result.

    A finished binding is dropped the tick it finishes, after its final
    value has been written -- so a tween to an exact destination lands on
    that destination rather than one frame short of it.
    """

    def __init__(self, entity_manager: EntityManager) -> None:
        """Initialise the system.

        Args:
            entity_manager: The scene's entity manager.
        """
        self._entity_manager = entity_manager

    def update(self, dt: float) -> None:
        """Tick every binding on every entity carrying a `Tweener`.

        Args:
            dt: Seconds since the last call.
        """
        for entity in self._entity_manager.get_entities_with(Tweener):
            tweener = entity.get_component(Tweener)
            if not tweener.bindings:
                continue

            finished: list[Binding] = []
            for binding in list(tweener.bindings):
                running = binding.animatable.update(dt)
                if not self._write(binding, entity):
                    running = False
                if not running:
                    finished.append(binding)

            for binding in finished:
                # Guarded: an `on_complete` callback may already have
                # stopped it, or started a replacement on the same path.
                if binding in tweener.bindings:
                    tweener.bindings.remove(binding)
                self._restore_interpolation(binding, entity)

    @staticmethod
    def _restore_interpolation(binding: Binding, entity: Entity) -> None:
        """Put `interpolate` back after a position tween ends.

        Only for a transform this binding switched on itself -- `Binding`
        records that, so a transform that was already interpolating is left
        alone. And never for an entity with a `RigidBody`: physics owns
        that flag and sets it for the life of the body, so clearing it here
        would stop interpolating a body that still needs it. A tween can
        finish on a physics entity if something tweened its position
        directly.

        Args:
            binding: The finished binding.
            entity: Its entity, checked for a `RigidBody`.
        """
        transform = binding.interpolated
        if transform is None:
            return
        binding.interpolated = None
        if entity.has_component(RigidBody):
            return
        transform.interpolate = False

    @staticmethod
    def _write(binding: Binding, entity: Entity) -> bool:
        """Write a binding's current value to its destination.

        `current_value` is read with `getattr` because `Animatable` does
        not promise one: a `Timeline` has no value of its own and is bound
        only to drive callbacks. A binding without a value writes nothing
        and keeps running.

        A write that *raises* drops the binding rather than logging the
        same failure every frame for the rest of the scene -- one game's
        bad destination should not become a 60 Hz log firehose, nor stop
        every other entity's animation.

        Args:
            binding: The binding to write.
            entity: Its entity, for the message.

        Returns:
            False if the binding should be dropped.
        """
        value = getattr(binding.animatable, "current_value", None)
        if value is None:
            return True
        try:
            binding.apply(value)
        except Exception as error:  # noqa: BLE001 - a game's destination
            logger.exception(
                error,
                f"Tween on {binding.path!r} for entity {entity.id} could not "
                f"write its value; the binding is dropped.",
            )
            binding.animatable.stop()
            return False
        return True
