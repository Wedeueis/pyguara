"""The nesting clip stack every `UIRenderer` backend shares.

`UIRenderer.push_clip` / `pop_clip` promise that a nested push *intersects*
rather than replaces, and that a pop restores whatever was in force before.
That is the whole of the semantics, it is identical for every backend, and
the backends differ only in what they do with the resulting rectangle --
pygame sets it on a surface, GL would set a scissor, the headless one
discards it. So it lives here once instead of three times.
"""

from pyguara.common.types import Rect


class ClipStack:
    """The stack of clip regions a single UI pass pushes and pops.

    Holds *effective* rectangles -- each already intersected with the one
    below it -- so `current` is what a backend applies without further
    arithmetic, and a pop is a list pop rather than a recomputation.
    """

    def __init__(self) -> None:
        """Start with nothing clipped."""
        self._stack: list[Rect] = []

    @property
    def current(self) -> Rect | None:
        """The region in force, or None when nothing is clipped."""
        return self._stack[-1] if self._stack else None

    @property
    def depth(self) -> int:
        """How many pushes are outstanding."""
        return len(self._stack)

    def push(self, rect: Rect) -> Rect:
        """Narrow the clip to `rect`, intersected with the current one.

        Intersecting is the only behaviour that lets a scroll container sit
        inside another: an inventory inside a scrolling sidebar must not
        draw outside the sidebar just because its own viewport is larger.

        An empty intersection is kept as a zero-size rectangle rather than
        discarded. It clips everything away, which is correct -- none of
        the inner element is on screen -- and it keeps the stack's depth
        matching the caller's pushes, so the matching pop still lands in
        the right place.

        Args:
            rect: The region to clip to, in screen pixels.

        Returns:
            The effective region, after intersection.
        """
        effective = rect if self.current is None else rect.clip(self.current)
        self._stack.append(effective)
        return effective

    def pop(self) -> Rect | None:
        """Undo the most recent push.

        A pop with nothing pushed is a no-op: a widget that pops in a
        `finally` should not turn one bug into two.

        Returns:
            The region now in force, or None if nothing is clipped any more.
        """
        if self._stack:
            self._stack.pop()
        return self.current

    def clear(self) -> Rect | None:
        """Drop every outstanding push.

        For a backend's end-of-frame reset, so an unbalanced push truncates
        one frame rather than every frame after it.

        Returns:
            None, always -- nothing is clipped once this returns.
        """
        self._stack.clear()
        return None
