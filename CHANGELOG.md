# Changelog

All notable changes to PyGuara will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.5.0] - 2026-09-09

This release is the output of a **systematic subsystem audit** (2026-09-06 →
2026-09-09): every Tier 1–4 subsystem got a code-and-architecture → tests →
docs → capability-gap pass, one subsystem at a time. ~50 PRs. Per-subsystem
detail, including what each pass found and why, is in `REFACTOR_STATE.md`.
Being Pre-Alpha, breaking changes ship without deprecation shims.

**Closed defect issues:** [#9](https://github.com/Wedeueis/pyguara/issues/9)
(pygame in the backend-agnostic core), [#23](https://github.com/Wedeueis/pyguara/issues/23)
(camera rotation ignored by the render path),
[#30](https://github.com/Wedeueis/pyguara/issues/30) (drifted physics guide
docs). Dozens of capability gaps found during the audit were opened as tracked
issues rather than fixed in place — #16, #19, #28, #37, #40, #43, #46, #49,
#51, #53, #55, #58, #61, #64–#73, #75.

### Removed
- **BREAKING: pygame is confined to `pyguara/graphics/backends/`, `pyguara/audio/backends/`, `pyguara/input/backends/`.** `application.py`, `input/manager.py`, `pyguara/tools/*` and `sandbox.py` no longer import it. (#9)
- **BREAKING: `Camera2D.rotation` removed.** It changed what `world_to_screen` reported but the render path never rotated. (#23)
- **BREAKING: `pyguara.dev.HotReloadManager`, `StatefulSystem`, `reload_system_class()` gone.** The Python-module hot-reload layer was never wired into the loop, ran on a background thread, and could not migrate state. `PollingFileWatcher` stays, now driving asset hot-reload.
- **BREAKING: the Dear ImGui editor (`pyguara/editor`) deleted** — it had never executed. Its useful parts were rebuilt as `UIRenderer`-drawn tools (see below).
- Dead parameters and attributes across subsystems (`Collider` `allow_rotation`, `PerformanceMonitor`'s unused `pygame.time.Clock`, and others named in `REFACTOR_STATE.md`).

### Changed
- **BREAKING: `Color` and `Rect` are no longer `pygame.Color`/`pygame.Rect` subclasses.** Plain backend-agnostic `@dataclass(slots=True)` value types in `pyguara.common.types`; only the pygame backend converts, via `graphics/backends/pygame/conversions.py`. Construction, equality, mutation and float→int truncation behave as before. `Color` gains `to_hsv()`/`from_hsv()` and named constants; `Rect` gains `colliderect()`, `contains()`, `inflate()`.
- **BREAKING: `Window.poll_events()` yields engine events**, not raw SDL structs — `QuitEvent`, `KeyDownEvent`, `KeyUpEvent`, `MouseButtonEvent`, `MouseMotionEvent`, `WindowResizeEvent`. `InputManager.process_event()` and every tool consume these. Key codes still pass through as SDL values, so bindings and replays are unchanged. (#9)
- **BREAKING: `Camera2D.world_to_screen` / `screen_to_world` / `get_view_bounds` take an optional `viewport`** and are now defined in terms of a single `screen_offset(viewport)` transform, shared with the batcher, particle system and light pass. (#23)
- **BREAKING: character movement is `CharacterMover` / `CharacterBody`**, not hand-rolled kinematic `RigidBody` sync. `PhysicsSystem` uses the pull pattern (queries entities itself).
- `ErrorHandlingStrategy` hoisted to a single `pyguara.errors` (was defined twice, in `di` and `events`, with incompatible members).
- Ruff `target-version` → `py312`; `UP`/`B`/`I`/`SIM` rule sets enabled; legacy `typing.Dict`/`Optional[X]` modernized engine-wide.
- Every subsystem package now exports a curated `__all__`.
- Frame timing goes through a new `Clock` protocol (below) instead of `pygame.time.Clock` directly.

### Added
- **`Clock` protocol** (`pyguara.application.clock`) — `FixedClock` for deterministic headless/test runs, `PygameClock` under the backend. Resolved from DI. (#9)
- **`WindowResizeEvent` now has a publisher** — the window boundary translates SDL `VIDEORESIZE`; it was defined but never dispatched.
- **Physics: spatial queries** (`raycast_all`, `point_query`, `overlap_box`/`overlap_box_all`, `overlap_circle`, `region_query`), per-body sleeping, configurable solver substeps, and a rebuilt trigger + joint layer (`TriggerVolume`, `EntityTags`, pin/spring/slider joints).
- **In-engine dev tools** on the engine's own `UIRenderer` (F12 master toggle, F1–F9): performance, entity inspector, event monitor, physics debugger, hierarchy, config inspector, assets browser, shortcuts panel, and an F9 transform gizmo. Tool lifecycle hooks (`Tool.on_removed()`, `ToolManager.unregister_tool()`/`clear()`).
- **ECS:** `Entity.get_all_components()`, `EntityManager.clear()`, `subscribe_entity_removed()`/`unsubscribe_entity_removed()` (multi-observer), `StrictComponent` (rejects logic methods at class-definition time).
- **Resources:** `ResourceManager.reload()`, `iter_indexed()`, `iter_cached()`.
- **Render-pipeline snapshot tests** (Syrupy) recording the backend call stream `RenderSystem.flush()` produces — deterministic, no rasterisation. `tests/integration/test_demos_render.py` asserts each demo draws a non-flat frame.
- `tools/agent_view.py` — boots a demo headlessly, drives it, writes PNG frames, for agent visual inspection.
- `pyguara.__version__` (via `importlib.metadata`).

### Fixed
- **Physics collision tunnelling** — fast bodies passed through thin static geometry; solver substepping added. (#24, #25)
- **Blank window under vsync** — SDL silently promoted the display to an OpenGL surface that never presented software blits; vsync is dropped with a warning when that happens. (#21)
- **Batcher counted the viewport origin twice** — invisible at fullscreen, displaced everything under a letterboxed viewport. Batcher and particle system unified on `Camera2D.screen_offset()`. (#22)
- `Camera2D` accepted zero/negative zoom and then produced coordinates six orders of magnitude out or raised `ZeroDivisionError`; the setter now rejects non-positive values.
- `ToolManager` double-ran a tool on repeat registration (twice per frame); `PerformanceMonitor` fed a `0.0` FPS sample on any `dt <= 0`, dragging the rolling average.
- `InputContext` was inert end to end (no setter); gamepad identity was keyed on the pygame device index instead of the SDL instance id, so unplugging a non-last pad flagged the wrong one.
- `pyguara atlas` silently dropped a sprite on a filename-stem collision and cropped a sprite wider than the atlas; both now raise.
- **Docs that described APIs which never existed** — `pyguara.log.config.setup_logging`, an entire `pyguara.error` hierarchy, `IPhysicsEngine.get_body`, `Collider(radius=)`, `EntityManager.add_component`. `tests/test_docs_api.py` now guards every `pyguara`-dotted reference under `docs/`. (#30)
- Roughly sixty smaller correctness fixes across every subsystem — see the `REFACTOR_STATE.md` iteration log.

## [0.4.0] - 2026-06-03

### Added
- **Click-Based build CLI Command**: Added `pyguara build` using PyInstaller to package games into standalone executable directories/binaries, including automatic asset mapping.
- **Headless Validation Suite**: Added `games/validate_demos.py` to automatically run and test all demo games for 30 ticks under headless SDL drivers (`dummy` driver setup).
- **Zero to Hero Tutorial Guide**: Created the comprehensive walkthrough guide `docs/guides/zero_to_hero.md` explaining booting, ECS, inputs, physics, UI, and compilation.
- **Compiler CLI Unit Tests**: Created unit tests in `tests/test_build_tool.py` for Click CLI and PyInstaller argument builders.

### Fixed
- **Platformer System Crash**: Fixed crash in `PlatformerSystem` when handling entities lacking a `Collider` component.
- **Headless Test Key Modifiers Crash**: Wrapped `pygame.key.get_mods()` in `pyguara/input/manager.py` with try-except block to support headless/non-windowed testing environments.
- **Broken Documentation References**: Removed non-existent brand guide links in `index.md`.

### Removed
- **Obsolete Scene Files**: Removed `pyguara/app_scene.py` (legacy scene class) and duplicate `pyguara/scene/__init__py` (incorrect extension file).

### Added - Advanced Graphics Pipeline (P1-011)

#### Multi-Pass Render Graph
- New `RenderGraph` orchestrator for multi-pass rendering
- `FramebufferManager` for FBO lifecycle management (create/resize/release)
- `BaseRenderPass` abstract class for render pass implementations
- New protocols: `IFramebuffer`, `IRenderPass` in `graphics/protocols.py`

#### Render Passes
- `WorldPass`: Renders sprites/geometry to world framebuffer
- `LightPass`: Renders dynamic lights with additive blending to light map
- `CompositePass`: Multiplies world texture by light map for final lit scene
- `PostProcessPass`: Executes post-processing effect stack
- `FinalPass`: Blits composed result to screen via fullscreen quad

#### Material System
- `Material` dataclass combining shader, texture, and uniforms
- `Shader` wrapper with uniform caching
- `ShaderCache` for avoiding redundant shader compilation
- `DefaultMaterialManager` with inline default shaders
- Material-based batching: sort by `(layer, material_id, z_index)`
- Backward compatible: sprites without materials use default

#### 2D Dynamic Lighting
- `LightSource` component with color, radius, intensity, and falloff
- `AmbientLight` component for global scene illumination
- `LightingSystem` queries and manages light entities
- Radial gradient lights with configurable quadratic falloff
- Light map compositing with ambient color base

#### Post-Processing Effects
- `PostProcessStack` with ping-pong FBO management
- `PostProcessEffect` base class for screen-space effects
- `BloomEffect`: threshold extraction, Gaussian blur, additive composite
- `VignetteEffect`: edge darkening with configurable radius/softness
- Chainable effects with enable/disable per effect

#### GLSL Shaders
- `fullscreen_quad.vert`: Generates fullscreen quad via gl_VertexID
- `blit.frag`: Simple texture copy
- `light.vert` / `light.frag`: Radial gradient light rendering
- `composite.frag`: World * lightmap multiplication
- `bloom_threshold.frag`: Bright pixel extraction
- `blur.frag`: Separable 9-tap Gaussian blur
- `bloom_composite.frag`: Additive bloom compositing
- `vignette.frag`: Edge darkening effect

#### Pygame Backend Graceful Degradation
- `PygameLightingSystem`: No-op stub (renders fully lit)
- `PygamePostProcessStack`: Pass-through stub
- `PygameFramebufferManager`: Returns None for all FBOs
- `PygameRenderGraph`: No-op execution
- Game code using advanced features runs unchanged on Pygame

### Changed

#### Application Render Loop
- `Application` now uses `RenderGraph` when available
- Falls back to direct renderer calls when RenderGraph not registered
- UI rendering happens after render graph execution

#### Render Pipeline
- `RenderCommand` and `RenderBatch` now include optional `material` field
- Batching sorts by material ID in addition to layer and z_index
- `Sprite`, `Geometry`, and `Particle` classes have `material` attribute

---

## [0.3.2] - 2026-01-25

### Added

#### Prefab System
- New `pyguara.prefabs` module for data-driven entity creation
- `PrefabData`: template definition with components and metadata
- `PrefabFactory`: creates entities from templates with override support
- `PrefabLoader`: loads prefabs from JSON files
- `PrefabCache`: caches loaded prefabs for performance
- `ComponentRegistry`: maps component names to classes for serialization
- Inheritance support via 'extends' field for prefab composition
- Deep merge for partial component overrides

#### Replay System
- New `pyguara.replay` module for deterministic input recording/playback
- `ReplayRecorder`: records input events with frame-accurate timestamps
- `ReplayPlayer`: plays back recorded input deterministically
- `ReplaySerializer`: saves/loads replays with optional compression
- Seed support for deterministic random state reproduction
- Event handlers for custom playback integration
- Pause/resume and seek functionality

#### Development Tools
- New `pyguara.dev` module for faster development iteration
- `FileWatcher`: monitors files for changes via polling
- `HotReloadManager`: coordinates Python module reloading
- `StatefulSystem` protocol for systems that preserve state across reloads
- `reload_system_class()`: reloads a system while preserving its state

#### Audio Components
- `AudioSource` component: persistent audio with play/stop/loop control
- `AudioListener` component: marks listener position for spatial audio
- `AudioEmitter` component: one-shot fire-and-forget audio events
- `AudioSourceSystem`: processes audio components each frame
- Spatial audio support with distance-based attenuation
- Automatic clip caching for performance

#### Input Rebinding
- Runtime rebinding support in `KeyBindingManager`
- `ConflictResolution` strategies: ERROR, SWAP, UNBIND, ALLOW
- Reverse mapping for fast action → bindings lookup
- Serialization/deserialization for persisting user preferences
- New types: `ConflictResolution`, `RebindResult`, `BindingConflict`

#### ECS Improvements
- `Archetype` class for cache-friendly component storage
- `ArchetypeGraph` for tracking component transitions
- Parallel arrays for improved iteration performance
- Swap-and-pop removal for O(1) entity deletion

#### Lifecycle Improvements
- `cleanup()` method added to `IPhysicsEngine` protocol
- `cleanup()` method added to `SceneManager`
- `cleanup()` method added to `PhysicsSystem`

### Changed

#### Application Lifecycle
- Game loop now wrapped in try/except/finally for robust cleanup
- `KeyboardInterrupt` handled gracefully
- Critical errors logged with stack traces before shutdown
- Cleanup guaranteed even with `sys.exit()`

#### Scene Serializer
- Refactored to use `ComponentRegistry` instead of hardcoded component map
- Supports custom components via registry
- Fallback to legacy deserialization for complex types

#### Event Protocol
- `Event` protocol now uses class attributes instead of properties
- Simpler implementation for dataclass-based events

### Tests
- All 1018 tests passing (up from 887 in v0.3.1)
- New test files:
  - `test_input_rebinding.py` (23 tests)
  - `test_audio_components.py` (29 tests)
  - `test_prefab.py` (18 tests)
  - `test_replay.py` (25 tests)
  - `test_hot_reload.py` (36 tests)

---

## [0.3.1] - 2026-01-20

### Added

#### UIRenderer Protocol Enhancements
- Added `width` parameter to `draw_circle()` for outline support
- Added `draw_polygon()` method for shape rendering
- Both `PygameUIRenderer` and `GLUIRenderer` updated with new methods

#### Test Coverage Improvements
- Added 57 comprehensive MetaLoader tests covering:
  - TextureMeta, AudioMeta, SpritesheetMeta dataclasses
  - Type inference from file extensions
  - Caching behavior and roundtrip integrity
  - Error handling (invalid JSON, missing files, unknown types)

### Changed

#### Backend-Agnostic Debug Tools
- Refactored `PhysicsDebugger` to use UIRenderer protocol instead of direct pygame access
- Refactored `TransformGizmo` to use UIRenderer protocol methods
- Debug tools now work with any renderer backend (Pygame, ModernGL)

### Documentation
- Updated v0.3.0 assessment document with all issues resolved
- Marked all beta blockers as complete
- Updated test coverage gaps status

### Tests
- All 887 tests passing (up from 742 in v0.3.0)
- New test files: `test_meta.py` (57 tests)
- Previous additions: `test_tools.py`, `test_scene_serializer.py`, `test_spatial_audio.py`

---

## [0.3.0] - 2026-01-18

### Added - ModernGL Rendering Backend & P3 Polish 🚀

#### P1-010: ModernGL Rendering Backend
- Implemented GPU-accelerated rendering with OpenGL 3.3+ Core Profile
- Hardware instancing for efficient batch rendering (10,000+ sprites at 60 FPS)
- New `PygameGLWindow` backend for OpenGL context management
- New `ModernGLRenderer` with instanced sprite rendering
- New `GLTexture` and `GLTextureFactory` for GPU texture management
- New `GLTextureLoader` for loading textures to GPU
- New `GLUIRenderer` with hybrid pygame/OpenGL UI compositing
- GLSL shaders for instanced sprite rendering (`sprite.vert`, `sprite.frag`)
- Orthographic projection with Y-inverted coordinates (pygame compatibility)
- Alpha blending support (SRC_ALPHA, ONE_MINUS_SRC_ALPHA)

#### Backend Selection System
- Added `RenderingBackend` enum to `WindowConfig` (PYGAME, MODERNGL)
- Backend selection in bootstrap based on configuration
- Seamless switching between pygame and ModernGL renderers

#### TextureFactory Protocol
- Added `TextureFactory` protocol for backend-agnostic texture creation
- Implemented `PygameTextureFactory` for pygame backend
- Implemented `GLTextureFactory` for ModernGL backend
- Refactored `SpriteSheet` to use Pillow instead of pygame
- Added `SpriteSheet.from_image()` class method for in-memory images

#### P2-012: Logging Standardization
- Replaced all `print()` calls in library code with proper `logging`
- Added loggers to: window, animation, audio, tools, editor, headless renderer
- Consistent log levels (DEBUG for internal ops, INFO for lifecycle, ERROR for failures)

#### Error Message Quality Pass
- Added `exc_info=True` to all exception handlers for stack traces
- Improved error messages with contextual information
- Enhanced config manager error messages with file paths
- Enhanced persistence manager error messages with keys
- Enhanced physics backend error messages with type information

### Changed
- `UIRenderer` protocol now includes `present()` method for GL compositing
- `Application` and `Sandbox` now call `ui_renderer.present()` in render loop
- Improved import organization in editor modules

### Dependencies
- Added `moderngl>=5.8.0` for GPU rendering
- Added `numpy>=1.26.0` for efficient data packing

### Tests
- All 742 tests passing
- Full type checking compliance (mypy)
- Code quality passing (ruff)

### Documentation
- Updated logging-refactor.md with completion status
- Updated product-enhancement-proposal.md to Phase 3

---

## [0.2.0] - 2026-01-10

### Added - All P0 Critical Issues Resolved (7/7 Complete) 🎉

#### P0-001: Component Removal Tracking (ECS)
- Added component removal tracking in EntityManager
- Entities now properly clean up component index when components are removed
- Fixed potential memory leaks from orphaned component references

#### P0-002: DIScope Public API (DI)
- Added public `get()` method to DIScope class
- Scoped services can now be resolved within scope context
- Improved scope lifecycle management

#### P0-003: UI Event Type Enum (UI)
- Created UIEventType enum for type-safe UI events
- Replaced magic strings with structured event types
- Enhanced UI event handling consistency

#### P0-004: Resource Memory Leak (Resources)
- Implemented reference counting for resources
- Added automatic unloading of unused resources
- Added `unload()` method for manual resource cleanup
- Fixed memory leaks in long-running applications

#### P0-005: Error Handling Strategy (Events/DI)
- Added ErrorHandlingStrategy enum (LOG, RAISE, IGNORE)
- Configurable error handling in EventDispatcher
- Configurable error handling in DIContainer
- Enhanced error messages with full context and stack traces
- Default fail-fast behavior for development

#### P0-006: Gamepad Support (Input)
- Implemented comprehensive GamepadManager class
- Added GamepadButton enum (17 buttons: A, B, X, Y, bumpers, triggers, D-pad)
- Added GamepadAxis enum (6 axes: left stick, right stick, triggers)
- Hot-plug detection for controller connect/disconnect
- Multi-controller support (4+ simultaneous controllers)
- Configurable deadzone for analog inputs
- Rumble/vibration support (platform-dependent)
- Event-driven and polling APIs
- 9 comprehensive gamepad tests

#### P0-007: Audio System (Audio)
- Implemented AudioManager for high-level audio coordination
- Enhanced IAudioSystem protocol with 9 new methods
- Three-level volume control (Master → Category → Per-Sound)
- Complete playback control (play, stop, pause, resume)
- Channel management with ID tracking for SFX
- Looping support (infinite and finite)
- Music streaming from disk
- Fade in/out support for music transitions
- 32 simultaneous sound channels
- Resource manager integration
- 23 comprehensive audio tests

### Changed
- Enhanced EventDispatcher with error handling
- Enhanced DIContainer with error handling
- Improved ResourceManager with reference counting
- Updated InputManager with GamepadManager integration
- Enhanced PygameAudioSystem with volume hierarchy

### Tests
- Added 169 new tests across all modules
- All tests passing (ECS, DI, Events, Resources, Input, Audio, UI)
- Full type checking compliance (mypy)
- Code quality passing (ruff)

### Documentation
- Added 7 implementation plan documents (.github/IMPLEMENTATION_P0-*.md)
- Added PHASE1_SETUP_COMPLETE.md
- Updated Product Enhancement Proposal
- Added comprehensive API examples

### Performance
- Gamepad polling: < 0.1ms per frame
- SFX playback: < 0.1ms (cached in memory)
- Resource cleanup: Automatic reference counting

## [0.1.0] - 2026-01-05

### Initial Release
- Core ECS (Entity-Component-System) architecture
- Dependency Injection container
- Event dispatcher system
- Basic rendering pipeline (pygame-ce backend)
- Physics integration (pymunk)
- Input management (keyboard, mouse)
- Basic audio stub
- Resource management
- UI system with components
- Scene management
- Configuration system

---

[0.4.0]: https://github.com/wedeueis/pyguara/compare/v0.3.2...v0.4.0
[0.3.2]: https://github.com/wedeueis/pyguara/compare/v0.3.1...v0.3.2
[0.3.1]: https://github.com/wedeueis/pyguara/compare/v0.3.0...v0.3.1
[0.3.0]: https://github.com/wedeueis/pyguara/compare/v0.2.0...v0.3.0
[0.2.0]: https://github.com/wedeueis/pyguara/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/wedeueis/pyguara/releases/tag/v0.1.0
