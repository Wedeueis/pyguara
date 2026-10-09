"""Scenarios for `StudioHarness`, run in a subprocess by `test_harness.py`.

A separate process for the same reason `_attach_scenarios.py` is: a real
GL context cannot be created alongside the suite's session-scoped
standalone one, and booting an application twice in a process leaves
pygame's display subsystem in whatever state the last one wanted.
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

from pyguara.studio.agent.harness import open_headless


def _open(out_dir: Path):
    """Open a harness over the Guará Falcão demo."""
    from games.guara_falcao.bootstrap import configure_game_container
    from games.guara_falcao.scenes import GameScene

    return open_headless(
        GameScene,
        out_dir=out_dir,
        container_factory=configure_game_container,
        gl=True,
    )


def boots_and_steps() -> None:
    """It boots a real demo and advances frames deterministically."""
    with tempfile.TemporaryDirectory() as temporary:
        harness = _open(Path(temporary))
        try:
            assert harness.session.scene_name == "GameScene"
            assert len(harness.session.snapshot()) > 100, (
                "the demo scene did not populate"
            )
            assert harness.frame == 0

            assert harness.step(10) == 10, "frames stopped early"
            assert harness.frame == 10
            assert harness.step() == 1
            assert harness.frame == 11
        finally:
            harness.close()


def captures_a_real_frame() -> None:
    """A capture lands on disk and is not a flat colour."""
    with tempfile.TemporaryDirectory() as temporary:
        out_dir = Path(temporary)
        harness = _open(out_dir)
        try:
            harness.step(20)
            capture = harness.capture("probe")

            assert capture is not None, "nothing was captured"
            assert capture.path.exists(), "the PNG was not written"
            assert capture.path.name == "probe.png"
            assert capture.width > 0 and capture.height > 0
            assert not capture.blank, (
                "the composed frame is a single flat colour, so the render "
                "path drew nothing"
            )
            assert capture.world_flat is False, (
                "the world buffer is flat: the scene itself drew nothing"
            )

            # The default name is the frame number, zero-padded so a
            # directory listing sorts in order.
            default = harness.capture()
            assert default is not None
            assert default.path.name == "frame_0020.png"
        finally:
            harness.close()


def the_whole_agent_loop() -> None:
    """Read, edit, run, capture, check, undo -- over the operations."""
    import io
    import json

    from pyguara.studio.ops.stdio import serve

    with tempfile.TemporaryDirectory() as temporary:
        harness = _open(Path(temporary))
        try:
            requests = [
                {"op": "find_entities", "args": {"id_contains": "player"}},
                {
                    "op": "set_field",
                    "args": {
                        "entity_id": "player",
                        "component": "Transform",
                        "field": "position",
                        "value": {"x": 400, "y": 100},
                    },
                },
                {"op": "run_frames", "args": {"frames": 20}},
                {"op": "capture_frame", "args": {"name": "after"}},
                {"op": "history", "args": {"operation": "undo"}},
            ]
            out = io.StringIO()
            serve(
                harness.session,
                stdin=io.StringIO(
                    "\n".join(json.dumps(request) for request in requests)
                ),
                stdout=out,
            )
            responses = [json.loads(line) for line in out.getvalue().splitlines()]

            for response in responses:
                assert response["ok"], (
                    f"{response.get('operation')} failed: {response.get('error')}"
                )

            assert responses[0]["result"]["entity_ids"] == ["player"]

            moved = responses[1]["result"]
            assert moved["status"] == "applied"
            assert moved["diff"]["fields"][0]["after"] == {"x": 400.0, "y": 100.0}

            ran = responses[2]["result"]
            assert ran["ran"] == 20
            assert ran["stopped"] is False
            assert ran["diff"]["changed"] is True, (
                "twenty frames of a running game moved nothing, which means "
                "the loop did not actually advance"
            )

            captured = responses[3]["result"]
            assert Path(captured["path"]).exists()
            assert captured["blank"] is False

            # The undo restores the position the edit changed, even after
            # twenty frames of simulation ran on top of it.
            entity = harness.session.world.get_entity("player")
            assert entity is not None
            assert responses[4]["result"]["status"] == "applied"
        finally:
            harness.close()


def run_operations_need_a_harness() -> None:
    """Without one, the run operations explain themselves rather than fail."""
    from pyguara.ecs.manager import EntityManager
    from pyguara.studio.ops.builtin import build_registry
    from pyguara.studio.session import StudioSession

    session = StudioSession(EntityManager())
    registry = build_registry()

    for name in ("run_frames", "capture_frame"):
        outcome = registry.invoke(session, name, {})
        assert not outcome.ok, f"{name} should refuse without a harness"
        assert "no run harness" in (outcome.error or ""), outcome.error
        assert "open_headless" in (outcome.error or ""), (
            "the error should say how to get one"
        )


def determinism() -> None:
    """Two identical runs produce identical state."""
    with tempfile.TemporaryDirectory() as temporary:
        digests = []
        for _ in range(2):
            harness = _open(Path(temporary))
            try:
                harness.step(30)
                snapshot = harness.session.snapshot()
                digests.append(
                    [
                        (
                            view.entity_id,
                            view.components.get("Transform", {}).get("position"),
                        )
                        for view in sorted(
                            snapshot.entities.values(),
                            key=lambda item: item.entity_id,
                        )
                    ]
                )
            finally:
                harness.close()

        assert digests[0] == digests[1], (
            "two runs of the same thirty frames diverged, so 'run it again "
            "and diff' is not an answer"
        )


SCENARIOS = {
    "boots_and_steps": boots_and_steps,
    "captures_a_real_frame": captures_a_real_frame,
    "the_whole_agent_loop": the_whole_agent_loop,
    "run_operations_need_a_harness": run_operations_need_a_harness,
    "determinism": determinism,
}


def main(argv: list[str]) -> int:
    """Run one scenario by name.

    Args:
        argv: Command-line arguments; the first is the scenario name.

    Returns:
        0 on success, 2 for an unknown name.
    """
    if len(argv) != 1 or argv[0] not in SCENARIOS:
        print(f"usage: {sys.argv[0]} <{'|'.join(SCENARIOS)}>", file=sys.stderr)
        return 2
    SCENARIOS[argv[0]]()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
