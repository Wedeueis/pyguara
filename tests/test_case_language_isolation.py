"""Every test starts with the case language in English."""

from __future__ import annotations

from collections.abc import Iterator

import pytest

from pyguara.ui.text_case import case_language, set_case_language


@pytest.fixture(scope="module")
def _booted_in_russian() -> Iterator[None]:
    # What a module-scoped application does when its locale is Russian:
    # it sets the case language before any per-test fixture runs.
    set_case_language("ru")
    yield
    set_case_language("en")


def test_a_wider_fixture_does_not_set_a_tests_case_language(
    _booted_in_russian: None,
) -> None:
    assert case_language() == "en"


def test_the_next_test_starts_in_english_too(_booted_in_russian: None) -> None:
    assert case_language() == "en"
