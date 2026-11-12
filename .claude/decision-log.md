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
