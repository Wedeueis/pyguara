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
| GL HUD costs about 12 ms a frame at 1080p (pyguara #334) | 4 | **Done.** Reclaimer at 1920x1080 on native Windows (RTX 3050, vsync off, `bench_frame.py`, 2026-11-12): the whole frame, HUD included, is 1.82 ms on wgpu against 6.14 ms on pygame at 24 enemies, and 4.58 ms against 10.25 ms at 200 (p95 5.00 against 15.26) |
| Pitch variation needs the native audio backend; the game runs on `pygame`, which cannot change pitch | 4 | **Done.** Reclaimer on `native` reports `AudioCapability.PITCH`, so its feedback presenter varies each shot's pitch; checked on native Windows 2026-11-12 |
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
| **B, in a game** | Reclaimer's own frame on native Windows (DX12, RTX 3050), vsync off, enemy count held | **Measured 2026-11-10.** 24 enemies: 4.34 ms to 1.67 ms (p95 6.13 to 1.84). 200 enemies: 7.94 ms to 4.87 ms (p95 9.71 to 5.43); `draw_world` 2.64 to 1.46 ms. At 200 the frame is now mostly the simulation tick, not drawing |
| **C** | Sprites through the render system: a sprite batch in one native call, `filter: linear`, materials | **Done 2026-11-11.** Every demo that runs on pygame (eight) draws the same frame on wgpu, every pixel within 2/255 (`tests/integration/test_wgpu_demos.py`). A batch of 2000 sprites: 1.00 to 0.07 ms plain, 2.48 to 0.25 ms turned, scaled and tinted, byte-identical to the per-sprite loop it replaced. `filter: linear` now reaches a bilinear sampler. A material is drawn without, with a warning once: it is GLSL. `ShapeBatch` moved to D: its only consumers are the GL demos, and in Reclaimer `Sparks` costs 0.04 ms a frame |
| **D** | The render graph on wgpu: offscreen buffers, lighting, post-processing, materials (as WGSL), and `ShapeBatch` (whose rows use ModernGL's conventions -- capsule lines, GL circle edges -- where wgpu follows pygame's, so which wins is decided here). Passes and effects are written against a backend-neutral `GraphicsDevice` (`pipeline/device.py`); a `FullscreenShader` carries GLSL and WGSL until stage E, and each pass on wgpu is held to the same pass on ModernGL (`tests/integration/test_wgpu_graph.py`). In increments: **D1 done 2026-11-11** -- native targets and fullscreen passes, the device, composite and final ported, wgpu runs a real graph; all six GL demos byte-identical on ModernGL before and after. **D2 done 2026-11-11** -- `LightPass` on the device, instanced quads native; light map within 0.00024 of ModernGL's at HDR peak 4.0. **D3 done 2026-11-11** -- the post-process stack, bloom, vignette, heat haze, storm and `quintal_cerrado`'s soil-health grade on the device, each within 2/255 of ModernGL. Found: on ModernGL the heat haze's ground heat builds towards the *top* of the frame, the opposite of its docstring; fixed in both on the user's call, which moves `protocolo_bandeira`'s shimmer from over its title to the bottom of the arena. **D4 done 2026-11-11** -- `mourisco`'s pulse rings and `quintal`'s soil grade on the device; `ShapeBatch` on wgpu, drawn as ModernGL draws it (capsules), so `Sparks` matches the GL demos; and, at the user's request, **sprite materials in WGSL** (`SpriteShader`): one `material(sprite)` function on the engine's vertex stage, on wgpu and (with a GLSL twin) on ModernGL; see `docs/graphics/rendering.md`. **D5 done 2026-11-11** -- the six demos select wgpu, held to ModernGL whole-frame by `tests/integration/test_wgpu_gl_demos.py` (bounded: edges rasterise by different rules); `agent_view` and Studio's agent harness capture wgpu. Found on the way: ModernGL mirrored every diagonal line and spark streak (`shape.vert` turned the wrong way) -- fixed in both. **Stage D done.** | All six GL demos: `guara_falcao`, `tamandua_murundus`, `quintal_cerrado`, `protocolo_bandeira`, `true_coral`, `mourisco_ressonancia` |
| **E** | ModernGL retired; Studio's viewport moved. **E1 done 2026-11-12** -- Studio's editor, viewport and agent harness on wgpu (`WgpuImGuiRenderer`, ImGui as one native `mesh` step); the render-graph pixel tests became golden images in `tests/integration/golden/`, approved against ModernGL before it went. **E2 done 2026-11-12** -- ModernGL removed: the backend, its window (borderless chrome ported to `WgpuWindow`), GLSL from every pass, effect and material, the `moderngl` dependency. `display.backend: moderngl` raises `RetiredBackendError` at startup, on the user's call, rather than falling back. **Stage E done.** | Nothing imports `moderngl` |

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

But in Reclaimer itself, on the same machine, `draw_world` is 1.46 ms of a
4.87 ms frame at 200 enemies, and about 1 ms of that is the view's own
Python. The ceiling for a batch call there is about half a millisecond, so
this stays deferred until a game draws thousands of primitives.

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

### 3. Window, input, images and fonts off pygame

SDL2 through pygame is the other half of the platform stack. Replace with
winit or SDL3 once the renderer no longer needs a pygame surface. Not
before: stage A leans on the pygame window on purpose.

**Chosen 2026-11-12 (the user's calls):** winit and gilrs, in the existing
crate; and images and fonts leave pygame too, not only the window. Done when
a game on the wgpu backend runs without pygame ever being imported. The
software renderer keeps pygame; it is the reference the wgpu one is held to.

| Increment | What | Status |
| --- | --- | --- |
| **3a** | The window and its keyboard and mouse input on winit (`NativeWindow`, `rust/src/window.rs`), wgpu presenting to its handle; SDL keycodes and `KMOD_*` values kept, so saved bindings mean the same keys; clipboard on arboard; `post_event` for synthetic input; offscreen under `PYGUARA_WINDOW=offscreen` or SDL's `dummy`. AppKit handles are passed to wgpu, which is macOS's half of the window problem | **Done 2026-11-12.** Found: a windowed game ignored SIGTERM, because `pygame.mixer` still opened SDL and SDL's quit went unread; the window now turns it into a `QuitEvent` |
| **3b** | Gamepads on gilrs: an `IInputBackend` whose button and axis numbers are `GamepadButton`/`GamepadAxis`, from gilrs's standard mapping | **Done 2026-11-12.** `NativeGamepads` (`rust/src/gamepad.rs`) and `NativeInputBackend`; rumble through gilrs force feedback. Behind the default-on `gamepads` feature, as cpal is, because gilrs links udev on Linux. An Xbox 360 pad works on Windows. Found: pads read only while the process has a focused window (Windows.Gaming.Input), so a console probe sees nothing; documented in `docs/systems/input.md` |
| **3c** | The frame clock without `pygame.time` | **Done 2026-11-12.** `WallClock`: pygame's contract, without rounding to whole milliseconds |
| **3d** | Images decoded in Rust (`image` crate): a texture type holding RGBA, its loader and factory, premultiply; the wgpu renderers draw it | **Done 2026-11-12.** `ImageTexture`, `NativeImageLoader`, `ImageTextureFactory`. Every shipped PNG decodes byte-identical to pygame's, JPEGs within 4/255; every demo still matches its pygame frame |
| **3e** | Text rasterised in Rust with a bundled font; the UI's polygon fill off `pygame.draw`; goldens re-approved, since the glyphs change | **Done 2026-11-12.** Liberation Sans 2.1.5 (the user's call) on both renderers, `NativeFont` hinted with skrifa (the font's own TrueType instructions, as FreeType runs them; the user's call in review), laid out as SDL_ttf does: heights exact, widths exact on 99.2% and never more than a pixel out. Polygons as GPU triangles through the native mesh step (the user's call in review): ear-clipped fills and a mitred outline ring, edges within a pixel of pygame's. Five demo goldens re-approved, text only |
| **3f** | Nothing on the wgpu path imports pygame, asserted by a test; capture tools write PNGs without it | **Done 2026-11-12.** `test_wgpu_without_pygame.py` runs three render-graph demos in an interpreter where `import pygame` raises, gamepads and audio included. Bootstrap imports each backend only on its branch; `NativeClipboard` on arboard; the Studio harness writes PNGs through `encode_png` |

### 4. Native audio as the default backend

It exists and Reclaimer's feedback data already carries pitch variation
that only it can play. What is missing is hearing it on Windows.

**Chosen 2026-11-12 (the user's call):** the native backend owns the device
through cpal rather than handing buffers to `pygame.mixer` -- on Windows
and macOS. On Linux it loads ALSA with `dlopen` instead (the user's call,
2026-11-13), so the wheel never links it; see below.

| Increment | What | Status |
| --- | --- | --- |
| **4a** | A mixer in Rust: voices with continuous pitch and native loop regions, buses, music streamed with fades, written to cpal; an offline render for tests and `audio_capture` | **Done 2026-11-12, but for hearing it.** `NativeMixer` (`rust/src/mixer.rs`): sample-exact loop seams, music decoded off the frame, a silent clock when there is no device, `offline` for tests. cpal sits behind the default-on `audio-output` feature, so a Linux machine without ALSA headers still builds and tests the mixer; the device path is type-checked for Windows and unrun until the headers are installed here or it is heard on Windows (4d) |
| **4b** | `NativeAudioSystem` on it, with no pygame | **Done 2026-11-12.** pygame's policy (buses, spatial, priorities) over mixer voices; bus volumes now reach sounds already playing. `capture_native` keeps the seam and pitch output tests running on the new path |
| **4c** | `AudioConfig.backend` defaults to `native`; wheels build without linking ALSA | **Done 2026-11-12, CI unrun.** The default is `native`. `wheels.yml` installs ALSA's and udev's headers in each manylinux container, builds aarch64 on an ARM runner rather than cross, and passes `--auditwheel warn` on Linux so the wheel uses the system's libasound (a bundled one cannot find the host's ALSA plugins). Ran on `next` by hand (`workflow_dispatch`, 2026-11-12): all five wheels and the sdist build. **Found:** the Linux wheel needs `libasound.so.2` and `libudev.so.1` at load, so on a machine without ALSA (a slim container, a server) the whole extension fails to import, not only audio; open, see below |
| **4d** | Heard on native Windows | **Done 2026-11-12.** The user listened through `listen_audio.py`: pitch, a seamless loop region, live bus volume, music fades and twelve overlapping voices |

**Fixed 2026-11-13: the Linux wheel no longer links ALSA.** cpal linked
`libasound.so.2` as `DT_NEEDED`, so in `python:3.12-slim` the import failed
with `libasound.so.2: cannot open shared object file` and every native store
went with it. On the user's call (over a second extension module), Linux's
device is now ALSA opened with `dlopen` when a mixer asks for one: 16-bit
stereo at 48 kHz to `default`, a writer thread into `snd_pcm_writei`; cpal
stays on Windows and macOS. In the slim image the extension imports and the
mixer reports `silent: ALSA is not installed`. `tests/test_native_alsa.py`
pins the missing link and runs the path through ALSA's `null` device.
libudev (gilrs) is still linked; it is in Debian's and Fedora's base images.
Unheard on a real Linux desktop: this machine is WSL, with no card.

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
