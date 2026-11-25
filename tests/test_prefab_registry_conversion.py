"""Prefab data converts to a field's type, or says why it cannot."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

import pytest

from pyguara.common.types import Color, Vector2
from pyguara.ecs.component import BaseComponent
from pyguara.prefabs import ComponentRegistry

if TYPE_CHECKING:
    from pyguara.ai.behavior_tree import BehaviorTree


@dataclass
class Look(BaseComponent):
    """Test data: a colour, a required offset and an optional one."""

    color: Color = field(default_factory=lambda: Color(255, 255, 255))
    offset: Vector2 = field(default_factory=lambda: Vector2(0, 0))
    anchor: Vector2 | None = None
    note: Any = None

    def __post_init__(self) -> None:
        """Initialise the BaseComponent state the dataclass `__init__` skips."""
        BaseComponent.__init__(self)


@dataclass
class Brain(BaseComponent):
    """Test data: one field whose type exists only for type checking."""

    tree: BehaviorTree | None = None
    speed: Vector2 = field(default_factory=lambda: Vector2(0, 0))

    def __post_init__(self) -> None:
        """Initialise the BaseComponent state the dataclass `__init__` skips."""
        BaseComponent.__init__(self)


def _registry() -> ComponentRegistry:
    registry = ComponentRegistry()
    registry.register(Look)
    registry.register(Brain)
    return registry


def _look(**data: Any) -> Look:
    component = _registry().create("Look", data)
    assert isinstance(component, Look)
    return component


class TestColor:
    @pytest.mark.parametrize(
        "data",
        [
            {"r": 255, "g": 200, "b": 80},
            [255, 200, 80],
            "#ffc850",
            Color(255, 200, 80),
        ],
    )
    def test_every_spelling_gives_the_same_colour(self, data: Any) -> None:
        assert _look(color=data).color == Color(255, 200, 80)

    def test_alpha_is_kept(self) -> None:
        assert _look(color={"r": 1, "g": 2, "b": 3, "a": 4}).color == Color(1, 2, 3, 4)
        assert _look(color=[1, 2, 3, 4]).color == Color(1, 2, 3, 4)

    @pytest.mark.parametrize(
        "data",
        [{"r": 1, "g": 2}, {"r": 1, "g": 2, "b": 3, "x": 0}, [1, 2], [1, "2", 3], 7],
    )
    def test_anything_else_is_refused(self, data: Any) -> None:
        with pytest.raises(ValueError, match="Color"):
            _look(color=data)


class TestVector2:
    @pytest.mark.parametrize("data", [{"x": 3, "y": 4}, [3, 4], (3, 4)])
    def test_a_dict_or_a_pair_converts(self, data: Any) -> None:
        assert _look(offset=data).offset == Vector2(3, 4)

    @pytest.mark.parametrize(
        "data", [{"x": 3}, {"x": 3, "y": 4, "z": 5}, [3], "3,4", 3]
    )
    def test_a_partial_or_wrong_shape_is_refused(self, data: Any) -> None:
        with pytest.raises(ValueError, match="Vector2"):
            _look(offset=data)

    def test_an_optional_field_converts_through_its_type(self) -> None:
        assert _look(anchor={"x": 1, "y": 2}).anchor == Vector2(1, 2)
        with pytest.raises(ValueError, match="Vector2"):
            _look(anchor={"x": 1})

    def test_a_field_of_any_type_keeps_its_dict(self) -> None:
        assert _look(note={"x": 1, "y": 2}).note == {"x": 1, "y": 2}


class TestTransform:
    @pytest.mark.parametrize(
        ("data", "match"),
        [
            ({"positon": {"x": 1, "y": 2}}, r"no field\(s\) \['positon'\]"),
            ({"position": {"x": 1}}, "Vector2"),
            ({"rotation": "90"}, "rotation is a number"),
            ({"interpolate": "false"}, "interpolate is true or false"),
        ],
    )
    def test_bad_data_is_refused(self, data: dict[str, Any], match: str) -> None:
        from pyguara.common.components import Transform

        registry = ComponentRegistry()
        registry.register(Transform)
        with pytest.raises(ValueError, match=match):
            registry.create("Transform", data)


class TestUnresolvedAnnotations:
    def test_the_other_fields_still_convert(self) -> None:
        brain = _registry().create("Brain", {"speed": {"x": 1, "y": 2}})
        assert isinstance(brain, Brain)
        assert brain.speed == Vector2(1, 2)

    def test_setting_the_unresolved_field_names_it(self) -> None:
        with pytest.raises(ValueError, match="Brain.tree cannot be set from data"):
            _registry().create("Brain", {"tree": {}})


def test_a_cleared_registry_still_converts_colours() -> None:
    registry = _registry()
    registry.clear()
    registry.register(Look)
    look = registry.create("Look", {"color": [9, 8, 7]})
    assert isinstance(look, Look)
    assert look.color == Color(9, 8, 7)
