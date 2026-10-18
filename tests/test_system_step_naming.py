"""Guards the docstrings that carry ADR 0005's fixed/variable step naming.

`Scene.update` is the **variable** step and `Scene.fixed_update` the fixed
one. `System.update` is the **fixed** step and `System.variable_update` the
variable one. Exactly inverted, kept that way deliberately, and argued in
`docs/adr/0005-fixed-and-variable-step-naming.md`.

**The wiring is not tested here.** `tests/integration/test_scene_owned_systems.py`
already pins it, with a system that records each channel separately and a
deliberate three-frames-to-one-tick ratio so neither channel can stand in
for the other. Restating that would be a second copy of a guard that
already exists.

What is tested here is the part the ADR costs: the names cannot say which
step they are, so the **docstrings** have to, on every protocol a reader
might meet first. `System.update` carried "Update system logic. Args: dt:
Delta time in seconds since last update" -- equally true of either
channel, and so no help at all to the one reader who needs to know. The
fixed meaning was documented only on `VariableStepSystem`, which is the
one protocol a system need not implement to get `update` called.
"""

from __future__ import annotations

import inspect
import re
from pathlib import Path

import pytest

from pyguara.systems.protocols import (
    CleanupSystem,
    InitializableSystem,
    System,
    VariableStepSystem,
)

ADR = (
    Path(__file__).resolve().parent.parent
    / "docs"
    / "adr"
    / "0005-fixed-and-variable-step-naming.md"
)

# Every protocol in `systems/protocols.py` that declares `update`.
PROTOCOLS_WITH_UPDATE = [System, InitializableSystem, CleanupSystem]


def _prose(obj: object) -> str:
    """The docstring as one lower-case line, so a phrase survives wrapping.

    Matching raw `getdoc` output cannot work: "varies with framerate" is
    split across two lines by the 88-column limit, so a literal search for
    it fails on a docstring that does contain it.
    """
    return re.sub(r"\s+", " ", inspect.getdoc(obj) or "").lower()


# The ADR is called `0005-fixed-and-variable-step-naming.md`, which
# contains both of the words the content assertions below look for. So a
# docstring that said nothing at all but cited the ADR passed them --
# found by sabotage: stripping "fixed" out of `System.update`'s prose
# left every test green, because the filename in the citation still
# matched. Content and citation have to be checked against different
# text, or the citation vacuously satisfies the content.
_CITATION = re.compile(r"adr 0005|`?docs/adr/[0-9a-z-]+\.md`?")

# Markdown emphasis, so "**fixed** step" matches "fixed step".
_EMPHASIS = re.compile(r"[*`]")


def _claims(obj: object) -> str:
    """The docstring's own prose, with any ADR citation removed."""
    return _EMPHASIS.sub("", _CITATION.sub(" ", _prose(obj)))


class TestEveryUpdateDocstringNamesItsStep:
    """`update` is ambiguous in a name, so it cannot be ambiguous in prose."""

    @pytest.mark.parametrize(
        "protocol", PROTOCOLS_WITH_UPDATE, ids=lambda p: p.__name__
    )
    def test_update_says_it_is_the_fixed_step(self, protocol: type) -> None:
        doc = _claims(protocol.update)
        assert "fixed step" in doc, (
            f"{protocol.__name__}.update is the fixed step and its docstring "
            f"does not say so. A reader cannot tell from the name, because "
            f"`Scene.update` is the variable one.\n\n{doc}"
        )

    @pytest.mark.parametrize(
        "protocol", PROTOCOLS_WITH_UPDATE, ids=lambda p: p.__name__
    )
    def test_update_warns_about_the_inversion(self, protocol: type) -> None:
        """Naming the step is not enough; the trap is the inversion itself.

        A reader who has just written `Scene.update` and is now writing
        `System.update` needs telling that the two mean opposite things.
        """
        doc = _claims(protocol.update)
        assert "scene.update" in doc, (
            f"{protocol.__name__}.update should name `Scene.update` as the "
            f"opposite channel -- that collision is the documented hazard, "
            f"not a detail.\n\n{doc}"
        )

    def test_variable_update_says_which_step_it_is(self) -> None:
        """The other half, which also never used the word.

        `VariableStepSystem.variable_update` described its `dt` as "seconds
        since the last rendered frame" and left the reader to infer the
        rest.
        """
        doc = _claims(VariableStepSystem.variable_update)
        assert "variable step" in doc


class TestTheDecisionIsRecorded:
    """An inversion kept on purpose needs its reason written down."""

    def test_the_adr_exists(self) -> None:
        assert ADR.is_file(), f"{ADR} is missing; the docstrings cite it."

    def test_the_adr_states_the_decision_is_not_to_rename(self) -> None:
        text = ADR.read_text(encoding="utf-8").lower()
        assert "do not rename" in text

    @pytest.mark.parametrize(
        "protocol", PROTOCOLS_WITH_UPDATE, ids=lambda p: p.__name__
    )
    def test_each_docstring_points_at_the_adr(self, protocol: type) -> None:
        """So the reason is one hop away from the thing that confused you."""
        assert "adr 0005" in _prose(protocol.update)
