"""Integration tests for Pygame input backend."""

import os
import pytest
import pygame
from typing import Iterator
from pyguara.input.backends.pygame_backend import PygameInputBackend

# Ensure headless execution
os.environ["SDL_VIDEODRIVER"] = "dummy"


@pytest.fixture(scope="module")
def pygame_init() -> Iterator[None]:
    """Initialize pygame for the module."""
    pygame.init()
    # Also init joystick subsystem which PygameInputBackend manages,
    # but we can check if it initializes it correctly too.
    yield
    pygame.quit()


@pytest.fixture
def input_backend(pygame_init: None) -> Iterator[PygameInputBackend]:
    """Create a PygameInputBackend instance."""
    backend = PygameInputBackend()
    yield backend
    # Cleanup
    if backend.is_initialized():
        backend.quit_joysticks()


def test_backend_initialization(input_backend: PygameInputBackend) -> None:
    """Backend should initialize and quit joystick subsystem."""
    # Fixture already called pygame.init(), so it starts initialized
    assert input_backend.is_initialized()

    input_backend.quit_joysticks()
    assert not input_backend.is_initialized()

    input_backend.init_joysticks()
    assert input_backend.is_initialized()


def test_joystick_count(input_backend: PygameInputBackend) -> None:
    """Backend should report joystick count (0 in headless usually)."""
    input_backend.init_joysticks()

    # In dummy mode, usually 0
    count = input_backend.get_joystick_count()
    assert isinstance(count, int)
    assert count >= 0


def test_get_joystick_invalid_index(input_backend: PygameInputBackend) -> None:
    """Backend should raise error or handle invalid index."""
    input_backend.init_joysticks()

    # Pygame raises error for invalid index
    with pytest.raises(pygame.error):
        input_backend.get_joystick(999)
