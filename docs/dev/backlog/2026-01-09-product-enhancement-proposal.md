# Product Enhancement Proposal (PEP-2026.01)
## PyGuara Game Engine - Roadmap to Beta

**Document Version:** 1.0
**Date:** January 9, 2026
**Author:** Comprehensive Engine Review Committee
**Status:** DRAFT - Awaiting Approval

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
- **Version:** Pre-Alpha
- **Codebase:** ~10,000 lines across 100+ files
- **Overall Grade:** B+ (Excellent architecture, incomplete features)
- **Production Readiness:** 35% (suitable for prototypes, not commercial)

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
|--------|-------------|--------------|---------|---------------|----------|
| ECS Core | ⭐⭐⭐⭐⭐ | 90% | ⭐⭐⭐⭐ | ⭐⭐⭐⭐ | P1 |
| DI Container | ⭐⭐⭐⭐ | 85% | ⭐⭐⭐ | ⭐⭐⭐ | P1 |
| Event System | ⭐⭐⭐⭐½ | 80% | ⭐⭐⭐⭐ | ⭐⭐⭐⭐ | P1 |
| Graphics/Rendering | ⭐⭐⭐⭐ | 70% | ⭐⭐⭐ | ⭐⭐⭐⭐ | P0 |
| Physics | ⭐⭐⭐⭐ | 60% | ⭐⭐⭐ | ⭐⭐⭐ | P1 |
| Input | ⭐⭐⭐½ | 50% | ⭐⭐ | ⭐⭐ | P0 |
| Audio | ⭐⭐ | 10% | ⭐ | ⭐ | P0 |
| UI | ⭐⭐⭐½ | 40% | ⭐⭐ | ⭐⭐ | P1 |
| AI | ⭐⭐⭐ | 30% | ⭐⭐ | ⭐⭐ | P2 |
| Scene Mgmt | ⭐⭐⭐⭐ | 75% | ⭐⭐⭐ | ⭐⭐⭐ | P1 |
| Resources | ⭐⭐⭐⭐ | 70% | ⭐⭐⭐ | ⭐⭐⭐ | P1 |
| Persistence | ⭐⭐⭐ | 50% | ⭐⭐ | ⭐⭐ | P2 |
| Config | ⭐⭐⭐⭐ | 80% | ⭐⭐⭐⭐ | ⭐⭐⭐ | P2 |
| Editor | ⭐⭐⭐ | 25% | ⭐ | ⭐ | P3 |

**Priority Levels:**
- **P0**: Blocking issues - cannot ship without
- **P1**: High priority - critical for good UX
- **P2**: Medium priority - nice to have
- **P3**: Low priority - future enhancements

### 2.2 Critical Issues Identified

#### P0-001: Component Removal Tracking (ECS) ✅ RESOLVED
- **Location:** `pyguara/ecs/entity.py:94-106`
- **Impact:** Queries may return entities with deleted components
- **Risk:** HIGH - Data corruption potential
- **Resolution:** Implemented bidirectional observer pattern (see IMPLEMENTATION_P0-001.md)

#### P0-002: DIScope Public API Missing (DI) ✅ RESOLVED
- **Location:** `pyguara/di/container.py:247-298`
- **Impact:** Scoped services unusable in production code
- **Risk:** MEDIUM - Limits DI usefulness
- **Resolution:** Added DIScope.get() public API (see IMPLEMENTATION_P0-002.md)

#### P0-003: String-Based UI Events (UI) ✅ RESOLVED
- **Location:** `pyguara/ui/manager.py:41-47`
- **Impact:** Typos cause silent failures, no IDE autocomplete
- **Risk:** MEDIUM - Developer experience
- **Resolution:** Implemented UIEventType enum (commit 5ec8d1b, merged fb8290c)

#### P0-004: Resource Memory Leak (Resources) ✅ RESOLVED
- **Location:** `pyguara/resources/manager.py`
- **Impact:** Memory grows unbounded in long-running games
- **Risk:** HIGH - Performance degradation
- **Resolution:** Implemented reference counting system (commit 394e073, merged 2cbd35d)

#### P0-005: Event Error Swallowing (Events/DI) ✅ RESOLVED
- **Location:** `pyguara/events/dispatcher.py:98-99`, `pyguara/di/container.py:242-244`
- **Impact:** Debugging is extremely difficult
- **Risk:** MEDIUM - Developer experience
- **Resolution:** Implemented ErrorHandlingStrategy enum (commit 3b25641, merged 00fb8ad)

