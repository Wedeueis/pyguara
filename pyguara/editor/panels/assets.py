"""Assets Panel for the Editor."""

import os
import dataclasses
from typing import Optional, Dict, Any, Callable, Type, cast

try:
    import imgui
except ImportError:
    imgui = None

from pyguara.resources.manager import ResourceManager
from pyguara.resources.data import DataResource
from pyguara.ecs.manager import EntityManager
from pyguara.common.components import Tag, Transform, ResourceLink


class AssetsPanel:
    """Displays and manages game resources."""

    def __init__(
        self,
        resource_manager: ResourceManager,
        manager_provider: Callable[[], Optional[EntityManager]],
    ) -> None:
        """Initialize the Asset Paanel."""
        self._resource_manager = resource_manager
        self._manager_provider = manager_provider
        self.selected_resource_path: Optional[str] = None

    def render(self) -> None:
        """Draw the panel."""
        if not imgui:
            return

        imgui.begin("Assets", True)

        # 1. List Indexed Files
        if imgui.collapsing_header("Registry", imgui.TREE_NODE_DEFAULT_OPEN):
            for name, path in self._resource_manager._path_index.items():
                if name.endswith((".json", ".png", ".jpg")):
                    continue

                if imgui.selectable(f"{name} -> {path}")[0]:
                    self.selected_resource_path = path

        # 2. List Loaded Resources (Cache)
        imgui.separator()
        if imgui.collapsing_header("Cache (Loaded)", imgui.TREE_NODE_DEFAULT_OPEN):
            for path, resource in self._resource_manager._cache.items():
                label = f"[{type(resource).__name__}] {os.path.basename(path)}"

                is_selected = self.selected_resource_path == path
                if imgui.selectable(label, is_selected)[0]:
                    self.selected_resource_path = path

        imgui.end()

        # 3. Resource Inspector Window
        self._render_resource_inspector()

    def _render_resource_inspector(self) -> None:
        """Draw a separate window for the selected resource's data."""
        if not self.selected_resource_path:
            return

        path = self.selected_resource_path
        if path not in self._resource_manager._cache:
            return

        resource = self._resource_manager._cache[path]

        imgui.begin("Resource Inspector", True)
        imgui.text(f"Path: {path}")

        if isinstance(resource, DataResource):
            if imgui.button("Save to Disk"):
                resource.save()
                print(f"[Editor] Saved {path}")

            imgui.same_line()

            if imgui.button("Spawn into Scene"):
                self._spawn_resource(resource)

            imgui.separator()
            self._draw_dict_editor(resource._data)
        else:
            imgui.text(f"Type: {type(resource).__name__}")
            imgui.text("Manual editing not supported for this type.")

        if imgui.button("Close"):
            self.selected_resource_path = None

        imgui.end()

    def _spawn_resource(self, resource: DataResource) -> None:
        """Create an entity in the active manager based on resource data."""
        manager = self._manager_provider()
        if not manager:
            return

        entity = manager.create_entity()
        entity.add_component(ResourceLink(resource.path))

        from pyguara.physics.components import RigidBody, Collider

        comp_map: Dict[str, Type] = {
            "Tag": Tag,
            "Transform": Transform,
            "RigidBody": RigidBody,
            "Collider": Collider,
        }

        for comp_name, comp_data in resource._data.items():
            if comp_name in comp_map:
                cls = comp_map[comp_name]
                if dataclasses.is_dataclass(cls):
                    filtered = {
                        k: v
                        for k, v in comp_data.items()
                        if k in cls.__dataclass_fields__
                    }
                    instance = cls(**filtered)
                    entity.add_component(cast(Any, instance))
                elif cls == Transform:
                    t = Transform()
                    if "position" in comp_data:
                        t.position = comp_data["position"]
                    if "rotation" in comp_data:
                        t.rotation = comp_data["rotation"]
                    if "scale" in comp_data:
                        t.scale = comp_data["scale"]
                    entity.add_component(t)

        print(f"[Editor] Spawned entity from {resource.path}")

    def _draw_dict_editor(self, data: Dict[str, Any]) -> None:
        """Draw using simple recursive dictionary editor based on ImGui primitives."""
        for key, value in data.items():
            if isinstance(value, dict):
                if imgui.tree_node(str(key)):
                    self._draw_dict_editor(value)
                    imgui.tree_pop()
            elif isinstance(value, (int, float, str, bool)):
                if isinstance(value, bool):
                    changed, new_val = imgui.checkbox(str(key), value)
                    if changed:
                        data[key] = new_val
                elif isinstance(value, float):
                    changed, new_val = imgui.drag_float(str(key), value, 0.1)
                    if changed:
                        data[key] = new_val
                elif isinstance(value, int):
                    changed, new_val = imgui.drag_int(str(key), value)
                    if changed:
                        data[key] = new_val
                elif isinstance(value, str):
                    changed, new_val = imgui.input_text(str(key), value, 256)
                    if changed:
                        data[key] = new_val
            else:
                imgui.text(f"{key}: {value} (Unsupported)")
