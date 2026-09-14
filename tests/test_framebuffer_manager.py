"""Tests for `FramebufferManager.get_or_create`'s conflict rules.

The manager keys framebuffers by name, and used to hand back whatever was
already registered under a name regardless of the format asked for. That
is the quiet half of the HDR problem: a caller asking for a 16-bit float
buffer and getting an 8-bit one has no way to tell, so a format mismatch
becomes invisible data loss somewhere downstream rather than an error
where it happened.

These run against a mock context. What the framebuffer *does* needs a GL
context and belongs with the pixel tests; which one you get back does not.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from pyguara.graphics.pipeline.framebuffer import FramebufferManager


def make_manager(width: int = 800, height: int = 600) -> FramebufferManager:
    """A manager over a mock context."""
    ctx = MagicMock()
    ctx.texture.side_effect = lambda *a, **k: MagicMock()
    ctx.framebuffer.side_effect = lambda *a, **k: MagicMock()
    return FramebufferManager(ctx, width, height)


class TestCreating:
    def test_a_new_name_creates_a_framebuffer(self) -> None:
        manager = make_manager()

        fbo = manager.get_or_create("world")

        assert fbo.name == "world"

    def test_it_defaults_to_the_viewport_size(self) -> None:
        manager = make_manager(1024, 768)

        fbo = manager.get_or_create("world")

        assert (fbo.width, fbo.height) == (1024, 768)

    def test_it_defaults_to_eight_bit(self) -> None:
        """`f1` unless asked otherwise -- the HDR buffers are the
        exception, and they say so at the point they are claimed."""
        manager = make_manager()

        assert manager.get_or_create("world").dtype == "f1"

    def test_an_explicit_format_is_honoured(self) -> None:
        manager = make_manager()

        fbo = manager.get_or_create("lightmap", dtype="f2", samples=4)

        assert fbo.dtype == "f2"
        assert fbo.samples == 4

    def test_the_same_name_returns_the_same_object(self) -> None:
        manager = make_manager()

        first = manager.get_or_create("world")
        second = manager.get_or_create("world")

        assert first is second


class TestRequirementsAreEnforced:
    """An argument you pass is a requirement. This is the half that used
    to be silent."""

    def test_a_conflicting_dtype_raises(self) -> None:
        """The case the HDR chain kept hitting: a bootstrap claims the
        light map as `f2`, and anything later asking for `f1` should be
        told, not quietly handed a buffer with no range in it."""
        manager = make_manager()
        manager.get_or_create("lightmap", dtype="f2")

        with pytest.raises(ValueError, match="dtype"):
            manager.get_or_create("lightmap", dtype="f1")

    def test_a_conflicting_size_raises(self) -> None:
        manager = make_manager()
        manager.get_or_create("bloom", 256, 256)

        with pytest.raises(ValueError, match="width"):
            manager.get_or_create("bloom", 512, 256)

    def test_a_conflicting_sample_count_raises(self) -> None:
        manager = make_manager()
        manager.get_or_create("world", samples=4)

        with pytest.raises(ValueError, match="samples"):
            manager.get_or_create("world", samples=0)

    def test_the_message_names_what_was_asked_and_what_is_there(self) -> None:
        """An error that only says "conflict" sends the reader back to the
        code to find out which attribute and which way round."""
        manager = make_manager()
        manager.get_or_create("lightmap", dtype="f2")

        with pytest.raises(ValueError) as excinfo:
            manager.get_or_create("lightmap", dtype="f1")

        message = str(excinfo.value)
        assert "lightmap" in message
        assert "'f1'" in message and "'f2'" in message

    def test_every_mismatch_is_reported_at_once(self) -> None:
        """Fixing one and rediscovering the next is a slow way to learn
        the buffer is simply different."""
        manager = make_manager()
        manager.get_or_create("world", 256, 256, dtype="f2")

        with pytest.raises(ValueError) as excinfo:
            manager.get_or_create("world", 512, 512, dtype="f1")

        message = str(excinfo.value)
        assert "width" in message
        assert "height" in message
        assert "dtype" in message


class TestOmittedArgumentsAreNotRequirements:
    """What lets the two kinds of caller coexist: a bootstrap that claims
    a format, and a pass that just wants the buffer."""

    def test_asking_for_nothing_accepts_what_exists(self) -> None:
        """`LightPass` does exactly this, after a game's bootstrap has
        claimed the light map as `f2`. It must not raise."""
        manager = make_manager()
        manager.get_or_create("lightmap", dtype="f2")

        assert manager.get_or_create("lightmap").dtype == "f2"

    def test_asking_for_only_a_dtype_ignores_the_size(self) -> None:
        manager = make_manager()
        manager.get_or_create("bloom", 256, 128, dtype="f2")

        assert manager.get_or_create("bloom", dtype="f2").width == 256

    def test_a_matching_request_is_fine(self) -> None:
        manager = make_manager()
        manager.get_or_create("world", 800, 600, dtype="f1", samples=0)

        assert manager.get_or_create("world", 800, 600, dtype="f1", samples=0)
