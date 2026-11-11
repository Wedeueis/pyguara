# pyguara-next: the consolidated plan

Written 2026-11-10. This joins three things that each said what to do next
and did not agree: the roadmap in the "Path to a Competitive Engine" report,
the engine items Reclaimer's own plan is waiting on
(`reclaimer_v2/project/backlog/active/reclaimer_game_plan.md`, sections 4, 6
and 7), and what profiling Reclaimer on this fork showed (ADR 0009).

Where they conflict, **the profile and Reclaimer's plan win over the
report**. The report led with columnar component storage; the profile showed
that would not have moved any of Reclaimer's costs.

## What Reclaimer's plan was waiting on, and where each stands

| Reclaimer's plan says | Section | Status here |
| --- | --- | --- |
| Wall collision allocates and holds the enemy cap at 100; "waits for RFC-0003's native sweep" | 6 | **Done** (ADR 0009). Host tick at 200 enemies, four players: 13.97 ms to 4.28 ms mean, 21.2 ms to 6.0 ms at the 95th percentile. The cap can be re-set from measurement; that is the game's decision |
| "Rendering isn't measured yet" | 7 | **Measured.** One rendered frame at 200 enemies: 16.8 ms originally, 8.2 ms now, of which 53% is drawing |
| GL HUD costs about 12 ms a frame at 1080p (pyguara #334) | 4 | **Open, and the reason for workstream 1.** The ModernGL UI renderer uploads a whole screen-sized surface every frame. A renderer that draws UI as instanced quads has no such upload |
| Pitch variation needs the native audio backend; the game runs on `pygame`, which cannot change pitch | 4 | Open. Workstream 4 |
| Garbage collection stalled a tick | 6 | Done upstream (pyguara #397) |
| (not in the plan) The top-down movement step around the native sweep | -- | **Done** (ADR 0009, Decision 5). 1.28 to 0.51 ms at 200 enemies; host tick at 200 enemies and four players 4.64 to 3.83 ms, bit-identical |
| (not in the plan) Enemy brains, measured 2026-11-10 | -- | **Engine share trimmed; the rest is the game's.** At 200 enemies and four players the AI is 0.81 ms of a 3.62 ms host tick: about 0.5 ms in Reclaimer's own states (`_Chase` alone 0.43 ms, mostly `nearest_target` and its raycast) and about 0.3 ms in `AISystem` and `StateMachine`. Skipping an empty transition table and not allocating an empty event list took the AI to 0.74 ms, bit-identical. What remains is game code, and belongs in Reclaimer's repository, not this one |
| Packed assets (W30), near release | 4 | Open. Workstream 6 |
| Hosting may not work on players' home connections; "decide before M4" | 7 | Open. Workstream 5 |
| Input buffering (pyguara #73) | 4 | Deferred by the game's own plan; not scheduled here |

Two costs the plan does not name and the profile does:

- **A guest interpolates every replicated field of every entity each
  frame.** It is the largest engine cost on a guest's machine.
- **The game draws one primitive per enemy part, through Python.** That is
  most of the 53%, and no renderer makes a Python call cheaper.

## Order of work

Critical infrastructure first: the pieces that decide which platforms
exist and that everything else is built on.

### 1. The renderer: wgpu in place of ModernGL and the software path

The engine has two renderers and neither is the future. ModernGL is
OpenGL 3.3, which is deprecated on macOS and absent from the browser. The
pygame renderer is software, which is what Reclaimer actually runs on.

One renderer in Rust on wgpu (DX12 on Windows, Metal on macOS, Vulkan and
GL on Linux, WebGPU in the browser), behind the existing `IRenderer`,
`UIRenderer` and window protocols, selected by
`display.backend = "wgpu"`.

| Stage | What | Status |
| --- | --- | --- |
| **A** | Native core: one instanced pipeline for rectangles, circles, lines and textured quads. `IRenderer` and `UIRenderer` on top, text rasterised by `pygame.font` and cached as textures | **Done.** Held to the pygame renderer's pixels by `tests/integration/test_wgpu_pixels.py`; a Reclaimer frame differs in 10 to 14 pixels of 960,000 |
| **B** | A swapchain on the SDL window's native handle, with the offscreen copy kept as the fallback and for capture | **Done, and measured on native Windows (2026-11-10).** DX12 on an RTX 3050, presenting straight to the Win32 window: 400 rectangles at 1280x720 cost 0.52 ms a frame (push 0.16, render 0.13, present 0.22) against 1.39 ms for pygame's software renderer, 2.7x faster. On WSL the same frame costs about 10 ms, which is the GL-over-D3D12 translation layer, not the backend. At 4000 rectangles: 2.00 ms (push 1.60, render 0.17, present 0.23) against 7.50 ms, 3.75x. The GPU side is flat; what grows is push, about 0.4 us of Python per primitive, which is workstream 2's cost. The Win32 handle path, unrun until now, works |
| **C** | Sprites through the render system: `ShapeBatch`, filtering, materials. `render_batch` and `draw_texture` already work | The visual snapshot suite and the demos |
| **D** | The render graph on wgpu: offscreen buffers, lighting, post-processing | `true_coral`, `protocolo_bandeira`, `mourisco_ressonancia` |
| **E** | ModernGL retired; Studio's viewport moved | Nothing imports `moderngl` |

Stage A was the one whose result could be *checked* without a screen.
Stage B is the one that pays for it, and on native Windows it does:
2.7x faster than software on a frame of 400 shapes.

Two things known to be left on the table: the frame is rendered
offscreen and then copied to the window in a second pass, where it could
be rendered straight to the swapchain; and macOS is not handled, because
wgpu wants the window's view where SDL reports the window.

### 2. A batched drawing interface for game code

**Revisit, 2026-11-10:** on native Windows with wgpu, a frame of 4000
primitives is 1.60 ms of Python handing them over against 0.40 ms of GPU
work. With the renderer native, the per-primitive call is the frame's
largest drawing cost, which is the case this section was waiting for.

**Measured before building, 2026-11-10, and deferred.** At 200 enemies
`draw_world` is 2.6 ms of a 6.6 ms frame: about 1.5 ms inside the
renderer's calls and 1.0 ms in the view's own per-enemy Python, which a
batch call does not touch. The ceiling is about 1.2 ms, roughly 18% of
the frame, and almost nothing at 24 enemies. The movement step was the
larger cost and was done first instead (ADR 0009, Decision 5).

Once the renderer is native, the remaining cost is the call per primitive.
Let a scene hand over arrays -- positions, sizes, colours -- for many
shapes in one call. This is the first change that needs Reclaimer's view
code to change, and the first real consumer of ADR 0008's columns.

### 3. Window and input off pygame

SDL2 through pygame is the other half of the platform stack. Replace with
winit or SDL3 once the renderer no longer needs a pygame surface. Not
before: stage A leans on the pygame window on purpose.

### 4. Native audio as the default backend

It exists and Reclaimer's feedback data already carries pitch variation
that only it can play. What is missing is hearing it on Windows.

### 5. Hosting on home connections

A relay, or Steam Datagram Relay for the Steam release. Reclaimer's plan
wants this decided before M4.

### 6. Packed assets

A bake step in `pyguara build`. Near release.

### 7. Columnar components (ADR 0008)

Kept, and moved down. Increment 1 measured bulk work at 290x to 1000x and
per-entity reads at 4.7x to 9.5x *slower*, so it belongs to state that is
consumed in bulk. Its first real use is workstream 2.

## What is not in this plan

- 3D, visual scripting, a custom physics solver.
- A Rapier physics backend. The wall sweep removed the reason Reclaimer
  needed one; revisit if rollback netcode is wanted.
- Rust ports of gameplay kits.
