"""A theme a test installs does not reach the next test.

A game installs its own theme, so a test that runs one leaves it as the
global. `tests/conftest.py` puts the previous theme back after every test.
The two tests here run in file order: the first installs a theme with
shadows and keeps it, the second checks it starts on the default.
"""

from __future__ import annotations

import pytest

from pyguara.ui.theme import UITheme, get_theme, set_theme
from pyguara.ui.types import ShadowScheme


@pytest.mark.xdist_group("ui-theme-isolation")
def test_installs_a_theme_the_way_a_game_does() -> None:
    set_theme(UITheme(name="leaked", shadows=ShadowScheme(enabled=True)))
    assert get_theme().name == "leaked"


@pytest.mark.xdist_group("ui-theme-isolation")
def test_the_next_test_starts_on_the_previous_theme() -> None:
    assert get_theme().name != "leaked"
    assert not get_theme().shadows.enabled
