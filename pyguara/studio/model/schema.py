"""What a component looks like, derived from the component itself.

Drives three things: the Inspector's widgets, the schema browser, and the
JSON Schema an agent reads to learn what arguments an operation takes.
One emitter rather than three, because they were going to disagree.

Two kinds of component have to be handled, and the second is the reason
this is not four lines of `dataclasses.fields`:

- **Dataclasses**, which is most of them. Fields, types and defaults all
  come from the decorator.
- **`StrictComponent`s built from properties**, of which `Transform` is
  the one that matters. It is *not* a dataclass -- it stores private
  fields and exposes `position`, `rotation` and `scale` as properties with
  setters, plus `interpolate` as a plain attribute. `dataclasses.fields`
  returns nothing for it, which is why the existing reflection sites all
  special-case `Transform` by name. Reflecting over writable properties
  handles it without a name check, and handles the next one like it for
  free.

Read-only derived properties are reported, not hidden: `Transform.
world_position` is genuinely useful to see in an inspector and genuinely
not settable, and an agent told it exists but is read-only will not try.
"""

from __future__ import annotations

import dataclasses
import enum
import re
import typing
from dataclasses import dataclass
from typing import Any

from pyguara.common.types import Color, Vector2
from pyguara.ecs.component import Component
from pyguara.log import get_logger
from pyguara.prefabs.registry import ComponentRegistry
from pyguara.studio.model.values import encode

logger = get_logger(__name__)

# Properties every component inherits or derives that are noise in an
# inspector: the entity back-reference is not authored data, and the
# transform's direction vectors and child list restate what is already
# shown elsewhere.
_HIDDEN_FIELDS = frozenset(
    {
        "entity",
        "children",
        "right",
        "left",
        "up",
        "down",
        "forward",
    }
)

# Fields that restate state stored elsewhere. They are reported in a
# schema -- an inspector showing `world_position` beside `position` is
# useful -- but a *snapshot* skips them, because they are not independent
# state and recording them makes one edit look like several: setting
# `Transform.rotation` also moves `rotation_degrees` and `world_rotation`,
# and a diff that says so three times buries the edits that matter.
#
# Named explicitly rather than guessed. A heuristic ("a property is
# derived unless it has matching private storage") gets `world_position`
# wrong, because that one *is* backed by a field -- a cache, not state.
# The set is small and belongs to classes this engine owns.
_DERIVED_FIELDS = frozenset(
    {
        # Transform: alternative views of the local rotation, the resolved
        # world transform, and the render-interpolation snapshot that
        # `SceneManager.fixed_update()` rewrites every tick.
        "rotation_degrees",
        "world_position",
        "world_rotation",
        "world_scale",
        "previous_position",
    }
)

_JSON_TYPES: dict[type, str] = {
    bool: "boolean",
    int: "integer",
    float: "number",
    str: "string",
}


@dataclass(frozen=True)
class FieldSchema:
    """One field of one component.

    Attributes:
        name: The field's name.
        type_name: Its declared type's name, or the runtime type's name
            when there is no annotation.
        writable: Whether assigning to it works. False for a derived
            property and for every field of a frozen dataclass.
        editable: Whether Studio and an agent can set it from JSON. A
            writable field holding a texture is not editable: there is no
            JSON form for a resource handle to arrive as.
        default: Its default, encoded, or None when it has none.
        has_default: Whether `default` means anything -- distinguishing
            "defaults to None" from "has no default".
        doc: The property's docstring, where there is one.
        enum_values: Every accepted value, when the field holds an enum.
            Carried on the field rather than looked up later because this
            is the one piece of information an agent cannot guess and
            cannot discover from an error it has not made yet.
        derived: Whether the field restates state stored elsewhere. Shown
            in an inspector, skipped by a snapshot -- see
            `_DERIVED_FIELDS`.
    """

    name: str
    type_name: str
    writable: bool
    editable: bool
    default: Any = None
    has_default: bool = False
    doc: str | None = None
    enum_values: tuple[str, ...] = ()
    derived: bool = False

    def to_dict(self) -> dict[str, Any]:
        """Return the JSON-serializable form.

        Returns:
            The field as a plain dict, with empty keys omitted so a
            schema handed to an agent carries no filler.
        """
        data: dict[str, Any] = {
            "name": self.name,
            "type": self.type_name,
            "writable": self.writable,
            "editable": self.editable,
        }
        if self.has_default:
            data["default"] = self.default
        if self.doc:
            data["doc"] = self.doc
        if self.enum_values:
            data["values"] = list(self.enum_values)
        if self.derived:
            data["derived"] = True
        return data