#### P0-006: No Gamepad Support (Input)
- **Location:** `pyguara/input/manager.py`
- **Impact:** Cannot ship console-style games
- **Risk:** HIGH - Feature gap

#### P0-007: Audio System Stub Only (Audio)
- **Location:** `pyguara/audio/`
- **Impact:** No sound in games (critical UX gap)
- **Risk:** CRITICAL - Minimum viable product

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

### Phase 1: Critical Fixes & Stability (Weeks 1-3)

**Goal:** Resolve all P0 issues, achieve zero known crashes

#### Week 1: Core System Fixes
- [x] **P0-001**: Implement component removal tracking
- [x] **P0-002**: Add DIScope.get() public API
- [x] **P0-003**: Create UIEventType enum
- [x] **P0-005**: Configurable error handling strategy
- [ ] Test coverage for all fixes ≥ 90%

#### Week 2: Input & Audio Foundation
- [x] **P0-006**: Gamepad support (pygame-ce backend)
- [x] **P0-007**: Audio system implementation (pygame.mixer wrapper)
- [ ] Input action mapping system
- [ ] Audio manager with spatial audio support

#### Week 3: Resource Management & Testing
- [x] **P0-004**: Resource reference counting and unloading
- [ ] Memory leak detection in tests
- [ ] Integration test suite expansion
- [ ] Performance benchmarking harness

**Phase 1 Exit Criteria:**
- ✅ All P0 issues closed
- ✅ Test coverage ≥ 75%
- ✅ Zero critical bugs in issue tracker
- ✅ CI/CD pipeline green

---

### Phase 2: Feature Completeness (Weeks 4-11)

**Goal:** Bring all systems to production-ready state

#### Weeks 4-5: Rendering & Animation
- [ ] Automatic sprite batching implementation
- [ ] Sprite atlas generation tool
- [ ] Animation state machine
- [ ] Particle system enhancements
- [ ] Camera zoom/shake effects

#### Weeks 6-7: Physics & Collision
- [ ] Physics material presets
- [ ] Collision callback integration with events
- [ ] Joint support (distance, revolute, prismatic)
- [ ] Trigger volumes
- [ ] Platformer controller helper

#### Weeks 8-9: UI & Scene Management
- [ ] UI theme system (JSON-based)
- [ ] Layout constraints (anchors, margins)
- [ ] Scene transition effects
- [ ] Scene stack (push/pop for overlays)
- [ ] Nine-patch sprite support

#### Weeks 10-11: AI & Advanced Features
- [ ] Behavior tree implementation
- [ ] A* pathfinding integration
- [ ] Navmesh generation
- [ ] Tween/easing library
- [ ] Coroutine-based scripting

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

```
┌─────────────────────────────────────────────────────────────┐
│                     DEPENDENCY GRAPH                        │
└─────────────────────────────────────────────────────────────┘

P0-001 (Component Removal) ──┐
                             ├──> [ECS Stable] ──┐
P0-002 (DIScope API) ────────┤                   │
                             └──> [DI Stable] ───┤
                                                  ├──> [Core Systems Ready]
P0-003 (UI Events) ──────────┐                   │              │
                             ├──> [Event Stable] │              │
P0-005 (Error Handling) ─────┘                   │              │
                                                  │              │
P0-004 (Resource Leak) ───────> [Resources OK] ──┘              │
                                                                 │
P0-006 (Gamepad) ────────────┐                                  │
                             ├──> [Input Complete] ─────────────┤
Input Actions ───────────────┘                                  │
                                                                 │
P0-007 (Audio) ──────────────────> [Audio System] ──────────────┤
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

```
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

```
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

```
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
```
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
```
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

### 8.1 P0-001: Component Removal Tracking

**File:** `pyguara/ecs/entity.py`, `pyguara/ecs/manager.py`

#### Context
Currently, when a component is removed from an entity via `Entity.remove_component()`, the `EntityManager`'s inverted index is not updated. This means queries like `get_entities_with(ComponentType)` may return entities that no longer have that component, leading to `KeyError` when attempting to access it.

**Root Cause:** Lines 94-106 in `entity.py` acknowledge the issue but don't implement the fix.

