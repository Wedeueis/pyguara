# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

PyGuara is a modern, modular 2D game engine for Python 3.12+ featuring:
- Performance-optimized Entity-Component-System (ECS) architecture
- Native Dependency Injection (DI) container
- Decoupled event-driven design
- Backend-agnostic rendering pipeline (currently pygame-ce)
- Integrated physics (pymunk), AI (FSM, steering behaviors), and UI systems

**Status**: Pre-Alpha - APIs are subject to change

## Development Commands

### Environment Setup
```bash
# Install dependencies (recommended)
uv sync

# Or using pip
pip install -e .[dev]
```

### Testing
```bash
# Run all tests
pytest

# Run specific test markers
pytest -m unit                    # Unit tests only
pytest -m integration            # Integration tests only
pytest -m performance            # Performance/benchmark tests
pytest -m slow                   # Slow running tests
pytest -m cli                    # CLI system tests

# Run specific test file
pytest tests/test_ecs.py

# Run with coverage
pytest --cov=pyguara --cov-report=html
```

### Code Quality
```bash
# Run linter
ruff check .

# Auto-fix linting issues
ruff check --fix .

# Format code
ruff format .

# Type checking
mypy pyguara

# Pre-commit hooks (runs ruff, mypy, and other checks)
pre-commit run --all-files
```

### Running the Engine
```bash
# Run default example scene
python main.py
```

## Architecture Overview

### Core Design Principles

**1. Protocol-Based Decoupling**
PyGuara uses Protocol classes (structural subtyping) extensively to decouple interfaces from implementations. Key protocols include:
- `IRenderer` and `UIRenderer` for rendering backends (pyguara/graphics/protocols.py)
- `IPhysicsEngine` and `IPhysicsBody` for physics backends (pyguara/physics/protocols.py)
- `Event` for event system (pyguara/events/protocols.py)
- `Renderable` for anything that can be drawn

**2. Dependency Injection**
The DI container (pyguara/di/container.py) uses reflection-based auto-wiring:
- Automatically resolves constructor dependencies via type hints
- Supports three lifetimes: SINGLETON (shared app-wide), TRANSIENT (new instance), SCOPED (shared within context)
- Detects circular dependencies at runtime
- Application bootstrap (pyguara/application/bootstrap.py) handles all core service registration

**3. Entity-Component-System (ECS)**
- `EntityManager` uses **Inverted Indexes** for O(1) component queries (ComponentType -> Set[EntityID])
- Components are pure data classes, typically dataclasses inheriting from `BaseComponent`
- Query entities with: `entity_manager.get_entities_with(Transform, RigidBody)`
- Entities support dynamic attribute access (e.g., `entity.transform`) via `__getattr__` caching

**4. Event-Driven Communication**
- `EventDispatcher` provides synchronous (`dispatch()`) and async (`queue_event()`) event handling
- Queued events are processed at frame start from background threads
- Supports handler priority and filtering
- Events are typically dataclasses implementing the `Event` protocol

### Module Organization

```
pyguara/
├── ecs/              # Entity-Component-System core
│   ├── entity.py     # Entity class with dynamic component access
│   ├── component.py  # BaseComponent class
│   └── manager.py    # EntityManager with inverted indexing
├── di/               # Dependency Injection container
│   └── container.py  # DIContainer with auto-wiring
├── events/           # Event dispatching system
│   └── dispatcher.py # EventDispatcher with queue support
├── application/      # Application lifecycle
│   ├── application.py  # Main game loop
│   ├── bootstrap.py    # DI container setup
│   └── sandbox.py      # Development tools
├── scene/            # Scene management
│   ├── base.py       # Scene abstract base class
│   ├── manager.py    # SceneManager for transitions
│   └── serializer.py # Scene persistence
├── graphics/         # Rendering pipeline
│   ├── protocols.py  # Renderable, IRenderer, UIRenderer protocols
│   ├── backends/     # Backend implementations (pygame)
│   └── window.py     # Window abstraction
├── physics/          # Physics integration
│   ├── protocols.py  # IPhysicsEngine, IPhysicsBody protocols
│   └── backends/     # Backend implementations (pymunk)
├── input/            # Input management
├── ui/               # UI system with layout engine
├── ai/               # AI systems (FSM, steering, pathfinding)
├── resources/        # Resource loading and management
├── persistence/      # Save/load system
├── config/           # Configuration management
├── editor/           # In-engine editor tools
└── common/           # Shared types (Vector2, Color, Rect)
```