@dataclass(frozen=True)
class ComponentSchema:
    """A component's authorable shape.

    Attributes:
        name: The component's registered name, which is its class name.
        kind: How it was reflected -- "dataclass" or "properties".
        frozen: Whether it is a frozen dataclass, so no field is writable.
        doc: The class docstring's first line.
        fields: Its fields, in declaration order.
    """

    name: str
    kind: str
    frozen: bool
    doc: str | None
    fields: tuple[FieldSchema, ...]

    @property
    def editable_fields(self) -> tuple[FieldSchema, ...]:
        """The fields Studio and an agent can actually set."""
        return tuple(field for field in self.fields if field.editable)

    @property
    def stateful_fields(self) -> tuple[FieldSchema, ...]:
        """The fields that hold independent state.

        What a snapshot records: everything except the derived views, so
        one edit reads as one change rather than several.
        """
        return tuple(field for field in self.fields if not field.derived)

    def field(self, name: str) -> FieldSchema | None:
        """Look one field up by name.

        Args:
            name: The field name.

        Returns:
            The field, or None when there is no such field.
        """
        for field in self.fields:
            if field.name == name:
                return field
        return None

    def to_dict(self) -> dict[str, Any]:
        """Return the JSON-serializable form.

        Returns:
            The schema as a plain dict.
        """
        data: dict[str, Any] = {
            "name": self.name,
            "kind": self.kind,
            "fields": [field.to_dict() for field in self.fields],
        }
        if self.frozen:
            data["frozen"] = True
        if self.doc:
            data["doc"] = self.doc
        return data

    def to_json_schema(self) -> dict[str, Any]:
        """Return a JSON Schema for this component's authorable fields.

        What an agent is given as the argument schema for "add a component
        of this type": an object whose properties are the editable fields.
        Nothing is required -- every component here is constructible from
        its defaults, and a partial dict is the normal way to author one.

        Returns:
            A JSON Schema object.
        """
        properties: dict[str, Any] = {}
        for field in self.editable_fields:
            properties[field.name] = _json_type_for(field)

        return {
            "type": "object",
            "title": self.name,
            **({"description": self.doc} if self.doc else {}),
            "properties": properties,
            "additionalProperties": False,
        }


def describe_component(component_type: type[Component]) -> ComponentSchema:
    """Reflect over `component_type` and return its schema.

    Args:
        component_type: The component class to describe.

    Returns:
        Its schema.
    """
    doc = _first_line(component_type.__doc__)
    params = getattr(component_type, "__dataclass_params__", None)
    frozen = bool(getattr(params, "frozen", False))

    # Widened to `object` first: `is_dataclass` is a TypeGuard, and
    # narrowing the `Component` protocol through it leaves mypy with an
    # empty intersection, so it calls the branch below dead code. The same
    # dance `editor/panels/inspector.py` documents.
    candidate: object = component_type
    if dataclasses.is_dataclass(candidate):
        return ComponentSchema(
            name=component_type.__name__,
            kind="dataclass",
            frozen=frozen,
            doc=doc,
            fields=_dataclass_fields(component_type, frozen=frozen),
        )

    return ComponentSchema(
        name=component_type.__name__,
        kind="properties",
        frozen=False,
        doc=doc,
        fields=_property_fields(component_type),
    )


