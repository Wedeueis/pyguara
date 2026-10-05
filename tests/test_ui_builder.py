"""`UIBuilder` builds the tree the imperative API builds.

That equivalence is the whole claim: the builder is sugar over
`add_child()`, so anything it produces must be indistinguishable from the
same screen written by hand. The first test here is that comparison on a
real demo screen; the rest pin the parent stack, root/layer handling,
mounting, callback passthrough, and the errors that keep a misused builder
from silently producing half a menu.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from pyguara.common.types import Color, Rect, Vector2
from pyguara.events.dispatcher import EventDispatcher
from pyguara.graphics.protocols import UIRenderer
from pyguara.ui.base import UIElement
from pyguara.ui.builder import UIBuilder, UIBuilderError
from pyguara.ui.components.button import Button
from pyguara.ui.components.canvas import Canvas
from pyguara.ui.components.checkbox import Checkbox
from pyguara.ui.components.image import Image
from pyguara.ui.components.navbar import NavBar
from pyguara.ui.components.panel import Panel
from pyguara.ui.components.progress_bar import ProgressBar
from pyguara.ui.components.slider import Slider
from pyguara.ui.components.text import Label
from pyguara.ui.components.text_input import TextInput
from pyguara.ui.design_system.components import BevelButton, BevelPanel, Skins
from pyguara.ui.layout import BoxContainer
from pyguara.ui.manager import UIManager
from pyguara.ui.types import (
    LayoutAlignment,
    LayoutDirection,
    TextAlign,
    UILayer,
)

SCREEN = Rect(0, 0, 800, 600)


class Bevel(UIElement):
    """A game's own widget. Custom elements are the normal case, not the
    exception -- `guara_falcao` builds its screens out of three of them."""

    def __init__(self, text: str, position: Vector2, size: Vector2) -> None:
        super().__init__(position, size)
        self.text = text

    def render(self, renderer: UIRenderer) -> None:
        pass


def _renderer() -> MagicMock:
    """A renderer that measures text, so `Label.measure()` can size itself.

    A bare `MagicMock(spec=UIRenderer)` returns a mock from
    `get_text_size()`, which `Label` unpacks into two values -- the same
    stub every other UI test configures (`(50, 16)`).
    """
    renderer = MagicMock(spec=UIRenderer)
    renderer.get_text_size.return_value = (50, 16)
    return renderer


def _manager() -> UIManager:
    manager = UIManager(EventDispatcher())
    manager.set_screen_size(SCREEN.width, SCREEN.height)
    return manager


def _shape(element: UIElement) -> object:
    """Describe a tree by type, geometry and text, ignoring identity."""
    return (
        type(element).__name__,
        (element.rect.x, element.rect.y, element.rect.width, element.rect.height),
        getattr(element, "text", None),
        [_shape(child) for child in element.children],
    )


@pytest.mark.unit
class TestEquivalenceWithImperativeConstruction:
    """The claim that makes this sugar rather than a second UI API."""

    def test_a_real_title_column_matches_the_handwritten_one(self) -> None:
        """`guara_falcao`'s title screen, both ways, laid out and compared."""
        handlers = [lambda _e: None, lambda _e: None, lambda _e: None]
        buttons = ("Play", "Options", "Quit")

        imperative = BoxContainer(Vector2(270, 288), Vector2(260, 220), spacing=14)
        for text, handler in zip(buttons, handlers, strict=True):
            button = Button(text, Vector2(0, 0), Vector2(260, 52))
            button.on_click = handler
            imperative.add_child(button)

        with (
            UIBuilder() as ui,
            ui.box(Vector2(270, 288), Vector2(260, 220), spacing=14) as declarative,
        ):
            for text, handler in zip(buttons, handlers, strict=True):
                ui.button(text, size=Vector2(260, 52), on_click=handler)

        renderer = _renderer()
        imperative.layout(SCREEN, renderer)
        declarative.layout(SCREEN, renderer)

        assert _shape(declarative) == _shape(imperative)

    def test_the_callbacks_are_the_same_objects(self) -> None:
        """`on_click` is passthrough -- a bare attribute assignment, the
        same one every demo makes by hand. No wrapper, no indirection."""
        handler = MagicMock()
        with UIBuilder() as ui, ui.box():
            button = ui.button("Play", on_click=handler)
        assert button.on_click is handler

    def test_a_nested_tree_matches_by_hand(self) -> None:
        imperative = Panel(Vector2(10, 10), Vector2(400, 300))
        inner = BoxContainer(Vector2(0, 0), Vector2(380, 200))
        inner.add_child(Label("Title", Vector2(0, 0), font_size=22))
        inner.add_child(Button("Go", Vector2(0, 0)))
        imperative.add_child(inner)

        with UIBuilder() as ui:  # noqa: SIM117 - the nesting mirrors the UI tree
            with ui.panel(Vector2(10, 10), Vector2(400, 300)) as built:
                with ui.box(Vector2(0, 0), Vector2(380, 200)):
                    ui.label("Title", font_size=22)
                    ui.button("Go")

        renderer = _renderer()
        imperative.layout(SCREEN, renderer)
        built.layout(SCREEN, renderer)
        assert _shape(built) == _shape(imperative)


