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

- ✅ Use `Protocol` for all interfaces, not ABCs
- ✅ Use `dataclass` for DTOs and components
- ✅ Use type hints for ALL public APIs
- ✅ Use DI container for cross-cutting concerns
- ✅ Use events for decoupled communication
- ✅ Use generators for large result sets
- ✅ Use context managers for resource management

**DON'T:**

- ❌ Don't use inheritance for behavior sharing (use composition)
- ❌ Don't put logic in components (data only)
- ❌ Don't import a backend (pygame, the native module) outside its `backends/` directory; game code uses the protocols
- ❌ Don't use singletons (use DI instead)
- ❌ Don't use global state
- ❌ Don't use `print()` (use `pyguara.log.get_logger`)
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

# Type parameters: PEP 695 syntax (Python 3.12+), a single capital
# letter or PascalCase with a T suffix
def first[T](items: list[T]) -> T: ...
def get[ComponentT: Component](kind: type[ComponentT]) -> ComponentT: ...

# Protocols: I prefix for interfaces (optional but recommended)
class IRenderer(Protocol): ...
```

### 2.3. Type Annotations

```python
# Always annotate function signatures
def create_entity(self, entity_id: str | None = None) -> Entity:
    ...

# Always annotate class attributes
class Component:
    entity: Entity | None

# Use NewType for domain-specific types
EntityID = NewType("EntityID", str)

# Use Protocol for structural typing
class Renderable(Protocol):
    @property
    def position(self) -> Vector2: ...