def describe_registry(registry: ComponentRegistry) -> dict[str, ComponentSchema]:
    """Describe every component the registry knows.

    `ComponentRegistry.list_components()` returns names only, so a schema
    browser has to pair it with `get()` itself. This is that pairing.

    Args:
        registry: The registry to read.

    Returns:
        Schemas by component name, including only the names that resolve.
    """
    schemas: dict[str, ComponentSchema] = {}
    for name in registry.list_components():
        component_type = registry.get(name)
        if component_type is None:  # pragma: no cover - list_components is the keys
            continue
        try:
            schemas[name] = describe_component(component_type)
        except Exception as exc:
            # A component whose annotations will not resolve must not take
            # the whole schema browser down with it.
            logger.warning(f"Could not describe component '{name}': {exc}")
    return schemas


def _dataclass_fields(
    component_type: type[Component], *, frozen: bool
) -> tuple[FieldSchema, ...]:
    """Reflect a dataclass component's fields.

    Args:
        component_type: The dataclass to reflect.
        frozen: Whether assignment to its fields raises.

    Returns:
        Its fields, in declaration order.
    """
    # Resolved separately from `field.type`, which is the *string*
    # `"Vector2"` for every module using `from __future__ import
    # annotations` -- which is all of them here.
    hints = _resolved_hints(component_type)

    # Widened to `object` first: `is_dataclass` is a TypeGuard, and
    # narrowing `type[Component]` through it leaves mypy unable to accept
    # the result as a dataclass type.
    as_dataclass: Any = component_type
    fields: list[FieldSchema] = []
    for field in dataclasses.fields(as_dataclass):
        if field.name.startswith("_") or field.name in _HIDDEN_FIELDS:
            continue

        declared = hints.get(field.name, field.type)
        default, has_default = _dataclass_default(field)
        fields.append(
            FieldSchema(
                name=field.name,
                type_name=_type_label(declared),
                writable=not frozen,
                editable=not frozen and _is_editable_type(declared),
                default=encode(default) if has_default else None,
                has_default=has_default,
                enum_values=_enum_values(declared),
                derived=field.name in _DERIVED_FIELDS,
            )
        )
    return tuple(fields)


def _property_fields(component_type: type[Component]) -> tuple[FieldSchema, ...]:
    """Reflect a property-based component's fields.

    Covers `Transform`, which stores private state and exposes properties.
    Class annotations are included too, so a plain attribute like
    `Transform.interpolate` -- declared but not a property -- is not lost.

    Args:
        component_type: The class to reflect.

    Returns:
        Its fields, properties first, in declaration order.
    """
    hints = _resolved_hints(component_type)
    fields: list[FieldSchema] = []
    seen: set[str] = set()

    # `vars()` per class in MRO order, so a subclass's override of an
    # inherited property is reported once, at the subclass's position.
    for klass in component_type.__mro__:
        for name, member in vars(klass).items():
            if name.startswith("_") or name in _HIDDEN_FIELDS or name in seen:
                continue
            if not isinstance(member, property):
                continue
            seen.add(name)
            declared = hints.get(name, _return_annotation(member))
            fields.append(
                FieldSchema(
                    name=name,
                    type_name=_type_label(declared),
                    writable=member.fset is not None,
                    editable=member.fset is not None and _is_editable_type(declared),
                    doc=_first_line(member.__doc__),
                    enum_values=_enum_values(declared),
                    derived=name in _DERIVED_FIELDS,
                )
            )

    for name, declared in hints.items():
        if name.startswith("_") or name in _HIDDEN_FIELDS or name in seen:
            continue
        seen.add(name)
        fields.append(
            FieldSchema(
                name=name,
                type_name=_type_label(declared),
                writable=True,
                editable=_is_editable_type(declared),
                enum_values=_enum_values(declared),
                derived=name in _DERIVED_FIELDS,
            )
        )

    fields.extend(_instance_attribute_fields(component_type, seen))
    return tuple(fields)