#### Acceptance Criteria
- [ ] `Entity.remove_component()` notifies EntityManager via callback
- [ ] `EntityManager._component_index` correctly removes entity ID from set
- [ ] Queries never return entities without requested components
- [ ] Test: Create entity with component, remove it, verify query excludes it
- [ ] Test: Remove component from 1 of 3 entities, verify query returns only 2
- [ ] Performance: Component removal remains O(1) amortized

#### Implementation Steps

**Step 1: Add callback field to Entity**
```python
# entity.py
class Entity:
    def __init__(self, entity_id: Optional[str] = None) -> None:
        # ... existing code ...
        self._on_component_removed: Optional[Callable[[str, Type[Component]], None]] = None
```

**Step 2: Modify remove_component to call callback**
```python
# entity.py
def remove_component(self, component_type: Type[Component]) -> None:
    """Remove a component by type."""
    if component_type in self._components:
        comp = self._components.pop(component_type)
        comp.on_detach()

        # Remove from property cache
        snake_name = self._get_snake_name(component_type)
        if snake_name in self._property_cache:
            del self._property_cache[snake_name]

        # NEW: Notify the manager
        if self._on_component_removed:
            self._on_component_removed(self.id, component_type)
```

**Step 3: Implement handler in EntityManager**
```python
# manager.py
def add_entity(self, entity: Entity) -> None:
    """Register an existing entity."""
    self._entities[entity.id] = entity

    # Existing hook
    entity._on_component_added = self._on_entity_component_added

    # NEW: Hook for removal
    entity._on_component_removed = self._on_entity_component_removed

    # Index existing components...

def _on_entity_component_removed(
    self, entity_id: str, component_type: Type[Component]
) -> None:
    """Called when an entity removes a component."""
    if component_type in self._component_index:
        self._component_index[component_type].discard(entity_id)
```

**Step 4: Add comprehensive tests**
```python
# tests/test_ecs.py
def test_component_removal_updates_index():
    """Ensure removing a component updates manager's index."""
    manager = EntityManager()
    e1 = manager.create_entity()
    e1.add_component(Position())

    # Verify in index
    assert len(list(manager.get_entities_with(Position))) == 1

    # Remove component
    e1.remove_component(Position)

    # Verify no longer in index
    assert len(list(manager.get_entities_with(Position))) == 0

def test_partial_removal_from_multiple_entities():
    """Removing from one entity shouldn't affect others."""
    manager = EntityManager()
    e1 = manager.create_entity()
    e2 = manager.create_entity()
    e3 = manager.create_entity()

    e1.add_component(Position())
    e2.add_component(Position())
    e3.add_component(Position())

    # All 3 have Position
    assert len(list(manager.get_entities_with(Position))) == 3

    # Remove from e2 only
    e2.remove_component(Position)

    # Should have exactly 2 now
    results = list(manager.get_entities_with(Position))
    assert len(results) == 2
    assert set(results) == {e1, e3}
```

**Step 5: Update documentation**
- Update docstring for `remove_component()` noting index update
- Add note in architecture.md about bidirectional callbacks
- Add example in ECS tutorial

---

### 8.2 P0-002: DIScope Public API

**File:** `pyguara/di/container.py`

#### Context
The `DIScope` class currently lacks a public `get()` method, forcing users to call the internal `container._resolve_service(service_type, scope)`. This is evident in the test file (test_di.py:96) where internal methods are used directly.

**Design Flaw:** Scoped services can't be resolved in a user-friendly way.