### Key Architectural Patterns

**Scene Lifecycle**
1. Application creates Scene with EventDispatcher
2. SceneManager calls `scene.resolve_dependencies(container)` to inject DI container
3. Scene's `on_enter()` is called when activated
4. Scene's `update(dt)` is called each frame
5. Scene's `render()` is called each frame (may be deprecated in favor of RenderSystem)
6. Scene's `on_exit()` is called when switching away

**Application Lifecycle**
```python
# Bootstrap creates and wires all services
app = create_application()  # or create_sandbox_application()

# Create scene (gets EventDispatcher from container)
scene = MyScene("scene_name", event_dispatcher)

# Run (handles scene registration and main loop)
app.run(scene)
```

**Component Access Patterns**
```python
# EntityManager query
for entity in entity_manager.get_entities_with(Transform, Sprite):
    transform = entity.get_component(Transform)
    sprite = entity.get_component(Sprite)
    # OR use cached attribute access:
    # transform = entity.transform

# Adding components
entity.add_component(Transform(position=Vector2(100, 100)))
entity.add_component(Sprite(texture_path="assets/sprite.png"))
```

**Rendering Architecture**
- Scenes submit `Renderable` objects to the renderer
- `IRenderer` handles world/game rendering
- `UIRenderer` handles UI overlay rendering
- Backend implementations (e.g., `PygameBackend`) handle actual draw calls
- Supports Z-ordering and batching for performance

**Physics Integration**
- Physics engine (IPhysicsEngine) is registered as singleton in DI
- Entities with physics have a `RigidBody` component
- Physics updates happen in `Application._update()` before scene update
- Collision callbacks use the event system

## Important Implementation Notes

### Testing
- Tests are in `tests/` with separate `tests/integration/` for integration tests
- Use pytest markers to categorize tests (unit, integration, performance, etc.)
- Visual regression tests use Syrupy snapshots in `tests/visual/snapshots/`
- Conftest fixtures are in `tests/conftest.py`

### Type Checking
- Mypy strict mode is enabled for the `pyguara/` package
- Tests are excluded from type checking
- pygame modules have `ignore_missing_imports = true`
- All new code should include type hints for parameters and return types

### Code Style
- Line length: 88 characters (Black style)
- Use double quotes for strings
- Ruff handles linting and formatting
- Pre-commit hooks enforce code quality

### Common Gotchas

1. **EntityManager Indexing**: The component index is automatically updated when components are added via `Entity.add_component()`. Direct manipulation of `entity._components` will break indexing.

2. **Event Queue Threading**: Use `queue_event()` instead of `dispatch()` when emitting events from background threads (e.g., resource loaders, network callbacks).

3. **Scene DI Access**: Scenes must call `self.container.get(SomeService)` only after `resolve_dependencies()` has been called (typically in or after `on_enter()`).

4. **Protocol vs ABC**: This codebase prefers `Protocol` (structural subtyping) over `ABC` (nominal subtyping) for interfaces to avoid tight coupling.

5. **Renderer Decoupling**: Game code should never import pygame directly. Use protocols and DI to access rendering services.

### Current Development Focus

Based on the backlog (docs/dev/backlog/TODO.md):
- Removing pygame imports from game scenes in favor of abstracted services
- Implementing a `SystemManager` to automate Physics/AI/Animation execution
- Optimizing component iteration patterns
- Improving batching and multi-camera support

### Python Version Requirements
- Minimum: Python 3.12
- Uses modern Python features (match/case, type hints, Protocol, dataclasses)
