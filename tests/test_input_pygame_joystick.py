"""The pygame joystick wrapper, without needing a controller attached."""

from __future__ import annotations

from typing import Any

import pygame
import pytest

from pyguara.input.backends.pygame_backend import PygameJoystick


class FakeJoystick:
    """Behaves as pygame's does: created initialized, and able to be closed."""

    def __init__(self, device_index: int) -> None:
        self.initialized = True
        self.init_calls = 0

    def get_init(self) -> bool:
        return self.initialized

    def init(self) -> None:
        self.init_calls += 1
        self.initialized = True

    def quit(self) -> None:
        self.initialized = False


@pytest.fixture
def joystick(monkeypatch: pytest.MonkeyPatch) -> Any:
    monkeypatch.setattr(pygame.joystick, "Joystick", FakeJoystick)
    return PygameJoystick(0)


def test_a_new_joystick_isnt_initialized_a_second_time(joystick: Any) -> None:
    """pygame deprecates this, and the manager asks once a frame."""
    joystick.init()
    joystick.init()
    assert joystick._joystick.init_calls == 0


def test_a_closed_joystick_can_still_be_initialized(joystick: Any) -> None:
    joystick.quit()
    joystick.init()
    assert joystick._joystick.init_calls == 1
    assert joystick._joystick.get_init()