def _instance_attribute_fields(
    component_type: type[Component], seen: set[str]
) -> list[FieldSchema]:
    """Reflect public attributes that only exist on an instance.

    `Transform.interpolate` is assigned in `__init__` with no class-level
    annotation, so `get_type_hints` cannot see it -- yet it is authored
    state that the scene serializer round-trips and an inspector should
    show. Building a default instance is the only way to find it.

    Only attempted for classes that construct with no arguments, and any
    failure is ignored: a component that needs constructor arguments is
    described from its class alone, which for a dataclass is complete
    anyway.

    Args:
        component_type: The class to probe.
        seen: Field names already reported, which are skipped.

    Returns:
        Extra fields, sorted by name for a stable schema.
    """
    try:
        probe = component_type()
    except Exception:
        return []

    instance_dict = getattr(probe, "__dict__", None)
    if not instance_dict:
        return []

    fields: list[FieldSchema] = []
    for name, value in sorted(instance_dict.items()):
        if name.startswith("_") or name in _HIDDEN_FIELDS or name in seen:
            continue
        declared = type(value) if value is not None else None
        fields.append(
            FieldSchema(
                name=name,
                type_name=_type_label(declared),
                writable=True,
                editable=_is_editable_type(declared),
                default=encode(value),
                has_default=True,
                enum_values=_enum_values(declared),
                derived=name in _DERIVED_FIELDS,
            )
        )
    return fields


def _resolved_hints(component_type: type) -> dict[str, Any]:
    """Return `component_type`'s type hints as objects, not strings.

    Args:
        component_type: The class to resolve hints for.

    Returns:
        Hints by attribute name, empty when they cannot be resolved -- a
        forward reference to something not importable at runtime is a
        reason to describe a component with less detail, not to fail.
    """
    try:
        return typing.get_type_hints(component_type)
    except Exception as exc:
        logger.debug(f"Could not resolve hints for {component_type.__name__}: {exc}")
        return {}


def _dataclass_default(field: dataclasses.Field[Any]) -> tuple[Any, bool]:
    """Return a dataclass field's default and whether it has one.

    Args:
        field: The field to inspect.

    Returns:
        `(default, has_default)`. A `default_factory` is called, which is
        safe for the factories in use here -- `Vector2.zero`, `lambda:
        Color(...)`, `set`, `dict` -- and is the only way to see what the
        default actually is.
    """
    if field.default is not dataclasses.MISSING:
        return field.default, True
    if field.default_factory is not dataclasses.MISSING:
        try:
            return field.default_factory(), True
        except Exception:  # pragma: no cover - factories here are trivial
            return None, False
    return None, False


def _return_annotation(member: property) -> Any:
    """Return a property getter's return annotation, if it has one.

    Args:
        member: The property to inspect.

    Returns:
        The annotation, or None.
    """
    if member.fget is None:  # pragma: no cover - a setter-only property
        return None
    try:
        return typing.get_type_hints(member.fget).get("return")
    except Exception:  # pragma: no cover - unresolvable annotation
        return None


def _strip_optional(declared: Any) -> Any:
    """Return `T` for a `T | None` annotation, else `declared` unchanged.

    Args:
        declared: The annotation.

    Returns:
        The non-None member of a two-member union, or the input.
    """
    args = typing.get_args(declared)
    if not args:
        return declared
    non_none = [arg for arg in args if arg is not type(None)]
    if len(non_none) == 1:
        return non_none[0]
    return declared


def _is_editable_type(declared: Any) -> bool:
    """Whether a field of this declared type can be set from JSON.

    Args:
        declared: The field's resolved annotation.

    Returns:
        True when `values.decode` can produce a value of this type.
    """
    declared = _strip_optional(declared)

    if declared in (bool, int, float, str, Vector2, Color):
        return True
    if isinstance(declared, type) and issubclass(declared, enum.Enum):
        return True
    if isinstance(declared, type) and issubclass(declared, Vector2):
        return True

    # A nested dataclass -- `Collider.material`, `Collider.layer` -- is
    # editable: it encodes to a dict of its fields and `values.decode`
    # rebuilds it from one. Tweaking a physics material's friction is
    # exactly the sort of edit this is for.
    if (
        isinstance(declared, type)
        and dataclasses.is_dataclass(declared)
        and not issubclass(declared, enum.Enum)
    ):
        return True

    origin = typing.get_origin(declared)
    if origin in (list, tuple, set, frozenset):
        args = typing.get_args(declared)
        # An unparameterised `list` says nothing about its contents, so it
        # is treated as editable; a parameterised one is editable when its
        # element type is.
        return all(_is_editable_type(arg) for arg in args if arg is not Ellipsis)

    # A dict field round-trips as a JSON object whatever its value type:
    # `encode` walks it and `decode` hands it straight back.
    return origin is dict


