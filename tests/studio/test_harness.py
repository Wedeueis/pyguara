"""`StudioHarness`: the closed edit-run-check loop an agent drives.

`tools/agent_view.py` is the prior art, and the harness is its lesson
generalised: it can boot a demo and write frames, but not *loop* -- edit,
run, check, undo, try again -- because it has no edit surface and exits
when it is done.

The scenarios that boot a real demo run in a subprocess each, on the wgpu
backend; with no graphics adapter they skip, and fail instead under
`PYGUARA_REQUIRE_GPU=1`.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

from pyguara.studio.agent.harness import SAMPLE_GRID, Capture, is_flat

REPO_ROOT = Path(__file__).resolve().parents[2]


class _FakeSurface:
    """A surface whose pixels come from a function."""

    def __init__(self, width: int, height: int, colour_at) -> None:  # type: ignore[no-untyped-def]
        self._size = (width, height)
        self._colour_at = colour_at

    def get_size(self) -> tuple[int, int]:
        return self._size

    def get_at(self, position: tuple[int, int]) -> object:
        return self._colour_at(*position)


class TestIsFlat:
    """The check that catches a capture silently saying nothing."""

    def test_a_uniform_frame_is_flat(self) -> None:
        assert is_flat(_FakeSurface(1280, 720, lambda x, y: (0, 0, 0)))

    def test_a_varied_frame_is_not(self) -> None:
        assert not is_flat(_FakeSurface(1280, 720, lambda x, y: (x % 255, 0, 0)))

    def test_a_zero_sized_frame_counts_as_flat(self) -> None:
        assert is_flat(_FakeSurface(0, 0, lambda x, y: (0, 0, 0)))

    def test_it_samples_rather_than_scans(self) -> None:
        """A full pass over a 1280x720 frame is nearly a million `get_at`
        calls in Python, which is far too slow to do per captured
        frame."""
        reads: list[tuple[int, int]] = []

        def counting(x: int, y: int) -> tuple[int, int, int]:
            reads.append((x, y))
            return (0, 0, 0)

        is_flat(_FakeSurface(1280, 720, counting))

        assert len(reads) <= (SAMPLE_GRID + 1) ** 2 + 1
        assert len(reads) < 1280 * 720

    def test_it_still_finds_a_single_odd_region(self) -> None:
        """Sampling has to be dense enough to catch a real difference."""

        def mostly_black(x: int, y: int) -> tuple[int, int, int]:
            return (255, 255, 255) if x > 600 else (0, 0, 0)

        assert not is_flat(_FakeSurface(1280, 720, mostly_black))


class TestCapture:
    """The record of a written frame."""

    def test_it_serializes(self, tmp_path: Path) -> None:
        capture = Capture(path=tmp_path / "a.png", width=10, height=20, blank=False)
        data = capture.to_dict()
        assert data["width"] == 10
        assert data["blank"] is False

    def test_world_flat_is_omitted_when_unknown(self, tmp_path: Path) -> None:
        """Distinct from False: there may simply be no separate world
        buffer to look at."""
        capture = Capture(path=tmp_path / "a.png", width=10, height=20, blank=False)
        assert "world_flat" not in capture.to_dict()

    def test_world_flat_is_reported_when_known(self, tmp_path: Path) -> None:
        capture = Capture(
            path=tmp_path / "a.png",
            width=10,
            height=20,
            blank=False,
            world_flat=True,
        )
        assert capture.to_dict()["world_flat"] is True


class TestStepValidation:
    """Argument checking that needs no engine."""

    def test_a_negative_step_is_refused(self) -> None:
        from pyguara.ecs.manager import EntityManager
        from pyguara.studio.agent.harness import StudioHarness
        from pyguara.studio.session import StudioSession

        harness = StudioHarness(object(), StudioSession(EntityManager()))
        with pytest.raises(ValueError, match="must not be negative"):
            harness.step(-1)


class TestRunOperationsAreRegistered:
    """The loop is reachable from the operation surface."""

    def test_both_run_operations_exist(self, ops) -> None:
        assert ops.get("run_frames") is not None
        assert ops.get("capture_frame") is not None

    def test_run_frames_is_a_run_risk(self, ops) -> None:
        """So a caller can express "read anything, ask before running"
        without enumerating operations."""
        from pyguara.studio.ops.registry import RiskClass

        operation = ops.get("run_frames")
        assert operation is not None
        assert operation.risk is RiskClass.RUN

    def test_capture_frame_declares_that_it_writes(self, ops) -> None:
        from pyguara.studio.ops.registry import RiskClass

        operation = ops.get("capture_frame")
        assert operation is not None
        assert operation.risk is RiskClass.WRITE_DISK

    def test_capture_frame_warns_about_what_it_proves(self, ops) -> None:
        """A capture proves the render path, not that a window appears --
        a distinction this engine has already been bitten by."""
        operation = ops.get("capture_frame")
        assert operation is not None
        assert "does not prove a window" in operation.description


@pytest.mark.integration
class TestAgainstARealDemo:
    """A whole engine, driven a frame at a time."""

    @pytest.mark.parametrize(
        "scenario",
        [
            "run_operations_need_a_harness",
            "boots_and_steps",
            "captures_a_real_frame",
            "the_whole_agent_loop",
            "determinism",
        ],
    )
    def test_scenario(self, scenario: str) -> None:
        pytest.importorskip("imgui_bundle")

        from tests.conftest import REQUIRE_GPU

        environment = dict(os.environ)
        environment["SDL_VIDEODRIVER"] = "dummy"
        environment["SDL_AUDIODRIVER"] = "dummy"
        environment["PYGAME_HIDE_SUPPORT_PROMPT"] = "1"

        completed = subprocess.run(
            [sys.executable, "-m", "tests.studio._harness_scenarios", scenario],
            capture_output=True,
            text=True,
            timeout=300,
            check=False,
            cwd=REPO_ROOT,
            env=environment,
        )

        if completed.returncode != 0 and _is_missing_gpu(completed.stderr):
            if REQUIRE_GPU:
                pytest.fail(
                    "PYGUARA_REQUIRE_GPU is set and no graphics adapter was "
                    f"available, so this would have skipped silently.\n"
                    f"{completed.stderr}"
                )
            pytest.skip(f"no graphics adapter:\n{completed.stderr[-400:]}")

        assert completed.returncode == 0, (
            f"scenario '{scenario}' failed:\n{completed.stderr}"
        )


def _is_missing_gpu(stderr: str) -> bool:
    """Whether a failure is the machine having no graphics adapter for wgpu."""
    return "the graphics device could not be opened" in stderr or (
        "no graphics adapter is available" in stderr
    )
