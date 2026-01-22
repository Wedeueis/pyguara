# Architecture & Style Guide

## 1. Design Principles

### 1.1. SOLID Compliance

- **S - Single Responsibility**: Each class has ONE reason to change
- **O - Open/Closed**: Extend via protocols, not modification
- **L - Liskov Substitution**: Subtypes must be substitutable
- **I - Interface Segregation**: Prefer small, focused protocols
- **D - Dependency Inversion**: Depend on abstractions (protocols)

### 1.2. PyGuara-Specific Patterns

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

## 2. Code Style Standards

### 2.1. Formatting (Enforced by Ruff)

```markdown
# Line length: 88 characters (Black style)
# Quotes: Double quotes for strings
# Indentation: 4 spaces (no tabs)
# Imports: Sorted (isort), grouped (stdlib, third-party, local)
# Trailing commas: Yes (in multiline collections)
```

### 2.2. Naming Conventions

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

### 2.3. Type Annotations

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

### 2.4. Docstring Format (Google Style)

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

## 3. Architectural Patterns

### 3.1. Component Definition

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

### 3.2. System Definition

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

### 3.3. Service Registration

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

### 3.4. Event Definition and Usage

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

## 4. File Organization

```markdown
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

## 5. Error Handling Strategy

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

## 6. Repository Policies

### 6.1 Branch Strategy

```markdown
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

### 6.2 Commit Message Format

```markdown
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

### 6.3 Pull Request Process

#### 6.3.1 PR Template

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

#### 6.3.2 Review Requirements

- **Minimum Reviewers:** 1 (for large changes: 2)
- **Required Checks:**
  - ✅ CI tests pass
  - ✅ Code coverage doesn't decrease
  - ✅ Ruff and mypy checks pass
  - ✅ No merge conflicts
- **Approval Required:** Yes (from code owner or maintainer)

### 6.4 Issue Management

#### 6.4.1 Issue Labels

```markdown
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

#### 6.4.2 Issue Template

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

### 6.5 Testing Requirements

#### 6.5.1 Test Coverage Targets

- **Overall:** ≥ 80%
- **Core Systems (ECS, DI, Events):** ≥ 90%
- **New Features:** ≥ 85%
- **Bug Fixes:** 100% (must include regression test)

#### 6.5.2 Test Structure

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

#### 6.5.3 CI/CD Pipeline

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

### 6.6 Documentation Standards

#### 6.6.1 Required Documentation for Features

1. **API Reference**: Auto-generated from docstrings
2. **Tutorial**: Step-by-step guide for common use case
3. **Example**: Working code snippet in examples/
4. **Architecture Decision Record**: For significant design choices

#### 6.6.2 ADR Template

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

## 7. Quality Gates & Acceptance Criteria

### 7.1 Definition of Done (DoD)

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

### 7.2 Release Criteria

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

### 7.3 Performance Benchmarks

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

### 7.4 Security Checklist

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
| 1.0 | 2026-01-09 | Wedeueis Braz | Initial draft |