def _enum_values(declared: Any) -> tuple[str, ...]:
    """Return every accepted name for an enum-typed field.

    Names rather than values, because a name is what a human types and
    what reads well in an error; `values.decode` accepts either.

    Args:
        declared: The field's resolved annotation.

    Returns:
        The member names, sorted, or empty when the field is not an enum.
    """
    declared = _strip_optional(declared)
    if isinstance(declared, type) and issubclass(declared, enum.Enum):
        return tuple(sorted(declared.__members__))
    return ()


def _type_label(declared: Any) -> str:
    """Return a readable name for an annotation.

    Args:
        declared: The annotation, which may be a class, a string, or a
            parameterised generic.

    Returns:
        A short name suitable for display and for a schema.
    """
    if declared is None:
        return "unknown"
    if isinstance(declared, str):
        return declared
    if isinstance(declared, type):
        return declared.__name__
    # `list[str]`, `Transform | None` and friends have no __name__; their
    # str is already the readable form once the module paths are stripped.
    # Those matter: `pyguara.common.components.Transform | None` is the
    # same information as `Transform | None` and four times as long, in a
    # schema an agent pays for by the token.
    label = str(declared).replace("typing.", "")
    return re.sub(
        r"\b(?:[A-Za-z_][A-Za-z_0-9]*\.)+([A-Za-z_][A-Za-z_0-9]*)", r"\1", label
    )


def _json_type_for(field: FieldSchema) -> dict[str, Any]:
    """Return the JSON Schema fragment describing one field.

    Args:
        field: The field to describe.

    Returns:
        A JSON Schema fragment.
    """
    fragment: dict[str, Any] = {}
    if field.doc:
        fragment["description"] = field.doc

    if field.type_name == "Vector2":
        fragment.update(
            {
                "type": "object",
                "properties": {"x": {"type": "number"}, "y": {"type": "number"}},
                "required": ["x", "y"],
            }
        )
        return fragment

    if field.type_name == "Color":
        channel = {"type": "integer", "minimum": 0, "maximum": 255}
        fragment.update(
            {
                "type": "object",
                "properties": {
                    "r": channel,
                    "g": channel,
                    "b": channel,
                    "a": channel,
                },
                "required": ["r", "g", "b"],
            }
        )
        return fragment

    for python_type, json_type in _JSON_TYPES.items():
        if field.type_name == python_type.__name__:
            fragment["type"] = json_type
            if field.has_default:
                fragment["default"] = field.default
            return fragment

    if field.type_name.startswith(("list", "tuple", "set")):
        fragment["type"] = "array"
        return fragment
    if field.type_name.startswith("dict"):
        fragment["type"] = "object"
        return fragment

    if field.enum_values:
        fragment["enum"] = list(field.enum_values)
        fragment["description"] = (
            f"{field.doc + ' ' if field.doc else ''}({field.type_name})"
        )
        return fragment

    # Anything else: the type is named for a reader and left unconstrained
    # for a validator.
    fragment["description"] = (
        f"{field.doc + ' ' if field.doc else ''}({field.type_name})"
    )
    return fragment


def _first_line(doc: str | None) -> str | None:
    """Return a docstring's summary line.

    Args:
        doc: The docstring, or None.

    Returns:
        Its first non-empty line, or None.
    """
    if not doc:
        return None
    for line in doc.strip().splitlines():
        stripped = line.strip()
        if stripped:
            return stripped
    return None  # pragma: no cover - a docstring of only whitespace