@pytest.mark.unit
class TestParentStack:
    def test_children_attach_to_the_enclosing_container(self) -> None:
        with UIBuilder() as ui, ui.box() as outer:
            first = ui.label("a")
            with ui.box() as inner:
                second = ui.label("b")
            third = ui.label("c")

        assert first.parent is outer
        assert second.parent is inner
        assert third.parent is outer
        assert [type(c).__name__ for c in outer.children] == [
            "Label",
            "BoxContainer",
            "Label",
        ]

    def test_the_stack_unwinds_after_an_inner_failure(self) -> None:
        """A `nest()` left by an exception must not keep catching children:
        everything built afterwards would be silently reparented into a
        container the caller has already left."""
        builder = UIBuilder()
        with builder, builder.box() as outer:
            with pytest.raises(ValueError), builder.box():
                raise ValueError("boom")
            after = builder.label("after")

        assert after.parent is outer

    def test_current_reports_the_active_parent(self) -> None:
        with UIBuilder() as ui:
            assert ui.current is None
            with ui.box() as outer:
                assert ui.current is outer
                with ui.box() as inner:
                    assert ui.current is inner
                assert ui.current is outer
            assert ui.current is None


@pytest.mark.unit
class TestRootsAndLayers:
    def test_top_level_elements_become_roots(self) -> None:
        with UIBuilder() as ui:
            first = ui.label("one")
            with ui.box() as second:
                ui.label("nested")

        assert ui.roots == [first, second]

    def test_a_nested_element_is_not_a_root(self) -> None:
        with UIBuilder() as ui, ui.box() as container:
            ui.label("nested")
        assert ui.roots == [container]

    def test_roots_mount_at_the_builders_layer(self) -> None:
        manager = _manager()
        with UIBuilder(manager, layer=UILayer.HUD) as ui:
            root = ui.label("hud")
        assert root in manager.elements(UILayer.HUD)

    def test_the_layer_block_scopes_roots(self) -> None:
        """One builder, a backdrop and a content root -- what
        `guara_falcao`'s title screen actually needs."""
        manager = _manager()
        with UIBuilder(manager) as ui:
            with ui.layer(UILayer.BACKDROP):
                scrim = ui.add(Panel(Vector2(0, 0), Vector2(800, 600)))
            plate = ui.label("title")

        assert scrim in manager.elements(UILayer.BACKDROP)
        assert plate in manager.elements(UILayer.CONTENT)

    def test_the_layer_block_restores_the_previous_layer(self) -> None:
        manager = _manager()
        with UIBuilder(manager, layer=UILayer.HUD) as ui:
            with ui.layer(UILayer.BACKDROP):
                ui.label("back")
            after = ui.label("after")
        assert after in manager.elements(UILayer.HUD)

    def test_the_layer_is_restored_even_if_the_block_raises(self) -> None:
        builder = UIBuilder(layer=UILayer.HUD)
        with builder:
            with pytest.raises(ValueError), builder.layer(UILayer.BACKDROP):
                raise ValueError("boom")
            after = builder.label("after")
        assert builder.roots == [after]


