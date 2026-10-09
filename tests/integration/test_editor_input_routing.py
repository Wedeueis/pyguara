"""The editor gets input events before the game does.

The regression this locks: `attach_editor()` installs a render pass, so the
ImGui panels drew from the first frame -- but nothing ever called
`EditorLayer.process_event`. Every click and keystroke fell straight
through to the game, so the editor rendered and could not be used. A
`grep` for the method found a definition and no call sites.

Tested against `Application._process_input` with a fake window, rather
than through a real ImGui layer, because what is being asserted is the
*routing*: that an attached sink is consulted, that a consumed event stops
there, and that an unconsumed one carries on to the `InputManager`.
`tests/test_editor_input.py` covers the translation itself.
"""

from __future__ import annotations

import os
from typing import Any

os.environ["SDL_VIDEODRIVER"] = "dummy"
os.environ["SDL_AUDIODRIVER"] = "dummy"

import pygame
import pytest

from pyguara.application.application import Application, EditorInputSink
from pyguara.application.bootstrap import create_headless_application
from pyguara.editor.layer import EditorLayer
from pyguara.events.input import KeyDownEvent, MouseButtonEvent
from pyguara.input import keys


@pytest.fixture(autouse=True)
def _quit_pygame():
    yield
    pygame.quit()


class _RecordingSink:
    """An editor stand-in that consumes what it is told to."""

    def __init__(self, *, consume: bool) -> None:
        self._consume = consume
        self.seen: list[object] = []

    def process_event(self, event: object) -> bool:
        self.seen.append(event)
        return self._consume


class _FakeWindow:
    """Hands `_process_input` a scripted event list exactly once."""

    def __init__(self, events: list[Any]) -> None:
        self._events = events
        self.is_open = True

    def poll_events(self) -> list[Any]:
        events, self._events = self._events, []
        return events


def _wire(app: Application, sink: object | None, events: list[Any]) -> list[Any]:
    """Point the app at a fake window and a sink; return what the game saw."""
    app._window = _FakeWindow(events)  # type: ignore[assignment]

    game_saw: list[Any] = []
    app._input_manager.process_event = game_saw.append  # type: ignore[method-assign]

    # `_editor_layer` resolves from the container and caches the answer;
    # setting the cache directly is what attaching a real editor amounts to.
    app._editor_layer_checked = True
    app._editor_layer_cache = sink  # type: ignore[assignment]
    return game_saw


@pytest.fixture
def app() -> Application:
    return create_headless_application()


@pytest.mark.integration
class TestEditorInputRouting:
    """Routing order and consumption."""

    def test_the_editor_sees_events(self, app: Application) -> None:
        """The call that did not exist."""
        sink = _RecordingSink(consume=False)
        event = KeyDownEvent(key_code=keys.A)
        _wire(app, sink, [event])

        app._process_input(1 / 60)

        assert sink.seen == [event]

    def test_a_consumed_event_does_not_reach_the_game(self, app: Application) -> None:
        """Typing in the Inspector must not also drive the player."""
        sink = _RecordingSink(consume=True)
        event = KeyDownEvent(key_code=keys.A)
        game_saw = _wire(app, sink, [event])

        app._process_input(1 / 60)

        assert sink.seen == [event]
        assert game_saw == []

    def test_an_unconsumed_event_reaches_the_game(self, app: Application) -> None:
        """Clicking the viewport still moves the character."""
        sink = _RecordingSink(consume=False)
        event = MouseButtonEvent(button=1, x=10, y=10, is_down=True)
        game_saw = _wire(app, sink, [event])

        app._process_input(1 / 60)

        assert game_saw == [event]

    def test_the_game_is_unaffected_with_no_editor_attached(
        self, app: Application
    ) -> None:
        """A shipped game pays nothing for this."""
        event = KeyDownEvent(key_code=keys.A)
        game_saw = _wire(app, None, [event])

        app._process_input(1 / 60)

        assert game_saw == [event]

    def test_quit_is_handled_before_the_editor_sees_it(self, app: Application) -> None:
        """An editor panel must not be able to swallow a window close."""
        from pyguara.events.lifecycle import QuitEvent

        sink = _RecordingSink(consume=True)
        _wire(app, sink, [QuitEvent()])

        app._process_input(1 / 60)

        assert app._is_running is False
        assert sink.seen == []


@pytest.mark.integration
class TestEditorLayerSatisfiesTheProtocol:
    """`EditorLayer` is the real implementation behind the structural type."""

    def test_the_layer_is_an_editor_input_sink(self) -> None:
        """Declared structurally, so the editor never imports the protocol.

        If `EditorLayer.process_event` is renamed or its signature drifts,
        the routing silently stops finding it -- which is the exact failure
        mode this whole commit exists to fix. So it is asserted.
        """
        from pyguara.di.container import DIContainer

        layer = EditorLayer(DIContainer())
        try:
            assert isinstance(layer, EditorInputSink)
        finally:
            layer.release()
