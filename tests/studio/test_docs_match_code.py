"""The Studio docs describe what actually exists.

Phase C of this repository's subsystem audit kept finding the same thing:
three documentation pages described functions that had never existed. A
doc is only load-bearing if something checks it, so the claims most likely
to rot -- the operation list, the risk classes, the panel set -- are
asserted here rather than left to a reader to discover are wrong.

Prose is not checked, and should not be. What is checked is every place
the docs enumerate something the code also enumerates.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from pyguara.studio.attach import DEFAULT_LAYOUT_REGIONS
from pyguara.studio.ops.builtin import build_registry
from pyguara.studio.ops.registry import RiskClass

DOCS = Path(__file__).resolve().parents[2] / "docs"
STUDIO_DOC = DOCS / "systems" / "studio.md"
AGENT_GUIDE = DOCS / "guides" / "agent-integration.md"


@pytest.fixture(scope="module")
def studio_doc() -> str:
    """The Studio systems page."""
    return STUDIO_DOC.read_text(encoding="utf-8")


class TestPagesExist:
    """The nav entries point at real files."""

    @pytest.mark.parametrize(
        "relative",
        [
            "systems/studio.md",
            "guides/agent-integration.md",
            "adr/0001-one-mutation-seam-for-studio.md",
            "adr/0002-studio-agent-transports.md",
        ],
    )
    def test_the_page_exists(self, relative: str) -> None:
        assert (DOCS / relative).is_file()

    @pytest.mark.parametrize(
        "relative",
        [
            "systems/studio.md",
            "guides/agent-integration.md",
            "adr/0001-one-mutation-seam-for-studio.md",
            "adr/0002-studio-agent-transports.md",
        ],
    )
    def test_the_page_is_in_the_nav(self, relative: str) -> None:
        """A page not in `mkdocs.yml` is a page nobody finds."""
        nav = (DOCS.parent / "mkdocs.yml").read_text(encoding="utf-8")
        assert relative in nav


class TestOperationsTable:
    """The documented operation list matches the registry."""

    def _documented(self, studio_doc: str) -> set[str]:
        """Return the operation names from the page's table."""
        table = studio_doc.split("| Group | Operations |")[1].split("Each declares")[0]
        return set(re.findall(r"`([a-z_]+)`", table))

    def test_every_operation_is_documented(self, studio_doc: str) -> None:
        missing = set(build_registry().names()) - self._documented(studio_doc)
        assert not missing, f"undocumented operations: {sorted(missing)}"

    def test_nothing_documented_is_missing_from_the_code(self, studio_doc: str) -> None:
        """The failure Phase C kept finding."""
        invented = self._documented(studio_doc) - set(build_registry().names())
        assert not invented, f"documented but absent: {sorted(invented)}"

    def test_every_risk_class_is_explained(self, studio_doc: str) -> None:
        named = set(re.findall(r"`(read|edit|run|write_disk)`", studio_doc))
        missing = {risk.value for risk in RiskClass} - named
        assert not missing, f"undocumented risk classes: {sorted(missing)}"


class TestPanelTable:
    """The documented panel set matches the default layout."""

    def test_every_default_panel_is_documented(self, studio_doc: str) -> None:
        table = studio_doc.split("| Panel | What it is for |")[1].split(
            "Panels open docked"
        )[0]
        documented = set(re.findall(r"\*\*([A-Z][a-z]+)\*\*", table))

        expected = {
            title for titles in DEFAULT_LAYOUT_REGIONS.values() for title in titles
        }
        missing = expected - documented
        assert not missing, f"undocumented panels: {sorted(missing)}"


class TestCommandsAreReal:
    """Every CLI invocation the docs show is one the CLI offers."""

    @pytest.mark.parametrize("page", [STUDIO_DOC, AGENT_GUIDE])
    def test_documented_subcommands_exist(self, page: Path) -> None:
        from pyguara.cli.studio import studio

        text = page.read_text(encoding="utf-8")
        shown = set(re.findall(r"pyguara studio ([a-z]+)", text))
        available = set(studio.commands)

        invented = shown - available
        assert not invented, f"documented but absent: {sorted(invented)}"

    def test_every_subcommand_is_documented_somewhere(self) -> None:
        from pyguara.cli.studio import studio

        text = STUDIO_DOC.read_text(encoding="utf-8") + AGENT_GUIDE.read_text(
            encoding="utf-8"
        )
        for name in studio.commands:
            assert f"pyguara studio {name}" in text, (
                f"`pyguara studio {name}` is not documented anywhere"
            )


class TestTheExtraIsNamedCorrectly:
    """The install instructions work."""

    def test_the_studio_extra_exists(self) -> None:
        pyproject = (DOCS.parent / "pyproject.toml").read_text(encoding="utf-8")
        assert "\nstudio = [" in pyproject

    def test_the_guide_names_that_extra(self) -> None:
        text = AGENT_GUIDE.read_text(encoding="utf-8")
        assert "--extra studio" in text


class TestTheCaptureWarningIsPresent:
    """A capture proves the render path, not that a window appears.

    This engine has already been bitten by the difference, so a page that
    tells an agent to capture frames has to say what a capture does not
    prove.
    """

    @pytest.mark.parametrize("page", [STUDIO_DOC, AGENT_GUIDE])
    def test_the_page_warns(self, page: Path) -> None:
        text = page.read_text(encoding="utf-8")
        assert "does not" in text and "window appears" in text

    @pytest.mark.parametrize("page", [STUDIO_DOC, AGENT_GUIDE])
    def test_the_page_links_the_inspection_guide(self, page: Path) -> None:
        text = page.read_text(encoding="utf-8")
        assert "agent-visual-inspection.md" in text