```

### 2.4. Docstring Format (Google Style)

The full standard, and what does not belong in a docstring, is in
[Docstrings](../agents/docstrings.md). `make lint` checks both.

```python
def complex_function(param1: int, param2: str) -> dict[str, Any]:
    """Brief one-line summary.

    Longer description if needed: what a caller cannot see from the
    signature. At most 8 lines.

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

@dataclass(slots=True)
class Health(BaseComponent):
    """Hit points.

    Document what the fields mean and their units.
    """
    current: float = 100.0
    maximum: float = 100.0

    # NO METHODS (data only). BaseComponent raises TypeError at class
    # definition if one is declared. Logic goes in a system, or in a free
    # function beside the component.


@dataclass(slots=True)
class Velocity(BaseComponent):
    """Linear velocity in units per second."""
    value: Vector2 = Vector2(0, 0)
```

### 3.2. System Definition

```python
from pyguara.ecs.manager import EntityManager

class MovementSystem:
    """Integrates each entity's velocity into its Transform every frame.

    A system is stateless: it owns no game data, only references to the
    services it queries. All state lives in the components it reads
    (the engine's `Transform`, and `Velocity` from 3.1).
    """

    def __init__(self, entity_manager: EntityManager):
        self._entities = entity_manager

    def update(self, dt: float) -> None:
        for entity in self._entities.get_entities_with(Transform, Velocity):
            transform = entity.get_component(Transform)
            velocity = entity.get_component(Velocity)
            transform.position += velocity.value * dt
            # Anything mirroring the component keeps the old value otherwise.
            self._entities.notify_component_changed(entity.id, Transform)
```

For simulated rigid bodies, do not hand-roll this: add `RigidBody` /
`Collider` components and let the engine's `PhysicsSystem` own the
Transform↔body sync. For player and NPC movement, use `CharacterBody` with
`CharacterMover`. See `docs/physics/simulation.md` and
`docs/physics/character-movement.md`.

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
    container.register_scoped(SceneResources, SceneResources)

    return container
```

Bootstrap registers the core services (see `pyguara/application/bootstrap.py`).
Gameplay systems such as `PhysicsSystem` are not registered here — a scene
constructs the ones it needs and registers them with its own
`SystemManager`, at priority 500 or above. A game adds its own services by
calling `create_container()` and registering on the result.

### 3.4. Event Definition and Usage

```python
from dataclasses import dataclass, field
from time import time
from typing import Any

# `Event` is a Protocol: any dataclass with `timestamp` and `source`
# qualifies. From a background thread, emit with `queue_event()`, never
# `dispatch()`.
@dataclass
class EntityDiedEvent:
    """Fired when an entity's health reaches zero.

    Subscribers can use this to trigger death animations,
    drop loot, update score, etc.
    """
    entity_id: str
    damage_source: str | None = None
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
│       ├── native/          # Wraps the Rust extension
│       └── pygame/
tests/
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

A guard must not return a plausible wrong value. `x or 1`,
`if d != 0 else 0` and a bare `except: pass` have each hidden a real defect
in this codebase; raising is easier to diagnose.

## 6. Repository Policies

`AGENTS.md` at the repository root is the canonical statement of these
rules, for people and coding agents alike. This section summarises it;
where the two disagree, `AGENTS.md` wins.

### 6.1 Branch Strategy

There is no `develop` branch. Every independent branch is cut from `main`:

```bash
git checkout main && git pull --ff-only
git checkout -b <type>/<scope>-<subject>
```

- **Merge commits**, never squash or rebase-and-merge. Commits are split
  deliberately so they review independently.
- **A branch is frozen once its PR is open.** Follow-up work goes on a new
  branch cut from `main`.
- Stack a branch on another only for a real dependency, and say so in the
  PR.

The reasons and the full procedure are in `docs/agents/branching.md`.

### 6.2 Commit Message Format

```markdown
<type>(<scope>): <subject>

<body>
```

**Types:** `feat`, `fix`, `docs`, `refactor`, `perf`, `test`, `ci`,
`chore`.

The subject says what is true after the commit, not what was done:

```markdown
fix(vfx): hash noise with integers, so every GPU draws the same haze and rain
feat(graphics): wgpu is the default renderer; no GPU fails with a way out
```

When a branch carries several commits, each one passes the checks below on
its own, not merely the tip.

### 6.3 Before Opening a Pull Request

```bash
uv run pytest && uv run ruff check . && uv run mypy pyguara
```

All three must pass.

- The native parity suites **skip when the extension is not built**, so a
  green run without it has tested none of the accelerator. Run
  `make native` after editing Rust.
- `tests/visual/` snapshots record the renderer's call stream. Update them
  with `--snapshot-update` and read the diff: a changed snapshot is a
  changed frame.
- A stacked PR names its parent and the merge order in its description.

### 6.4 Issues

Issues live on GitHub, in `Wedeueis/pyguara`. The triage labels are
`needs-triage`, `needs-info`, `ready-for-agent`, `ready-for-human` and
`wontfix`; see `docs/agents/issue-tracker.md` and
`docs/agents/triage-labels.md`.

### 6.5 Testing

- **Reproduce a suspected defect with a throwaway probe before fixing it**,
  and keep the probe as the regression test.
- Select by marker: `pytest -m unit`, `-m integration`, `-m performance`,
  `-m slow`, `-m cli`. `make help` lists the wrapped runs.
- Coverage is gated at **60%** overall (`make coverage-check`).
- **A test that compares against Python uses `tests/reference/`**, never
  the Rust-only class itself, or it compares Rust with itself.
- Do not test a stall with `time.sleep` or a Python busy loop.

CI (`.github/workflows/ci.yml`) runs formatting, lint and mypy; the unit
and integration suites on Python 3.12 and 3.13 with a software Vulkan
driver so the wgpu renderer is exercised; the unit suite again with the
accelerator disabled; the wheel build; and the network suites on Windows.

### 6.6 Documentation

- Public API carries a Google-style docstring.
- A subsystem's reference page lives under `docs/core/`, `docs/systems/`,
  `docs/graphics/` or `docs/physics/`, and is listed in `mkdocs.yml`.
- **Every performance claim carries a before and after number**, added to
  `docs/guides/performance.md`.
- A decision that will keep constraining the code gets a record in
  `docs/adr/`, numbered in sequence. The existing records are the template:
  status and date, context, the decision, its consequences, and what was
  measured.
- User-visible changes go in `CHANGELOG.md`, through a separate changelog
  PR: a feature PR drafts its entry in its body under `## Changelog`. See
  `docs/agents/branching.md`.

## 7. Definition of Done

A change is done when:

- [ ] `pytest`, `ruff check .` and `mypy pyguara` pass, with the native
      extension built
- [ ] Each commit passes on its own
- [ ] A defect fix carries the test that reproduced it
- [ ] Public API has type hints and docstrings
- [ ] No `print()`, no commented-out code, no untracked TODO
- [ ] The reference page for the subsystem says what the code now does
- [ ] A performance claim has its before and after number in
      `docs/guides/performance.md`
- [ ] A rendering change has been looked at with `tools/agent_view.py`,
      bearing in mind that a capture proves the render path, not that a
      window appeared

What is left before the engine is something another team could pick up,
and in what order, is in
`project/backlog/active/engine_completion_roadmap.md`.

---

## Appendix A: Glossary

**ECS**: Entity-Component-System architecture pattern
**DI**: Dependency Injection (IoC container)
**DoD**: Definition of Done
**ADR**: Architecture Decision Record
**HAL**: Hardware Abstraction Layer
**SFX**: Sound Effects
**UI**: User Interface
**DX**: Developer Experience

---

## Appendix B: References

- [PyGuara Repository](https://github.com/Wedeueis/pyguara)
- [Python Type Hints (PEP 484)](https://peps.python.org/pep-0484/)
- [wgpu](https://wgpu.rs) and [pygame-ce Documentation](https://pyga.me/docs/)
- [Pymunk Documentation](http://www.pymunk.org/)
- [ECS FAQ](https://github.com/SanderMertens/ecs-faq)
- [Game Programming Patterns](https://gameprogrammingpatterns.com/)

---

## Document History

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 1.0 | 2026-01-09 | Wedeueis Braz | Initial draft |