#### Acceptance Criteria
- [ ] `DIScope.get(service_type)` method added
- [ ] Method delegates to container's resolver with self as scope
- [ ] Type hints preserve generic type information
- [ ] Tests use public API exclusively
- [ ] Documentation shows scoped service usage pattern
- [ ] Backward compatibility maintained (don't break existing code)

#### Implementation Steps

**Step 1: Add public get method to DIScope**
```python
# container.py
class DIScope:
    """Service scope for managing scoped lifetimes and cleanup."""

    def __init__(self, container: DIContainer) -> None:
        # ... existing code ...

    def get(self, service_type: Type[T]) -> T:
        """Resolve a service within this scope.

        For scoped services, returns the same instance throughout
        the scope's lifetime. For singleton/transient services,
        delegates to container's normal resolution logic.

        Args:
            service_type: The service interface or class to resolve.

        Returns:
            An instance of the requested service.

        Raises:
            ServiceNotFoundException: If service not registered.
            DIException: If scoped service accessed without scope.

        Example:
            >>> with container.create_scope() as scope:
            ...     db = scope.get(IDatabase)
            ...     service = scope.get(MyService)  # Gets same db instance
        """
        return self._container._resolve_service(service_type, scope=self)

    # ... rest of existing methods ...
```

**Step 2: Update tests to use public API**
```python
# tests/test_di.py
def test_scoped_resolution(container):
    container.register_scoped(IService, ServiceImpl)

    with container.create_scope() as scope:
        # OLD: container._resolve_service(IService, scope)
        # NEW: Use public API
        s1 = scope.get(IService)
        s2 = scope.get(IService)
        assert s1 is s2

    with container.create_scope() as scope2:
        s3 = scope2.get(IService)
        assert s1 is not s3
```

**Step 3: Add usage examples to documentation**
```python
# docs/core/dependency-injection.md
## Using Scoped Services

Scoped services are useful for request-scoped resources like database
connections, transactions, or scene-specific managers.

```python
# Register a scoped service
container.register_scoped(IDatabase, SqliteDatabase)

# Use within a scope
with container.create_scope() as scope:
    db = scope.get(IDatabase)
    service1 = scope.get(UserService)  # Injects same db
    service2 = scope.get(OrderService)  # Injects same db

    # db is automatically cleaned up on scope exit
```
```

**Step 4: Integration test for typical game usage**
```python
def test_scoped_scene_services(container):
    """Verify scoped services work for scene lifecycle."""

    class ScenePhysics:
        def __init__(self):
            self.initialized = True
            self.disposed = False
        def dispose(self):
            self.disposed = True

    container.register_scoped(ScenePhysics, ScenePhysics)

    # Scene 1
    with container.create_scope() as scene1_scope:
        physics1 = scene1_scope.get(ScenePhysics)
        assert physics1.initialized

    # Physics1 should be disposed after scope exit
    assert physics1.disposed

    # Scene 2 gets a fresh instance
    with container.create_scope() as scene2_scope:
        physics2 = scene2_scope.get(ScenePhysics)
        assert physics2 is not physics1
```

---

### 8.3 P0-007: Audio System Implementation

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
- [ ] Can play music with looping
- [ ] Can play sound effects with volume/pitch variation
- [ ] 2D positional audio (left/right pan based on position)
- [ ] Volume controls work (master, music, sfx independently)
- [ ] Audio files loaded via ResourceManager
- [ ] Fade in/out animations supported
- [ ] No audio crackling or popping
- [ ] Test: Play overlapping sounds without issues
- [ ] Test: Spatial audio pans correctly based on listener position
- [ ] Performance: Can handle 32+ simultaneous sounds

#### Implementation Steps

**Step 1: Define audio types and protocols**
```python
# types.py
from dataclasses import dataclass
from enum import Enum
from typing import Protocol

class AudioType(Enum):
    """Classification of audio resources."""
    MUSIC = "music"
    SFX = "sfx"
    VOICE = "voice"

@dataclass
class AudioClip:
    """Represents a loaded audio resource."""
    path: str
    audio_type: AudioType
    native_handle: Any  # pygame.mixer.Sound or Music
    duration: float  # seconds

@dataclass
class AudioSettings:
    """Global audio configuration."""
    master_volume: float = 1.0  # 0.0 to 1.0
    music_volume: float = 0.8
    sfx_volume: float = 1.0
    max_channels: int = 32
    frequency: int = 44100
    buffer_size: int = 512

class IAudioBackend(Protocol):
    """Interface for audio backend implementations."""

    def initialize(self, settings: AudioSettings) -> None:
        """Initialize the audio system."""
        ...

    def load_music(self, path: str) -> Any:
        """Load a music track."""
        ...

    def load_sound(self, path: str) -> Any:
        """Load a sound effect."""
        ...

    def play_music(self, music: Any, loops: int, fade_ms: int) -> None:
        """Play background music."""
        ...

    def play_sound(self, sound: Any, volume: float, pan: float) -> int:
        """Play a sound effect. Returns channel ID."""
        ...

    def stop_music(self, fade_ms: int) -> None:
        """Stop music playback."""
        ...

    def set_master_volume(self, volume: float) -> None:
        """Set master volume."""
        ...
```

**Step 2: Implement pygame backend**
```python
# backends/pygame_audio.py
import pygame.mixer
from pyguara.audio.types import AudioSettings, IAudioBackend
from pyguara.common.types import Vector2

class PygameAudioBackend(IAudioBackend):
    """Audio backend using pygame.mixer."""

    def __init__(self):
        self._settings: Optional[AudioSettings] = None
        self._initialized = False

    def initialize(self, settings: AudioSettings) -> None:
        """Initialize pygame.mixer."""
        pygame.mixer.init(
            frequency=settings.frequency,
            size=-16,  # 16-bit
            channels=2,  # Stereo
            buffer=settings.buffer_size
        )
        pygame.mixer.set_num_channels(settings.max_channels)
        self._settings = settings
        self._initialized = True

    def load_music(self, path: str) -> Any:
        """Load music (pygame handles this globally)."""
        # pygame.mixer.music is a singleton, return path
        return path

    def load_sound(self, path: str) -> Any:
        """Load sound effect."""
        return pygame.mixer.Sound(path)

    def play_music(self, music: Any, loops: int, fade_ms: int) -> None:
        """Play music track."""
        pygame.mixer.music.load(music)  # music is path
        pygame.mixer.music.play(loops=loops, fade_ms=fade_ms)

    def play_sound(self, sound: Any, volume: float, pan: float) -> int:
        """Play sound with panning.

        Args:
            sound: pygame.mixer.Sound object
            volume: 0.0 to 1.0
            pan: -1.0 (left) to 1.0 (right)

        Returns:
            Channel ID or -1 if no channels available
        """
        channel = sound.play()
        if channel:
            channel.set_volume(volume)
            # Stereo panning: pan -1 = left only, +1 = right only
            left_vol = (1.0 - pan) / 2.0
            right_vol = (1.0 + pan) / 2.0
            channel.set_volume(left_vol, right_vol)
            return channel
        return -1

    def stop_music(self, fade_ms: int) -> None:
        """Stop music."""
        pygame.mixer.music.fadeout(fade_ms)

    def set_master_volume(self, volume: float) -> None:
        """Set master volume (affects all channels)."""
        # pygame.mixer doesn't have true master volume,
        # but we can scale music volume
        pygame.mixer.music.set_volume(volume)
```

**Step 3: Implement AudioManager**
```python
# manager.py
from typing import Dict, Optional
from pyguara.audio.types import AudioClip, AudioSettings, AudioType, IAudioBackend
from pyguara.common.types import Vector2
from pyguara.resources.manager import ResourceManager

class AudioManager:
    """Manages audio playback and resources."""

    def __init__(
        self,
        backend: IAudioBackend,
        resource_manager: ResourceManager,
        settings: Optional[AudioSettings] = None
    ):
        self._backend = backend
        self._resources = resource_manager
        self._settings = settings or AudioSettings()

        # Cache loaded audio
        self._clips: Dict[str, AudioClip] = {}

        # Listener position for 3D audio
        self._listener_position = Vector2(0, 0)

        # Current music track
        self._current_music: Optional[str] = None

        # Initialize backend
        self._backend.initialize(self._settings)

    def set_listener_position(self, position: Vector2) -> None:
        """Update the audio listener position for spatial audio."""
        self._listener_position = position

    def play_music(self, music_name: str, loops: int = -1, fade_ms: int = 0) -> None:
        """Play background music.

        Args:
            music_name: Resource name or path
            loops: -1 for infinite loop, 0 for once, N for N+1 times
            fade_ms: Fade in duration in milliseconds
        """
        if music_name == self._current_music and pygame.mixer.music.get_busy():
            return  # Already playing

        # Stop current music
        if self._current_music:
            self._backend.stop_music(fade_ms=fade_ms)

        # Load if not cached
        if music_name not in self._clips:
            music_handle = self._backend.load_music(music_name)
            self._clips[music_name] = AudioClip(
                path=music_name,
                audio_type=AudioType.MUSIC,
                native_handle=music_handle,
                duration=0.0  # TODO: Get duration
            )

        clip = self._clips[music_name]
        self._backend.play_music(clip.native_handle, loops, fade_ms)
        self._current_music = music_name

    def play_sound(
        self,
        sound_name: str,
        volume: float = 1.0,
        position: Optional[Vector2] = None
    ) -> int:
        """Play a sound effect.

        Args:
            sound_name: Resource name or path
            volume: 0.0 to 1.0 (scaled by sfx volume setting)
            position: World position for spatial audio (optional)

        Returns:
            Channel ID or -1 if failed
        """
        # Load if not cached
        if sound_name not in self._clips:
            sound_handle = self._backend.load_sound(sound_name)
            self._clips[sound_name] = AudioClip(
                path=sound_name,
                audio_type=AudioType.SFX,
                native_handle=sound_handle,
                duration=0.0  # TODO: Get duration
            )

        clip = self._clips[sound_name]

        # Calculate panning if position provided
        pan = 0.0
        if position:
            pan = self._calculate_pan(position)

        # Apply volume scaling
        final_volume = volume * self._settings.sfx_volume * self._settings.master_volume

        return self._backend.play_sound(clip.native_handle, final_volume, pan)

    def _calculate_pan(self, sound_position: Vector2) -> float:
        """Calculate stereo pan based on relative position.

        Args:
            sound_position: World position of sound source

        Returns:
            Pan value from -1.0 (left) to 1.0 (right)
        """
        # Simple linear panning based on X offset
        # Can be enhanced with distance falloff, etc.
        offset = sound_position.x - self._listener_position.x

        # Normalize to -1 to 1 range (assuming reasonable game world scale)
        pan = offset / 1000.0  # Adjust divisor based on game scale
        return max(-1.0, min(1.0, pan))  # Clamp

    def stop_music(self, fade_ms: int = 0) -> None:
        """Stop currently playing music."""
        self._backend.stop_music(fade_ms)
        self._current_music = None

    def set_master_volume(self, volume: float) -> None:
        """Set master volume (0.0 to 1.0)."""
        self._settings.master_volume = max(0.0, min(1.0, volume))
        self._backend.set_master_volume(self._settings.master_volume)

    def set_music_volume(self, volume: float) -> None:
        """Set music volume (0.0 to 1.0)."""
        self._settings.music_volume = max(0.0, min(1.0, volume))
        # Reapply if music is playing
        if self._current_music:
            pygame.mixer.music.set_volume(
                self._settings.music_volume * self._settings.master_volume
            )

    def set_sfx_volume(self, volume: float) -> None:
        """Set sound effects volume (0.0 to 1.0)."""
        self._settings.sfx_volume = max(0.0, min(1.0, volume))
```

**Step 4: Register in bootstrap**
```python
# application/bootstrap.py
def _setup_container() -> DIContainer:
    # ... existing code ...

    # Audio System
    audio_backend = PygameAudioBackend()
    audio_manager = AudioManager(
        backend=audio_backend,
        resource_manager=res_manager,
        settings=AudioSettings()  # Could load from config
    )
    container.register_instance(AudioManager, audio_manager)

    return container
```

**Step 5: Add comprehensive tests**
```python
# tests/test_audio.py
import pytest
from pyguara.audio.manager import AudioManager
from pyguara.audio.types import AudioSettings
from pyguara.common.types import Vector2

@pytest.fixture
def audio_manager(mock_backend, mock_resources):
    return AudioManager(mock_backend, mock_resources)

def test_play_music(audio_manager):
    """Verify music playback."""
    audio_manager.play_music("theme.mp3")
    # Verify backend.play_music was called
    assert audio_manager._current_music == "theme.mp3"

def test_spatial_audio_panning(audio_manager):
    """Verify sounds pan correctly based on position."""
    audio_manager.set_listener_position(Vector2(0, 0))

    # Sound to the right
    pan_right = audio_manager._calculate_pan(Vector2(500, 0))
    assert pan_right > 0

    # Sound to the left
    pan_left = audio_manager._calculate_pan(Vector2(-500, 0))
    assert pan_left < 0

    # Sound centered
    pan_center = audio_manager._calculate_pan(Vector2(0, 0))
    assert pan_center == 0.0

def test_volume_stacking(audio_manager):
    """Verify volume settings multiply correctly."""
    audio_manager.set_master_volume(0.5)
    audio_manager.set_sfx_volume(0.8)

    # When playing sound at volume 1.0
    # Final should be 1.0 * 0.8 (sfx) * 0.5 (master) = 0.4
    # Test implementation details...
```

---

### 8.4 P0-006: Gamepad Support

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
- [ ] Detects connected gamepads on startup
- [ ] Hot-plug support (connect controller during gameplay)
- [ ] All standard buttons accessible
- [ ] Analog stick input with configurable deadzones
- [ ] Trigger input (L2/R2, LT/RT)
- [ ] Action mapping system (logical actions -> physical inputs)
- [ ] Test: Button press events fired correctly
- [ ] Test: Analog stick values accurate with deadzone
- [ ] Test: Multiple controllers distinguished
- [ ] Documentation: Controller setup guide

#### Implementation Steps

**Step 1: Define gamepad types**
```python
# input/types.py
from enum import IntEnum

class GamepadButton(IntEnum):
    """Standard gamepad buttons (Xbox layout)."""
    A = 0  # Cross on PlayStation
    B = 1  # Circle on PlayStation
    X = 2  # Square on PlayStation
    Y = 3  # Triangle on PlayStation

    LEFT_BUMPER = 4   # L1
    RIGHT_BUMPER = 5  # R1

    BACK = 6   # Select/Share
    START = 7
    GUIDE = 8  # Home/PS button

    LEFT_STICK_CLICK = 9
    RIGHT_STICK_CLICK = 10

    DPAD_UP = 11
    DPAD_DOWN = 12
    DPAD_LEFT = 13
    DPAD_RIGHT = 14

class GamepadAxis(IntEnum):
    """Standard gamepad axes."""
    LEFT_STICK_X = 0
    LEFT_STICK_Y = 1
    RIGHT_STICK_X = 2
    RIGHT_STICK_Y = 3
    LEFT_TRIGGER = 4
    RIGHT_TRIGGER = 5

@dataclass
class GamepadState:
    """Current state of a gamepad."""
    device_id: int
    name: str
    buttons: Dict[GamepadButton, bool]  # Pressed state
    axes: Dict[GamepadAxis, float]  # -1.0 to 1.0
    connected: bool = True

@dataclass
class GamepadConfig:
    """Configuration for gamepad input processing."""
    deadzone: float = 0.15  # Ignore input below this threshold
    trigger_threshold: float = 0.1  # Treat as button press if above
```

**Step 2: Create Gamepad Manager**
```python
# input/gamepad.py
import pygame
from typing import Dict, Optional
from pyguara.input.types import GamepadState, GamepadButton, GamepadAxis, GamepadConfig
from pyguara.events.dispatcher import EventDispatcher

@dataclass
class GamepadButtonEvent:
    """Fired when gamepad button state changes."""
    device_id: int
    button: GamepadButton
    pressed: bool
    timestamp: float = field(default_factory=time)
    source: Any = None

@dataclass
class GamepadAxisEvent:
    """Fired when gamepad axis moves significantly."""
    device_id: int
    axis: GamepadAxis
    value: float  # -1.0 to 1.0
    timestamp: float = field(default_factory=time)
    source: Any = None

class GamepadManager:
    """Manages gamepad input and state."""

    def __init__(self, dispatcher: EventDispatcher, config: Optional[GamepadConfig] = None):
        self._dispatcher = dispatcher
        self._config = config or GamepadConfig()

        # Device ID -> pygame.joystick.Joystick
        self._joysticks: Dict[int, pygame.joystick.Joystick] = {}

        # Device ID -> GamepadState
        self._states: Dict[int, GamepadState] = {}

        # Initialize pygame joystick module
        pygame.joystick.init()

        # Detect connected controllers
        self._scan_devices()

    def _scan_devices(self) -> None:
        """Scan for connected gamepad devices."""
        for i in range(pygame.joystick.get_count()):
            if i not in self._joysticks:
                self._connect_device(i)

    def _connect_device(self, device_id: int) -> None:
        """Initialize a gamepad device."""
        joystick = pygame.joystick.Joystick(device_id)
        joystick.init()

        self._joysticks[device_id] = joystick
        self._states[device_id] = GamepadState(
            device_id=device_id,
            name=joystick.get_name(),
            buttons={btn: False for btn in GamepadButton},
            axes={axis: 0.0 for axis in GamepadAxis}
        )

        print(f"[Input] Gamepad connected: {joystick.get_name()} (ID: {device_id})")

    def _disconnect_device(self, device_id: int) -> None:
        """Handle gamepad disconnection."""
        if device_id in self._joysticks:
            self._joysticks[device_id].quit()
            del self._joysticks[device_id]

            if device_id in self._states:
                self._states[device_id].connected = False

            print(f"[Input] Gamepad disconnected: ID {device_id}")

    def update(self) -> None:
        """Update gamepad states (call each frame)."""
        # Check for new devices (hot-plug)
        self._scan_devices()

        for device_id, joystick in self._joysticks.items():
            state = self._states[device_id]

            # Update button states
            for button in GamepadButton:
                if button.value < joystick.get_numbuttons():
                    pressed = joystick.get_button(button.value)

                    # Fire event on state change
                    if pressed != state.buttons[button]:
                        state.buttons[button] = pressed
                        self._dispatcher.dispatch(GamepadButtonEvent(
                            device_id=device_id,
                            button=button,
                            pressed=pressed
                        ))

            # Update axis states
            for axis in GamepadAxis:
                if axis.value < joystick.get_numaxes():
                    raw_value = joystick.get_axis(axis.value)

                    # Apply deadzone
                    if abs(raw_value) < self._config.deadzone:
                        value = 0.0
                    else:
                        # Scale to account for deadzone
                        sign = 1 if raw_value > 0 else -1
                        value = sign * (abs(raw_value) - self._config.deadzone) / (1.0 - self._config.deadzone)

                    # Fire event if changed significantly
                    if abs(value - state.axes[axis]) > 0.01:
                        state.axes[axis] = value
                        self._dispatcher.dispatch(GamepadAxisEvent(
                            device_id=device_id,
                            axis=axis,
                            value=value
                        ))

    def get_button(self, device_id: int, button: GamepadButton) -> bool:
        """Check if a button is currently pressed."""
        if device_id in self._states:
            return self._states[device_id].buttons.get(button, False)
        return False

    def get_axis(self, device_id: int, axis: GamepadAxis) -> float:
        """Get current axis value (-1.0 to 1.0)."""
        if device_id in self._states:
            return self._states[device_id].axes.get(axis, 0.0)
        return 0.0

    def get_connected_gamepads(self) -> list[GamepadState]:
        """Return list of all connected gamepads."""
        return [s for s in self._states.values() if s.connected]

    def set_rumble(self, device_id: int, low_freq: float, high_freq: float, duration_ms: int) -> None:
        """Trigger controller vibration (if supported).

        Args:
            device_id: Controller to vibrate
            low_freq: Low frequency motor strength (0.0 to 1.0)
            high_freq: High frequency motor strength (0.0 to 1.0)
            duration_ms: Duration in milliseconds
        """
        if device_id in self._joysticks:
            joystick = self._joysticks[device_id]
            # Note: pygame 2.0+ supports rumble
            if hasattr(joystick, 'rumble'):
                joystick.rumble(low_freq, high_freq, duration_ms)
```

**Step 3: Integrate with InputManager**
```python
# input/manager.py (modifications)
class InputManager:
    def __init__(self, dispatcher: EventDispatcher):
        self._dispatcher = dispatcher
        # ... existing code ...

        # NEW: Add gamepad manager
        self._gamepad_manager = GamepadManager(dispatcher)

    def update(self) -> None:
        """Update input state (call each frame)."""
        # ... existing keyboard/mouse updates ...

        # NEW: Update gamepads
        self._gamepad_manager.update()

    @property
    def gamepads(self) -> GamepadManager:
        """Access to gamepad subsystem."""
        return self._gamepad_manager
```

**Step 4: Add tests**
```python
# tests/test_input.py
def test_gamepad_button_press(mock_joystick):
    """Verify button press events fire correctly."""
    dispatcher = EventDispatcher()
    gamepad_mgr = GamepadManager(dispatcher)

    events_received = []
    dispatcher.subscribe(GamepadButtonEvent, lambda e: events_received.append(e))

    # Simulate button press
    mock_joystick.get_button.return_value = True
    gamepad_mgr.update()

    assert len(events_received) == 1
    assert events_received[0].button == GamepadButton.A
    assert events_received[0].pressed == True

def test_deadzone_application():
    """Verify deadzone filters small movements."""
    config = GamepadConfig(deadzone=0.15)
    gamepad_mgr = GamepadManager(EventDispatcher(), config)

    # Simulate small stick movement (within deadzone)
    # Should return 0.0

    # Simulate large stick movement (outside deadzone)
    # Should return scaled value
```

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

---

**END OF DOCUMENT**

*This Product Enhancement Proposal is a living document and will be updated as implementation progresses.*