@pytest.mark.unit
class TestMounting:
    def test_exiting_mounts_into_the_manager(self) -> None:
        manager = _manager()
        with UIBuilder(manager) as ui:
            root = ui.label("hello")
            assert manager.elements() == []  # not before the block ends
        assert manager.elements() == [root]

    def test_without_a_manager_nothing_is_mounted(self) -> None:
        with UIBuilder() as ui:
            root = ui.label("detached")
        assert ui.roots == [root]

    def test_mount_places_a_detached_tree_later(self) -> None:
        manager = _manager()
        with UIBuilder() as ui:
            root = ui.label("detached")
        ui.mount(manager)
        assert manager.elements() == [root]

    def test_mount_can_override_the_layer(self) -> None:
        manager = _manager()
        with UIBuilder() as ui:
            root = ui.label("x")
        ui.mount(manager, layer=UILayer.OVERLAY)
        assert root in manager.elements(UILayer.OVERLAY)

    def test_mount_without_any_manager_is_an_error(self) -> None:
        with UIBuilder() as ui:
            ui.label("x")
        with pytest.raises(UIBuilderError, match="needs a UIManager"):
            ui.mount()

    def test_a_failed_block_mounts_nothing(self) -> None:
        """Half a menu on screen is harder to diagnose than no menu, and
        the exception already says what went wrong."""
        manager = _manager()
        with pytest.raises(ValueError), UIBuilder(manager) as ui:
            ui.label("built")
            raise ValueError("boom")
        assert manager.elements() == []


@pytest.mark.unit
class TestCustomElements:
    def test_add_keeps_a_custom_element(self) -> None:
        with UIBuilder() as ui, ui.box() as container:
            bevel = ui.add(Bevel("Play", Vector2(0, 0), Vector2(260, 52)))
        assert bevel.parent is container
        assert container.children == [bevel]

    def test_add_wires_on_click_for_a_custom_element(self) -> None:
        handler = MagicMock()
        with UIBuilder() as ui:
            bevel = ui.add(
                Bevel("Play", Vector2(0, 0), Vector2(10, 10)), on_click=handler
            )
        assert bevel.on_click is handler

    def test_nest_descends_into_a_custom_container(self) -> None:
        with UIBuilder() as ui:  # noqa: SIM117 - the nesting mirrors the UI tree
            with ui.nest(Bevel("Plate", Vector2(0, 0), Vector2(520, 132))) as plate:
                label = ui.label("GUARÁ & FALCÃO", font_size=44)
        assert label.parent is plate

    def test_a_container_without_a_with_block_is_still_added(self) -> None:
        """A childless container is a reasonable thing to want, and a
        factory call that silently added nothing would be the worst of the
        options.

        The attachment happens in `nest()`, not in `__enter__`. An earlier
        generator-based version attached on `__enter__` and popped the
        parent stack from a `finally` -- so a factory called without
        `with` added nothing, and one entered without exiting stayed on
        the stack until the garbage collector happened to run the
        generator's `finally`.
        """
        with UIBuilder() as ui, ui.box() as outer:
            ui.panel(Vector2(0, 0), Vector2(10, 10))
            sibling = ui.label("after")

        assert [type(c).__name__ for c in outer.children] == ["Panel", "Label"]
        assert sibling.parent is outer

    def test_entering_a_container_is_what_descends_into_it(self) -> None:
        """The other half: attaching and descending are separate steps."""
        with UIBuilder() as ui, ui.box() as outer:
            scope = ui.panel(Vector2(0, 0), Vector2(10, 10))
            assert ui.current is outer
            with scope as panel:
                assert ui.current is panel
            assert ui.current is outer

    def test_re_attaching_an_owned_element_is_an_error(self) -> None:
        """An element belongs to one tree. Silently reparenting it would
        remove it from the first without saying so."""
        with UIBuilder() as ui, ui.box():
            label = ui.label("once")
        with (
            UIBuilder() as other,
            pytest.raises(UIBuilderError, match="already has a parent"),
        ):
            other.add(label)


