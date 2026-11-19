"""Finding the editor layer when Studio is absent, or broken.

A shipped game is built without `pyguara.studio`, so the lookup must
treat a missing module as "no editor". Anything else that goes wrong
while resolving the editor is a real error and must not be swallowed.
"""

from __future__ import annotations

import sys

import pytest

from pyguara.application.application import Application
from pyguara.application.bootstrap import create_headless_application


@pytest.fixture
def app() -> Application:
    return create_headless_application()


def test_no_editor_when_studio_is_not_importable(
    app: Application, monkeypatch: pytest.MonkeyPatch
) -> None:
    # A `None` entry in sys.modules makes the import raise ImportError,
    # which is what a build that excluded the package does.
    monkeypatch.setitem(sys.modules, "pyguara.studio", None)
    monkeypatch.setitem(sys.modules, "pyguara.studio.layer", None)

    assert app._editor_layer is None


def test_no_editor_when_none_is_attached(app: Application) -> None:
    pytest.importorskip("imgui_bundle")
    assert app._editor_layer is None


def test_an_error_resolving_the_editor_is_raised(
    app: Application, monkeypatch: pytest.MonkeyPatch
) -> None:
    pytest.importorskip("imgui_bundle")

    def broken(service_type: object) -> object:
        raise RuntimeError("the editor failed to build")

    monkeypatch.setattr(app._container, "get", broken)

    with pytest.raises(RuntimeError, match="failed to build"):
        _ = app._editor_layer
