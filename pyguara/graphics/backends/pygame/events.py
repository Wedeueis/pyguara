"""Translate SDL (pygame) events into the engine's backend-neutral events.

The pygame and ModernGL window backends both pump SDL via `pygame.event.get()`
and call this to hand the rest of the engine `QuitEvent` / `KeyDownEvent` /
`KeyUpEvent` / `MouseButtonEvent` / `MouseMotionEvent` / `WindowResizeEvent`
instead of raw SDL structs -- so `application.py`, `InputManager`,
`pyguara/tools/*` and `sandbox.py` stop importing pygame (issue #9).
"""

from __future__ import annotations

from typing import Any

import pygame

from pyguara.events.input import (
    KeyDownEvent,
    KeyUpEvent,
    MouseButtonEvent,
    MouseMotionEvent,
)
from pyguara.events.lifecycle import QuitEvent
from pyguara.events.window import WindowResizeEvent

_KMOD = ((pygame.KMOD_SHIFT,), (pygame.KMOD_CTRL,), (pygame.KMOD_ALT,))


def _held_modifiers() -> set[int]:
    """Return the shift/ctrl/alt masks held now, or empty if SDL video is down."""
    try:
        mods = pygame.key.get_mods()
    except pygame.error:
        return set()
    return {mask for (mask,) in _KMOD if mods & mask}


def translate_event(raw: Any) -> object | None:
    """Map one pygame event to an engine event, or ``None`` to drop it."""
    etype = getattr(raw, "type", None)

    if etype == pygame.QUIT:
        return QuitEvent()

    if etype == pygame.KEYDOWN:
        return KeyDownEvent(key_code=raw.key, modifiers=_held_modifiers())
    if etype == pygame.KEYUP:
        return KeyUpEvent(key_code=raw.key, modifiers=_held_modifiers())

    if etype in (pygame.MOUSEBUTTONDOWN, pygame.MOUSEBUTTONUP):
        return MouseButtonEvent(
            button=raw.button,
            x=raw.pos[0],
            y=raw.pos[1],
            is_down=etype == pygame.MOUSEBUTTONDOWN,
            modifiers=_held_modifiers(),
        )

    if etype == pygame.MOUSEMOTION:
        return MouseMotionEvent(
            x=raw.pos[0],
            y=raw.pos[1],
            rel_x=raw.rel[0],
            rel_y=raw.rel[1],
        )

    if etype == pygame.VIDEORESIZE:
        return WindowResizeEvent(width=raw.w, height=raw.h)

    return None


def translate_events(raw_events: list[Any]) -> list[object]:
    """Translate a batch of pygame events, dropping the ones with no mapping."""
    out: list[object] = []
    for raw in raw_events:
        engine_event = translate_event(raw)
        if engine_event is not None:
            out.append(engine_event)
    return out