@pytest.mark.unit
class TestFactories:
    def test_every_factory_builds_its_component(self) -> None:
        texture = object()
        with UIBuilder() as ui:
            built = [
                ui.label("text"),
                ui.button("press"),
                ui.checkbox("toggle"),
                ui.slider(),
                ui.text_input(),
                ui.progress_bar(),
                ui.image(texture, size=Vector2(32, 32)),
            ]
        assert [type(e) for e in built] == [
            Label,
            Button,
            Checkbox,
            Slider,
            TextInput,
            ProgressBar,
            Image,
        ]

    def test_every_container_factory_builds_its_container(self) -> None:
        with UIBuilder() as ui:  # noqa: SIM117 - the nesting mirrors the UI tree
            with ui.box() as box:
                pass
            with ui.panel(Vector2(0, 0), Vector2(10, 10)) as panel:
                pass
            with ui.navbar(800) as navbar:
                pass
            with ui.canvas(Vector2(0, 0), Vector2(10, 10)) as canvas:
                pass
        assert isinstance(box, BoxContainer)
        assert isinstance(panel, Panel)
        assert isinstance(navbar, NavBar)
        assert isinstance(canvas, Canvas)

    def test_label_arguments_reach_the_component(self) -> None:
        with UIBuilder() as ui:
            label = ui.label(
                "centred",
                Vector2(5, 6),
                font_size=44,
                color=Color(1, 2, 3),
                width=520,
                align=TextAlign.CENTER,
            )
        assert label.text == "centred"
        assert label.font_size == 44
        assert (label.rect.x, label.rect.y) == (5, 6)
        assert label.align == TextAlign.CENTER

    def test_box_arguments_reach_the_container(self) -> None:
        with (
            UIBuilder() as ui,
            ui.box(
                Vector2(1, 2),
                Vector2(3, 4),
                direction=LayoutDirection.HORIZONTAL,
                alignment=LayoutAlignment.CENTER,
                spacing=14,
            ) as box,
        ):
            pass
        assert box.direction == LayoutDirection.HORIZONTAL
        assert box.alignment == LayoutAlignment.CENTER
        assert box.spacing == 14

    def test_button_size_defaults_to_the_components_own(self) -> None:
        """Omitting size must not mean a zero-sized button."""
        with UIBuilder() as ui:
            default = ui.button("a")
            sized = ui.button("b", size=Vector2(260, 52))
        assert (default.rect.width, default.rect.height) == (120, 40)
        assert (sized.rect.width, sized.rect.height) == (260, 52)

    def test_progress_bar_size_defaults_to_the_components_own(self) -> None:
        with UIBuilder() as ui:
            default = ui.progress_bar()
        assert (default.rect.width, default.rect.height) == (200, 20)

    def test_slider_arguments_reach_the_component(self) -> None:
        with UIBuilder() as ui:
            slider = ui.slider(width=240, min_val=1.0, max_val=5.0, step=0.5)
        assert (slider.min_val, slider.max_val, slider.step) == (1.0, 5.0, 0.5)


@pytest.mark.unit
class TestChangeCallbacks:
    def test_checkbox_on_change(self) -> None:
        handler = MagicMock()
        with UIBuilder() as ui:
            checkbox = ui.checkbox("toggle", checked=True, on_change=handler)
        assert checkbox.on_change is handler
        assert checkbox.checked is True

    def test_slider_on_change(self) -> None:
        handler = MagicMock()
        with UIBuilder() as ui:
            slider = ui.slider(on_change=handler)
        assert slider.on_change is handler

    def test_text_input_on_change(self) -> None:
        handler = MagicMock()
        with UIBuilder() as ui:
            field = ui.text_input(placeholder="name", on_change=handler)
        assert field.on_change is handler
        assert field.placeholder == "name"

    def test_callbacks_are_left_alone_when_not_given(self) -> None:
        with UIBuilder() as ui:
            assert ui.checkbox("a").on_change is None
            assert ui.slider().on_change is None
            assert ui.text_input().on_change is None
            assert ui.button("b").on_click is None


@pytest.mark.unit
class TestMisuse:
    def test_adding_outside_the_with_block_is_an_error(self) -> None:
        builder = UIBuilder()
        with pytest.raises(UIBuilderError, match="`with` block"):
            builder.label("orphan")

    def test_adding_after_the_block_is_an_error(self) -> None:
        """Elements added afterwards would never be mounted."""
        with UIBuilder() as ui:
            ui.label("inside")
        with pytest.raises(UIBuilderError, match="closed"):
            ui.label("outside")

    def test_reusing_a_builder_is_an_error(self) -> None:
        builder = UIBuilder()
        with builder:
            builder.label("first")
        with pytest.raises(UIBuilderError, match="already been used"), builder:
            pass


