#!/usr/bin/env python3
"""Warn when an edit to the graphics stack stops a demo drawing anything.

PostToolUse hook on Edit|Write. Reads the hook payload on stdin, and for edits
under `pyguara/graphics/` boots one demo headlessly through its real bootstrap
and checks the frame is not a single flat colour -- the same check
`tests/integration/test_demos_render.py` makes, run in about a second so the
feedback arrives with the edit rather than at the next test run.

It never blocks. A render break is reported into the transcript; what to do
about it is the agent's decision, not this script's.

Exits 0 unconditionally, including when the check cannot run at all. A hook
that fails the turn because `uv` is missing is worse than no hook.

Runs on the system interpreter with no third-party imports, so it works before
the project environment is synced.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

DEMO = "guara_falcao"
FRAMES = 20
TIMEOUT_SECONDS = 120

# 0 = drew something, 1 = flat frame, 2 = the demo raised. Any other code
# (uv absent, timeout, 127) means the instrument is broken, not the engine.
REPORTABLE = (1, 2)


def target_file(payload: dict) -> Path | None:
    """Pull the edited path out of a hook payload.

    Args:
        payload: The decoded PostToolUse stdin JSON.

    Returns:
        The edited file, or None if the payload names none.
    """
    raw = payload.get("tool_input", {}).get("file_path") or payload.get(
        "tool_response", {}
    ).get("filePath")
    return Path(raw) if raw else None


def main() -> int:
    """Run the render check if the edit touched graphics, and report."""
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        return 0

    edited = target_file(payload)
    if edited is None or "graphics" not in edited.parts:
        return 0
    if "pyguara" not in edited.parts[: edited.parts.index("graphics")]:
        return 0

    repo = Path(__file__).resolve().parent.parent.parent
    tool = repo / "tools" / "agent_view.py"
    if not tool.is_file():
        return 0

    try:
        result = subprocess.run(
            ["uv", "run", "python", str(tool), DEMO, "--frames", str(FRAMES)],
            cwd=repo,
            capture_output=True,
            text=True,
            timeout=TIMEOUT_SECONDS,
        )
    except (OSError, subprocess.SubprocessError):
        return 0

    if result.returncode not in REPORTABLE:
        return 0

    try:
        shown = edited.relative_to(repo)
    except ValueError:
        shown = edited

    warning = (
        f"Render check failed after editing {shown}\n\n"
        f"{(result.stdout + result.stderr).strip()}\n\n"
        f"Reproduce: uv run python tools/agent_view.py {DEMO} --frames {FRAMES}"
    )
    json.dump(
        {
            "systemMessage": "Graphics edit broke the render path (see transcript)",
            "hookSpecificOutput": {
                "hookEventName": "PostToolUse",
                "additionalContext": warning,
            },
        },
        sys.stdout,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
