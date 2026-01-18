# Changelog

All notable changes to PyGuara will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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

[0.3.0]: https://github.com/wedeueis/pyguara/compare/v0.2.0...v0.3.0
[0.2.0]: https://github.com/wedeueis/pyguara/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/wedeueis/pyguara/releases/tag/v0.1.0
