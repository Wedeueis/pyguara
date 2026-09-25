"""A private GL context must not leave the shared one unusable.

`isolated_gl_ctx` exists for a test that needs to change context-global
state and so cannot use the session-scoped `gl_ctx`. The hazard it wraps is
not obvious: creating a standalone context makes it current, and releasing
it leaves *no* context current -- not the one that was current before. The
shared `gl_ctx` is then still a live Python object, and every GL call
through it fails with `cannot create renderbuffer`, raised from whatever
fixture happens to run next.

That is a nasty shape of bug to have no test for, because whether it fires
depends on collection order rather than on anything either module does.
While `test_gl_blend_state.py` -- the only module with a private context --
happened to sort before every other GL module, `gl_ctx` did not exist yet
when those contexts came and went, so it was created afterwards and was
current. Adding one GL test file that sorted earlier in the directory broke
28 tests across seven modules that nothing had touched.

The fixture is driven by hand here, the way `test_gl_fixture_guard.py`
drives `gl_ctx`: the property under test is what the *teardown* does, and a
teardown that ran normally would run after the last assertion -- which is
exactly where the damage used to be invisible.
"""

from __future__ import annotations

from typing import Any

import pytest

from tests import conftest

pytestmark = pytest.mark.integration


def _can_allocate(ctx: Any) -> bool:
    """Whether `ctx` can still serve the simplest possible GL allocation.

    Args:
        ctx: A ModernGL context.

    Returns:
        True if a renderbuffer could be created and released on it.
    """
    try:
        ctx.simple_framebuffer((8, 8)).release()
    except Exception:
        return False
    return True


def test_the_shared_context_survives_a_private_one(gl_ctx: Any) -> None:
    """The regression, start to finish: usable, private, usable again."""
    assert _can_allocate(gl_ctx), "precondition: the shared context works"

    fixture = conftest.isolated_gl_ctx.__wrapped__(gl_ctx)  # type: ignore[attr-defined]
    private = next(fixture)
    assert _can_allocate(private), "the private context must be usable too"

    with pytest.raises(StopIteration):
        next(fixture)  # the teardown: release the private, restore the shared

    assert _can_allocate(gl_ctx), (
        "releasing a private standalone context left no context current, so "
        "every later GL test draws through a live object whose every call "
        "fails -- see isolated_gl_ctx in tests/conftest.py"
    )


def test_a_hand_rolled_private_context_is_what_the_fixture_prevents(
    gl_ctx: Any,
) -> None:
    """The hazard itself, so the test above is not guarding nothing.

    Without this, `isolated_gl_ctx`'s restoring teardown could be deleted
    and the suite would still be green on any machine where the contexts
    happen not to interfere -- and the regression would come back the next
    time a GL test file was added with an early-sorting name.

    Whether releasing a context drops currency is the driver's business,
    not ours, so this skips rather than fails where it does not happen.
    A skip here is worth reading: on that platform the fixture's teardown
    is guarding nothing and could be simplified.
    """
    assert _can_allocate(gl_ctx), "precondition: the shared context works"

    # Through the shared helper, not `moderngl.create_standalone_context()`
    # -- the bare call picks GLX and dies on a headless runner.
    private = conftest.create_standalone_context()
    private.release()

    broken = not _can_allocate(gl_ctx)
    gl_ctx.__enter__()  # put it back before anything else runs
    assert _can_allocate(gl_ctx), "re-entering the shared context has to be the cure"

    if not broken:  # pragma: no cover - depends on the driver
        pytest.skip(
            "releasing a standalone context does not drop currency on this "
            "platform, so isolated_gl_ctx's teardown is a no-op here"
        )
