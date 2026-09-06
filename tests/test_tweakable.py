"""Tests for the shared dev-tool tweakable-field dispatch (wayfinder ticket 38)."""

import dataclasses
from enum import Enum, auto
from unittest.mock import MagicMock

from pyguara.common.types import Color, Rect, Vector2
from pyguara.graphics.protocols import UIRenderer
from pyguara.tools.tweakable import (
    TweakableLeaf,
    apply_click,
    collect_tweakable_leaves,
    cycle_enum,
    format_leaf_value,
    render_tweakable_leaves,
)


class Mode(Enum):
    A = auto()
    B = auto()
    C = auto()


@dataclasses.dataclass
class _Inner:
    speed: float = 1.5
    enabled: bool = True


@dataclasses.dataclass
class _Outer:
    mode: Mode = Mode.A
    position: Vector2 = dataclasses.field(default_factory=lambda: Vector2(1.0, 2.0))
    tint: Color = dataclasses.field(default_factory=lambda: Color(10, 20, 30, 255))
    inner: _Inner = dataclasses.field(default_factory=_Inner)
    label: str = "unedited"  # unsupported type -> read-only
    _hidden: int = 99  # private -> skipped entirely


class TestCollectTweakableLeaves:
    def test_scalar_fields(self):
        outer = _Outer()
        leaves = {leaf.label: leaf for leaf in collect_tweakable_leaves(outer)}

        assert leaves["mode"].kind == "enum"
        assert leaves["mode"].value is Mode.A
        assert leaves["label"].kind == "readonly"
        assert "_hidden" not in leaves

    def test_vector2_becomes_two_number_leaves(self):
        outer = _Outer()
        leaves = {leaf.label: leaf for leaf in collect_tweakable_leaves(outer)}

        assert leaves["position.x"].kind == "number"
        assert leaves["position.x"].value == 1.0
        assert leaves["position.y"].value == 2.0

    def test_nested_dataclass_recurses(self):
        outer = _Outer()
        leaves = {leaf.label: leaf for leaf in collect_tweakable_leaves(outer)}

        assert leaves["inner.speed"].kind == "number"
        assert leaves["inner.enabled"].kind == "bool"

    def test_slotted_dataclass_recurses_via_dataclasses_fields(self):
        """Color is @dataclass(slots=True) -- no __dict__, so this only
        works if the fallback to dataclasses.fields() actually fires."""
        outer = _Outer()
        leaves = {leaf.label: leaf for leaf in collect_tweakable_leaves(outer)}

        assert leaves["tint.r"].kind == "number"
        assert leaves["tint.r"].value == 10


class TestApplyClick:
    def test_bool_toggles_regardless_of_click_position(self):
        applied = []
        leaf = TweakableLeaf("flag", True, "bool", applied.append)

        apply_click(leaf, local_x=5, row_width=100)

        assert applied == [False]

    def test_enum_cycles_to_next_member(self):
        applied = []
        leaf = TweakableLeaf("mode", Mode.A, "enum", applied.append)

        apply_click(leaf, local_x=5, row_width=100)

        assert applied == [Mode.B]

    def test_enum_cycle_wraps_around(self):
        assert cycle_enum(Mode.C) is Mode.A

    def test_number_left_half_decrements(self):
        applied = []
        leaf = TweakableLeaf("speed", 5.0, "number", applied.append)

        apply_click(leaf, local_x=10, row_width=100)  # left half

        assert applied == [4.0]

    def test_number_right_half_increments(self):
        applied = []
        leaf = TweakableLeaf("speed", 5.0, "number", applied.append)

        apply_click(leaf, local_x=90, row_width=100)  # right half

        assert applied == [6.0]

    def test_number_step_stays_int_for_int_fields(self):
        applied = []
        leaf = TweakableLeaf("count", 5, "number", applied.append)

        apply_click(leaf, local_x=90, row_width=100)

        assert applied == [6]
        assert isinstance(applied[0], int)

    def test_readonly_is_a_no_op(self):
        applied = []
        leaf = TweakableLeaf("label", "text", "readonly", applied.append)

        apply_click(leaf, local_x=50, row_width=100)

        assert applied == []


class TestFormatAndRender:
    def test_format_leaf_value_formats_floats(self):
        leaf = TweakableLeaf("speed", 1.23456, "number", lambda v: None)
        assert format_leaf_value(leaf) == "1.23"

    def test_format_leaf_value_uses_enum_name(self):
        leaf = TweakableLeaf("mode", Mode.B, "enum", lambda v: None)
        assert format_leaf_value(leaf) == "B"

    def test_render_returns_hit_rects_only_for_editable_leaves(self):
        renderer = MagicMock(spec=UIRenderer)
        leaves = [
            TweakableLeaf("flag", True, "bool", lambda v: None),
            TweakableLeaf("label", "text", "readonly", lambda v: None),
        ]

        rows = render_tweakable_leaves(
            renderer,
            leaves,
            x=10,
            y=20,
            row_width=200,
            row_height=16,
            text_color=Color(255, 255, 255),
        )

        assert renderer.draw_text.call_count == 2  # both leaves drawn
        assert len(rows) == 1  # only the editable one is clickable
        rect, leaf = rows[0]
        assert rect == Rect(10, 20, 200, 16)
        assert leaf.label == "flag"
