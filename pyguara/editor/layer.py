"""The Editor Tool manages the ImGui context and tool overlays."""

from typing import Optional, Any

try:
    import imgui
    from imgui.integrations.pygame import PygameRenderer

    HAS_IMGUI = True
except ImportError:
    HAS_IMGUI = False
    imgui = None
    PygameRenderer = None

from pyguara.di.container import DIContainer
from pyguara.ecs.manager import EntityManager
from pyguara.scene.manager import SceneManager
from pyguara.scene.serializer import SceneSerializer
from pyguara.resources.manager import ResourceManager
from pyguara.editor.panels.hierarchy import HierarchyPanel
from pyguara.editor.panels.inspector import InspectorPanel
from pyguara.editor.panels.assets import AssetsPanel
from pyguara.tools.base import Tool
from pyguara.graphics.protocols import UIRenderer


class EditorTool(Tool):
    """A robust ImGui-based editor integrated into the Tool system."""

    def __init__(self, container: DIContainer) -> None:
        """Initialize the editor tool."""
        super().__init__("Editor", container)

        self._renderer: Optional[PygameRenderer] = None
        self._initialized = False

        # Panels
        self._show_hierarchy = True
        self._show_inspector = True
        self._show_assets = True

        resource_manager = self._container.get(ResourceManager)

        self._hierarchy_panel = HierarchyPanel(self._get_current_manager)
        self._inspector_panel = InspectorPanel(resource_manager)

        self._assets_panel = AssetsPanel(resource_manager, self._get_current_manager)

    def _get_current_manager(self) -> Optional[EntityManager]:
        """Resolve the active EntityManager from the current scene."""
        scene_manager = self._container.get(SceneManager)
        if scene_manager.current_scene:
            return scene_manager.current_scene.entity_manager
        return None

    def initialize(self) -> None:
        """Configure ImGui context."""
        if not HAS_IMGUI:
            print("[Editor] ImGui not found. Editor disabled.")
            return

        imgui.create_context()
        self._renderer = PygameRenderer()

        # Apply style (Dark Theme)
        style = imgui.get_style()
        style.colors[imgui.COLOR_WINDOW_BACKGROUND] = (0.1, 0.1, 0.1, 0.95)
        style.colors[imgui.COLOR_TITLE_BACKGROUND_ACTIVE] = (0.2, 0.3, 0.4, 1.0)

        self._initialized = True
        print("[Editor] ImGui Initialized.")

    def process_event(self, event: Any) -> bool:
        """Process inputs for the editor."""
        if not self.is_active or not self.is_visible:
            return False

        if not self._initialized:
            self.initialize()
            if not self._initialized:
                return False

        # Pass to ImGui
        if self._renderer:
            self._renderer.process_event(event)

        # Consume mouse/keyboard if ImGui wants them
        io = imgui.get_io()
        if io.want_capture_mouse or io.want_capture_keyboard:
            return True

        return False

    def update(self, dt: float) -> None:
        """Update editor logic."""
        # Synchronize selection
        self._inspector_panel.selected_entity = self._hierarchy_panel.selected_entity

    def render(self, renderer: UIRenderer) -> None:
        """Render the editor UI."""
        if not self.is_visible:
            return

        if not self._initialized:
            self.initialize()
            if not self._initialized:
                return

        imgui.new_frame()

        # Main Menu
        if imgui.begin_main_menu_bar():
            if imgui.begin_menu("File", True):
                if imgui.menu_item("Save Scene", "Ctrl+S")[0]:
                    # Implement Save Logic
                    scene_manager = self._container.get(SceneManager)
                    if scene_manager.current_scene:
                        serializer = self._container.get(SceneSerializer)
                        success = serializer.save_scene(
                            scene_manager.current_scene, "current_scene"
                        )
                        print(
                            f"[Editor] Save Triggered: {'Success' if success else 'Failed'}"
                        )

                if imgui.menu_item("Load Scene", "Ctrl+L")[0]:
                    scene_manager = self._container.get(SceneManager)
                    if scene_manager.current_scene:
                        serializer = self._container.get(SceneSerializer)
                        success = serializer.load_scene(
                            scene_manager.current_scene, "current_scene"
                        )
                        print(
                            f"[Editor] Load Triggered: {'Success' if success else 'Failed'}"
                        )

                imgui.end_menu()

            if imgui.begin_menu("View", True):
                clicked, self._show_hierarchy = imgui.menu_item(
                    "Hierarchy", None, self._show_hierarchy
                )
                clicked, self._show_inspector = imgui.menu_item(
                    "Inspector", None, self._show_inspector
                )
                clicked, self._show_assets = imgui.menu_item(
                    "Assets", None, self._show_assets
                )
                imgui.end_menu()

            imgui.end_main_menu_bar()

        # Draw Panels
        if self._show_hierarchy:
            self._hierarchy_panel.render()

        if self._show_inspector:
            self._inspector_panel.render()

        if self._show_assets:
            self._assets_panel.render()

        imgui.render()
        if self._renderer:
            self._renderer.render(imgui.get_draw_data())
