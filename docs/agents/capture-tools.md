# Seeing and hearing the engine

Moved out of `AGENTS.md` on 2026-11-14, unchanged, so that file stays short
enough to read every session. `AGENTS.md` keeps the rules; this has the
reasons and the detail.

## Seeing what the engine draws

An agent cannot look at a window. `tools/agent_view.py` boots a demo
headlessly, drives it, and writes PNG frames to `.agent-view/`:

```bash
uv run python tools/agent_view.py --list
uv run python tools/agent_view.py guara_falcao --frames 120 --shot 1 --shot 119
uv run python tools/agent_view.py guara_falcao --click 400,265@30 --shot 80
```

A capture proves the **render path** works. It does **not** prove a window
appears on screen -- those have already diverged here, when vsync silently
promoted the display to an OpenGL surface that never presented software blits.
Read `docs/guides/agent-visual-inspection.md` before reporting on either.

## Hearing what the engine plays

The same problem one sense over: an agent cannot listen to a speaker.
`tools/audio_capture.py` opens the mixer on SDL's `disk` driver, which
writes the mixed output to a file instead of handing it to a device, and
reports what came out:

```bash
uv run python tools/audio_capture.py --asset games/quintal_cerrado/assets/audio/seed.wav --wav
uv run python tools/audio_capture.py --seam --laps 5 --stall 0.35
```

A capture proves the **output path** works -- the clip decoded, the bus
volumes applied, and something other than silence reached the far end. It
cannot hear an ALSA underrun or a muted system mixer, exactly as a frame
capture cannot see a blank window. A wholly silent capture is flagged, for
the reason a flat frame is.

`--seam` measures whether a queued loop joins with no gap and no dropped
sample, which is the assumption W28b's staging rests on and what
`tests/integration/test_audio_output.py` pins.
