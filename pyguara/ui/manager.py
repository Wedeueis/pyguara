"""UI Manager and event integration."""

from pyguara.common.types import Rect, Vector2
from pyguara.events.dispatcher import EventDispatcher
from pyguara.events.window import WindowResizeEvent
from pyguara.graphics.protocols import UIRenderer
from pyguara.input import keys
from pyguara.input.events import OnMouseEvent, OnRawKeyEvent
from pyguara.log import get_logger
from pyguara.ui.base import UIElement
from pyguara.ui.types import UIEventType, UILayer

logger = get_logger(__name__)


class UIManager:
    """Manages the UI Scene Graph and routes engine events."""

    def __init__(self, dispatcher: EventDispatcher) -> None:
        """Initialize the UI manager and subscribe to input events."""
        # Roots by layer, each layer keeping the order things were added.
        # A flat list could not say "the HUD is under the pause menu" -- it
        # could only say "the HUD was added first", which stops being true
        # the moment a scene rebuilds it.
        self._layers: dict[int, list[UIElement]] = {}
        self._dispatcher = dispatcher
        self._focused_element: UIElement | None = None

        # Space the roots lay themselves out in. Seeded by Application via
        # set_screen_size(); a resize refreshes it. Layout is skipped while
        # this is degenerate (nothing has told us the screen size yet).
        self._screen_rect = Rect(0, 0, 0, 0)
        self._layout_dirty = True
        self._warned_no_screen = False

        # Subscribe to Engine Input Events
        self._dispatcher.subscribe(OnMouseEvent, self._on_mouse_event)
        self._dispatcher.subscribe(OnRawKeyEvent, self._on_key_event)
        self._dispatcher.subscribe(WindowResizeEvent, self._on_resize_event)

    def add_element(self, element: UIElement, layer: int = UILayer.CONTENT) -> None:
        """Add a root-level UI element to `layer`.

        Args:
            element: The root to add.
            layer: Which band it belongs to. Higher draws later and is hit
                first. `UILayer` names the four the engine expects.
        """
        self._layers.setdefault(int(layer), []).append(element)
        element._manager = self
        self._layout_dirty = True

    def remove_element(self, element: UIElement) -> bool:
        """Remove a root element, whichever layer it is in.

        Args:
            element: The root to remove.

        Returns:
            True if it was there.
        """
        for roots in self._layers.values():
            if element in roots:
                roots.remove(element)
                element._manager = None
                if self._focused_element is element:
                    self.set_focus(None)
                self._layout_dirty = True
                return True
        return False

    def clear(self, layer: int | None = None) -> None:
        """Drop every root element, or every root in one layer.

        Scene teardown is what this is for. Before it existed, every demo in
        the repository reached into the manager's private list to do the
        same thing.

        Args:
            layer: The layer to empty, or None for all of them.
        """
        if layer is None:
            targets = list(self._layers.values())
        else:
            targets = [self._layers.get(int(layer), [])]

        for roots in targets:
            for element in roots:
                element._manager = None
            roots.clear()

        if self._focused_element is not None and not any(
            self._focused_element in roots
            or self._is_descendant(root, self._focused_element)
            for roots in self._layers.values()
            for root in roots
        ):
            self.set_focus(None)
        self._layout_dirty = True

    def elements(self, layer: int | None = None) -> list[UIElement]:
        """The root elements, back to front.

        Args:
            layer: Restrict to one layer, or None for all of them.

        Returns:
            A snapshot list -- mutate the manager, not this.
        """
        if layer is not None:
            return list(self._layers.get(int(layer), []))
        return [element for _, element in self._ordered_roots()]

    def _ordered_roots(self) -> list[tuple[int, UIElement]]:
        """Every root as `(layer, element)`, back to front."""
        return [
            (layer, element)
            for layer in sorted(self._layers)
            for element in self._layers[layer]
        ]

    @staticmethod
    def _is_descendant(root: UIElement, element: UIElement) -> bool:
        """Whether `element` sits anywhere under `root`."""
        if root is element:
            return True
        return any(UIManager._is_descendant(child, element) for child in root.children)

    def set_screen_size(self, width: int, height: int) -> None:
        """Tell the UI the size of the surface its roots lay out against.

        Called once at startup and again whenever the window is resized, so
        percentage- and anchor-based constraints resolve against the real
        drawable area.
        """
        new_rect = Rect(0, 0, width, height)
        if new_rect == self._screen_rect:
            return
        self._screen_rect = new_rect
        self._layout_dirty = True

    def invalidate_layout(self) -> None:
        """Force a layout pass on the next render.

        Call after mutating something a layout depends on but the manager
        cannot see -- a label's text, an element's `visible` flag, a
        container's child list.
        """
        self._layout_dirty = True

    def update(self, dt: float) -> None:
        """Update all managed UI elements."""
        for _, element in self._ordered_roots():
            element.update(dt)

    def render(self, renderer: UIRenderer) -> None:
        """Draw the entire UI stack using the abstract renderer."""
        if self._layout_dirty:
            self._run_layout(renderer)
            self._layout_dirty = False

        for _, element in self._ordered_roots():
            if element.visible:
                element.render(renderer)

    def _run_layout(self, renderer: UIRenderer) -> None:
        """Lay every root out against the current screen rect."""
        if self._screen_rect.width <= 0 or self._screen_rect.height <= 0:
            has_constraints = any(
                self._subtree_has_constraints(el) for _, el in self._ordered_roots()
            )
            if has_constraints and not self._warned_no_screen:
                logger.warning(
                    "UI layout skipped: screen size unknown. Call "
                    "UIManager.set_screen_size() before adding constrained "
                    "elements."
                )
                self._warned_no_screen = True
            return

        for _, element in self._ordered_roots():
            element.layout(self._screen_rect, renderer)

    @staticmethod
    def _subtree_has_constraints(element: UIElement) -> bool:
        """Report whether `element` or any descendant carries constraints."""
        if element.constraints is not None:
            return True
        return any(
            UIManager._subtree_has_constraints(child) for child in element.children
        )

    def set_focus(self, element: UIElement | None, *, visible: bool = False) -> None:
        """Set the focused element.

        Args:
            element: Element to focus, or None to clear focus.
            visible: Whether a component should paint a focus ring for it.
                False for a mouse click or a screen pre-focusing its first
                button on build -- neither is the keyboard asking to see
                where it is. Keyboard traversal (`_step_focus`) and the
                Enter/Space activation path are the only callers that pass
                `True`.
        """
        if self._focused_element is element:
            # Still update visibility: pressing Tab when only one
            # focusable element exists re-selects the same element, and
            # the ring has to appear even though nothing else changed.
            if element is not None:
                element.set_focused(True, visible=visible)
            return

        # Notify old element of focus lost
        if self._focused_element:
            self._focused_element.set_focused(False)
            self._focused_element.handle_event(UIEventType.FOCUS_LOST, Vector2(0, 0), 0)

        self._focused_element = element

        # Notify new element of focus gained
        if self._focused_element:
            self._focused_element.set_focused(True, visible=visible)
            self._focused_element.handle_event(
                UIEventType.FOCUS_GAINED, Vector2(0, 0), 0
            )

    @property
    def focused_element(self) -> UIElement | None:
        """Get the currently focused element."""
        return self._focused_element

    def _on_mouse_event(self, event: OnMouseEvent) -> None:
        """Handle engine mouse events and route them to UI elements."""
        # Map Engine Event -> UI Event Type
        if event.is_motion:
            event_type = UIEventType.MOUSE_MOVE
        elif event.is_down:
            event_type = UIEventType.MOUSE_DOWN
        else:
            event_type = UIEventType.MOUSE_UP

        # Convert tuple pos to Vector2
        pos = Vector2(event.position[0], event.position[1])

        # On click, track focus changes
        clicked_element: UIElement | None = None

        # Front-to-back across every layer, so an overlay takes the click
        # before the HUD underneath it does.
        for _, element in reversed(self._ordered_roots()):
            if element.handle_event(event_type, pos, event.button):
                if event_type == UIEventType.MOUSE_DOWN:
                    # `element` is only the root the event bubbled up
                    # through -- a click on a button inside a BoxContainer
                    # root would otherwise focus the container. `hit_test`
                    # finds the actual leaf under the cursor; walking up
                    # from it finds the nearest thing Tab can reach, which
                    # is a decorative label's button, panel or container,
                    # not the label itself.
                    clicked_element = self._nearest_focusable(element.hit_test(pos))
                break

        # Update focus on mouse down. No ring: a mouse click is not the
        # keyboard asking to see where focus is.
        if event_type == UIEventType.MOUSE_DOWN:
            self.set_focus(clicked_element)

    @staticmethod
    def _nearest_focusable(element: UIElement) -> UIElement | None:
        """`element` if it is a stop on the Tab ring, else None.

        `hit_test()` finds the deepest thing under the cursor, which can be
        a decorative label or an un-focusable panel background rather than
        the button it happens to sit next to -- a click that lands on
        neither should not silently focus something the user did not
        click. It should not focus the *container* either, which is what
        happened before `hit_test()` existed: the root the click bubbled
        up through is not what was actually hit.

        Args:
            element: The element actually under the cursor.

        Returns:
            `element` if focusable, else None.
        """
        return element if element.focusable else None

    def focus_ring(self) -> list[UIElement]:
        """Every focusable element, in traversal order.

        Order is a depth-first walk of the element tree in the order roots
        were added and children were parented -- which is the order a
        reader's eye takes through a declared layout, and needs no
        geometry. A hidden or disabled element is skipped along with its
        whole subtree: a collapsed panel's contents are not reachable by
        Tab just because they still exist.

        Rebuilt per call rather than cached. A cache would have to be
        invalidated by every `add_child`, every `visible` flip and every
        `enabled` flip, and traversal happens on a keypress -- human-speed,
        not frame-speed.

        Returns:
            The focusable elements of the topmost layer that has any.
        """

        def walk(element: UIElement, ring: list[UIElement]) -> None:
            if not element.visible or not element.enabled:
                return
            if element.focusable:
                ring.append(element)
            for child in element.children:
                walk(child, ring)

        # Only the topmost layer that has anything focusable. That is what
        # makes a modal modal: while an options panel is up, Tab cycles the
        # options and cannot wander into the HUD frozen behind it.
        for layer in sorted(self._layers, reverse=True):
            ring: list[UIElement] = []
            for root in self._layers[layer]:
                walk(root, ring)
            if ring:
                return ring
        return []

    def focus_next(self) -> UIElement | None:
        """Move focus to the next focusable element, wrapping at the end.

        Returns:
            The newly focused element, or None if nothing is focusable.
        """
        return self._step_focus(1)

    def focus_previous(self) -> UIElement | None:
        """Move focus to the previous focusable element, wrapping at the start.

        Returns:
            The newly focused element, or None if nothing is focusable.
        """
        return self._step_focus(-1)

    def _step_focus(self, step: int) -> UIElement | None:
        """Move focus `step` places along the ring, wrapping.

        Focus that is currently on nothing -- or on an element that has
        since been hidden, disabled or removed -- enters the ring at its
        start when stepping forward and at its end when stepping back,
        rather than being stuck.
        """
        ring = self.focus_ring()
        if not ring:
            self.set_focus(None)
            return None

        if self._focused_element in ring:
            index = ring.index(self._focused_element) + step
        else:
            index = 0 if step > 0 else -1

        target = ring[index % len(ring)]
        self.set_focus(target, visible=True)
        return target

    def _on_key_event(self, event: OnRawKeyEvent) -> None:
        """Handle keyboard events and route to focused element.

        Traversal is the fallback, not the first move: the focused element
        sees the key first, and Tab or an arrow only moves focus if it did
        not consume it. That is what lets a text input use its arrow keys
        for the caret while the same keys still traverse a row of buttons.
        """
        event_type = UIEventType.KEY_DOWN if event.is_down else UIEventType.KEY_UP

        consumed = False
        if self._focused_element is not None:
            consumed = self._focused_element.handle_event(
                event_type, Vector2(0, 0), event.key_code
            )

        if consumed or not event.is_down:
            return

        if event.key_code in (keys.RETURN, keys.SPACE):
            self._activate_focused()
        elif event.key_code == keys.TAB:
            shifted = bool(event.modifiers & {keys.L_SHIFT, keys.R_SHIFT})
            if shifted:
                self.focus_previous()
            else:
                self.focus_next()
        elif event.key_code in (keys.DOWN, keys.RIGHT):
            self.focus_next()
        elif event.key_code in (keys.UP, keys.LEFT):
            self.focus_previous()

    def _activate_focused(self) -> None:
        """Fire the focused element's click callback.

        What makes a menu keyboard-complete: Tab to a button, press Enter.
        Without it the ring could move but never choose, and a showcase
        that needs a mouse to press a button is not showing much.
        """
        element = self._focused_element
        if element is None or not element.enabled or not element.visible:
            return
        if element.on_click is not None:
            element.on_click(element)

    def _on_resize_event(self, event: WindowResizeEvent) -> None:
        """Re-lay the UI out against the new window size."""
        self.set_screen_size(event.width, event.height)
