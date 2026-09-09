"""Assets browser: list indexed and loaded resources, spawn entities from data."""

from typing import Any

import pygame

from pyguara.common.components import ResourceLink
from pyguara.common.types import Color, Rect, Vector2
from pyguara.di.container import DIContainer
from pyguara.ecs.entity import Entity
from pyguara.graphics.protocols import UIRenderer
from pyguara.log import get_logger
from pyguara.prefabs.registry import ComponentRegistry
from pyguara.resources.data import DataResource
from pyguara.resources.manager import ResourceManager
from pyguara.scene.manager import SceneManager
from pyguara.tools.base import Tool

logger = get_logger(__name__)

_ROW_HEIGHT = 16


class AssetsTool(Tool):
    """Browse `ResourceManager` contents and spawn entities from `DataResource`s.

    Two lists -- everything `index_directory()` mapped, and everything
    currently loaded -- plus, for a selected `DataResource`, a read-only data
    preview and two actions: **Spawn** (build an entity, routing each
    `{"ComponentName": {...}}` entry through the shared `ComponentRegistry`,
    exactly as `SceneSerializer` does) and **Reload** (`ResourceManager.reload`).
    Replaces the ImGui `AssetsPanel` that never executed; the old panel's
    bespoke four-type spawn map is gone.
    """

    def __init__(self, container: DIContainer) -> None:
        """Initialize the assets browser.

        Args:
            container: The global DI container.
        """
        super().__init__("assets_browser", container)
        self._resources = container.get(ResourceManager)
        self._registry = container.get(ComponentRegistry)
        self._scenes = container.get(SceneManager)

        self._panel_rect = Rect(280, 80, 340, 460)
        self._bg_color = Color(30, 30, 40, 230)
        self._text_color = Color(220, 220, 220)
        self._highlight_color = Color(100, 200, 255)

        self._selected_path: str | None = None
        self._status: str = ""

        # This frame's clickable regions, rebuilt every render().
        self._rows: list[tuple[Rect, str]] = []
        self._spawn_rect: Rect | None = None
        self._reload_rect: Rect | None = None

    def update(self, dt: float) -> None:
        """No per-frame state.

        Args:
            dt: Delta time.
        """

    def render(self, renderer: UIRenderer) -> None:
        """Render the two resource lists and the selection actions.

        Args:
            renderer: The UI renderer backend.
        """
        self._rows = []
        self._spawn_rect = None
        self._reload_rect = None

        renderer.draw_rect(self._panel_rect, self._bg_color, 0)
        renderer.draw_rect(self._panel_rect, Color(100, 100, 100), 2)

        x = self._panel_rect.x + 10
        y = self._panel_rect.y + 10
        renderer.draw_text("Assets", Vector2(x, y), self._highlight_color, 18)
        y += 26

        y = self._render_section(
            renderer, "Indexed", sorted(self._resources.iter_indexed()), x, y
        )
        y += 6
        loaded = sorted(
            (path, type(res).__name__) for path, res in self._resources.iter_cached()
        )
        y = self._render_section(renderer, "Loaded", loaded, x, y, typed=True)

        if self._selected_path is not None:
            self._render_actions(renderer, x, y + 8)

        if self._status:
            renderer.draw_text(
                self._status,
                Vector2(x, self._panel_rect.y + self._panel_rect.height - 22),
                Color(150, 200, 150),
                13,
            )

    def _render_section(
        self,
        renderer: UIRenderer,
        title: str,
        entries: list[tuple[str, str]],
        x: int,
        y: int,
        typed: bool = False,
    ) -> int:
        renderer.draw_text(title, Vector2(x, y), self._highlight_color, 14)
        y += 18
        max_y = self._panel_rect.y + self._panel_rect.height - 90
        for key, value in entries:
            if y > max_y:
                renderer.draw_text("...", Vector2(x + 8, y), Color(150, 150, 150), 12)
                y += _ROW_HEIGHT
                break
            # For "Indexed", key=name value=path; for "Loaded", key=path value=type.
            path = key if typed else value
            label = f"[{value}] {_basename(key)}" if typed else key
            selected = path == self._selected_path
            color = self._highlight_color if selected else self._text_color
            renderer.draw_text(label, Vector2(x + 8, y), color, 12)
            self._rows.append(
                (Rect(x, y, self._panel_rect.width - 20, _ROW_HEIGHT), path)
            )
            y += _ROW_HEIGHT
        return y

    def _render_actions(self, renderer: UIRenderer, x: int, y: int) -> None:
        path = self._selected_path
        assert path is not None
        renderer.draw_line(
            Vector2(x, y),
            Vector2(x + self._panel_rect.width - 20, y),
            Color(90, 90, 90),
        )
        y += 8
        renderer.draw_text(_basename(path), Vector2(x, y), self._text_color, 13)
        y += 20

        cached = dict(self._resources.iter_cached())
        resource = cached.get(path)
        is_data = isinstance(resource, DataResource)
        is_loaded = resource is not None
        # Spawn is for data files; a not-yet-loaded path might be one (we find
        # out on click), so it is only *disabled* when the loaded resource is
        # definitively not a DataResource.
        can_spawn = is_data or not is_loaded

        # Draw both buttons every frame, but only keep the hit rect for the
        # one that is actually enabled -- a greyed-out button must not act.
        spawn_rect = _button(renderer, "Spawn into Scene", x, y, enabled=can_spawn)
        reload_rect = _button(renderer, "Reload", x + 160, y, enabled=is_loaded)
        self._spawn_rect = spawn_rect if can_spawn else None
        self._reload_rect = reload_rect if is_loaded else None
        y += 28

        if is_data:
            assert isinstance(resource, DataResource)
            for line in _preview_lines(resource.native_handle):
                renderer.draw_text(line, Vector2(x, y), Color(170, 170, 170), 12)
                y += 14
        elif resource is not None:
            renderer.draw_text(
                "Not a DataResource -- preview/spawn unavailable.",
                Vector2(x, y),
                Color(150, 150, 150),
                12,
            )
        else:
            renderer.draw_text(
                "Not loaded -- Spawn will load it first.",
                Vector2(x, y),
                Color(150, 150, 150),
                12,
            )

    def process_event(self, event: Any) -> bool:
        """Handle row selection and the Spawn / Reload buttons.

        Args:
            event: Pygame event.
        """
        if not (event.type == pygame.MOUSEBUTTONDOWN and event.button == 1):
            return False

        mx, my = event.pos
        if self._spawn_rect and _hit(self._spawn_rect, mx, my):
            self._spawn_selected()
            return True
        if self._reload_rect and _hit(self._reload_rect, mx, my):
            self._reload_selected()
            return True
        for rect, path in self._rows:
            if _hit(rect, mx, my):
                self._selected_path = path
                self._status = ""
                return True
        return False

    def _spawn_selected(self) -> Entity | None:
        path = self._selected_path
        if path is None:
            return None

        scene = self._scenes.current_scene
        if scene is None:
            self._status = "No active scene to spawn into."
            return None

        try:
            resource = self._resources.load(path, DataResource)
        except Exception as exc:  # noqa: BLE001 -- surfaced in the panel
            self._status = f"Load failed: {exc}"
            return None

        entity = scene.entity_manager.create_entity()
        entity.add_component(ResourceLink(path))

        spawned = 0
        for comp_name, comp_data in resource.native_handle.items():
            if not (self._registry.has(comp_name) and isinstance(comp_data, dict)):
                continue
            try:
                entity.add_component(self._registry.create(comp_name, comp_data))
                spawned += 1
            except Exception as exc:  # noqa: BLE001 -- one bad component, keep going
                logger.warning(
                    "Assets spawn: component '%s' skipped (%s)", comp_name, exc
                )

        self._status = f"Spawned {entity.id[:8]} ({spawned} components)."
        return entity

    def _reload_selected(self) -> None:
        path = self._selected_path
        if path is None:
            return
        try:
            self._resources.reload(path)
            self._status = f"Reloaded {_basename(path)}."
        except (KeyError, ValueError, TypeError) as exc:
            self._status = f"Reload failed: {exc}"


def _basename(path: str) -> str:
    return path.replace("\\", "/").rsplit("/", 1)[-1]


def _hit(rect: Rect, mx: int, my: int) -> bool:
    return rect.x <= mx <= rect.x + rect.width and rect.y <= my <= rect.y + rect.height


def _button(renderer: UIRenderer, label: str, x: int, y: int, enabled: bool) -> Rect:
    rect = Rect(x, y, 150, 22)
    fill = Color(60, 90, 120) if enabled else Color(50, 50, 55)
    renderer.draw_rect(rect, fill, 0)
    renderer.draw_rect(rect, Color(110, 110, 120), 1)
    text_color = Color(230, 230, 230) if enabled else Color(120, 120, 120)
    renderer.draw_text(label, Vector2(x + 6, y + 4), text_color, 12)
    return rect


def _preview_lines(data: dict[str, Any], limit: int = 10) -> list[str]:
    lines: list[str] = []
    for key, value in list(data.items())[:limit]:
        text = value if isinstance(value, str) else repr(value)
        if len(text) > 42:
            text = text[:39] + "..."
        lines.append(f"{key}: {text}")
    if len(data) > limit:
        lines.append(f"... (+{len(data) - limit} more)")
    return lines
