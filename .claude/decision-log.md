# Decision log -- choice points resolved during implementation

## Fork as a separate private repository with full history
- **Context:** Isolating the columnar/native-runtime work from `Wedeueis/pyguara` so the original engine carries none of the risk.
- **Alternatives:** (a) a long-lived branch in the original repo; (b) a GitHub fork (not possible into the same account); (c) a fresh repo seeded with a squashed snapshot; (d) a new repo carrying the full history, with the original as a push-disabled `upstream` remote.
- **Chose:** (d). Full history keeps `git blame` and the SHAs the ADRs cite, and `upstream` lets fixes from the original be merged in while a disabled push URL makes writing back to it impossible by accident. Private and named `pyguara-next` as reversible defaults.
- **Tags:** repository, fork, risk

## Sparse sets with deferred order-preserving compaction, not archetype tables
- **Context:** Choosing the storage layout for the native column store (`rust/src/world.rs`).
- **Alternatives:** (a) archetype tables -- aligned columns across components, but an entity moves tables on every add/remove and row order follows swap-removes; (b) sparse set per component with swap-remove -- O(1) removal, reorders rows; (c) sparse set per component with tombstones compacted in insertion order at `flush()`.
- **Chose:** (c). Query order is part of the simulation here (#324), and the existing `EntityManager` already defers index cleanup to the frame boundary, so (c) reproduces today's ordering and removal semantics exactly. Archetypes stay a candidate to price once render extraction exists.
- **Tags:** ecs, columnar world, determinism

## f64 columns for simulation floats
- **Context:** Picking the dtype a Python `float` field maps to.
- **Alternatives:** f32 (half the memory, what the GPU wants, what the particle pools use) or f64 (what Python computes in).
- **Chose:** f64. A column must hold exactly the value Python wrote or every system reading it diverges from the object ECS in its last bits, which is the tolerance regime the pools needed and gameplay state cannot accept. f32 remains available as an explicit dtype and is where a render pack would convert.
- **Tags:** columnar world, determinism, parity

## Structural changes raise while array views are alive
- **Context:** A NumPy array over a column holds a raw pointer into a `Vec` that a later insert may reallocate.
- **Alternatives:** (a) invalidate views on change and raise on later access -- NumPy cannot be told its memory is gone; (b) chunked storage with stable addresses -- views stop being one contiguous array; (c) count live buffer exports and refuse any reallocating or compacting change while the count is non-zero, as `bytearray` does.
- **Chose:** (c). It is the only option that is memory-safe with a plain contiguous `ndarray`, and it fails loudly at the offending write with a `BufferError`.
- **Tags:** columnar world, memory safety, numpy

## The native world has no Python fallback
- **Context:** Whether `pyguara.columnar` follows the two-store pattern of ADR 0004.
- **Alternatives:** write a pure-Python column store alongside and a parity suite, or load through `native.require_extension()` as audio and net do.
- **Chose:** no fallback. The point of the fork is native ownership of state; a NumPy-backed twin would double the work being priced and its parity suite would test nothing the object ECS comparison does not.
- **Tags:** native boundary, columnar world

## Native descriptors for view access, not Python properties
- **Context:** A held view's `Vector2` read measured 350 ns against `Transform.position`'s 37 ns, with the view built from Python `property` objects calling `NativeWorld.get_pair`.
- **Alternatives:** (a) keep properties and accept it; (b) a native view class resolving names in `__getattr__` -- only reached after normal lookup fails, so it pays for the failure first; (c) a native `RowView` base with one native `FieldAccessor` descriptor per field on a generated subclass.
- **Chose:** (c). The interpreter calls `tp_descr_get` directly, so there is no Python frame and no argument tuple. Reads went 350 -> 170 ns for a vector and 105 -> 67 ns for a scalar; writes reached parity with `Transform` (88 vs 94 ns).
- **Tags:** columnar world, performance, native boundary

## Build Vector2 through tuple's own constructor, not a raw allocation
- **Context:** Returning a `Vector2` from a native read without paying 210 ns for `Vec2d.__new__`.
- **Alternatives:** (a) call `Vector2(x, y)` from Rust; (b) `PyType_GenericAlloc` plus `PyTuple_SetItem`, the cheapest; (c) call `tuple`'s `tp_new` slot with the subclass, i.e. `tuple.__new__(Vector2, (x, y))` without the Python call.
- **Chose:** (c). (b) leaves the tuple header to zero-initialisation, and the wheel is `abi3` so it runs on interpreters newer than the one it was built for -- a CPython that caches a tuple's hash in its header would get 0 instead of the "not computed" sentinel and hash every vector alike. (c) runs the allocator that owns the layout.
- **Tags:** columnar world, abi3, memory safety


## Target the profile, not the plan: wall probes before columnar storage
- **Context:** Asked to make the current Reclaimer run much faster on the fork. Profiled it first: at 200 enemies, `CharacterMover`'s per-pixel `overlap_box` was 31% of a rendered frame and half of a host tick, each probe building a `pymunk.Body` and `Poly` in Python.
- **Alternatives:** (a) continue the columnar world into `Transform`/`EntityManager`, the architecture the report leads with; (b) cache and reuse the probe shape in Python; (c) move the swept move itself native.
- **Chose:** (c). The profile says columnar storage would not touch Reclaimer's top costs, and the owner had already ruled (2026-11-09) that the mover waits for a native sweep rather than a Python fix.
- **Tags:** performance, character mover, reclaimer

## A mirror that answers only when certain, not a second collision engine
- **Context:** Making the mover's overlap queries native while Chipmunk stays the physics backend.
- **Alternatives:** (a) reimplement Chipmunk's box and segment queries bit-exactly in Rust; (b) a Rust static-collision backend replacing pymunk for wall-only worlds; (c) a native mirror of the static boxes that returns "certainly clear", "certainly this box" or "ask Chipmunk", deferring anything within 1e-6 px of touching and any multi-box overlap.
- **Chose:** (c). Exactness holds by construction instead of by matching another library's float operations, so it cannot diverge -- only decline. (a) would be a parity obligation against code this project does not own.
- **Tags:** physics, native boundary, parity

## The mirror turns itself off for anything but static axis-aligned boxes
- **Context:** Which spaces may be answered from the mirror.
- **Alternatives:** track dynamic and kinematic bodies in the mirror and refresh them per step, or mirror only when every solid in the space is a static, unrotated box and otherwise return None.
- **Chose:** the second. It is exactly the level-geometry world a mover sweeps against, and a space with anything richer keeps today's behaviour untouched.
- **Tags:** physics, native boundary

## Geometry read from each shape's cached bounding box
- **Context:** Where the mirror reads a wall's extent from.
- **Alternatives:** compute it from the body's position plus the collider's dimensions, or read `shape.bb`.
- **Chose:** `shape.bb`. Chipmunk does not reindex a static body that is repositioned, so its queries keep answering from the old place; the cached box is what those queries test, and the mirror has to share the quirk to stay identical.
- **Tags:** physics, parity

## A shared flag instead of a callback for "a static body moved"
- **Context:** The body adapter must tell the engine to rebuild the mirror when a static body is repositioned.
- **Alternatives:** give the adapter a bound method of the engine, or share a one-element list both can set.
- **Chose:** the list. The bound method made every adapter reference the engine, and Studio's scene snapshot deep-copies `RigidBody` handles: the copy walked into the engine and failed a Studio test.
- **Tags:** physics, studio

## The mover accepts a tuple, not "anything but None"
- **Context:** `CharacterMover` finds the optional `sweep_box` with `getattr`.
- **Alternatives:** a `runtime_checkable` capability protocol and `isinstance`, or checking the returned value's type.
- **Chose:** `type(swept) is tuple`. A `MagicMock` engine satisfies any `getattr` and any structural `isinstance`, and nine existing tests pass one; only the answer's type tells a real engine from a double.
- **Tags:** physics, testing

## One integration branch, `next`, instead of a branch per increment from main
- **Context:** The repo's rule is that every independent branch is cut from `main` and gets its own PR. The increments here are independent of each other, but each one has to be measured against Reclaimer together with all the others.
- **Alternatives:** separate branches from `main`, merged into a throwaway branch for every measurement; or one integration branch carrying one commit per increment.
- **Chose:** `next`, one commit per increment. Nothing here is being reviewed into `main` yet, and the commits stay split so each can be lifted onto its own branch when it is.
- **Tags:** repository, workflow

## wgpu for the renderer, behind the existing protocols
- **Context:** Asked to replace the most critical infrastructure first, naming the OpenGL stack.
- **Alternatives:** (a) keep ModernGL and fix its UI upload (issue #334); (b) SDL's own GPU API through a newer SDL; (c) wgpu in the Rust extension behind `IRenderer`/`UIRenderer`.
- **Chose:** (c). OpenGL 3.3 is deprecated on macOS and absent from the browser, so fixing (a) improves a backend with no future. wgpu reaches DX12, Metal, Vulkan, GL and WebGPU from one code path and lives beside the rest of the native code. It grows the extension from 2.6 MB to 7.6 MB.
- **Tags:** renderer, wgpu, platform

## Stage A renders offscreen and presents by copying into the pygame window
- **Context:** The first wgpu increment needs a way to show a frame.
- **Alternatives:** go straight to a swapchain on the SDL window's native handle, or render offscreen and blit a readback to the pygame surface.
- **Chose:** offscreen plus readback first. It can be verified here, headless, against the pygame renderer's own pixels, before any platform's window handle is involved. The readback costs about 19 ms a frame on this machine, so the backend is opt-in and stage B (the swapchain) is what makes it usable.
- **Tags:** renderer, wgpu, verification

## One instanced quad pipeline; a primitive is a row
- **Context:** How the native renderer represents rectangles, circles, lines, sprites and text.
- **Alternatives:** separate pipelines per primitive kind (as the ModernGL renderer has for sprites and shapes), or one pipeline whose fragment shader branches on a per-instance kind.
- **Chose:** one pipeline. Painter's order must be kept across kinds, and a separate pipeline per kind breaks a batch every time the kind changes; with one, a batch breaks only on a texture or scissor change. 600 mixed rectangles, circles and lines are one draw call.
- **Tags:** renderer, wgpu, batching

## Match the pygame renderer's pixels, not the ModernGL renderer's
- **Context:** Which existing backend the new one is held to.
- **Alternatives:** ModernGL (the other GPU backend) or pygame (software).
- **Chose:** pygame. It is what Reclaimer runs on, and its conventions are checkable without a GPU on the reference side. That meant learning them: a circle is centred on a pixel's corner and drawn 0.25 px inside its radius; a thick line is thickened along its minor axis, not across itself, and an even width sits half a pixel towards positive.
- **Tags:** renderer, parity

## Text stays rasterised by pygame.font, cached white and tinted
- **Context:** Drawing text on the GPU.
- **Alternatives:** native shaping and a glyph atlas now, or `pygame.font` into a cached texture per string.
- **Chose:** `pygame.font`, rendered once in white and tinted by the instance colour, so one texture serves every colour and every step of a fade. Glyphs are then identical to the pygame backend's. Native shaping is its own workstream.
- **Tags:** renderer, text

## Keep pygame's texture type and image loader for the wgpu backend
- **Context:** What a `Texture` is under the new backend.
- **Alternatives:** a new GPU texture type with its own loader and factory, or keep `PygameTexture` (a CPU surface) and upload it on first draw.
- **Chose:** keep it. No new loader, the UI's `as_surface` path works unchanged, and nothing reads pixels back from the GPU. The cost is one copy of each image in system memory.
- **Tags:** renderer, resources

## A device-open panic becomes RuntimeError, and the pixel suite also runs in a clean process
- **Context:** wgpu's GL backend panics with EGL `BadAccess` if another OpenGL context is current, which is the case inside a full test run after the ModernGL tests.
- **Alternatives:** let the `PanicException` propagate; skip the suite whenever a device cannot be opened; or convert the panic and add a wrapper test that runs the suite in a fresh interpreter.
- **Chose:** convert and wrap. Skipping alone would leave a full run green having drawn nothing, which is the failure this repo's own instructions warn about for its parity suites.
- **Tags:** renderer, testing

## Present to the SDL window's own handle; keep pygame for the window and input
- **Context:** Stage B needs a swapchain.
- **Alternatives:** replace the window too, with winit, in the same step; or keep the pygame/SDL window and hand its native handle (HWND, X11 window, Wayland surface) to wgpu.
- **Chose:** keep the window. It changes one thing at a time: input, events and every test that opens a pygame display are untouched, and the windowing swap stays its own workstream.
- **Tags:** renderer, wgpu, window

## Choose the window kind by SDL's driver name
- **Context:** `pygame.display.get_wm_info()` returns a dictionary describing the native window.
- **Alternatives:** infer the platform from which keys are present, or ask `pygame.display.get_driver()`.
- **Chose:** the driver name. On X11 the dictionary also carries `surface` and `shell_surface`, the Wayland members of the same C union, holding leftover bytes; inferring from keys read them as a Wayland surface and crashed the process. Regression-tested in `tests/test_wgpu_window.py`.
- **Tags:** renderer, window, crash

## Always render offscreen, then copy to the window
- **Context:** Where the frame is drawn when a swapchain exists.
- **Alternatives:** draw straight into the swapchain's texture, or keep drawing into the offscreen target and copy it across in a second pass.
- **Chose:** offscreen plus a copy, for now. `read_pixels` -- and so headless capture and the pixel suite -- works identically with or without a window, and the swapchain's format (often BGRA, sometimes sRGB) never reaches the drawing pipeline. It costs one extra pass, which is recorded in the plan as something to take back.
- **Tags:** renderer, wgpu

## Measure the batched draw interface before building it, and defer it
- **Context:** Workstream 2 was next; the plan said per-primitive drawing was "most of the 53%".
- **Alternatives:** build `ShapeBatch` support in the pygame and wgpu backends and port Reclaimer's view; or measure the split first.
- **Chose:** measure. `draw_world` was 2.6 ms of 6.6 ms at 200 enemies, about 1.5 ms of it in renderer calls and 1.0 ms in the view's own Python, so a batch call could save about 1.2 ms. The top-down step was 1.28 ms with more of it removable, and the user chose it.
- **Tags:** performance, renderer, measurement

## Batch the top-down step through the engine, keep `step_body` as the reference
- **Context:** The Python around each native sweep cost about 6.4 us per body.
- **Alternatives:** make `step_body` leaner in Python; move the whole `TopDownSystem` (separation too) into Rust; or one engine call taking a row per body and returning per-body results or None.
- **Chose:** the per-body-row call, `step_bodies`, offered by the engine like `sweep_box` is. Exact because the mirror only exists for all-static worlds, so the order of moves cannot matter. Separation stays in Python because its order does matter and it costs 0.06 ms. `step_body` stays unchanged for client prediction.
- **Tags:** physics, native, parity

## Hand the centre across already offset
- **Context:** Rust could add the collider offset itself, which would be one fewer Python operation per body.
- **Alternatives:** add in Rust, or have Python pass the centre exactly as `collider_bounds` computes it.
- **Chose:** Python passes the centre. With no collider `step_body` adds nothing, and `-0.0 + 0.0` is `+0.0`, so adding a zero offset is not bit-identical. Pinned by a dedicated test, the only one that catches it.
- **Tags:** parity, floats

## Trim the FSM's per-tick cost in the engine, leave the brains to the game
- **Context:** Enemy brains were named as the next largest host cost. Split unprofiled: 0.81 ms of 3.62 ms, of which about 0.5 ms is Reclaimer's own state code and about 0.3 ms the engine's `AISystem`/`StateMachine`.
- **Alternatives:** rewrite Reclaimer's `_Chase`/`nearest_target` in the fork's Reclaimer worktree; a native FSM; or only make the engine's dispatch leaner.
- **Chose:** the engine's dispatch only. Skip the transition table when none is declared, reuse the empty pending-event list, and read each `AIComponent` field once. 0.81 to 0.74 ms, tick hash unchanged. Game changes made in the fork's worktree would never reach Reclaimer itself, and a native FSM cannot help states written in Python.
- **Tags:** performance, ai, parity

## Stage C's demo check: compare whole frames on a pinned clock, in clean processes
- **Context:** The plan named "the visual snapshot suite and the demos" as stage C's check. The snapshot suite records backend calls through a recording renderer, so it never touches a backend.
- **Alternatives:** extend the snapshot suite; extend `test_demos_render` (not-blank only); or render each pygame demo on both backends and compare frames.
- **Chose:** compare frames, every pixel within 2/255, each render in its own process with the clock pinned to 1/60 s and `PYTHONHASHSEED=0`, and the pygame frame rendered twice so an unreproducible demo fails as that rather than as a renderer bug. Without the pinned clock `ecs_mental_model` differed by 4 px only because wgpu's headless frames are slower.
- **Tags:** renderer, testing, parity

## Move a sprite batch's placement into Rust, in f64, keeping the Python loop as the reference
- **Context:** `render_batch` cost 0.5-1.2 us a sprite, nearly all of it Python placing each sprite before its `quad` call.
- **Alternatives:** vectorise the placement in NumPy, as the ModernGL packer does; or port the loop to Rust.
- **Chose:** Rust, taking the batch's lists as pyo3 extracts them, with the loop's arithmetic in f64 and in its order. Rust's `f64::cos` is the platform libm, as `math.cos` is, so the frames are byte-identical to the old loop, which stays as `sprites_one_by_one` and is what the test compares against. NumPy's own trig gives no such promise.
- **Tags:** renderer, native, parity, performance

## Defer `ShapeBatch` on wgpu to stage D
- **Context:** `render_shapes` was listed in stage C.
- **Alternatives:** take the rows as ModernGL draws them; convert them in Rust to wgpu's pygame-matching primitives; or defer.
- **Chose:** defer. Its consumers are the four GL demos, which need stage D to run on wgpu at all, and in Reclaimer `Sparks` averages 5 live and 0.04 ms a frame. Taking the rows as they are would also make sparks look different depending on which path drew them, a choice better made with those demos in front of it.
- **Tags:** renderer, scope

## Warn once on a material under wgpu rather than dropping it silently
- **Context:** A material is a GLSL program; wgpu runs WGSL.
- **Alternatives:** silent, as pygame does; raise; or draw without it and log once.
- **Chose:** draw without and log once. Raising would stop a game that runs today on pygame; silence leaves an author guessing why a shader has no effect.
- **Tags:** renderer, materials

## Stage D: one pass hierarchy on a GraphicsDevice, shaders in both languages until E
- **Context:** Passes and effects received a `moderngl.Context` and ran GLSL; two demos ship their own GLSL passes. The user chose a neutral API with WGSL, held to ModernGL's frames.
- **Alternatives:** wgpu twins of every pass beside the ModernGL ones; translate GLSL with naga; or one hierarchy over a device that runs either language.
- **Chose:** one hierarchy. `GraphicsDevice.run(shader, inputs, uniforms, output, blend, viewport, clear)`; `FullscreenShader` carries `glsl` and `wgsl`; `ModernGLDevice` and `WgpuDevice` run them. `RenderGraph`/`FramebufferManager` accept a device or a bare context (wrapped), so no existing caller changed. Stage E deletes the GLSL and the context path.
- **Tags:** renderer, architecture, render-graph

## Devices are an ABC, not a Protocol
- **Context:** The graph must tell a device from a ModernGL context, and unit tests pass `MagicMock` as the context.
- **Alternatives:** a runtime-checkable Protocol; duck-typing on an attribute.
- **Chose:** an abstract base class. A mock satisfies any runtime-checkable protocol and has every attribute, so either alternative would treat a mock context as a device. Unit-tested.
- **Tags:** architecture, testing

## WGSL's uv has its origin top-left; GLSL's bottom-left; ports flip deliberately
- **Context:** GL framebuffer rows run bottom-up, wgpu's top-down.
- **Alternatives:** flip every wgpu target to imitate GL; or let each language use its own native convention and flip in the shaders that have a direction.
- **Chose:** native conventions. Shaders that only sample at `uv` port unchanged; directional ones (rain, rising heat, light positions) flip `y` in their WGSL. The graph test's picture carries a corner marker so an upside-down port fails.
- **Tags:** renderer, shaders, parity

## Input buffers sample linear and repeating, as GL framebuffer textures do
- **Context:** The sampler wgpu's fullscreen passes read inputs through.
- **Alternatives:** clamp-to-edge, the usual choice; or ModernGL's defaults.
- **Chose:** ModernGL's -- linear, repeat. Effects were written against them, and one offsetting UVs near an edge reads the far side on GL; clamping would change those edge pixels.
- **Tags:** renderer, parity

## Pin the clock and seed unseeded streams to compare GL demo frames
- **Context:** Checking the D1 refactor left the GL demos unchanged.
- **Alternatives:** compare pass-level tests only; or compare whole demo frames before and after.
- **Chose:** whole frames, byte for byte, through a wrapper of `agent_view` that pins `PygameClock` to 1/60 s and gives an unseeded `RandomStream` seed 0. Unpinned, five of six differed from themselves; `true_coral` is unseeded by design.
- **Tags:** testing, parity

## Procedural shaders are ported in GL's coordinate convention
- **Context:** Heat haze and storm hash screen position into noise.
- **Alternatives:** port in wgpu's top-left convention and accept different noise; or rebuild GL's `v_uv` (y up) in the WGSL and flip only at the texture read.
- **Chose:** GL's convention. The same inputs give the same noise, so the frames can be compared exactly; a mirrored port would draw a different storm, not a flipped one. Sabotage-tested.
- **Tags:** shaders, parity

## Keep the heat haze's inverted horizon in the port
- **Context:** Measured on ModernGL, ground heat builds towards the top of the frame; the docstring says bottom.
- **Alternatives:** fix it in the WGSL only; fix both; or port it as it is.
- **Chose:** port it as it is and record it. Fixing one side breaks the comparison that proves the port, and fixing both changes how `protocolo_bandeira` looks -- a decision for the user, made separately.
- **Tags:** shaders, bug, parity

## ShapeBatch on wgpu follows ModernGL's shapes, not pygame's
- **Context:** A batch's rows use ModernGL's conventions (capsule lines, distance-tested circle edges); wgpu's per-primitive calls match pygame.
- **Alternatives:** convert rows to pygame-style primitives in Rust; or port `shape.vert/frag` as they are.
- **Chose:** port them. The only producer is `Sparks`, and the four GL demos that use it were made to look like ModernGL, which stage D holds them to. Side effect: Reclaimer's sparks on wgpu become capsules.
- **Tags:** renderer, parity

## Defer materials to stage E
- **Context:** Materials were listed in D4.
- **Alternatives:** design a WGSL sprite-material API now; or defer.
- **Chose:** defer. No game, demo or Reclaimer uses a material; the API is a wrapped ModernGL `Program`. With no consumer, nothing would check the design. On wgpu a material is drawn without, with a warning once.
- **Tags:** renderer, scope

## Compare 8-bit buffers on colour; alpha is a known divergence
- **Context:** The shape case differed on 700 pixels, almost all in alpha.
- **Alternatives:** make wgpu blend alpha as GL does; or compare colour and state the divergence.
- **Chose:** colour. GL lowering a buffer's alpha under translucent draws is the worse behaviour (the final blit then shows the window's previous frame through), and imitating it would make wgpu wrong to make the test pass.
- **Tags:** renderer, testing, parity

## Sprite materials: the author writes one function, the engine owns the vertex stage
- **Context:** The user asked for per-sprite shaders after materials had been deferred.
- **Alternatives:** let a material supply its own vertex shader, as the ModernGL `Shader` route allows; or a fragment-only `material(sprite)` on the engine's vertex stage.
- **Chose:** fragment-only. A material sprite is then placed, batched and ordered exactly as a plain one, which is what lets each material be tested against a plain draw byte for byte; a custom vertex stage is a later addition if a game needs one. Natively a material is a pipeline variant with a third bind group, carried per run.
- **Tags:** renderer, materials, api

## Test materials against plain draws on the same backend, not across backends
- **Context:** GL and wgpu place sprites by different conventions (wgpu follows pygame).
- **Alternatives:** compare material sprites between backends with a tolerance; or choose material functions whose output a plain draw can also produce.
- **Chose:** the latter, on each backend: identity, inverted texture, uniform tint vs per-sprite tint, mask vs pre-masked texture. Exact, and a dropped tint in the native wrapper fails it.
- **Tags:** testing, materials

## Fix the shape shader's rotation rather than the producers' angles
- **Context:** `shape.vert` rotated from +x towards -y; both producers (`draw_line`, the spark pool) pass `atan2(dy, dx)` in screen space. Every diagonal line and streak on ModernGL was mirrored, and the D4 WGSL port copied it.
- **Alternatives:** negate the angle in each producer and keep the documented "counter-clockwise"; or turn the shader the way the producers measure.
- **Chose:** the shader, in both languages, and correct the layout doc. Two producers agree on the convention and the shader was the odd one out; sprites have their own vertex stage and are unaffected.
- **Tags:** renderer, bug

## Hold the GL demos to ModernGL with a bound, not exactly
- **Context:** Whole demo frames on wgpu against ModernGL differ at every shape edge: wgpu rasterises primitives as pygame does, ModernGL by distance, with round line caps.
- **Alternatives:** make wgpu's primitives match ModernGL's; exact comparison per pass only; or a bounded whole-frame comparison.
- **Chose:** passes exact (`test_wgpu_graph.py`), frames bounded -- 1.5% of pixels over 32 apart, mean 2.0, against measured 0.03-0.98% and 0.03-0.66 -- and sabotage-checked: no lights on wgpu fails four demos by wide margins. wgpu stays matched to pygame, which is what Reclaimer runs on.
- **Tags:** testing, parity

## A config naming the retired backend raises; it does not fall back
- **Context:** Removing ModernGL left configs and `PYGUARA_BACKEND` values naming it. The enum's usual handling of an unknown value is to log and keep the default.
- **Alternatives:** map `moderngl` to `wgpu` silently; log and fall back to pygame; or raise at startup.
- **Chose:** raise, on the user's call: `RenderingBackend._missing_` raises `RetiredBackendError(RuntimeError)` naming both live backends. A `RuntimeError`, not a `ValueError`, so neither the env-override loader nor the config fallback swallows it.
- **Tags:** config, renderer, api

## Port the borderless window chrome to WgpuWindow rather than drop it
- **Context:** Minimise, maximise, drag and close for a borderless window lived only on the GL window, and Studio's title bar uses them.
- **Alternatives:** drop borderless Studio with the GL window; or move the methods across.
- **Chose:** move them. They are SDL window calls with nothing GL in them, and Studio's title bar is what a borderless editor has to close with.
- **Tags:** studio, window

## Delete the isolated wgpu pixel runner along with GL
- **Context:** `test_wgpu_pixels_isolated.py` ran the wgpu pixel suite in a subprocess because wgpu's GL backend panics when another GL context is current, which ModernGL's tests made the case.
- **Alternatives:** keep it as a guard; or delete it.
- **Chose:** delete. With no GL context left in the process there is nothing to isolate from, and it doubled the suite's GPU time.
- **Tags:** testing

## The agent harness loses its `gl` flag
- **Context:** `open_headless(gl=True)` chose SDL's `offscreen` driver so a ModernGL scene could create a context.
- **Alternatives:** keep the flag as a no-op for compatibility; or remove it.
- **Chose:** remove. wgpu renders offscreen under `dummy`, the only caller was a test scenario, and a flag that does nothing invites a wrong belief about what it buys.
- **Tags:** studio, api

## Workstream 3: winit + gilrs for the window and input (user's call)
- **Context:** Taking the wgpu backend's window and input off SDL-through-pygame.
- **Alternatives:** winit + gilrs in the existing crate; SDL3 via the Rust crate (needs a C toolchain and CMake in every wheel build); SDL3 via Python bindings.
- **Chose:** winit + gilrs, on the user's call. Pure Rust, hands wgpu its window directly, and the event loop is pumped once a frame from Python.
- **Tags:** window, input, native

## Workstream 3 also takes images and fonts off pygame (user's call)
- **Context:** Deciding how much of pygame leaves the wgpu path.
- **Alternatives:** window, input and clock only (textures stay `pygame.Surface`); or images and fonts as well.
- **Chose:** images and fonts as well, on the user's call. Done when a wgpu game runs without pygame ever being imported. The software renderer keeps pygame.
- **Tags:** resources, text, native

## Workstream 4 owns the audio device through cpal (user's call)
- **Context:** What making native audio the default includes.
- **Alternatives:** default to native with output still on `pygame.mixer`; or a Rust mixer writing to the device through cpal.
- **Chose:** cpal, on the user's call. On Linux the wheel now links ALSA, which `audio.rs` used to avoid on purpose.
- **Tags:** audio, native, packaging

## The wgpu window goes offscreen only under `PYGUARA_WINDOW=offscreen` (user's override)
- **Context:** Without SDL, nothing makes the wgpu window headless; every test, `agent_view` and the Studio harness asked for it through `SDL_VIDEODRIVER=dummy`.
- **Alternatives:** only a new engine variable (touch every caller); only fall back when no display can be opened (tests would open real windows under WSLg); honour both the SDL variable and a new one.
- **Chose:** I first honoured both; in review the user chose the engine's variable alone. `tests/conftest.py`, `agent_view` and the Studio harness set it; SDL's variable no longer reaches the wgpu window. A failure to open a window still falls back to offscreen, with a warning.
- **Tags:** window, testing, tools

## Synthetic input goes through `post_event` on the window backend, as engine events
- **Context:** `agent_view` injected keys and clicks by posting pygame events into SDL's queue, which a winit window never reads.
- **Alternatives:** a winit-side injection of raw tuples; dispatching straight to `InputManager` (skips the editor's routing and replay); `post_event(engine_event)` on both window backends, returned by the next `poll_events`.
- **Chose:** `post_event`. An injected event takes the same path as a real one, on either backend, and the tool stops needing SDL constants for it.
- **Tags:** window, input, tools

## SIGTERM becomes a QuitEvent on the wgpu window
- **Context:** Off the SDL window, a windowed game ignored SIGTERM: `pygame.mixer` still opened SDL, SDL caught the signal and queued a quit nobody read.
- **Alternatives:** only set `SDL_NO_SIGNAL_HANDLERS` (SIGTERM kills outright, no shutdown, no save flush); a Python handler posting `QuitEvent`, as SDL effectively did.
- **Chose:** both: the hint keeps SDL out, and the handler keeps the clean shutdown games had. Installed only over `SIG_DFL` and on the main thread, restored on close.
- **Tags:** window, lifecycle

## WallClock reports fractional milliseconds and sleeps rather than spins
- **Context:** Replacing `pygame.time.Clock` on the wgpu backend.
- **Alternatives:** copy pygame exactly (whole milliseconds, sleep); round nothing and sleep; sleep then busy-wait the last millisecond for precision.
- **Chose:** fractional and sleep-only. Whole milliseconds alternate 16/17 at 60 Hz, jitter the game then absorbs; spinning buys sub-millisecond pacing nobody sees at the cost of a core. Same blocking behaviour as pygame's `tick`.
- **Tags:** clock, application

## The wgpu path still draws a pygame.Surface a game made, but never imports pygame for it
- **Context:** Moving the wgpu backend's textures to `ImageTexture` (RGBA decoded in Rust).
- **Alternatives:** accept only `ImageTexture` (a game drawing its own surface breaks); keep `as_surface`, which imports pygame; recognise a surface only when `pygame` is already in `sys.modules`.
- **Chose:** the last. A game that uses pygame itself keeps working, and one that does not never loads it.
- **Tags:** textures, renderer, api

## JPEG decodes are held to pygame within 4/255, PNGs exactly
- **Context:** Testing the Rust decoder against `pygame.image.load`.
- **Alternatives:** byte-exact for everything (JPEG fails: two IDCTs round differently); a frame-level tolerance only.
- **Chose:** exact on every PNG the repository ships (all 21 are), and a bound for the three JPEGs (measured max 4, mean under 0.13).
- **Tags:** textures, testing

## The default font is Liberation Sans 2.1.5, on both renderers (user's call)
- **Context:** Text leaves `pygame.font`, so the engine needs a face of its own; before, each renderer asked for system "arial" and got Arial on Windows, Ubuntu on Ubuntu.
- **Alternatives:** Liberation Sans 2.x (OFL, Arial's metrics, downloaded); DejaVu Sans (local, permissive, wider than Arial); Noto Sans or Inter (OFL, a different look).
- **Chose:** Liberation Sans 2.1.5, on the user's call, from the official release (sha256 7191c669...). Embedded in the extension from the same files the pygame renderers open, so both backends draw one typeface on every platform.
- **Tags:** text, renderer, packaging

## Text is hinted with skrifa, laid out as SDL_ttf lays out (user's override)
- **Context:** Rasterising text in Rust.
- **Alternatives:** fontdue (simple, no hinting interpreter); skrifa or swash (TrueType hinting, closer to FreeType's pixels, more work).
- **Chose:** I first used fontdue (widths exact on 97%, up to 8 px out); in review the user chose hinting. skrifa runs the font's TrueType instructions in FreeType's v40 normal mode, ab_glyph_rasterizer fills the hinted outline, kerning comes from the `kern` table. Now heights exact, widths exact on 99.2% and never more than 1 px out, and no text pixel off by more than 64/255 from pygame.
- **Tags:** text, renderer

## The UI's polygons are GPU triangles (user's override)
- **Context:** `draw_polygon` on wgpu drew into a scratch `pygame.Surface` with `pygame.draw.polygon`.
- **Alternatives:** tessellate into wgpu triangles (different edge pixels); a Rust rasteriser; transcribe pygame-ce 2.5.6's `draw_fillpoly`, `draw_filltri` and `draw_line_width` into Python.
- **Chose:** I first transcribed pygame's rules (identical on 750 random polygons); in review the user chose GPU triangles. Fill by ear clipping, outline as one mitred ring (miter limit 4, so a translucent outline blends once at its corners), one native `mesh` step. Edges sit within a pixel of pygame's; a thin diagonal outline is fuller, since pygame measures width along an axis.
- **Tags:** renderer, ui

## Whole-demo parity gets a measured text budget per demo, not a tolerance
- **Context:** Text no longer matches pygame pixel for pixel, so four demo frames stopped being identical.
- **Alternatives:** a global tolerance (would hide a broken sprite); render pygame's text through `NativeFont` too (pygame backend's look would depend on the extension being built); a budget per demo that has text, zero for the rest.
- **Chose:** per-demo budgets, measured plus a quarter, with every other demo still exact.
- **Tags:** testing, text

## The no-pygame promise is tested now, with joysticks and audio stood in, and pinned by a strict xfail
- **Context:** Gamepads (3b) and audio (4b) are blocked on system headers, but the rest of the wgpu path is clear of pygame.
- **Alternatives:** wait for 3b/4b before testing; test the real configuration only (it cannot pass yet); test with stand-ins for just those two, plus the real one as a strict xfail.
- **Chose:** the stand-ins plus a strict xfail. The first guards everything else from regressing today; the second fails the suite as soon as it passes, so the marker cannot outlive its reason.
- **Tags:** testing, packaging

## cpal behind a default-on `audio-output` feature
- **Context:** The mixer is pure Rust; only the device links ALSA on Linux, and this machine has no ALSA headers.
- **Alternatives:** make cpal unconditional (no Linux build without headers, so nothing here builds); split the mixer into its own crate; an optional dependency behind a default feature.
- **Chose:** the feature. Every wheel has it; a headerless build gets a mixer that runs silent and says so in `output` and the boot log, which is also what a machine with no sound card gets.
- **Tags:** audio, packaging, native

## The mixer clamps the sum, pygame-style, and the policy stays in Python
- **Context:** Rebuilding `NativeAudioSystem` without `pygame.mixer`.
- **Alternatives:** move priorities, buses and spatial maths into Rust; keep them in Python over a voice API.
- **Chose:** Python. It is `PygameAudioSystem`'s logic, so a game hears the same mix on either backend, and none of it is per-sample. The mixer only knows voices, two groups and gains, and hard-clips the sum as SDL's mixer does.
- **Tags:** audio, architecture

## Bus volumes now reach sounds already playing, on the native backend
- **Context:** pygame fixed a channel's loudness when it started; the native backend can recompute gains.
- **Alternatives:** copy pygame (a slider moves only new sounds); recompute every playing voice on a bus change.
- **Chose:** recompute. A looping ambience that ignores the volume slider is a bug players report; the pygame backend keeps its behaviour.
- **Tags:** audio, behaviour

## Linux wheels use the system's libasound and libudev (`--auditwheel warn`)
- **Context:** cpal links ALSA and gilrs links udev, neither in the manylinux whitelist.
- **Alternatives:** `repair` (bundles libasound, which then cannot load the host's ALSA plugins, so no sound through PulseAudio/PipeWire); a dlopen-based ALSA (not available in cpal); `warn`, leaving them as system dependencies every desktop Linux has.
- **Chose:** `warn`, as other cpal-based wheels do; aarch64 moves to a native ARM runner because the cross image has no target sysroot for the headers. Unverified until CI runs it.
- **Tags:** packaging, audio, ci

## Gamepad buttons come from gilrs's standard layout, not raw indices
- **Context:** pygame handed `GamepadManager` a joystick's raw button indices, which matched `GamepadButton` only on pads that report in that order.
- **Alternatives:** expose gilrs's raw codes (same problem); map gilrs's standard buttons (SDL's controller database) onto the engine's numbering.
- **Chose:** the standard layout. `GamepadButton.A` is the south button on every pad gilrs knows; sticks are flipped to the engine's y-down.
- **Tags:** input, gamepads

## Linux's audio device loads ALSA with dlopen instead of linking it through cpal
- **Context:** The CI wheel linked `libasound.so.2` (via cpal), so in `python:3.12-slim` the whole extension failed to import, not only audio.
- **Alternatives:** dlopen ALSA when a mixer opens the device (cpal has no such option, so our own small ALSA writer on Linux); move the device code into a second extension module.
- **Chose:** dlopen, on the user's call (2026-11-13). cpal kept on Windows/macOS. The writer uses ALSA's simple API: 16-bit stereo, 48 kHz, 40 ms latency to `default`, 256-frame periods. ALSA's stderr error handler is silenced only while the device opens. libudev (gilrs) left linked: present in Debian and Fedora base images.
- **Tags:** audio, native-extension, wheels, linux
- **Review:** approved by the user 2026-11-13.

## Over Steam, renet rides Steam's unreliable messages rather than Steam's own reliable lanes
- **Context:** 5a, the Steam core. Steam's ISteamNetworkingMessages has its own reliable and unreliable sends, so renet could be dropped as well as renetcode.
- **Alternatives:** map the five channels onto Steam's reliable/unreliable sends directly; keep renet and carry its packets in Steam's unreliable, no-Nagle messages.
- **Chose:** keep renet. The channel limits, the half-limit rule in `bytes_to_check`, backpressure through `can_send_message`, slicing and link stats then behave exactly as on UDP, which is what lets `tests/test_net_steam_core.py` re-run 18 of `test_net_transport.py`'s tests unchanged. Steam's reliability would have needed its own limits and its own stats.
- **Tags:** net, steam, transport
- **Review:** approved by the user 2026-11-13.

## The Steam core's handshake is a repeated HELLO answered by WELCOME, with renetcode's reason names
- **Context:** 5a. With no renetcode, something has to carry the guest's user data (versions, content hash) and tell the guest it was admitted.
- **Alternatives:** send the user data as the first CONTROL message over renet (but renet needs a connection first, and a refusal needs a reason before one exists); a raw tagged HELLO resent every 100 ms until any reply.
- **Chose:** the tagged HELLO; a host answers every HELLO from a peer with WELCOME, so a lost one costs a resend, not the join. Refusals (`REFUSED`, rate-limited by the shared stranger budget) and goodbyes (`BYE`, three times) carry a reason. A client's reasons reuse renetcode's names (`ConnectionDenied`, `ConnectionTimedOut`, `ConnectionRequestTimedOut`, `DisconnectedByServer`) so `session._explain` words them the same for players. A host is closed by default (admits only `allow`ed Steam IDs, which 5c's lobby will drive); `open_room` admits anyone, for development.
- **Tags:** net, steam, transport, security
- **Review:** approved by the user 2026-11-13.

## Steam callbacks by manual dispatch, drained by the caller each frame
- **Context:** 5b, the Steam binding. Steam delivers session requests and failures as callbacks.
- **Alternatives:** Steam's automatic dispatch (`SteamAPI_RunCallbacks` into registered C++ objects: needs the C++ ABI, and would run code on whatever thread calls it); manual dispatch drained on one thread.
- **Chose:** manual dispatch through the flat C API, drained by `NativeSteam.run_callbacks()` and returned as tuples, so no C++ ABI is involved and nothing Steam does runs Python behind the frame loop. Messages go unreliable + no-Nagle + auto-restart-broken-session on channel 0, since renet carries its own reliability (see the 5a entry). The class is `unsendable` and one per process, as Steam allows.
- **Tags:** net, steam, native-extension
- **Reviewed:** approved by the user 2026-11-14, after the binding ran against real Steam on Windows.

## Lobby results as call results only, not broadcast callbacks
- **Context:** 5c, `NativeSteam.create_lobby`/`join_lobby`. Steam reports `LobbyCreated_t`/`LobbyEnter_t` as call results for the handle, and may also post them as broadcast callbacks.
- **Alternatives:** handle the broadcasts (would also see lobby entries this object never asked for, and needs de-duplicating against the call results); handle both and de-duplicate by lobby ID; take only the call results for handles this object holds.
- **Chose:** call results only. Each request yields exactly one event, and a result for a handle this object did not ask for is dropped. A failed or unreadable call result still yields its event (EResult 2 / enter response 5), so a request never hangs silently.
- **Tags:** net, steam, native-extension
- **Reviewed:** approved by the user 2026-11-14.

## SteamLobby reports join requests instead of acting on them
- **Context:** 5c, `pyguara/net/steam_lobby.py`. An overlay invite accepted, or "Join Game" clicked, while the game is already running.
- **Alternatives:** leave the current lobby and join the new one automatically; report a `JoinRequested` event and let the game decide.
- **Chose:** report it. Leaving mid-match is a game decision (confirm dialog, save, etc.), and the lobby ID comes from a friend's untrusted rich presence, so nothing is done with it beyond strict parsing.
- **Tags:** net, steam, lobby
- **Reviewed:** approved by the user 2026-11-14.

## Lobby membership is admission, and guests show "Join Game" too
- **Context:** 5c. Who the host allows on the Steam transport, and whether a guest advertises the lobby.
- **Alternatives:** admit only players the host invited personally; admit every lobby member; guests advertise the lobby or not.
- **Chose:** every member of the friends-only lobby is admitted (`MemberAdmitted`/`MemberRemoved` map to the core's `allow`/`revoke`), and guests set the same `connect` rich presence. That is Steam's friends-only policy ("allows those who join to invite their own friends"), which suits a co-op game for friends; a game wanting host-only invites can ignore guests' presence later.
- **Tags:** net, steam, lobby, security
- **Reviewed:** approved by the user 2026-11-14.

## SteamNetwork hub owns the one callback stream
- **Context:** 5d. Steam has one callback stream, and both the lobby (lobby results, membership) and the transport (session requests, failures) need it; the lobby exists before the transport, since a guest learns the host from it.
- **Alternatives:** the transport drains callbacks in its `poll` and forwards lobby ones (but there is no transport yet while joining); the game drains and routes by hand; a hub that drains once per frame and routes to both.
- **Chose:** `SteamNetwork.update()`, once a frame before the session. It also applies admission (lobby member in/out to `allow`/`revoke`), so a game cannot forget to.
- **Tags:** net, steam, lobby
- **Reviewed:** approved by the user 2026-11-14.

## No native thread for Steam; pump from the frame
- **Context:** 5d, `SteamTransport.poll` receives, ticks the core and sends. `UdpTransport` runs a Rust thread so a stalled frame does not stall acks.
- **Alternatives:** a Rust thread calling Steam's networking functions while Python runs callbacks on the main thread; pump everything from the frame.
- **Chose:** pump from the frame. Steam's API is not documented as safe across threads in manual dispatch mode, and the core's 10 s timeout dwarfs any frame stall. Can be revisited if the playtest shows acks lagging.
- **Tags:** net, steam, native-extension
- **Reviewed:** approved by the user 2026-11-14.

## Session requests before admission wait, bounded
- **Context:** 5d. A guest's first message can reach the host before the host sees the guest enter the lobby.
- **Alternatives:** refuse and rely on Steam's auto-restart of a broken session; accept everyone and let the core refuse strangers; hold the request until the lobby admits them.
- **Chose:** hold it (at most 64 strangers, oldest dropped), accept on `allow`. Accepting everyone would let any Steam user make the host open a relay session; refusing would cost each guest a failed session first.
- **Tags:** net, steam, security
- **Reviewed:** approved by the user 2026-11-14.

## steam_api copied into the built game by `pyguara dist steam`
- **Context:** 5d. Valve's library must sit beside the executable; the engine cannot ship it.
- **Alternatives:** `pyguara build --add-binary` (PyInstaller puts it in `_internal` or a temp dir for onefile); copy it into the content root at `pyguara dist steam --steam-api`; leave it to the developer.
- **Chose:** `dist steam --steam-api`, copying beside the executable where Valve expects it, refusing a file that is not a 64-bit steam_api, and printing a note when the content has none. At run time `find_steam_api` looks: explicit path, `PYGUARA_STEAM_API`, beside the executable, PyInstaller's bundle dir, the working directory.
- **Tags:** net, steam, dist
- **Reviewed:** approved by the user 2026-11-14.

## Reclaimer opens the Steam lobby before the room starts
- **Context:** 5e wiring. `HostGame`/`ClientGame` take a session at construction, and on Steam the transport needs an open lobby (host) or the lobby owner (guest), which arrive asynchronously.
- **Alternatives:** make the scenes start without a session and attach one when the lobby answers (touches HostGame/ClientGame and every scene path); a lobby screen scene; wait for the lobby in `__main__` before the room, up to 15 s, failing with Steam's reason.
- **Chose:** wait in `__main__`, before the window is created (a terminal line, not a frozen window). The room and join scenes then receive a ready `SteamNetwork` and change only where the transport comes from. A lobby browser or in-game "host" menu can replace the wait later. The wall clock is passed in, since Reclaimer's gameplay modules may not read one.
- **Tags:** net, steam, reclaimer
- **Reviewed:** approved by the user 2026-11-14.

## SimulatedSteam is public engine API, not a test helper
- **Context:** Reclaimer needed to test its Steam path; the fake Steam lived in the engine's tests.
- **Alternatives:** copy the fake into Reclaimer's tests; expose it in the engine beside `SimulatedNetwork`.
- **Chose:** `pyguara.net.simulated_steam.SimulatedSteamCloud`, exported from `pyguara.net`, so every game tests its Steam path the same way and the engine's tests run on the same double.
- **Tags:** net, steam, testing
- **Reviewed:** approved by the user 2026-11-14.

## Steam is flushed after the session's driver
- **Context:** `HostDriver`/`ClientDriver` send in `after_fixed_updates`; Steam has no thread, so those sends waited for the next frame's pump.
- **Alternatives:** flush inside `SteamTransport.send` (one Steam call per message, and renet only packs on tick); accept a frame of delay; a `flush()` the game calls after the fixed updates.
- **Chose:** `SteamNetwork.flush()`, run by Reclaimer's `SteamFrame.after` hook registered after the driver.
- **Tags:** net, steam
- **Reviewed:** approved by the user 2026-11-14.

## The fork merges back before the 5e playtest
- **Context:** 2026-11-14. The merge into `pyguara` was gated on 5e, and 5e is postponed indefinitely (no second Steam account).
- **Alternatives:** keep waiting, continuing other work in the fork; merge now and carry the playtest as an issue on `pyguara`.
- **Chose:** merge now (the user's call). The Steam code is complete and tested over SimulatedSteam and against one real account; the risks a merge carries (new defaults on untried machines) do not shrink by waiting. The playtest is pyguara #402.
- **Tags:** repo, merge, steam
- **Reviewed:** chosen by the user 2026-11-14.


# From the pyguara checkout's local log, before the merge

## Keyed invites instead of renetcode's Unsecure mode
- **Context:** Phase 1 handshake for networked multiplayer. Owner asked for no security issues; Unsecure mode lets anyone connect and seals tokens with an all-zero key.
- **Alternatives:** (a) Unsecure mode, encryption added later, as the plan said. (b) A random 256-bit session key shared in an invite string; each client mints its own token under it, with a fixed placeholder as the token's server address so a host behind NAT need not know its public IP.
- **Chose:** (b). It is the same code with one real key: strangers can't connect, so the renet panic path needs an invited player, and traffic is actually confidential. Cost: an invite is a long string to paste rather than an IP.
- **Tags:** networking, security, handshake
- **Status:** Approved by owner 2026-11-06.

## Token time counts from zero instead of wall clock
- **Context:** renetcode expires tokens by comparing a client-minted timestamp with the host's clock; a guest with a wrong clock would fail silently.
- **Alternatives:** (a) wall clock plus a long expiry, tolerating skew up to that expiry. (b) Both cores start their netcode time at zero and tokens get a 10-year expiry, so no wall clock is involved.
- **Chose:** (b). Skew stops being possible rather than merely tolerated, and tests need no clock faking. Expiry normally bounds token replay, but a replayer lacks the keys to finish a handshake, and renetcode refuses one token from a second address.
- **Tags:** networking, security, handshake
- **Status:** Approved by owner 2026-11-06.

## Rate limit only after authentication
- **Context:** plan section 5 said malformed input "counts against the peer".
- **Alternatives:** (a) strike or throttle by source address before the MAC check, as the plan said. (b) Only authenticated traffic counts against a peer; unauthenticated traffic shares one global budget.
- **Chose:** (b). UDP source addresses are spoofable, so (a) would let anyone get a real player kicked or throttled with forged packets.
- **Tags:** networking, security, rate-limiting
- **Status:** Approved by owner 2026-11-06.

## One mutex-guarded core, not message queues between thread and Python
- **Context:** the plan describes a Rust socket thread handing messages to Python through a queue.
- **Alternatives:** (a) the thread owns the core, with command and event queues either way. (b) The sans-IO core sits behind one `Mutex`, locked briefly by the thread and by Python's send and poll; the thread never needs the GIL.
- **Chose:** (b). It is less code, has no queue to keep bounded twice, and sans-IO and socket modes share every code path. The thread holds the lock for microseconds per datagram (a frame's core work measured 23 us), so Python can't stall on it noticeably. Revisit if contention measures badly.
- **Tags:** networking, native-boundary, threading
- **Status:** Approved by owner 2026-11-06.

## Messages pumped into a bounded inbox each tick
- **Context:** renet returns nothing from a connection once it is disconnected, so a refusal message could be lost if Python polled after the disconnect arrived.
- **Alternatives:** (a) Python polls renet directly, with back-pressure but losing final messages. (b) The core moves messages into an inbox each tick, and stops pumping above a byte limit so reliable back-pressure still reaches renet.
- **Chose:** (b). A refused guest must see why, per the plan's version check.
- **Tags:** networking, handshake
- **Status:** Approved by owner 2026-11-06.

## Reliable sends capped at half the channel limit
- **Context:** renet's sender counts actual bytes but its receiver charges each sliced message as whole 1,200-byte slices, against the same limit, and disconnects the peer when over. A test found a message the sender accepted that made the receiver disconnect.
- **Alternatives:** (a) patch renet, which means a fork. (b) Reject only a single message whose rounded size exceeds the limit, which still fails with many small sliced messages. (c) Only accept a reliable send if used + rounded size fits in half the limit, since rounding can at most double the charge.
- **Chose:** (c). It covers the worst case with no fork. Cost: the usable backlog is half the configured figure, so LEVEL's largest message is 8 MiB.
- **Tags:** networking, reliability
- **Status:** Approved by owner 2026-11-06.

## Host holds a peer's traffic until the client confirms the handshake
- **Context:** renetcode deadlocks a join: if the first keepalive is lost, the client ignores payloads while waiting for another, and each payload resets the host's keepalive timer. A seeded test found the host admitting a player whose client then timed out.
- **Alternatives:** (a) patch renetcode to accept a payload as confirmation, which means a fork. (b) Host delays its first payload by a fixed time, which only narrows the race. (c) The client sends a one-byte confirmation (a byte renet never uses as a packet type) until it hears a payload, and the host sends no renet traffic and reports no connection until any authenticated payload arrives from that peer.
- **Chose:** (c). It closes the deadlock with no fork, and "connected" now means both ends know, so the host's view can't desync from the client's. Cost: admission waits about one round trip longer.
- **Tags:** networking, handshake, desync
- **Status:** Approved by owner 2026-11-06.

## Quick saves serialize on a worker thread and coalesce per key
- **Context:** owner wants a guest's character saved as run events arrive, without hurting performance. `save_data` serializes and fsyncs on the calling thread.
- **Alternatives:** (a) serialize on the main thread, write on a worker: safe against later mutation, but the serialization cost lands on the frame. (b) Hand over the value and do everything on a worker, keeping only the newest value per key and writing at most once per interval.
- **Chose:** (b). `request` is O(1), and a burst of events costs one write. The cost is a rule: the caller must hand over a value it won't mutate. The GIL means a huge blob can still cost a frame; measured in docs.
- **Tags:** persistence, performance
- **Status:** Approved by owner 2026-11-02. Follow-up: add a form taking a function, called on the main thread only when a write is due, so a game doesn't build a copy per event.

## Spawn and despawn run on the interpolation timeline
- **Context:** Phase 2. Plan's desync rules say to hold records for unseen spawns and to apply events at their tick.
- **Alternatives:** (a) apply on arrival, dropping records for unknown ids: a kill shows 100 ms before the death animation on screen. (b) Queue spawns and despawns in order, and apply when the render clock reaches their tick; a spawn known but not yet applied keeps its records.
- **Chose:** (b). Things appear and vanish in step with the motion around them, and it gives the plan's "hold" rule for free. Records for a spawn that has not arrived at all are dropped, since the next snapshot repeats them.
- **Tags:** networking, replication, desync
- **Status:** Approved by owner 2026-11-02. Covers appearing and vanishing only; hit sparks and damage numbers are decided in Phase 4.

## Network ids freed on a time quarantine rather than per-client acks
- **Context:** plan said to hold a freed 16-bit id until every client acknowledged a newer snapshot.
- **Alternatives:** (a) clients ack event sequence numbers, costing an upstream message and per-peer state. (b) Keep freed ids unusable for 30 seconds of ticks. Any peer that far behind on reliable traffic has already timed out, at 10 seconds of silence.
- **Chose:** (b). No wire cost. Stale records are already dropped by the per-entity tick rule, so the worst case is one brief wrong position. Acks can come with delta encoding if that gets built.
- **Tags:** networking, replication, desync
- **Status:** Approved by owner 2026-11-02. Revisit if delta encoding is built, since that needs acks anyway.

## Over-budget snapshots rotate instead of prioritising
- **Context:** plan section 6 says send nearby and recently changed entities first when over budget.
- **Alternatives:** (a) priority by distance now. (b) A per-client round-robin cursor, so every entity is sent within a few snapshots, with priority added once a measurement asks.
- **Chose:** (b). Starvation is a desync (an entity that never updates), and rotation rules that out by construction. At 500 entities a snapshot is 6 KB against a 16 KB budget, so this path is rare today.
- **Tags:** networking, replication, performance
- **Status:** Approved by owner 2026-11-02. Follow-up: priority that builds with waiting when a real game goes over budget; adaptive sending in Phase 5, because a host's upload can saturate before the fixed budget applies.

## Commands numbered by host tick, not by a client sequence
- **Context:** Phase 3. The host has to know which input belongs to which step, and the client has to know which inputs a host state already includes.
- **Alternatives:** (a) a sequence number, with the host applying one queued command per tick and acknowledging the sequence, as Quake and Source do. No shared clock, but the queue depth drifts and a tick has no shared meaning. (b) Commands name the host tick they apply to, as the plan says, and a state "at tick N" includes every command before N.
- **Chose:** (b). Reconciling needs no separate ack, and Phase 4's projectile events and any later lag compensation can use the same numbers. Cost: the client has to run ahead of the host by the right amount.
- **Tags:** networking, prediction
- **Status:** Approved by owner 2026-11-05.

## Client lead steered by how early commands arrive, not by round trip
- **Context:** the client has to run ahead just enough for its commands to arrive in time. The plan said to estimate that from round-trip time.
- **Alternatives:** (a) derive lead from RTT plus a margin, which needs jitter estimated separately and is wrong whenever the two directions differ. (b) The host measures the slack it actually saw when taking each command, and echoes the smallest; the client adds or skips ticks to hold a target. Each change starts a new epoch that commands carry and the host echoes. An earlier version compared tick numbers instead, and swung by 200 ticks after a rewind, because commands from before a rewind have the larger numbers. (c) Run the client's simulation slightly faster or slower. Smoothest, but the fixed step belongs to `Application`, which is core.
- **Chose:** (b). It measures the only thing that matters and needs no transport stats. Cost: an adjustment moves the character one tick off the steady rhythm, which happens rarely and is small.
- **Tags:** networking, prediction
- **Status:** Approved by owner 2026-11-05.

## Owner state is a separate message of exact doubles
- **Context:** replay is only bit-exact from position and `_remainder`, and `QuantisedVector` rounds positions.
- **Alternatives:** (a) add owner-only fields to the schema and records, which complicates the shared record and its digests. (b) A separate unreliable message per player, holding `PredictedBody.capture()` as doubles, with finiteness checked on arrival.
- **Chose:** (b). Exact, independent of the snapshot budget, and a game with a dash timer just returns a longer tuple. Cost: about 50 bytes per player at 20 Hz.
- **Tags:** networking, prediction, desync
- **Status:** Approved by owner 2026-11-05.

## Correction smoothing shown through the step hooks
- **Context:** a correction should glide, but the mover reads `Transform.position`, so a visual offset must never reach the simulation.
- **Alternatives:** (a) a separate render-position component, which every renderer and game would have to learn. (b) Add the offset to `Transform` after the fixed updates and restore the exact simulated state before the next ones.
- **Chose:** (b). Rendering needs no changes, and the simulation only ever sees exact state. Cost: code running between `after_fixed_updates` and the next frame reads the shown position.
- **Tags:** networking, prediction
- **Status:** Approved by owner 2026-11-05.

## No audio output falls back to SDL's dummy driver
- **Context:** the Windows CI runner has no sound device, and `pygame.mixer.init` raising during bootstrap stopped every game from starting.
- **Alternatives:** (a) set `SDL_AUDIODRIVER=dummy` in the failing test, as other tests do. It would pass CI and leave players affected. (b) A `NullAudioSystem` chosen at bootstrap, which is one more backend to keep in step, and bootstrap would have to probe the device. (c) Retry on the dummy driver inside the existing backend.
- **Chose:** (c). Every caller, including the native backend that inherits from it, works unchanged, and it's a few lines. Cost: a mistyped `SDL_AUDIODRIVER` now gives silence and a warning rather than an error.
- **Tags:** audio, windows, bootstrap
- **Status:** Approved by owner 2026-11-05.

## A projectile judges a hit from the target's Transform, not the index's copy
- **Context:** pyguara ProjectileSystem swept hits (for Reclaimer's Precise Shot)
- **Alternatives:** add `SpatialHash.position_of()` (a Rust API on the native store as well); read the target's `Transform`
- **Chose:** `Transform`. No native change, and it is the entity's current position. Cost: a target must have one (anything tracked by `SpatialIndexSystem` already does); manual index users without one are now skipped.
- **Tags:** projectiles, spatial hash, engine boundary
- **Status:** Approved by owner 2026-11-05.

## A declined hit is a pass, remembered per projectile
- **Context:** `on_hit` returning False (a dodge)
- **Alternatives:** stop the shot on any contact; let it fly on and re-offer the target next tick; fly on and remember the target as passed
- **Chose:** remember it in `Projectile.passed`, so a dodge rolls once per shot rather than every tick it overlaps. Same mechanism a piercing shot would use later.
- **Tags:** projectiles, dodge, determinism
- **Status:** Approved by owner 2026-11-05.

## The handler sees the shot at the impact point
- **Context:** where `projectile.position` is when `on_hit` runs
- **Alternatives:** the step's end; the closest point on the step to the target
- **Chose:** the impact point, so hit sparks and damage numbers are placed right; a declined shot then continues to the step's end.
- **Tags:** projectiles, feel
- **Status:** Approved by owner 2026-11-05.

## A sound over its limit is dropped, not queued and not stealing a voice
- **Context:** `AudioManager.set_sfx_limit`, so ten hits in one frame don't start ten copies of one clip.
- **Alternatives:** (a) drop the new play. (b) Stop the oldest copy and start the new one (FMOD's "steal oldest"). (c) Queue it for when a voice frees.
- **Chose:** (a). The copies already playing are that moment's sound; a queued one is heard late, after the thing it was for, and stealing cuts a sound off mid-way, which is audible as a click on short clips. Stealing can be added as an option if a game wants a rapid-fire sound to restart.
- **Tags:** audio
- **Status:** Approved by owner 2026-11-06.

## Sound limits keyed by clip path, timed by real time
- **Context:** same feature.
- **Alternatives:** (a) key by path, which `play_sfx_clip` reads from the clip. (b) A separate name a game chooses, so several clips share one limit. Timing: (i) `time.monotonic`, injectable. (ii) Frames or ticks, counted by whoever calls `update`.
- **Chose:** (a) and (i). A path is what both play methods already have, with nothing new to name. Real time because the gap is heard in real time, and `AudioManager` has no tick of its own; a test passes a clock.
- **Tags:** audio
- **Status:** Approved by owner 2026-11-06.

## Placeholder sounds: the demo's builders moved into the engine as they were
- **Context:** Reclaimer needs placeholder sounds; the only builder was a script inside Quintal do Cerrado. Owner chose to move it into the engine.
- **Alternatives:** (a) move the functions unchanged, standard library only, 22,050 Hz fixed. (b) Rewrite on numpy, which is already a dependency, and make the sample rate a parameter.
- **Chose:** (a). The demo's files then rebuild byte for byte, which a test pins, and a few short clips build in well under a second without numpy. The rate stays a module constant because a placeholder doesn't need a choice of quality.
- **Tags:** audio, tooling
- **Status:** Approved by owner 2026-11-06.

## Placeholder recipes are a tree of one-key nodes mirroring the functions
- **Context:** a game keeps its tuning in data, so sounds need a data form too.
- **Alternatives:** (a) a tree where each node names a function and holds its arguments (`{"envelope": {"of": {"mix": [...]}}}`). (b) A flat list of layers per sound, each with its own envelope, mixed together. (c) Python only, with games writing their own script.
- **Chose:** (a). It says exactly what the functions do, so one page documents both, and anything the functions can build a recipe can too. (b) can't express a sequence of notes. Errors name the path down the tree and the closest valid name.
- **Tags:** audio, tooling, data
- **Status:** Approved by owner 2026-11-06.

## Faded text: alpha baked into the glyph pixels, not set on the surface
- **Context:** `Font.render` ignores a colour's alpha; fixing faded text on all four renderers.
- **Alternatives:** (a) `surface.set_alpha(a)` after rendering. (b) Multiply the alpha into every pixel (`BLEND_RGBA_MULT`).
- **Chose:** (b). Surface alpha applies only when blitting; the ModernGL world renderer uploads the pixels to a texture, where (a) would be lost. (b) works for both, from one shared helper.
- **Tags:** graphics, rendering
- **Status:** Approved by owner 2026-11-06.

## Game events ride replication's reliable stream, declared on its schema
- **Context:** network Phase 4, for Reclaimer M2: hits, kills and heals must agree on every screen.
- **Alternatives:** (a) a separate event module with its own message kind, its own fingerprint check, and its own way to name entities. (b) Events registered on `ReplicationSchema` and sent by `ReplicationHost`, queued in the same per-peer outbox as spawns and despawns and applied on the same delayed timeline by `ReplicationClient`.
- **Chose:** (b). Ordering against spawns and despawns comes for free (a kill always lands before that enemy's despawn), entity references use replication's own network ids, and the existing hello fingerprint covers events, so a client with different event layouts refuses rather than misreading. Cost: replication grows a little; a small `EventRelay` stays separate to forward a dispatcher's events.
- **Tags:** networking, events, replication
- **Status:** Approved by owner 2026-11-06.

## An event is stamped with the first tick whose state includes it
- **Context:** a client applies an event when its delayed view reaches the event's tick.
- **Alternatives:** (a) the tick of the last snapshot, as despawns are. (b) `fixed_tick + 1` during the fixed update that produced it, the tick of the first snapshot that shows its result.
- **Chose:** (b). A hit number appears with the snapshot where the health drops, not a frame before it. Spawns still go out before any event queued after them, since sending an event first announces pending spawns.
- **Tags:** networking, events, ticks
- **Status:** Approved by owner 2026-11-06.

## No separate engine PR for projectiles in M2: shots ride game events
- **Context:** Phase 4's second half, "projectile spawn events", for Reclaimer's M2.
- **Alternatives:** (a) an engine projectile-replication module: shot ids, spawn and removal messages, fast-forwarding by latency. (b) The game registers its own `ShotFired` event (origin, velocity, skill, shot id) on the event schema just built; a client spawns it into a display-only `ProjectileSystem` (walls, no targets), and the host's hit event, carrying the shot id, switches it off.
- **Chose:** (b) for now. Events already apply on the delayed timeline, so a shot spawned there is in step with the enemies and the Shell that fired it, and needs no fast-forward. That correction only matters for enemy bullets aimed at a player who sees their own Shell in the present; M2's only enemy is melee, so it waits for the first enemy that shoots (M3), which is when to build it in the engine if it proves general.
- **Tags:** networking, projectiles, scope
- **Status:** Approved by owner 2026-11-06.

## Shots over the network live in the projectiles kit, not in `pyguara.net`
- **Context:** Phase 4 projectile spawn events need `ProjectileSystem`; `tests/test_kit_layering.py` forbids core importing a kit.
- **Alternatives:** (a) a generic shot relay in `pyguara.net` with no kit dependency, leaving the game to wire it to its pool. (b) `pyguara.kits.projectiles.net`, depending on core `pyguara.net`, not imported by the kit's `__init__`.
- **Chose:** (b). The relay needs the pool's spawn and end hooks to be exact, and a single-player game still imports no networking.
- **Tags:** networking, layering, projectiles
- **Status:** Pending owner review.

## A predicted shot is matched by (slot, tick, index), not by an id the host assigns
- **Context:** M2 decision: a guest's own shots appear at once, the host decides hits.
- **Alternatives:** (a) the client sends a shot id in its command, which the host echoes. (b) Both sides derive the key from who fired, the command's tick, and the order within that tick.
- **Chose:** (b). Commands already name host ticks, so no command field or trust in a client-chosen id is needed. Cost: both sides must fire a tick's shots in the same order. A mismatch degrades visibly but safely (ghost removed after 30 ticks, or the host's copy shown late), and is counted.
- **Tags:** networking, prediction, projectiles
- **Status:** Pending owner review.

## The host sends a shot's end only when it stops early
- **Context:** clients must stop their copy where the host's stopped.
- **Alternatives:** (a) an end event for every shot. (b) Only for a hit, a wall or a clear; expiry is computed identically on both sides.
- **Chose:** (b). Halves the events for shots that miss, and the client's walls may not match the host's after quantisation, so walls are sent rather than recomputed.
- **Tags:** networking, bandwidth, projectiles
- **Status:** Pending owner review.

## Client shots advance on the delayed view's clock, not the frame's
- **Context:** first version used frame dt and drifted 11 px from the host over a 3 s flight under jitter.
- **Alternatives:** (a) frame dt. (b) the change in `ReplicationClient.render_tick` each frame.
- **Chose:** (b). Shots stay in step with the interpolated world they fly through. Own predicted shots move on the same clock, which runs at about real time.
- **Tags:** networking, interpolation, projectiles
- **Status:** Pending owner review.

## Callbacks whose result is ignored return `object`, not `None` (#394)
- **Context:** strict mypy refused `on_event=dispatcher.dispatch`, the documented call, since `dispatch` returns a bool.
- **Alternatives:** (a) change only `on_event`. (b) every net callback whose result is discarded, plus the kit's `EndHandler`.
- **Chose:** (b). The same trap waited in each of them. Callbacks whose result is read (`send`, `drop`, `HitHandler`) are unchanged.
- **Tags:** networking, typing
- **Status:** Pending owner review.

## Prediction names the tick being simulated, as `PredictionClient.advancing` (#395)
- **Context:** an own shot fired from inside `advance` needs the host tick, but one `step` can advance several and a replay re-runs past ones.
- **Alternatives:** (a) pass the tick to `PredictedBody.advance`, changing the protocol for every body. (b) the game counts advances itself from `tick` before stepping. (c) a read-only property valid during `advance`.
- **Chose:** (c). No protocol change and no game bookkeeping that mirrors engine internals.
- **Tags:** networking, prediction
- **Status:** Pending owner review.

## Own shots are numbered per advance, via `PredictionClient.advances` (#396)
- **Context:** a replay of the tick last fired on looked like more shots on that tick and showed twice.
- **Alternatives:** (a) the game passes each shot's index itself. (b) a monotonic advance counter on prediction, which `ProjectileClient` reads when given `prediction`.
- **Chose:** (b). The engine keeps owning the numbering both sides must agree on. Without `prediction` the old behaviour stays, for clients that fire outside prediction.
- **Tags:** networking, prediction, projectiles
- **Status:** Pending owner review.

## Reclaimer: skill readiness rides in the prediction state, not in snapshots
- **Context:** a guest must know when its skills are ready to show its own shots at once.
- **Alternatives:** (a) read the replicated, delayed `Energy`/`Loadout` and accept mispredictions. (b) predict them in `ShellPrediction`, with the host capturing the same tuple (11 movement values plus 2 and 2 per skill: 23 of the 32 allowed).
- **Chose:** (b). Exact, and corrected like position. Cost: a Shell with many more skills could reach the 32-value limit.
- **Tags:** reclaimer, networking, prediction
- **Status:** Pending owner review.

## Reclaimer: a guest's own shot stops at the enemy as drawn, on the delayed view
- **Context:** own shots fly in the present, enemies are drawn about 100 ms behind.
- **Alternatives:** (a) never stop own shots until the host's end arrives. (b) stop at the first enemy the guest draws in the way.
- **Chose:** (b). It matches what the player sees. The host still decides hits, so a drawn stop with no host hit is a cosmetic disagreement.
- **Tags:** reclaimer, networking, feel
- **Status:** Pending owner review.

## PyGuara: settle memory when the scenes being run change (#397)
- **Context:** full garbage collections walk everything a game loaded and stall a tick by 15-20 ms.
- **Alternatives:** (a) hook each of the scene manager's entry paths (switch, push, pop, layers, with or without transitions). (b) check once a frame, in `Application.step()`, whether the current scene's name or the layers changed. (c) leave it to games to call `gc.freeze()`.
- **Chose:** (b), on by default behind `PerformanceConfig.freeze_on_scene_change`, with `settle_memory()` public for loads the engine can't see. One check covers every path, and transitions settle only at the end because that's when the manager makes the target current. Cost: re-entering a scene under the same name isn't seen.
- **Tags:** pyguara, performance, application
- **Status:** Pending owner review.

## The default wgpu renderer fails without a GPU instead of falling back
- **Context:** phase 3 of `engine_completion_roadmap.md`, wgpu as the default `display.backend`. A machine with no usable GPU (no driver, a VM, a server) cannot open it.
- **Alternatives:** fall back to the pygame renderer with a warning; fail at startup with an error saying how to choose pygame.
- **Chose:** fail, with `NoGraphicsAdapterError` naming `display.backend = "pygame"` (the user's call). The renderers look different -- pygame has no lighting or post-processing -- so a silent switch would make the same game look different per machine, which the engine's no-silent-fallback rule exists to prevent. Only Rust's "no graphics adapter" failure is mapped; any other window failure propagates unchanged.
- **Tags:** graphics, config, bootstrap
- **Reviewed:** chosen by the user 2026-11-14.

## Scene service accessors look up on each read
- **Context:** phase 3 item 2 (ADR 0012), `Scene.application`, `scene_manager`, `ui_manager`, `input_manager`.
- **Alternatives:** resolve the four once in `resolve_dependencies()` and store them as attributes; look each up in `self.container` on every read.
- **Chose:** look up on read. Resolving eagerly would make every scene fail to resolve in a container that lacks one of the four (tests build such containers), and a copy taken at resolve time would miss a service a test substitutes later. A container `get` of a registered instance is a dict hit, and these are read in event handlers, not per entity.
- **Tags:** scene, di
- **Reviewed:** approved by the user 2026-11-14.

## Not-ready accessors raise `SceneNotReadyError(RuntimeError)`
- **Context:** the same accessors, read before `resolve_dependencies()` (typically from `__init__`).
- **Alternatives:** return `None` and type the accessors `X | None`; raise a plain `RuntimeError` as `start_coroutine` did; raise a named subclass of it.
- **Chose:** a named subclass. Optional types would push a `None` check into all ~100 call sites and invite a plausible wrong value, which AGENTS.md forbids; subclassing `RuntimeError` keeps `start_coroutine`'s existing callers working.
- **Tags:** scene, errors
- **Reviewed:** approved by the user 2026-11-14.

## Crash reporting is opt-in, by game name
- **Context:** roadmap phase 2, crash capture (`pyguara.crash`).
- **Alternatives:** install the hook automatically in `create_application()`, naming the folder after `display.title` or the engine; make the game call `install_crash_reporter(app_name)`.
- **Chose:** the explicit call, as `user_data_path` already does: the engine cannot invent the game's name, and a folder named "Pyguara Engine" shared by every game mixes their reports. An explicit call can also be made before `create_application()`, which is where startup failures such as `NoGraphicsAdapterError` happen; an automatic install inside it would miss anything raised earlier.
- **Tags:** crash, shipping, bootstrap
- **Reviewed:** approved by the user 2026-11-14.

## Facts reach the report through module-level notes
- **Context:** the report should say which renderer and GPU were running, which the hook, installed before the app exists, cannot ask for.
- **Alternatives:** pass the `Application` to the reporter; have the reporter search for a running app; let the engine `note(key, value)` facts as it learns them into a module dict the reporter reads.
- **Chose:** notes. They work before an application exists, let a game add its own (the level, a build id), and need nothing from the reporter but a dict. Bootstrap notes `renderer` and, on wgpu, `gpu`.
- **Tags:** crash, bootstrap
- **Reviewed:** approved by the user 2026-11-14.

## Only the main thread's crashes are reported, and Ctrl+C is not one
- **Context:** which exceptions the hook writes a report for.
- **Alternatives:** also hook `threading.excepthook`; report every `BaseException` that reaches `sys.excepthook`.
- **Chose:** main thread, `KeyboardInterrupt` skipped. A background thread's exception does not end the game, so reporting it as a crash would mislabel it and fill the 20-report limit with noise; Ctrl+C is the player stopping the game.
- **Tags:** crash
- **Reviewed:** approved by the user 2026-11-14.

## String tables are flat JSON per locale
- **Context:** localisation L1, `pyguara.i18n`, the format translators and the game write.
- **Alternatives:** gettext `.po` files (English text as the key); Mozilla Fluent `.ftl`; Android-style XML; one flat JSON object per locale, keys like `hud.salvage`, a plural entry being an object of CLDR forms.
- **Chose:** flat JSON. Python reads it with no dependency, Crowdin, Weblate and Lokalise all import it, a key survives the English text changing (gettext's does not), and plural forms are just an object. Nested namespaces were left out because a nested object would be ambiguous with a plural entry.
- **Tags:** i18n, data-format
- **Reviewed:** approved by the user 2026-11-15.

## Placeholders are plain names only, checked at load
- **Context:** the same; filling `{player}` and `{count}` in translated text.
- **Alternatives:** `str.format` as is; `string.Template` (`$name`); `str.format` restricted to `{name}` and `{name:spec}`, refusing attribute, index, positional, conversion and nested fields when the file loads.
- **Chose:** restricted `str.format`. Translation files come from outside the code, and unrestricted `format` can walk the attributes of a passed object (`{player.__class__}`). Keeping `{name:spec}` lets a translator format numbers (`{ratio:.0%}`); `$name` would lose that.
- **Tags:** i18n, security
- **Reviewed:** approved by the user 2026-11-15.

## A missing translation shows English; a missing English string raises
- **Context:** the same; what a lookup does when a key is absent.
- **Alternatives:** show the key itself; raise always; fall back to the source locale and log once per key and locale, but raise `MissingStringError` when the source has no such key.
- **Chose:** the split. A gap in a translation is expected mid-project and English is the readable answer; a key missing from English is code asking for text nobody wrote, and showing the key would be a plausible wrong value. A missing plural form falls back to `other`.
- **Tags:** i18n, errors
- **Reviewed:** approved by the user 2026-11-15.

## Plural rules are hand-transcribed from CLDR for the supported languages
- **Context:** the same; choosing `one`/`few`/`many`/`other` for a count.
- **Alternatives:** depend on Babel, which carries all of CLDR (tens of MB); transcribe the integer rules for the languages the engine supports and refuse any other.
- **Chose:** transcribe. Eleven small functions cover the ten target languages (plus Italian), tested against CLDR's examples; an unknown language is refused rather than given English's rule. Babel can replace them if the list grows.
- **Tags:** i18n, dependencies
- **Reviewed:** approved by the user 2026-11-15.

## Scenes translate with `self.tr(key, ...)`; other code takes the `Translator`
- **Context:** localisation L1; how game code reaches the translator.
- **Alternatives:** a module-level `tr()` bound to a global current translator, as gettext's `_()` is; `self.container.get(Translator)` only; a `Scene.translator` property in the ADR 0012 style plus a `Scene.tr()` shorthand, with systems and UI builders handed the `Translator`.
- **Chose:** the property and the shorthand. A global would make two applications in one process (as the tests run) share a language, and ADR 0012 already makes scene accessors the way in; `tr` is there because a translated screen calls it on nearly every line. A game with no locales folder gets a `RuntimeError` naming the folder, not a lookup failure.
- **Tags:** i18n, scene, di
- **Reviewed:** approved by the user 2026-11-15.

## The locale is chosen once at startup, from config, then the system
- **Context:** the same; which language a game starts in.
- **Alternatives:** require the game to choose; read only the config; read config, else the operating system's locale, narrowed to the closest available file (`pt-PT` to `pt-BR`, Chinese by script, else the source).
- **Chose:** config, then system, narrowed. A player sees their language without a settings screen, and a game on Steam overrides it with Steam's language (`locale_from_steam`). The folder is optional: without `locales/` no translator is registered, so a game that is not localised pays nothing.
- **Tags:** i18n, config, bootstrap
- **Reviewed:** approved by the user 2026-11-15.

## Fallback faces are engine-wide, set by the game, tried per character
- **Context:** localisation L2, drawing CJK text that Liberation Sans lacks.
- **Alternatives:** bundle Noto Sans CJK in the engine (about 16 MB per region and weight in the wheel); make fallbacks a per-font or per-label option; one engine-wide ordered list the game sets with `set_fallback_fonts()`, tried per character, which both renderers read.
- **Chose:** the engine-wide list set by the game. The game knows its languages and ships only the faces it needs; one list keeps the two renderers in agreement; the order is how a game picks Japanese or Chinese Han forms for the player's language. Single-face files only, because pygame opens fonts by path and cannot pick a face from a collection.
- **Tags:** i18n, text, fonts

## Line metrics stay the default face's when a fallback draws
- **Context:** the same; how tall a string with a CJK character is.
- **Alternatives:** take ascent and descent from every face in use, so a line grows when a CJK glyph appears; keep the default face's metrics always.
- **Chose:** the default face's. A label must not change height because of which characters it holds, and Noto Sans CJK's box fits inside Liberation's at the same size (ascent 0.88 em against 0.905, descent 0.12 against 0.21). Kerning applies only between glyphs of the same face.
- **Tags:** i18n, text, layout

## The pygame renderer splits text into runs using the native character maps
- **Context:** the same, on the software renderer, where SDL_ttf draws one file and does not report missing glyphs.
- **Alternatives:** parse `cmap` tables in Python; depend on fontTools; ask the extension's `NativeFace.covers()`, the same answer the wgpu path uses, and render each run with its own `pygame.font.Font` on the default face's baseline.
- **Chose:** the extension. The two renderers then agree on which face draws each character by construction, and with no fallbacks set the default face renders exactly as before, so existing pixel goldens are untouched. Without the extension, fallbacks are inert and one warning is logged.
- **Tags:** i18n, text, pygame

## CJK line breaking is a hand-written subset of UAX #14
- **Context:** localisation L3, wrapping Chinese and Japanese, which have no spaces between words.
- **Alternatives:** the full Unicode line-breaking algorithm through a Rust crate (`unicode-linebreak`) exposed by the extension; ICU through PyICU; break between CJK characters, between CJK and other text, and nowhere else, with the kinsoku tables for what may not start or end a line.
- **Chose:** the subset. It is what the ten target languages need (Korean and the rest wrap on spaces), it stays in the pure-Python layout that both renderers share and the tests drive with a fake measure, and it adds no dependency. The full algorithm can replace `break_offsets()` behind the same signature if Thai or Khmer, which need dictionaries, are ever added.
- **Tags:** i18n, text, layout

## Case changes take an engine-wide case language
- **Context:** the same; the design system's `uppercase` buttons, wrong in Turkish with `str.upper()`.
- **Alternatives:** pass a locale to every case change; read the translator's locale from the container where the case changes; one engine-wide case language in `pyguara.ui.text_case`, set from the locale.
- **Chose:** the engine-wide setting. A button's draw has no container, threading a locale through every widget would touch every call site, and a game has one text language at a time. Wiring it to `Translator`'s locale changes waits for L1 (#415) to merge; until then a game calls `set_case_language()`.
- **Tags:** i18n, text, ui
