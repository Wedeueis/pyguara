"""A scene must find the Application that is actually running."""

from __future__ import annotations

from typing import Any

import pytest

from pyguara.application.application import Application
from pyguara.application.bootstrap import (
    create_headless_application,
    create_headless_sandbox_application,
)


@pytest.mark.parametrize(
    "factory",
    [
        create_headless_application,
        create_headless_sandbox_application,
    ],
)
def test_a_scene_finds_the_application_that_is_actually_running(factory: Any) -> None:
    """A hook registered on another instance would silently never run."""
    application = factory()
    try:
        assert application._container.get(Application) is application
    finally:
        application.shutdown()
