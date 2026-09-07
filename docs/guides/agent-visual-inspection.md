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

### Run automatically

Two things use this tool without being asked:

- `tests/integration/test_demos_render.py` asserts every demo draws a
  non-flat frame. It found `physics_integration` crashing on its first run.
- `.claude/hooks/graphics_render_check.py` — a warn-only `PostToolUse` hook
  on edits under `pyguara/graphics/`. Boots `guara_falcao` for 20 frames
  (~0.6s) and reports into the transcript if the frame comes out flat. It
  never blocks and always exits 0, including when it cannot run at all.

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
\$g = [System.Drawing.Graphics]::FromImage(\$bmp);
\$g.CopyFromScreen(\$b.X, \$b.Y, 0, 0, \$bmp.Size);
\$bmp.Save(\"\$env:TEMP\shot.png\", [System.Drawing.Imaging.ImageFormat]::Png);
\$g.Dispose(); \$bmp.Dispose()"
```

Dispose the `Graphics` and give `Save` an explicit format: without both, it
throws `ExternalException` and writes nothing while still printing whatever
you echoed after it.

Read it back from `/mnt/c/Users/<windows-user>/AppData/Local/Temp/shot.png`.
The Windows account name is often **not** your WSL username — ask for it
rather than guessing:

```bash
powershell.exe -NoProfile -Command "\$env:TEMP"
```

### Reading window coordinates

Two traps, both of which have already cost an hour here.

**The virtual screen origin is not (0,0).** With a monitor to the left of the
primary, it is negative. A window Windows reports at `(528,208)` is at bitmap
pixel `(528 - originX, 208 - originY)` in the screenshot — with an origin of
`(-2560,0)`, that is `(3088,208)`, i.e. the *other* monitor. Print the origin
alongside the rect, and convert, before concluding a window is missing:

```bash
powershell.exe -NoProfile -Command "
\$b = [System.Windows.Forms.SystemInformation]::VirtualScreen;
Write-Output \"origin=(\$(\$b.X),\$(\$b.Y)) size=\$(\$b.Width)x\$(\$b.Height)\""
```

**`SetForegroundWindow` will not raise a window over a fullscreen app** when
called from a background process; Windows refuses the foreground change and
returns without error. Use `SetWindowPos` with `HWND_TOPMOST` (`-1`) to move
the window somewhere empty and pin it, then `HWND_NOTOPMOST` (`-2`) to
release it afterwards.

Also beware stale windows: a window belonging to an already-exited process can
linger in the enumeration at `(-32000,-32000)` with a tiny size, which is
Windows' canonical position for a minimised window. Confirm the process is
alive before believing anything you read about its window.

WSLg windows are hosted by `msrdc`:

```bash
powershell.exe -NoProfile -Command "
Get-Process msrdc | Where-Object {\$_.MainWindowTitle -ne ''} |
  Select-Object MainWindowTitle"
```

### When no window displays at all

A title prefixed `[WARN:COPY MODE]` means WSLg fell back to copying surfaces
over RDP instead of redirecting them. Windows then register normally — app
list, taskbar icon, a real rect, `IsWindowVisible` true — while their pixels
never reach the Windows compositor. Everything you can query says the window
is fine; it simply never paints.

The cause is in `/mnt/wslg/weston.log`, at WSLg startup:

```
rdp_allocate_shared_memory: Failed to open
  "/mnt/shared_memory/{...}" with error: Input/output error
RDP backend: use_gfxredir = 0
```

Check those two lines first:

```bash
grep -n "use_gfxredir\|rdp_allocate_shared_memory" /mnt/wslg/weston.log
```

`use_gfxredir = 0` is the fault. `use_gfxredir = 1` and no allocation failure
means the graphics path is healthy and the problem is elsewhere.

**The fix is to restart WSL** — from Windows, not from inside the distro:

```
wsl --shutdown
```

then reopen the terminal. The shared-memory device is created by the Windows
host when the VM starts, so nothing inside Ubuntu can repair it. If it
survives a restart, `wsl --update` and shut down again.

Confirmed here: before, every window (including `xmessage`, with no SDL in it
at all) failed to paint; after, `use_gfxredir = 1`, titles lost the prefix,
and both a bare pygame window and `guara_falcao` displayed correctly.

Note this clears `/tmp`, so anything scratch you left there is gone.
`.agent-view/` lives in the repo root and survives.

### Fixes that do not work here

Forcing the SDL drivers is the suggestion this comes up against most often:

```python
os.environ["SDL_VIDEODRIVER"] = "x11"       # already the default
os.environ["SDL_RENDER_DRIVER"] = "software"  # nothing to configure
```

Tested, with a bare pygame window and no PyGuara in it: the window is
created, X11 lists it, `msrdc` lists it, and it still does not appear on the
Windows desktop. Neither variable can help —

- pygame already resolves to `x11` here (`pygame.display.get_driver()`), so
  the first line changes nothing.
- `SDL_RENDER_DRIVER` configures SDL's `SDL_Renderer` API. This codebase
  never creates one — the window is a plain `set_mode` surface — so the
  second line configures a subsystem that is not in use.

When these were tried, the actual fault was WSLg's graphics redirection being
off (see "When no window displays at all" above). No environment variable
inside the distro can reach that; the SDL driver was never the problem.

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
