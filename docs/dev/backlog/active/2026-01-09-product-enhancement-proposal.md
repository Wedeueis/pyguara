# Product Enhancement Proposal (PEP-2026.01)

## PyGuara Game Engine - Roadmap to Beta

**Document Version:** 1.2
**Date:** January 11, 2026
**Author:** Comprehensive Engine Review Committee
**Status:** ACTIVE - Phase 2 (Weeks 4-5) Complete

---

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [Current State Assessment](#2-current-state-assessment)
3. [Strategic Priorities](#3-strategic-priorities)
4. [Implementation Roadmap](#4-implementation-roadmap)
5. [Dependency Map](#5-dependency-map)
6. [Architecture & Style Guide](#6-architecture--style-guide)
7. [Repository Policies](#7-repository-policies)
8. [Implementation Specifications](#8-implementation-specifications)
9. [Quality Gates & Acceptance Criteria](#9-quality-gates--acceptance-criteria)

---

## 1. Executive Summary

### 1.1 Current Status

- **Version:** Alpha (Phase 1 Complete)
- **Codebase:** ~11,500 lines across 115+ files
- **Overall Grade:** A- (Excellent architecture, core systems stable)
- **Production Readiness:** 45% (suitable for prototypes and small games)

### 1.2 Vision Statement

Transform PyGuara from a pre-alpha engine with excellent architecture into a **production-ready, Python-native 2D game engine** suitable for indie game development, educational projects, and rapid prototyping.

### 1.3 Success Criteria (Beta Release)

- ✅ All P0 (Critical) issues resolved
- ✅ Feature completeness ≥ 70% across all systems
- ✅ Test coverage ≥ 80%
- ✅ At least 3 complete example games
- ✅ Full API documentation
- ✅ Performance benchmarks published

### 1.4 Timeline Estimate

- **Phase 1 (Critical Fixes):** 2-3 weeks
- **Phase 2 (Core Features):** 6-8 weeks
- **Phase 3 (Polish & Docs):** 4-6 weeks
- **Total to Beta:** ~3-4 months with full-time focus

---

## 2. Current State Assessment

### 2.1 System Health Matrix

| System | Architecture | Completeness | Testing | Documentation | Priority |
|--------|--------------|--------------|---------|---------------|----------|
| ECS Core | ⭐⭐⭐⭐⭐ | 95% | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | P1 |
| DI Container | ⭐⭐⭐⭐⭐ | 90% | ⭐⭐⭐⭐ | ⭐⭐⭐⭐ | P1 |
| Event System | ⭐⭐⭐⭐⭐ | 90% | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | P1 |
| Graphics/Rendering | ⭐⭐⭐⭐ | 70% | ⭐⭐⭐ | ⭐⭐⭐⭐ | P0 |
| Physics | ⭐⭐⭐⭐ | 60% | ⭐⭐⭐ | ⭐⭐⭐ | P1 |
| Input | ⭐⭐⭐⭐½ | 85% | ⭐⭐⭐⭐ | ⭐⭐⭐⭐ | P1 |
| Audio | ⭐⭐⭐⭐ | 80% | ⭐⭐⭐⭐ | ⭐⭐⭐⭐ | P1 |
| UI | ⭐⭐⭐⭐ | 65% | ⭐⭐⭐ | ⭐⭐⭐⭐ | P1 |
| AI | ⭐⭐⭐ | 30% | ⭐⭐ | ⭐⭐ | P2 |
| Scene Mgmt | ⭐⭐⭐⭐ | 75% | ⭐⭐⭐ | ⭐⭐⭐ | P1 |
| Resources | ⭐⭐⭐⭐⭐ | 85% | ⭐⭐⭐⭐ | ⭐⭐⭐⭐ | P1 |
| Persistence | ⭐⭐⭐ | 50% | ⭐⭐ | ⭐⭐ | P2 |
| Config | ⭐⭐⭐⭐ | 80% | ⭐⭐⭐⭐ | ⭐⭐⭐ | P2 |
| Editor | ⭐⭐⭐ | 25% | ⭐ | ⭐ | P3 |

**Priority Levels:**

- **P0**: Blocking issues - cannot ship without
- **P1**: High priority - critical for good UX
- **P2**: Medium priority - nice to have
- **P3**: Low priority - future enhancements

### 2.2 Critical Issues (Resolved)

#### P0-001: Component Removal Tracking (ECS) - ✅ RESOLVED

- **Status:** Fixed. `EntityManager` now uses bidirectional callbacks to sync indexes.
- **Impact:** Query consistency guaranteed.

#### P0-002: DIScope Public API Missing (DI) - ✅ RESOLVED

- **Status:** Fixed. `DIScope.get()` implemented as public API.
- **Impact:** Scoped services fully usable.

#### P0-003: String-Based UI Events (UI) - ✅ RESOLVED

- **Status:** Fixed. Refactored to use `UIEventType` Enum.
- **Impact:** Type-safe UI event handling.

#### P0-004: Resource Memory Leak (Resources) - ✅ RESOLVED

- **Status:** Fixed. Reference counting and auto-unloading implemented.
- **Impact:** Stable memory usage in long sessions.

#### P0-005: Event Error Swallowing (Events/DI) - ✅ RESOLVED

- **Status:** Fixed. Configurable `ErrorHandlingStrategy` added to both systems.
- **Impact:** Greatly improved debuggability.

#### P0-006: No Gamepad Support (Input) - ✅ RESOLVED

- **Status:** Fixed. `GamepadManager` implemented with hot-plug support.
- **Impact:** Console-style games possible.

#### P0-007: Audio System Stub Only (Audio) - ✅ RESOLVED

- **Status:** Fixed. Full `AudioManager` with music/SFX support implemented.
- **Impact:** Immersive audio experience enabled.

---

## 3. Strategic Priorities

### 3.1 North Star Metrics

1. **Developer Productivity**: Time from idea to playable prototype < 2 hours
2. **Performance**: 10,000+ entities at 60 FPS on mid-range hardware
3. **Stability**: Zero crashes in 8+ hour playtesting sessions
4. **Learning Curve**: Complete tutorial game in < 4 hours (for Python devs)

### 3.2 Target Audience

**Primary:**

- Python developers wanting to make 2D games
- Educational institutions teaching game development
- Game jam participants
- Indie developers prototyping concepts

**Secondary:**

- Hobbyists learning game engine architecture
- Developers porting existing Pygame projects

### 3.3 Competitive Positioning

**Differentiation:**

- **vs Pygame**: High-level ECS architecture, batteries included
- **vs Arcade**: Better separation of concerns, enterprise patterns
- **vs Godot (Python)**: Pure Python, simpler for Python-first devs
- **vs Unity**: Open source, Python-native, educational focus

**Target Niche:** *"The professional Python developer's choice for 2D games"*

---

## 4. Implementation Roadmap

### Phase 1: Critical Fixes & Stability (Weeks 1-3) - ✅ COMPLETE

**Goal:** Resolve all P0 issues, achieve zero known crashes

#### Week 1: Core System Fixes

- [x] **P0-001**: Implement component removal tracking
- [x] **P0-002**: Add DIScope.get() public API
- [x] **P0-003**: Create UIEventType enum
- [x] **P0-005**: Configurable error handling strategy
- [x] Test coverage for all fixes ≥ 90%

#### Week 2: Input & Audio Foundation

- [x] **P0-006**: Gamepad support (SDL2 backend)
- [x] **P0-007**: Audio system implementation (pygame.mixer wrapper)
- [x] Input action mapping system
- [x] Audio manager with spatial audio support

#### Week 3: Resource Management & Testing

- [x] **P0-004**: Resource reference counting and unloading
- [x] Memory leak detection in tests
- [x] Integration test suite expansion
- [x] Performance benchmarking harness

**Phase 1 Exit Criteria:**

- ✅ All P0 issues closed
- ✅ Test coverage ≥ 75%
- ✅ Zero critical bugs in issue tracker
- ✅ CI/CD pipeline green

---

### Phase 2: Feature Completeness (Weeks 4-11) - 🚀 IN PROGRESS

**Goal:** Bring all systems to production-ready state

#### Weeks 4-5: Rendering & Animation - ✅ COMPLETE

- [x] Automatic sprite batching implementation
- [x] Sprite atlas generation tool
- [x] Animation state machine
- [x] Particle system enhancements
- [x] Camera zoom/shake effects
- [x] **P2-001**: RenderSystem hot-loop optimization (`getattr` removal)

#### Weeks 6-7: Physics & Collision - ✅ COMPLETE

- [x] Physics material presets
- [x] Collision callback integration with events
- [x] Joint support (distance, revolute, prismatic, spring, gear, motor)
- [x] Trigger volumes
- [x] Platformer controller helper
- [x] **P1-008**: Cached Component Queries (Physics/ECS Optimization)
- [ ] **P1-010**: ModernGL Rendering Backend (High-Performance GPU Path) - DEFERRED
- [ ] **P1-011**: Advanced Graphics Pipeline (Materials, Lighting, VFX) - DEFERRED

#### Weeks 8-9: UI & Scene Management - ✅ COMPLETE

- [x] UI theme system (JSON-based)
- [x] Layout constraints (anchors, margins)
- [x] Scene transition effects
- [x] Scene stack (push/pop for overlays)
- [x] Nine-patch sprite support
- [x] **P2-002**: SystemManager (Logic Orchestration)

#### Weeks 10-11: AI & Advanced Features - 🚀 IN PROGRESS

- [x] Tween/easing library
- [x] Behavior tree implementation
- [x] A* pathfinding integration
- [x] Navmesh generation
- [x] Coroutine-based scripting
- [ ] **P1-009**: Event Queue Time Budget & Safety
- [ ] **P2-003**: DI Hot-path Audit (remove resolution from loops)

#### Parallel Work Stream: Editor & Tooling

- [ ] **P2-004**: Atomic Writes for Data Safety
- [ ] **P2-005**: Gizmos & Visual Handles
- [ ] **P2-006**: Strict Component Typing (Data-only enforcement)
- [ ] **P2-012**: Logging Standardization (Replace print with logging)
- [ ] **P2-013**: Architecture Cleanup (Standardize ECS patterns, Abstract Input)

**Phase 2 Exit Criteria:**

- ✅ Feature completeness ≥ 70% all systems
- ✅ Test coverage ≥ 80%
- ✅ Performance benchmarks meet targets
- ✅ At least 2 example games complete

---

### Phase 3: Polish & Documentation (Weeks 12-17)

**Goal:** Production-ready release with excellent DX

#### Weeks 12-13: Documentation Sprint

- [ ] Complete API reference (Sphinx)
- [ ] Architecture decision records (ADR)
- [ ] Tutorial series (5+ complete tutorials)
- [ ] Example game: Platformer
- [ ] Example game: Top-down shooter
- [ ] Example game: Puzzle game

#### Weeks 14-15: Developer Experience

- [ ] Error message quality pass
- [ ] Type stub improvements
- [ ] VSCode extension (snippets, templates)
- [ ] Project scaffolding CLI tool
- [ ] Asset pipeline documentation

#### Weeks 16-17: Performance & Stability

- [ ] Performance profiling and optimization
- [ ] Memory leak auditing
- [ ] Fuzz testing
- [ ] Beta release candidate testing
- [ ] Migration guide from raw Pygame

**Phase 3 Exit Criteria:**

- ✅ All documentation complete
- ✅ 3+ example games published
- ✅ Beta release tagged
- ✅ Community feedback incorporated

---

## 5. Dependency Map

### 5.1 Critical Path Analysis

```text
┌─────────────────────────────────────────────────────────────┐
│                     DEPENDENCY GRAPH                        │
└─────────────────────────────────────────────────────────────┘

P0-001 (Component Removal) ──┐
                             ├──> [ECS Stable] ──┐
P0-002 (DIScope API) ────────┤                   │
                             └──> [DI Stable] ───┤
                                                 ├────> [Core Systems Ready]
P0-003 (UI Events) ──────────┐                   │               │
                             ├──> [Event Stable] │               │
P0-005 (Error Handling) ─────┘                   │               │
                                                 │               │
P0-004 (Resource Leak) ───────> [Resources OK] ──┘               │
                                                                 │
P0-006 (Gamepad) ────────────┐                                   │
                             ├──> [Input Complete] ──────────────┤
Input Actions ───────────────┘                                   │
                                                                 │
P0-007 (Audio) ──────────────────> [Audio System] ───────────────┤
                                                                 │
                                                                 V
                                            [Phase 1 Complete] ──┐
                                                                 │
Batching ─────────────┐                                          │
Sprite Atlas ─────────┤                                          │
Animation FSM ────────├──> [Rendering Advanced] ─────────────────┤
Particles ────────────┘                                          │
                                                                 │
Physics Materials ────┐                                          │
Joints ───────────────├──> [Physics Complete] ───────────────────┤
Callbacks ────────────┘                                          │
                                                                 │
UI Themes ────────────┐                                          │
Layouts ──────────────├──> [UI Production Ready] ────────────────┤
Scene Stack ──────────┘                                          │
                                                                 V
                                            [Phase 2 Complete] ──┐
                                                                 │
API Docs ─────────────┐                                          │
Tutorials ────────────├──> [Documentation] ──────────────────────┤
Examples ─────────────┘                                          │
                                                                 │
Profiling ────────────┐                                          │
Optimization ─────────├──> [Performance] ────────────────────────┤
Testing ──────────────┘                                          │
                                                                 V
                                               [BETA RELEASE]
```

### 5.2 Blocking Relationships

| Task | Blocked By | Blocks |
|------|-----------|--------|
| Animation System | Sprite Batching | Example Games |
| Physics Callbacks | Event Error Handling | Platformer Tutorial |
| Scene Stack | UI Event Enum | Pause Menu Pattern |
| Resource Unloading | Reference Counting Design | Long-Running Game Stability |
| Behavior Trees | Blackboard System (exists) | Advanced AI Tutorial |
| Audio Spatial | Audio System Core | Immersive Game Feel |
| UI Themes | UI Refactor Complete | Professional UI Look |
| Performance Optimization | Profiling Tools | Beta Release |

### 5.3 Parallelizable Work Streams

**Stream A (Core Systems):**

- P0-001, P0-002, P0-005 → ECS/DI hardening
- Can be done by: Core engine developer

**Stream B (Input/Audio):**

- P0-006, P0-007 → Input/Audio implementation
- Can be done by: Systems programmer (independent)

**Stream C (Resources):**

- P0-004 → Resource management
- Can be done by: Tools programmer (independent)

**Stream D (Rendering):**

- Batching, Atlas, Animation
- Depends on: Stream A completion
- Can be done by: Graphics programmer

**Stream E (Documentation):**

- Can start immediately (in parallel with all)
- Can be done by: Technical writer / community

---

## 6. Architecture & Style Guide

### 6.1 Design Principles

#### 6.1.1 SOLID Compliance

- **S - Single Responsibility**: Each class has ONE reason to change
- **O - Open/Closed**: Extend via protocols, not modification
- **L - Liskov Substitution**: Subtypes must be substitutable
- **I - Interface Segregation**: Prefer small, focused protocols
- **D - Dependency Inversion**: Depend on abstractions (protocols)

#### 6.1.2 PyGuara-Specific Patterns

**DO:**

- ✅ Use `Protocol` for all interfaces
- ✅ Use `dataclass` for DTOs and components
- ✅ Use type hints for ALL public APIs
- ✅ Use DI container for cross-cutting concerns
- ✅ Use events for decoupled communication
- ✅ Use generators for large result sets
- ✅ Use context managers for resource management

**DON'T:**

- ❌ Don't use inheritance for behavior sharing (use composition)
- ❌ Don't put logic in components (data only)
- ❌ Don't import pygame outside `backends/` directory
- ❌ Don't use singletons (use DI instead)
- ❌ Don't use global state (except unavoidable like pygame)
- ❌ Don't use `print()` (use `logging`)
- ❌ Don't use string-based event types (use enums or classes)

### 6.2 Code Style Standards

#### 6.2.1 Formatting (Enforced by Ruff)

```python
# Line length: 88 characters (Black style)
# Quotes: Double quotes for strings
# Indentation: 4 spaces (no tabs)
# Imports: Sorted (isort), grouped (stdlib, third-party, local)
# Trailing commas: Yes (in multiline collections)
```

#### 6.2.2 Naming Conventions

```python
# Classes: PascalCase
class EntityManager: ...

# Functions/Methods: snake_case
def get_entities_with(...): ...

# Constants: UPPER_SNAKE_CASE
MAX_ENTITIES = 10000

# Private members: Leading underscore
self._internal_cache = {}

# Type variables: Single capital letter or PascalCase with T suffix
T = TypeVar("T")
ComponentT = TypeVar("ComponentT", bound=Component)

# Protocols: I prefix for interfaces (optional but recommended)
class IRenderer(Protocol): ...
```

#### 6.2.3 Type Annotations

```python
# Always annotate function signatures
def create_entity(self, entity_id: Optional[str] = None) -> Entity:
    ...

# Always annotate class attributes
class Component:
    entity: Optional[Entity]

# Use NewType for domain-specific types
EntityID = NewType("EntityID", str)

# Use Protocol for structural typing
class Renderable(Protocol):
    @property
    def position(self) -> Vector2: ...
```

#### 6.2.4 Docstring Format (Google Style)

```python
def complex_function(param1: int, param2: str) -> dict[str, Any]:
    """Brief one-line summary.

    Longer description if needed. Explain the "why" not the "what".
    The "what" should be obvious from the code.

    Args:
        param1: Description of param1.
        param2: Description of param2.

    Returns:
        A dictionary containing the results. Structure described here.

    Raises:
        ValueError: When param1 is negative.
        KeyError: When param2 not in valid set.

    Example:
        >>> result = complex_function(42, "test")
        >>> assert "key" in result
    """
```

### 6.3 Architectural Patterns

#### 6.3.1 Component Definition

```python
from dataclasses import dataclass
from pyguara.ecs.component import BaseComponent
from pyguara.common.types import Vector2

@dataclass
class Transform(BaseComponent):
    """World space position and orientation.

    This component should be present on all visible entities.
    """
    position: Vector2 = Vector2(0, 0)
    rotation: float = 0.0  # degrees
    scale: Vector2 = Vector2(1, 1)

    # NO METHODS (data only)
    # Logic goes in Systems, not Components
```

#### 6.3.2 System Definition

```python
from pyguara.ecs.manager import EntityManager
from pyguara.common.components import Transform
from pyguara.physics.components import RigidBody

class PhysicsSystem:
    """Synchronizes physics engine with ECS transform components.

    Runs during the physics update phase, before rendering.
    """

    def __init__(self, entity_manager: EntityManager, physics_engine: IPhysicsEngine):
        self._entities = entity_manager
        self._physics = physics_engine

    def update(self, dt: float) -> None:
        """Update all physics-enabled entities."""
        for entity in self._entities.get_entities_with(Transform, RigidBody):
            transform = entity.get_component(Transform)
            rigidbody = entity.get_component(RigidBody)

            # Sync physics -> ECS (for dynamic bodies)
            if rigidbody.body_type == BodyType.DYNAMIC:
                physics_body = self._physics.get_body(entity.id)
                transform.position = physics_body.position
                transform.rotation = physics_body.rotation
            # Sync ECS -> physics (for kinematic bodies)
            else:
                physics_body = self._physics.get_body(entity.id)
                physics_body.position = transform.position
                physics_body.rotation = transform.rotation
```

#### 6.3.3 Service Registration

```python
# In bootstrap.py or scene setup
def _setup_container() -> DIContainer:
    container = DIContainer()

    # Singletons: Shared app-wide state
    container.register_singleton(EventDispatcher, EventDispatcher)
    container.register_singleton(ResourceManager, ResourceManager)

    # Transient: New instance every request
    container.register_transient(ParticleEmitter, ParticleEmitter)

    # Scoped: Shared within a scene/scope
    container.register_scoped(PhysicsSystem, PhysicsSystem)

    return container
```

#### 6.3.4 Event Definition and Usage

```python
from dataclasses import dataclass, field
from time import time
from typing import Any

@dataclass
class EntityDiedEvent:
    """Fired when an entity's health reaches zero.

    Subscribers can use this to trigger death animations,
    drop loot, update score, etc.
    """
    entity_id: str
    damage_source: Optional[str] = None
    timestamp: float = field(default_factory=time)
    source: Any = None  # The system that created the event

# Usage
dispatcher.subscribe(EntityDiedEvent, self._on_entity_died)

def _on_entity_died(self, event: EntityDiedEvent) -> None:
    print(f"Entity {event.entity_id} died from {event.damage_source}")
```

### 6.4 File Organization

```text
pyguara/
├── subsystem_name/
│   ├── __init__.py          # Public API exports
│   ├── protocols.py         # Interfaces (I* classes)
│   ├── types.py             # DTOs, Enums, TypeAliases
│   ├── exceptions.py        # Custom exceptions
│   ├── manager.py           # Main coordinator class
│   ├── components/          # If ECS-related
│   │   ├── foo.py
│   │   └── bar.py
│   └── backends/            # If hardware-abstracted
│       ├── pygame_impl.py
│       └── headless_impl.py
└── tests/
    └── test_subsystem_name.py
```

### 6.5 Error Handling Strategy

```python
# Use specific exceptions
from pyguara.subsystem.exceptions import SubsystemException

class EntityNotFoundException(SubsystemException):
    """Raised when entity lookup fails."""
    pass

# Always provide context
raise EntityNotFoundException(
    f"Entity '{entity_id}' not found in manager. "
    f"Available entities: {list(self._entities.keys())[:5]}..."
)

# Log before raising (for async/event contexts)
logger.error(f"Failed to process event: {event}", exc_info=True)
raise

# Use early returns
def process(self, entity: Entity) -> None:
    if not entity.has_component(Transform):
        logger.warning(f"Entity {entity.id} missing Transform, skipping")
        return

    # Main logic here
```

---

## 7. Repository Policies

### 7.1 Branch Strategy

```text
main (protected)
  ├── develop (integration branch)
  │   ├── feature/P0-001-component-removal-tracking
  │   ├── feature/audio-system-implementation
  │   ├── bugfix/resource-memory-leak
  │   └── docs/api-reference-sphinx
  └── release/v0.2.0-beta
```

**Branch Naming:**

- `feature/` - New features
- `bugfix/` - Bug fixes
- `hotfix/` - Critical production fixes
- `docs/` - Documentation only
- `refactor/` - Code refactoring
- `test/` - Test additions/improvements

### 7.2 Commit Message Format

```xml
<type>(<scope>): <subject>

<body>

<footer>
```

**Types:**

- `feat`: New feature
- `fix`: Bug fix
- `docs`: Documentation changes
- `style`: Formatting, no code change
- `refactor`: Code restructuring
- `perf`: Performance improvement
- `test`: Adding tests
- `chore`: Build process, tooling

**Example:**

```markdown
feat(input): add gamepad support with SDL2 backend

Implements Xbox and PlayStation controller support using
pygame's joystick API wrapped in our input abstraction.

- Added GamepadButton and GamepadAxis enums
- Created JoystickBackend protocol
- Implemented SDL2JoystickBackend
- Added input action mapping for buttons

Closes #42
Relates to P0-006
```

### 7.3 Pull Request Process

#### 7.3.1 PR Template

```markdown
## Description
Brief summary of changes

## Type of Change
- [ ] Bug fix (non-breaking change which fixes an issue)
- [ ] New feature (non-breaking change which adds functionality)
- [ ] Breaking change (fix or feature that would cause existing functionality to not work as expected)
- [ ] Documentation update

## Related Issues
Closes #XXX
Relates to #YYY

## Testing
- [ ] Unit tests added/updated
- [ ] Integration tests added/updated
- [ ] Manual testing performed
- [ ] Performance impact assessed

## Checklist
- [ ] Code follows style guidelines (ruff check passes)
- [ ] Type hints complete (mypy passes)
- [ ] Docstrings added for public APIs
- [ ] Tests pass locally
- [ ] No breaking changes OR migration guide provided
- [ ] Documentation updated
```

#### 7.3.2 Review Requirements

- **Minimum Reviewers:** 1 (for large changes: 2)
- **Required Checks:**
  - ✅ CI tests pass
  - ✅ Code coverage doesn't decrease
  - ✅ Ruff and mypy checks pass
  - ✅ No merge conflicts
- **Approval Required:** Yes (from code owner or maintainer)

### 7.4 Issue Management

#### 7.4.1 Issue Labels

```text
Priority:
- P0-critical: Blocking release
- P1-high: Important but not blocking
- P2-medium: Nice to have
- P3-low: Future consideration

Type:
- bug: Something isn't working
- enhancement: New feature request
- documentation: Docs improvement
- performance: Performance issue
- technical-debt: Refactoring needed

Status:
- needs-triage: Awaiting review
- accepted: Approved for implementation
- in-progress: Being worked on
- blocked: Waiting on dependency
- wontfix: Closed without action
```

#### 7.4.2 Issue Template

```markdown
**Describe the Issue**
Clear description of the problem or request

**Expected Behavior**
What should happen

**Actual Behavior**
What actually happens

**Steps to Reproduce**
1. Step 1
2. Step 2
3. ...

**Environment**
- PyGuara Version: X.Y.Z
- Python Version: 3.12.X
- OS: Linux/Windows/Mac
- pygame-ce Version: X.Y.Z

**Additional Context**
Screenshots, code snippets, error traces
```

### 7.5 Testing Requirements

#### 7.5.1 Test Coverage Targets

- **Overall:** ≥ 80%
- **Core Systems (ECS, DI, Events):** ≥ 90%
- **New Features:** ≥ 85%
- **Bug Fixes:** 100% (must include regression test)

#### 7.5.2 Test Structure

```python
# tests/test_subsystem.py
import pytest
from pyguara.subsystem import Thing

class TestThing:
    """Test suite for Thing class."""

    def test_creation(self):
        """Verify Thing can be created with defaults."""
        thing = Thing()
        assert thing is not None

    def test_method_with_valid_input(self):
        """Test method behavior with valid input."""
        thing = Thing()
        result = thing.method(valid_input)
        assert result == expected

    def test_method_raises_on_invalid_input(self):
        """Test method raises appropriate exception."""
        thing = Thing()
        with pytest.raises(ValueError, match="expected pattern"):
            thing.method(invalid_input)

    @pytest.mark.performance
    def test_performance_at_scale(self):
        """Verify performance with large dataset."""
        thing = Thing()
        # Benchmark code
```

#### 7.5.3 CI/CD Pipeline

```yaml
# .github/workflows/ci.yml structure
Jobs:
  - lint: Run ruff check
  - typecheck: Run mypy
  - test-unit: Run pytest (unit tests)
  - test-integration: Run pytest (integration tests)
  - test-performance: Run pytest (benchmark tests)
  - coverage: Generate and upload coverage report
  - build: Verify package builds
```

### 7.6 Documentation Standards

#### 7.6.1 Required Documentation for Features

1. **API Reference**: Auto-generated from docstrings
2. **Tutorial**: Step-by-step guide for common use case
3. **Example**: Working code snippet in examples/
4. **Architecture Decision Record**: For significant design choices

#### 7.6.2 ADR Template

```markdown
# ADR-XXX: Title

## Status
Proposed | Accepted | Deprecated | Superseded by ADR-YYY

## Context
What is the issue we're facing?

## Decision
What did we decide?

## Consequences
What are the trade-offs?

### Positive
- Benefit 1
- Benefit 2

### Negative
- Cost 1
- Cost 2

## Alternatives Considered
- Alternative 1: Why rejected
- Alternative 2: Why rejected
```

---

## 8. Implementation Specifications

### 8.1 P0-001: Component Removal Tracking - ✅ COMPLETED

**File:** `pyguara/ecs/entity.py`, `pyguara/ecs/manager.py`

#### Context

Currently, when a component is removed from an entity via `Entity.remove_component()`, the `EntityManager`'s inverted index is not updated. This means queries like `get_entities_with(ComponentType)` may return entities that no longer have that component, leading to `KeyError` when attempting to access it.

**Root Cause:** Lines 94-106 in `entity.py` acknowledge the issue but don't implement the fix.

#### Acceptance Criteria

- [x] `Entity.remove_component()` notifies EntityManager via callback
- [x] `EntityManager._component_index` correctly removes entity ID from set
- [x] Queries never return entities without requested components
- [x] Test: Create entity with component, remove it, verify query excludes it
- [x] Test: Remove component from 1 of 3 entities, verify query returns only 2
- [x] Performance: Component removal remains O(1) amortized

#### Implementation Summary

Implemented bidirectional notification between `Entity` and `EntityManager`. `Entity.remove_component()` now triggers a callback that updates the manager's inverted index.

---

### 8.2 P0-002: DIScope Public API - ✅ COMPLETED

**File:** `pyguara/di/container.py`

#### Context

The `DIScope` class currently lacks a public `get()` method, forcing users to call the internal `container._resolve_service(service_type, scope)`. This is evident in the test file (test_di.py:96) where internal methods are used directly.

**Design Flaw:** Scoped services can't be resolved in a user-friendly way.

#### Acceptance Criteria

- [x] `DIScope.get(service_type)` method added
- [x] Method delegates to container's resolver with self as scope
- [x] Type hints preserve generic type information
- [x] Tests use public API exclusively
- [x] Documentation shows scoped service usage pattern
- [x] Backward compatibility maintained (don't break existing code)

#### Implementation Summary

Added `DIScope.get()` which delegates to `_resolve_service`. Updated all tests and internal usages to prefer this public API.

---

### 8.3 P0-007: Audio System Implementation - ✅ COMPLETED

**Files:** `pyguara/audio/manager.py`, `pyguara/audio/backends/pygame_audio.py`, `pyguara/audio/types.py`

#### Context

The audio system currently exists only as stubs. This is a critical gap as audio is essential for game feel. We need a production-ready audio manager with support for music, sound effects, and basic spatial audio.

**Requirements:**

- Music playback (looping background tracks)
- Sound effect playback (one-shot sounds)
- Volume control (master, music, sfx)
- Basic 2D positional audio
- Audio resource management
- Fade in/out support

#### Acceptance Criteria

- [x] Can play music with looping
- [x] Can play sound effects with volume/pitch variation
- [x] 2D positional audio (left/right pan based on position)
- [x] Volume controls work (master, music, sfx independently)
- [x] Audio files loaded via ResourceManager
- [x] Fade in/out animations supported
- [x] No audio crackling or popping
- [x] Test: Play overlapping sounds without issues
- [x] Test: Spatial audio pans correctly based on listener position
- [x] Performance: Can handle 32+ simultaneous sounds

#### Implementation Summary

Implemented `AudioManager` using `pygame-ce` mixer backend. Integrated with `ResourceManager` for clip loading. Added 2D spatial panning and multi-track volume management.

---

### 8.4 P0-006: Gamepad Support - ✅ COMPLETED

**Files:** `pyguara/input/gamepad.py`, `pyguara/input/manager.py`, `pyguara/input/types.py`

#### Context

Modern games require gamepad support. The input system currently only handles keyboard and mouse. We need to add comprehensive gamepad support with action mapping.

**Requirements:**

- Support Xbox, PlayStation, Nintendo controllers
- Button and axis input
- Deadzone configuration
- Action mapping (e.g., "Jump" -> Button A/X/B depending on controller)
- Multiple controller support
- Vibration/rumble support

#### Acceptance Criteria

- [x] Detects connected gamepads on startup
- [x] Hot-plug support (connect controller during gameplay)
- [x] All standard buttons accessible
- [x] Analog stick input with configurable deadzones
- [x] Trigger input (L2/R2, LT/RT)
- [x] Action mapping system (logical actions -> physical inputs)
- [x] Test: Button press events fired correctly
- [x] Test: Analog stick values accurate with deadzone
- [x] Test: Multiple controllers distinguished
- [x] Documentation: Controller setup guide

#### Implementation Summary

Created `GamepadManager` with hot-plug support via `JOYDEVICEADDED`/`JOYDEVICEREMOVED`. Implemented deadzone scaling and axis normalization. Integrated with semantic `OnActionEvent` system.

---

### 8.5 P1-010: ModernGL Rendering Backend

**Status:** Proposed (Design Drafted)
**Specification:** [docs/dev/backlog/active/2026-01-11-modern-gl-migration.md](2026-01-11-modern-gl-migration.md)

---

### 8.6 P1-011: Advanced Graphics Pipeline

**Status:** Proposed (Design Drafted)
**Specification:** [docs/dev/backlog/active/2026-01-11-advanced-graphics-pipeline.md](2026-01-11-advanced-graphics-pipeline.md)

---

### 8.7 P1-008: Cached Component Queries (Physics/ECS Optimization)

**Files:** `pyguara/ecs/manager.py`, `pyguara/physics/physics_system.py`

#### Context

Currently, `get_entities_with()` performs set intersections every time it is called. Systems like Physics call this every frame, creating unnecessary overhead. Additionally, systems often convert the generator result to a list (`list(manager.get_entities_with(...))`), causing list allocation pressure.

**Optimization:** The ECS should maintain a cached `Set[Entity]` for specific queries (e.g., `(Transform, RigidBody)`) that is updated only when relevant components are added/removed.

#### Acceptance Criteria

- [ ] `EntityManager` supports "Cached Queries" or "Archetypes"
- [ ] PhysicsSystem uses cached query instead of ad-hoc intersection
- [ ] No list allocations in hot-loops for entity retrieval
- [ ] Benchmark: 10,000 entities physics update < 16ms

### 8.6 P1-009: Event Queue Safety

**File:** `pyguara/application/application.py`

#### Context

`Application._update` calls `_event_dispatcher.process_queue()` without limits. If systems produce events faster than they can be consumed (e.g., a loop creating events), the application will hang in a "death spiral."

#### Acceptance Criteria

- [ ] `EventDispatcher.process_queue()` accepts a `max_time_ms` or `max_events` parameter
- [ ] Application loop enforces this budget (e.g., 2-5ms per frame)
- [ ] Unprocessed events remain in queue for next frame
- [ ] Warning logged if queue size exceeds safety threshold (e.g., 10k events)

### 8.7 P2-003: DI Hot-path Audit

**File:** `pyguara/physics/physics_system.py`, `pyguara/graphics/pipeline/render_system.py`

#### Context

Code reviews indicate `inspect.signature` usage during runtime and potential service resolution inside update loops. This is too slow for production.

#### Acceptance Criteria

- [ ] Verify no `container.get()` calls inside `update()` or `render()` methods
- [ ] All dependencies resolved in `__init__` and stored as attributes
- [ ] `inspect` usage restricted to registration time only

---

### 8.8 P2-012: Logging Standardization

**Status:** Proposed (Design Drafted)
**Specification:** [docs/dev/backlog/active/2026-01-11-logging-refactor.md](2026-01-11-logging-refactor.md)

---

### 8.9 P2-013: Architecture Cleanup

**Status:** Proposed (Design Drafted)
**Specification:** [docs/dev/backlog/active/2026-01-11-architecture-cleanup.md](2026-01-11-architecture-cleanup.md)

---

## 9. Quality Gates & Acceptance Criteria

### 9.1 Definition of Done (DoD)

A feature/fix is considered "Done" when ALL of the following are true:

#### Code Quality

- [ ] Code follows style guide (ruff check passes)
- [ ] Type hints complete (mypy passes with no errors)
- [ ] No TODO/FIXME comments (unless tracked in issues)
- [ ] No commented-out code
- [ ] No print() statements (use logging)
- [ ] Docstrings added for all public APIs (Google style)

#### Testing

- [ ] Unit tests written (coverage ≥ 85% for new code)
- [ ] Integration tests added (if applicable)
- [ ] All tests pass locally
- [ ] CI pipeline green
- [ ] Performance impact assessed (benchmarks run)
- [ ] Manual testing completed (test plan documented)

#### Documentation

- [ ] API reference updated (docstrings)
- [ ] Tutorial/guide written (for features)
- [ ] Example code added (if applicable)
- [ ] CHANGELOG.md updated
- [ ] Architecture decision recorded (for significant changes)

#### Review

- [ ] Code reviewed and approved
- [ ] No unresolved review comments
- [ ] Breaking changes flagged and documented
- [ ] Migration guide provided (if breaking change)

#### Integration

- [ ] Merged to develop branch
- [ ] No merge conflicts
- [ ] Build succeeds
- [ ] Integration tests pass

### 9.2 Release Criteria

#### Alpha Release (Current)

- ✅ Core systems functional
- ✅ Basic example works
- ⚠️ Known bugs acceptable
- ⚠️ Documentation minimal

#### Beta Release (Target)

- [ ] All P0 issues resolved
- [ ] All P1 issues resolved
- [ ] Test coverage ≥ 80%
- [ ] API stable (no breaking changes planned)
- [ ] 3+ complete example games
- [ ] Full API documentation
- [ ] Tutorial series complete
- [ ] Performance benchmarks published
- [ ] Community beta testing (2+ weeks)
- [ ] Critical bugs < 5
- [ ] Known issues documented

#### 1.0 Release (Future)

- [ ] All P0-P2 issues resolved
- [ ] Test coverage ≥ 90%
- [ ] Production games shipped
- [ ] Stability tested (1000+ hours gameplay)
- [ ] Plugin system mature
- [ ] Community contributions accepted
- [ ] Professional documentation
- [ ] Video tutorials available
- [ ] No critical or high-priority bugs

### 9.3 Performance Benchmarks

All releases must meet these minimum performance targets on reference hardware (mid-range laptop):

| Benchmark | Target | Measurement |
|-----------|--------|-------------|
| Entity Creation | 10,000/sec | `benchmark_entity_creation()` |
| Component Query | 100,000/sec | `benchmark_component_query()` |
| Event Dispatch | 50,000/sec | `benchmark_event_dispatch()` |
| Sprite Rendering | 60 FPS @ 5000 sprites | `benchmark_sprite_rendering()` |
| Physics Simulation | 60 FPS @ 1000 bodies | `benchmark_physics()` |
| Scene Load Time | < 1 second | `benchmark_scene_load()` |
| Memory Usage | < 500 MB @ 10k entities | `benchmark_memory()` |
| Asset Load | < 100ms per 1MB | `benchmark_asset_loading()` |

**Reference Hardware:**

- CPU: Intel i5-8250U or equivalent
- RAM: 8GB DDR4
- GPU: Integrated graphics
- OS: Ubuntu 22.04 LTS

### 9.4 Security Checklist

For each release, verify:

- [ ] No secrets in codebase (API keys, passwords)
- [ ] User input sanitized (file paths, save data)
- [ ] No code execution from data files (unless sandboxed)
- [ ] Dependencies scanned for vulnerabilities
- [ ] Save files validated before loading
- [ ] Network code (future) uses encryption
- [ ] Error messages don't leak sensitive info

---

## Appendix A: Glossary

**ECS**: Entity-Component-System architecture pattern
**DI**: Dependency Injection (IoC container)
**DoD**: Definition of Done
**ADR**: Architecture Decision Record
**HAL**: Hardware Abstraction Layer
**P0/P1/P2/P3**: Priority levels (0 = Critical, 3 = Low)
**SFX**: Sound Effects
**UI**: User Interface
**DX**: Developer Experience

---

## Appendix B: References

- [PyGuara Repository](https://github.com/yourusername/pyguara)
- [Python Type Hints (PEP 484)](https://peps.python.org/pep-0484/)
- [Pygame Documentation](https://www.pygame.org/docs/)
- [Pymunk Documentation](http://www.pymunk.org/)
- [ECS FAQ](https://github.com/SanderMertens/ecs-faq)
- [Game Programming Patterns](https://gameprogrammingpatterns.com/)

---

## Document History

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 1.0 | 2026-01-09 | Review Committee | Initial draft |
| 1.1 | 2026-01-10 | Review Committee | Phase 1 completion update |
| 1.2 | 2026-01-11 | Review Committee | Phase 2 Weeks 4-5 completion (Rendering & Animation) |

---

**END OF DOCUMENT**

*This Product Enhancement Proposal is a living document and will be updated as implementation progresses.*
