"""Parity tests for the pygame stand-ins for ModernGL-only features.

`graphics/backends/pygame/stubs.py` exists so game code using framebuffers,
lighting or post-processing runs unchanged on the pygame backend. Its entire
value is interface parity: a method the real class has and the stub does not is
an `AttributeError` that surfaces only after switching backend, in someone
else's game.

Nothing tested it, and it had drifted -- `PygameLightingSystem` was missing
`collect_lights_screen_space` (which `light_pass.py` calls) and
`PygameRenderGraph` was missing `ctx` (which `application.py` reads). These
tests compare the public surfaces directly, so the next divergence fails here.
"""

import inspect

import pytest

from pyguara.graphics.backends.pygame.stubs import (
    PygameFramebufferManager,
    PygameLightingSystem,
    PygamePostProcessStack,
    PygameRenderGraph,
)
from pyguara.graphics.lighting.light_system import LightingSystem
from pyguara.graphics.pipeline.framebuffer import FramebufferManager
from pyguara.graphics.pipeline.graph import RenderGraph
from pyguara.graphics.vfx.post_process import PostProcessStack

STUB_PAIRS = [
    (PygameLightingSystem, LightingSystem),
    (PygamePostProcessStack, PostProcessStack),
    (PygameFramebufferManager, FramebufferManager),
    (PygameRenderGraph, RenderGraph),
]


def public_members(cls: type) -> set[str]:
    """Public attribute names a caller could reach on instances of `cls`."""
    return {
        name
        for name, member in inspect.getmembers(cls)
        if not name.startswith("_")
        and (isinstance(member, property) or callable(member))
    }


@pytest.mark.parametrize(
    ("stub", "real"), STUB_PAIRS, ids=lambda c: getattr(c, "__name__", str(c))
)
def test_the_stub_covers_the_real_classs_surface(stub: type, real: type) -> None:
    missing = sorted(public_members(real) - public_members(stub))

    assert not missing, (
        f"{stub.__name__} is missing {missing}, which exist on {real.__name__}. "
        f"Game code calling them works on ModernGL and raises AttributeError on "
        f"pygame -- exactly what these stubs exist to prevent."
    )


@pytest.mark.parametrize(
    ("stub", "real"), STUB_PAIRS, ids=lambda c: getattr(c, "__name__", str(c))
)
def test_the_stub_takes_the_same_arguments(stub: type, real: type) -> None:
    """Names alone are not parity: a caller passing the real signature must not
    hit a TypeError on the stub."""
    mismatches = []
    for name in sorted(public_members(real) & public_members(stub)):
        real_member, stub_member = getattr(real, name), getattr(stub, name)
        if isinstance(real_member, property) or isinstance(stub_member, property):
            continue
        try:
            real_params = list(inspect.signature(real_member).parameters)
            stub_params = list(inspect.signature(stub_member).parameters)
        except (TypeError, ValueError):
            continue
        # A stub accepting **kwargs absorbs whatever the real one declares.
        if any(
            inspect.signature(stub_member).parameters[p].kind
            is inspect.Parameter.VAR_KEYWORD
            for p in stub_params
        ):
            continue
        if real_params != stub_params:
            mismatches.append(
                f"{name}: real{tuple(real_params)} stub{tuple(stub_params)}"
            )

    assert not mismatches, "\n".join(mismatches)


class TestStubBehaviour:
    """The no-op behaviour itself, which nothing covered either."""

    def test_the_lighting_stub_reports_no_lights(self) -> None:
        from unittest.mock import MagicMock

        from pyguara.common.types import Vector2

        system = PygameLightingSystem(MagicMock())

        assert system.lights == []
        assert (
            system.collect_lights_screen_space(Vector2.zero(), 1.0, Vector2.zero())
            == []
        )

    def test_the_lighting_stub_reports_full_ambient(self) -> None:
        """The pygame backend renders everything fully lit, so ambient has to
        read as full brightness rather than as darkness."""
        from unittest.mock import MagicMock

        system = PygameLightingSystem(MagicMock())

        assert system.get_ambient_normalized() == (1.0, 1.0, 1.0)
        assert system.ambient_intensity == 1.0

    def test_the_render_graph_stub_has_no_context(self) -> None:
        assert PygameRenderGraph(800, 600).ctx is None

    def test_the_render_graph_stub_accepts_and_reports_passes(self) -> None:
        graph = PygameRenderGraph(800, 600)
        graph.add_pass(object())

        assert graph.passes == []
        assert graph.get_pass("anything") is None

    def test_the_framebuffer_stub_reports_its_size(self) -> None:
        manager = PygameFramebufferManager(800, 600)

        assert (manager.width, manager.height) == (800, 600)
        assert manager.get_or_create("world") is None

    def test_the_post_process_stub_passes_frames_through_untouched(self) -> None:
        stack = PygamePostProcessStack()
        sentinel = object()

        assert stack.process(sentinel) is sentinel
        assert stack.effects == []

    def test_stub_lifecycle_calls_are_harmless(self) -> None:
        from unittest.mock import MagicMock

        PygameLightingSystem(MagicMock()).cleanup()
        PygameRenderGraph(8, 8).release()
        PygameFramebufferManager(8, 8).release_all()
        PygamePostProcessStack().release()
