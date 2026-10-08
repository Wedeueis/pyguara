"""The UI clip stack: nesting, intersection, and the backends that apply it."""

import pygame
import pytest

from pyguara.common.types import Rect
from pyguara.graphics.backends.clipping import ClipStack
from pyguara.graphics.backends.headless_renderer import HeadlessUIRenderer
from pyguara.graphics.backends.pygame.ui_renderer import PygameUIRenderer
from pyguara.graphics.protocols import UIRenderer

# -- The shared stack --


def test_a_single_push_is_the_region_itself():
    stack = ClipStack()
    assert stack.push(Rect(10, 20, 100, 50)) == Rect(10, 20, 100, 50)
    assert stack.current == Rect(10, 20, 100, 50)


def test_a_nested_push_intersects_rather_than_replacing():
    """A scroll container inside another must not draw outside the outer
    one just because its own viewport is larger."""
    stack = ClipStack()
    stack.push(Rect(0, 0, 100, 100))

    effective = stack.push(Rect(50, 50, 500, 500))

    assert effective == Rect(50, 50, 50, 50)


def test_a_disjoint_push_clips_everything_away():
    """Correctly: none of the inner element is on screen."""
    stack = ClipStack()
    stack.push(Rect(0, 0, 100, 100))

    effective = stack.push(Rect(900, 900, 50, 50))

    assert effective.width == 0
    assert effective.height == 0


def test_a_disjoint_push_still_takes_a_slot_so_the_pop_lands_right():
    stack = ClipStack()
    stack.push(Rect(0, 0, 100, 100))
    stack.push(Rect(900, 900, 50, 50))

    assert stack.depth == 2
    assert stack.pop() == Rect(0, 0, 100, 100)


def test_popping_restores_the_region_underneath():
    stack = ClipStack()
    stack.push(Rect(0, 0, 200, 200))
    stack.push(Rect(0, 0, 50, 50))

    assert stack.pop() == Rect(0, 0, 200, 200)
    assert stack.pop() is None


def test_popping_an_empty_stack_is_a_no_op():
    """A widget that pops in a `finally` should not turn one bug into two."""
    stack = ClipStack()
    assert stack.pop() is None
    assert stack.depth == 0


def test_clear_drops_every_outstanding_push():
    stack = ClipStack()
    for _ in range(5):
        stack.push(Rect(0, 0, 100, 100))

    assert stack.clear() is None
    assert stack.depth == 0


# -- The pygame backend --


@pytest.fixture
def surface():
    pygame.init()
    return pygame.Surface((400, 300))


def test_pygame_push_sets_the_surface_clip(surface):
    renderer = PygameUIRenderer(surface)

    renderer.push_clip(Rect(10, 10, 100, 100))

    assert surface.get_clip() == pygame.Rect(10, 10, 100, 100)


def test_pygame_pop_clears_the_surface_clip(surface):
    renderer = PygameUIRenderer(surface)
    renderer.push_clip(Rect(10, 10, 100, 100))

    renderer.pop_clip()

    assert surface.get_clip() == pygame.Rect(0, 0, 400, 300)


def test_pygame_nesting_narrows_the_surface_clip(surface):
    renderer = PygameUIRenderer(surface)
    renderer.push_clip(Rect(0, 0, 100, 100))
    renderer.push_clip(Rect(50, 50, 200, 200))

    assert surface.get_clip() == pygame.Rect(50, 50, 50, 50)

    renderer.pop_clip()

    assert surface.get_clip() == pygame.Rect(0, 0, 100, 100)


def test_pygame_actually_refuses_to_draw_outside_the_clip(surface):
    """The point of the whole exercise. A stack nobody applies is a list."""
    from pyguara.common.types import Color

    surface.fill((0, 0, 0))
    renderer = PygameUIRenderer(surface)

    renderer.push_clip(Rect(0, 0, 10, 10))
    renderer.draw_rect(Rect(0, 0, 400, 300), Color(255, 0, 0), width=0)
    renderer.pop_clip()

    assert surface.get_at((5, 5))[:3] == (255, 0, 0)
    assert surface.get_at((50, 50))[:3] == (0, 0, 0)


def test_pygame_present_drops_a_leaked_clip_and_says_so(surface, caplog):
    """Otherwise one unbalanced push truncates every frame after it, and
    the symptom appears nowhere near the cause."""
    import logging

    renderer = PygameUIRenderer(surface)
    renderer.push_clip(Rect(0, 0, 10, 10))

    with caplog.at_level(logging.WARNING):
        renderer.present()

    assert surface.get_clip() == pygame.Rect(0, 0, 400, 300)
    assert "never popped" in caplog.text


def test_pygame_warns_once_not_sixty_times_a_second(surface, caplog):
    import logging

    renderer = PygameUIRenderer(surface)

    with caplog.at_level(logging.WARNING):
        for _ in range(10):
            renderer.push_clip(Rect(0, 0, 10, 10))
            renderer.present()

    assert caplog.text.count("never popped") == 1


def test_pygame_a_target_swap_keeps_the_clip(surface):
    """The clip belongs to the UI pass, not to the surface."""
    renderer = PygameUIRenderer(surface)
    renderer.push_clip(Rect(10, 10, 50, 50))

    other = pygame.Surface((400, 300))
    renderer.set_target(other)

    assert other.get_clip() == pygame.Rect(10, 10, 50, 50)


# -- The headless backend --


def test_the_headless_renderer_keeps_the_stack_for_tests_to_read():
    renderer = HeadlessUIRenderer()

    renderer.push_clip(Rect(0, 0, 100, 100))
    renderer.push_clip(Rect(50, 50, 100, 100))

    assert renderer.clip_stack.current == Rect(50, 50, 50, 50)

    renderer.pop_clip()

    assert renderer.clip_stack.current == Rect(0, 0, 100, 100)


def test_the_headless_renderer_resets_on_present():
    renderer = HeadlessUIRenderer()
    renderer.push_clip(Rect(0, 0, 10, 10))

    renderer.present()

    assert renderer.clip_stack.depth == 0


# -- Protocol conformance --


def test_every_ui_backend_still_satisfies_the_protocol(surface):
    """Adding `push_clip`/`pop_clip` to `UIRenderer` is only safe if every
    backend grew them; mypy checks the two real ones at the registration
    site, and this covers the headless one at runtime."""
    assert isinstance(HeadlessUIRenderer(), UIRenderer)
    assert isinstance(PygameUIRenderer(surface), UIRenderer)
