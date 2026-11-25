"""A resource a prefab names is loaded as the prefab is built, so a
missing one fails there, naming the prefab."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pytest

from pyguara.common.components import Tag
from pyguara.ecs.component import BaseComponent
from pyguara.ecs.manager import EntityManager
from pyguara.prefabs import ComponentRegistry, PrefabChild, PrefabData, PrefabFactory
from pyguara.resources.types import AudioClip, Texture


class _Texture(Texture):
    @property
    def width(self) -> int:
        return 4

    @property
    def height(self) -> int:
        return 4

    @property
    def native_handle(self) -> object:
        return None


@dataclass
class Look(BaseComponent):
    """Test data: one texture field, typed as `Sprite.texture` is."""

    texture: Texture

    def __post_init__(self) -> None:
        """Initialise the BaseComponent state the dataclass `__init__` skips."""
        BaseComponent.__init__(self)


class _Textures:
    """Stands in for a resource manager: loads only the paths it holds."""

    def __init__(self, *paths: str) -> None:
        self.paths = set(paths)
        self.loaded: list[str] = []

    def load(self, path: str, kind: type) -> Any:
        if path not in self.paths:
            raise FileNotFoundError(path)
        self.loaded.append(path)
        return _Texture(path)


def _factory(
    textures: _Textures, prefabs: dict[str, PrefabData]
) -> tuple[PrefabFactory, EntityManager]:
    from pyguara.application.bootstrap import _resource_converter

    registry = ComponentRegistry()
    registry.register(Look)
    registry.register(Tag)
    registry.register_type_converter(
        Texture,
        _resource_converter(textures, Texture),  # type: ignore[arg-type]
    )
    manager = EntityManager()
    return PrefabFactory(manager, registry, prefabs.get), manager


GOBLIN = PrefabData(name="goblin", components={"Look": {"texture": "goblin.png"}})
TORCH = PrefabData(name="torch", components={"Look": {"texture": "torch.png"}})
CARRIER = PrefabData(
    name="carrier",
    components={"Tag": {"name": "carrier"}},
    children=[PrefabChild("torch", overrides={"Look": {"texture": "bright.png"}})],
)
PREFABS = {"goblin": GOBLIN, "torch": TORCH, "carrier": CARRIER}


class TestCreate:
    def test_a_named_texture_is_loaded(self) -> None:
        factory, _ = _factory(_Textures("goblin.png"), PREFABS)
        goblin = factory.create_from_path("goblin")
        assert goblin is not None
        texture = goblin.get_component(Look).texture
        assert isinstance(texture, Texture)
        assert texture.path == "goblin.png"

    def test_a_missing_texture_names_the_prefab_and_component(self) -> None:
        factory, manager = _factory(_Textures(), PREFABS)
        with pytest.raises(
            ValueError,
            match=r"prefab 'goblin', component Look: FileNotFoundError: goblin.png",
        ):
            factory.create_from_path("goblin")
        manager.flush_pending_removals()
        assert list(manager.get_all_entities()) == []

    def test_a_texture_given_as_something_else_is_refused(self) -> None:
        bad = PrefabData(name="bad", components={"Look": {"texture": 7}})
        factory, _ = _factory(_Textures(), {"bad": bad})
        with pytest.raises(ValueError, match="a Texture is named by its path, not 7"):
            factory.create_from_path("bad")


class TestCheck:
    def test_a_good_prefab_passes_and_creates_nothing(self) -> None:
        textures = _Textures("goblin.png")
        factory, manager = _factory(textures, PREFABS)

        factory.check_path("goblin")

        assert textures.loaded == ["goblin.png"]
        assert list(manager.get_all_entities()) == []

    def test_a_missing_texture_fails_the_check(self) -> None:
        factory, manager = _factory(_Textures(), PREFABS)
        with pytest.raises(ValueError, match="prefab 'goblin', component Look"):
            factory.check_path("goblin")
        assert list(manager.get_all_entities()) == []

    def test_a_child_is_checked_with_its_overrides(self) -> None:
        textures = _Textures("torch.png")
        factory, _ = _factory(textures, PREFABS)
        with pytest.raises(ValueError, match="prefab 'torch'.*bright.png"):
            factory.check_path("carrier")

        textures.paths.add("bright.png")
        factory.check_path("carrier")
        assert textures.loaded[-1] == "bright.png"

    def test_the_tree_is_checked_as_create_checks_it(self) -> None:
        orphan = PrefabData(name="orphan", children=[PrefabChild("nowhere")])
        factory, _ = _factory(_Textures(), {"orphan": orphan})
        with pytest.raises(ValueError, match="child 'nowhere', which did not load"):
            factory.check_path("orphan")

    def test_a_prefab_that_does_not_load_fails_the_check(self) -> None:
        factory, _ = _factory(_Textures(), PREFABS)
        with pytest.raises(ValueError, match="prefab 'nowhere' did not load"):
            factory.check_path("nowhere")


def test_the_application_loads_textures_and_sounds_named_in_prefabs() -> None:
    from pyguara.application.bootstrap import create_headless_application
    from pyguara.graphics.components.sprite import Sprite

    application = create_headless_application()
    registry = application.container.get(ComponentRegistry)
    for kind in (Texture, AudioClip):
        assert kind in registry._type_converters

    factory = PrefabFactory(EntityManager(), registry)
    if not registry.has("Sprite"):
        registry.register(Sprite)
    with pytest.raises(ValueError, match="prefab 'ghost', component Sprite"):
        factory.create(
            PrefabData(name="ghost", components={"Sprite": {"texture": "no/ghost.png"}})
        )