@pytest.mark.unit
class TestThemingNeedsNoWiring:
    def test_an_element_is_themed_at_construction(self) -> None:
        """`UIElement.__init__` calls `get_theme()` unconditionally, so the
        builder has nothing to wire -- this pins that it stayed true."""
        with UIBuilder() as ui:
            built = ui.button("themed")
        by_hand = Button("themed", Vector2(0, 0))
        assert built.theme is by_hand.theme


@pytest.mark.unit
class TestAgainstRealDesignSystemWidgets:
    """The stock components are the easy case. A game's screens are built
    from design-system subclasses with their own constructor arguments, so
    this rebuilds `guara_falcao`'s title screen shape out of `BevelPanel`
    and `BevelButton` and diffs it against the handwritten version."""

    def _imperative(self, manager: UIManager, handlers: list[object]) -> None:
        plate_width, plate_x = 520, (800 - 520) // 2
        manager.add_element(Panel(Vector2(0, 0), Vector2(800, 600)), UILayer.BACKDROP)
        plate = BevelPanel(
            Vector2(plate_x, 96), Vector2(plate_width, 132), border_width=3
        )
        plate.add_child(
            Label(
                "GUARÁ & FALCÃO",
                Vector2(plate_x, 126),
                font_size=44,
                width=plate_width,
                align=TextAlign.CENTER,
            )
        )
        manager.add_element(plate, UILayer.CONTENT)

        column = BoxContainer(Vector2(270, 288), Vector2(260, 220), spacing=14)
        for (text, skin), handler in zip(
            (("Play", Skins.SAGE), ("Quit", Skins.WOOD)), handlers, strict=True
        ):
            button = BevelButton(text, Vector2(0, 0), Vector2(260, 52), skin=skin)
            button.on_click = handler  # type: ignore[assignment]
            column.add_child(button)
        manager.add_element(column, UILayer.CONTENT)

    def _declarative(self, manager: UIManager, handlers: list[object]) -> None:
        plate_width, plate_x = 520, (800 - 520) // 2
        with UIBuilder(manager) as ui:
            with ui.layer(UILayer.BACKDROP):
                ui.add(Panel(Vector2(0, 0), Vector2(800, 600)))
            with ui.nest(
                BevelPanel(
                    Vector2(plate_x, 96), Vector2(plate_width, 132), border_width=3
                )
            ):
                ui.label(
                    "GUARÁ & FALCÃO",
                    Vector2(plate_x, 126),
                    font_size=44,
                    width=plate_width,
                    align=TextAlign.CENTER,
                )
            with ui.box(Vector2(270, 288), Vector2(260, 220), spacing=14):
                for (text, skin), handler in zip(
                    (("Play", Skins.SAGE), ("Quit", Skins.WOOD)),
                    handlers,
                    strict=True,
                ):
                    ui.add(
                        BevelButton(text, Vector2(0, 0), Vector2(260, 52), skin=skin),
                        on_click=handler,  # type: ignore[arg-type]
                    )

    def test_the_two_screens_are_indistinguishable(self) -> None:
        handlers: list[object] = [MagicMock(), MagicMock()]
        by_hand, built = _manager(), _manager()
        self._imperative(by_hand, handlers)
        self._declarative(built, handlers)

        renderer = _renderer()
        for layer in (UILayer.BACKDROP, UILayer.CONTENT):
            for element in by_hand.elements(layer):
                element.layout(SCREEN, renderer)
            for element in built.elements(layer):
                element.layout(SCREEN, renderer)

        for layer in (UILayer.BACKDROP, UILayer.CONTENT):
            assert [_shape(e) for e in built.elements(layer)] == [
                _shape(e) for e in by_hand.elements(layer)
            ], f"layer {layer!r} differs"

    def test_subclass_constructor_arguments_survive(self) -> None:
        """`skin=` is a `BevelButton` argument the builder knows nothing
        about -- which is the point of `add()` taking a built element."""
        built = _manager()
        self._declarative(built, [MagicMock(), MagicMock()])
        column = built.elements(UILayer.CONTENT)[-1]
        assert [child.skin for child in column.children] == [  # type: ignore[attr-defined]
            Skins.SAGE,
            Skins.WOOD,
        ]
