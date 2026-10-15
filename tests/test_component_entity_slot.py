"""Every component reports `entity` as None before it is attached.

`BaseComponent.__slots__` declares `entity` and `BaseComponent.__init__`
assigns it -- but almost every component is a `@dataclass`, and the
generated `__init__` never chains to the base. So the slot stays unset and
reading `entity` raises `AttributeError` instead of returning None.

The engine's answer is a `__post_init__` in each component that calls the
base `__init__` by name, which ~35 modules do in two different spellings.
Nothing enforced it, and four components shipped without it: `LightSource`,
`AmbientLight`, `Navigator` and `PrefabInstance`.

Fixing it centrally was measured and rejected. A `__new__` on the base cost
~190ns on *every* component construction; a `__getattr__` was free to
construct but disabled CPython's generic-attribute fast path for every
component instance, making ordinary reads 27% slower and property reads 90%
slower -- and components are read thousands of times a frame. See
`docs/guides/performance.md`.

So the guard is this test rather than a runtime cost: it finds every
component by reflection, so a new one that forgets the call fails here
instead of at whatever line first reads `entity`.
"""

import dataclasses
import importlib
import inspect
import pkgutil
from unittest.mock import MagicMock

import pytest

import pyguara
from pyguara.ecs.component import BaseComponent


def _every_component() -> list[type]:
    """Import the whole package, then collect `BaseComponent`'s subclasses.

    The import walk is what makes this exhaustive: a component in a module
    no test imports is still a component, and is exactly the one likely to
    be missed.
    """
    for module in pkgutil.walk_packages(pyguara.__path__, "pyguara."):
        try:
            importlib.import_module(module.name)
        except Exception:  # noqa: BLE001 - an optional backend, not our concern
            continue

    found: list[type] = []

    def walk(cls: type) -> None:
        for sub in cls.__subclasses__():
            found.append(sub)
            walk(sub)

    walk(BaseComponent)

    # Engine components only. `__subclasses__()` also sees components that
    # other test modules define, and which of those exist depends on what
    # the session has imported -- so including them makes this test
    # order-dependent, and makes it police fixtures rather than the engine.
    engine = [c for c in found if c.__module__.startswith("pyguara.")]
    return sorted(set(engine), key=lambda c: f"{c.__module__}.{c.__name__}")


def _construct(cls: type) -> object:
    """Build `cls`, mocking whatever its constructor insists on.

    Three shapes to cover: a component that takes nothing, a dataclass
    with required fields, and a component with a hand-written `__init__`
    (`Animator`, `AnimationStateMachine`, `DirectionalAnimator`). Raises
    if none works, so a component is never skipped quietly -- a skip here
    would read as a pass.
    """
    try:
        return cls()
    except TypeError:
        pass

    if dataclasses.is_dataclass(cls):
        required = {
            f.name: MagicMock()
            for f in dataclasses.fields(cls)
            if f.default is dataclasses.MISSING
            and f.default_factory is dataclasses.MISSING
        }
        return cls(**required)

    parameters = inspect.signature(cls.__init__).parameters
    required = {
        name: MagicMock()
        for name, p in parameters.items()
        if name != "self"
        and p.default is inspect.Parameter.empty
        and p.kind
        not in (inspect.Parameter.VAR_POSITIONAL, inspect.Parameter.VAR_KEYWORD)
    }
    return cls(**required)


COMPONENTS = _every_component()


def test_reflection_found_the_components():
    """A guard on the guard: if the import walk silently found nothing, the
    parametrised test below would vacuously pass."""
    assert len(COMPONENTS) > 30, f"only found {len(COMPONENTS)} components"


@pytest.mark.parametrize(
    "component", COMPONENTS, ids=lambda c: f"{c.__module__}.{c.__name__}"
)
def test_entity_reads_as_none_before_attach(component):
    instance = _construct(component)

    try:
        entity = instance.entity
    except AttributeError as exc:
        pytest.fail(
            f"{component.__module__}.{component.__name__} never initialises the "
            f"`entity` slot ({exc}). Add a `__post_init__` calling "
            f"`{component.__mro__[1].__name__}.__init__(self)`."
        )

    assert entity is None
