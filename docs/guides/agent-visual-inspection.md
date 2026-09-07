# Seeing the engine run, as an agent

An agent working on this engine cannot look at a window. This guide covers how
to see what the engine draws, how to drive it, and — the part that has already
caught us out once — what that does **not** tell you.

## The tool

```bash
uv run python tools/agent_view.py --list
uv run python tools/agent_view.py guara_falcao --frames 120 --shot 1 --shot 119
```

It boots a demo through its real bootstrap, advances it a fixed number of
frames, saves PNGs, and exits. Headless by default (SDL dummy driver), so it
needs no display and behaves the same on CI.

Frames land in `.agent-view/` (gitignored). Open them with the `Read` tool.

### Driving it

Input goes through the real path — `pygame.event.post()`, drained by the
window backend's `poll_events()`, dispatched by `InputManager` — so it
exercises the same code a keypress would.

```bash
# press a key on frame 30
uv run python tools/agent_view.py guara_falcao --press RETURN@30 --shot 45

# click a point on frame 30
uv run python tools/agent_view.py guara_falcao --click 400,265@30 --shot 80

# sample the run
uv run python tools/agent_view.py physics_integration --every 30 --frames 120
```

Clicking `400,265` on the title screen presses **START GAME** and transitions
into gameplay — a useful end-to-end check that UI hit-testing, event dispatch
and scene switching all work.

### Exit codes

| Code | Meaning |
| --- | --- |
| 0 | Frames captured, at least one had content |
| 1 | Every captured frame was a single flat colour |
| 2 | The demo raised; traceback printed |

Blank frames are flagged individually too:

```
.agent-view/boot_process_0020.png  BLANK - nothing was drawn
```

That check exists because a blank frame is the usual way this silently tells
you nothing. `boot_process` legitimately draws nothing — it only opens a
window — so a blank frame there is correct, not a defect. Know what the demo
is supposed to draw before reading the result.

## What this proves, and what it does not

**It proves the render path works.** Entities were queried, sprites submitted,
batches flushed, UI laid out and drawn. If a frame has the right content, the
engine drew the right thing.

**It does not prove a window appears on screen.** The tool reads the surface
the renderer blitted onto. Whether that surface reaches a display is a
separate question with separate failure modes.

Those two have already diverged here. With `display.vsync` enabled, pygame
silently promoted the display to an **OpenGL** surface, and software blits are
never presented to an OpenGL surface:

```
set_mode((1280, 720), 0, vsync=1)  ->  flags=2          OPENGL=True
set_mode((1280, 720), 0, vsync=0)  ->  flags=16777216   OPENGL=False
```

Captures looked perfect. The real window was blank. The capture read the
surface that still held the pixels; nothing was presenting it.

**So: never report "the demo renders correctly" on the strength of a capture
alone.** Say "the render path produces the expected frame", which is what you
actually verified.

## Checking that a window really displays

This needs a channel outside WSL. Two things that do **not** work here:

- **`ffmpeg -f x11grab`** — captures black even for a bare pygame window
  filling the screen red. WSLg composites through Wayland; the XWayland root
  window does not hold the real pixels.
- **Playwright / browser tooling** — irrelevant; this is a native SDL window.

What does work is a screenshot from the Windows side:

```bash
powershell.exe -NoProfile -Command "
Add-Type -AssemblyName System.Windows.Forms,System.Drawing;
\$b = [System.Windows.Forms.SystemInformation]::VirtualScreen;
\$bmp = New-Object System.Drawing.Bitmap \$b.Width, \$b.Height;
[System.Drawing.Graphics]::FromImage(\$bmp).CopyFromScreen(\$b.X, \$b.Y, 0, 0, \$bmp.Size);
\$bmp.Save('C:\Users\<you>\AppData\Local\Temp\shot.png')"
```

Then read `/mnt/c/Users/<you>/AppData/Local/Temp/shot.png`. Find the window
first — WSLg windows are hosted by `msrdc`, and X11 coordinates do **not** map
to Windows desktop coordinates:

```bash
powershell.exe -NoProfile -Command "
Get-Process msrdc | Where-Object {\$_.MainWindowTitle -ne ''} |
  Select-Object MainWindowTitle"
```

A title containing `[WARN:COPY MODE]` means WSLg's graphics path is degraded;
windows may never come to the front, whatever the app does.

### Always run the control first

Before concluding anything about the engine, run a window with **no PyGuara in
it at all**:

```python
import time, pygame
pygame.init()
s = pygame.display.set_mode((800, 600))
pygame.display.set_caption("CONTROL")
t = time.time()
while time.time() - t < 20:
    pygame.event.pump(); s.fill((220, 40, 40)); pygame.display.flip(); time.sleep(0.016)
```

If that red window does not appear, the engine cannot appear either, and the
problem is the environment. Skipping this control cost an hour of blaming the
engine for a WSLg display fault.

## Adding a demo

Add one line to `DEMOS` in `tools/agent_view.py`:

```python
"my_demo": ("games.my_demo.bootstrap", "games.my_demo.scenes", "MyScene"),
```

The registry is explicit rather than discovered, so a broken demo names itself
instead of failing during discovery.

## Related

- `games/validate_demos.py` — boots four capstone demos for 30 frames each and
  reports pass/fail. Faster than this tool when you only need "does it crash".
- Issue #19 — GPU-dependent graphics code (framebuffers, passes, materials,
  effects) has no headless coverage. This tool exercises the pygame path only.
