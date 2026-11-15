"""The engine loads a game's locales at startup and scenes translate through it."""

from __future__ import annotations

import json
import os
from pathlib import Path

os.environ["SDL_VIDEODRIVER"] = "dummy"
os.environ["SDL_AUDIODRIVER"] = "dummy"

import pygame
import pytest

from pyguara.application.bootstrap import create_headless_application
from pyguara.config.types import I18nConfig
from pyguara.events.dispatcher import EventDispatcher
from pyguara.i18n import LocaleChanged, Translator, install_translator
from pyguara.scene.base import Scene, SceneNotReadyError
from pyguara.scene.manager import SceneManager


class _Probe(Scene):
    def on_enter(self) -> None:
        pass

    def on_exit(self) -> None:
        pass

    def update(self, dt: float) -> None:
        pass


@pytest.fixture(autouse=True)
def _quit_pygame():
    yield
    pygame.quit()


@pytest.fixture
def locales(tmp_path: Path) -> Path:
    directory = tmp_path / "locales"
    directory.mkdir()
    for code, title in (("en", "Reclaimer"), ("ru", "Рекламатор"), ("de", "Rückholer")):
        (directory / f"{code}.json").write_text(
            json.dumps({"title": title, "hi": "Hi {name}"}, ensure_ascii=False),
            encoding="utf-8",
        )
    return directory


def test_the_configured_locale_is_used(locales: Path) -> None:
    dispatcher = EventDispatcher()
    translator = install_translator(
        I18nConfig(locale="ru", directory=str(locales)), dispatcher
    )
    assert translator is not None
    assert translator("title") == "Рекламатор"


def test_an_empty_locale_follows_the_system(locales: Path, monkeypatch) -> None:
    monkeypatch.setenv("LC_ALL", "de_AT.UTF-8")
    translator = install_translator(
        I18nConfig(locale="", directory=str(locales)), EventDispatcher()
    )
    assert translator is not None
    assert translator.locale == "de"


def test_a_locale_with_no_file_falls_to_the_closest(locales: Path) -> None:
    translator = install_translator(
        I18nConfig(locale="pt-BR", directory=str(locales)), EventDispatcher()
    )
    assert translator is not None
    assert translator.locale == "en"


def test_no_locales_folder_means_no_translator(tmp_path: Path) -> None:
    config = I18nConfig(directory=str(tmp_path / "absent"))
    assert install_translator(config, EventDispatcher()) is None


def test_a_change_of_locale_is_an_event(locales: Path) -> None:
    dispatcher = EventDispatcher()
    heard: list[str] = []
    dispatcher.subscribe(LocaleChanged, lambda event: heard.append(event.locale))
    translator = install_translator(
        I18nConfig(locale="en", directory=str(locales)), dispatcher
    )
    assert translator is not None

    translator.locale = "ru"

    assert heard == ["ru"]


def test_the_application_registers_it_and_a_scene_translates(
    locales: Path, monkeypatch
) -> None:
    monkeypatch.chdir(locales.parent)
    monkeypatch.setenv("LC_ALL", "ru_RU.UTF-8")
    app = create_headless_application()
    scene = _Probe("probe", app.container.get(EventDispatcher))
    manager = app.container.get(SceneManager)
    manager.register(scene)
    manager.switch_to(scene.name)

    assert scene.translator is app.container.get(Translator)
    assert scene.tr("hi", name="Ana") == "Hi Ana"
    assert scene.tr("title") == "Рекламатор"


def test_a_game_without_locales_is_told_how_to_add_them(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.chdir(tmp_path)
    app = create_headless_application()
    scene = _Probe("probe", app.container.get(EventDispatcher))
    manager = app.container.get(SceneManager)
    manager.register(scene)
    manager.switch_to(scene.name)

    with pytest.raises(RuntimeError, match="locales"):
        scene.tr("title")


def test_tr_before_the_scene_is_ready_says_so() -> None:
    with pytest.raises(SceneNotReadyError):
        _Probe("early", EventDispatcher()).tr("title")
