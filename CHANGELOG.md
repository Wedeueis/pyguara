# Changelog

All notable changes to PyGuara will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.4.0] - 2026-01-26

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
