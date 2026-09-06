"""Live config editor tool for GameConfig, decoupled from any entity."""

from typing import Any

import pygame

from pyguara.common.types import Color, Rect, Vector2
from pyguara.config.manager import ConfigManager
from pyguara.di.container import DIContainer
from pyguara.graphics.protocols import UIRenderer
from pyguara.tools.base import Tool
from pyguara.tools.tweakable import (
    TweakableLeaf,
    apply_click,
    collect_tweakable_leaves,
    render_tweakable_leaves,
)


class ConfigInspector(Tool):
    """Displays and edits `GameConfig`'s dataclass tree live.

    Unlike `EntityInspector`, there's no entity to select -- `GameConfig`
    (display/audio/input/physics/debug) isn't attached to any entity, so this
    is a second tool rather than an extension of the first. Shares the same
    per-type edit dispatch (`pyguara.tools.tweakable`). A Save action
    (`S` key) persists edits via the already-existing `ConfigManager.save()`.
    """

    def __init__(self, container: DIContainer) -> None:
        """Initialize the config inspector.

        Args:
            container: The global DI container.
        """
        super().__init__("config_inspector", container)
        self._config_manager = container.get(ConfigManager)

        self._panel_rect = Rect(330, 80, 300, 500)
        self._bg_color = Color(30, 30, 40, 230)
        self._text_color = Color(255, 255, 255)
        self._highlight_color = Color(100, 200, 255)
        self._saved_flash_timer = 0.0

        self._tweakable_rows: list[tuple[Rect, TweakableLeaf]] = []

    def update(self, dt: float) -> None:
        """Count down the "Saved" flash message, if one is showing.

        Args:
            dt: Delta time.
        """
        if self._saved_flash_timer > 0:
            self._saved_flash_timer = max(0.0, self._saved_flash_timer - dt)

    def render(self, renderer: UIRenderer) -> None:
        """Render the config panel.

        Args:
            renderer: The UI renderer backend.
        """
        self._tweakable_rows = []

        renderer.draw_rect(self._panel_rect, self._bg_color, 0)
        renderer.draw_rect(self._panel_rect, Color(100, 100, 100), 2)

        x = self._panel_rect.x + 10
        y = self._panel_rect.y + 10

        renderer.draw_text(
            "Config Inspector (S to Save)",
            Vector2(x, y),
            self._highlight_color,
            size=18,
        )
        y += 30

        leaves = collect_tweakable_leaves(self._config_manager.config)
        rows = render_tweakable_leaves(
            renderer,
            leaves,
            x=x,
            y=y,
            row_width=self._panel_rect.width - 20,
            row_height=16,
            text_color=self._text_color,
            font_size=14,
        )
        self._tweakable_rows.extend(rows)

        if self._saved_flash_timer > 0:
            footer_y = self._panel_rect.y + self._panel_rect.height - 30
            renderer.draw_text("Saved.", Vector2(x, footer_y), Color(120, 220, 120), 14)

    def process_event(self, event: Any) -> bool:
        """Handle clicks on editable field rows and the Save shortcut.

        Args:
            event: Pygame event.
        """
        if event.type == pygame.KEYDOWN and event.key == pygame.K_s:
            if self._config_manager.save():
                self._saved_flash_timer = 1.5
            return True

        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            mx, my = event.pos
            for rect, leaf in self._tweakable_rows:
                if (
                    rect.x <= mx <= rect.x + rect.width
                    and rect.y <= my <= rect.y + rect.height
                ):
                    apply_click(leaf, local_x=mx - rect.x, row_width=rect.width)
                    return True

        return False
