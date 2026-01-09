"""Inspector Panel for the Editor."""

from typing import Optional
try:
    import imgui # type: ignore
except ImportError:
    imgui = None

from pyguara.ecs.entity import Entity
from pyguara.common.types import Vector2, Color


class InspectorPanel:
    """Displays and edits details of the selected entity."""

    def __init__(self) -> None:
        self.selected_entity: Optional[Entity] = None

    def render(self) -> None:
        """Draw the panel."""
        if not imgui:
            return

        imgui.begin("Inspector", True)

        if not self.selected_entity:
            imgui.text("Select an entity in the Hierarchy")
            imgui.end()
            return

        entity = self.selected_entity
        imgui.text(f"Entity ID: {entity.id}")
        imgui.separator()

        # Iterate through components
        for comp_type, component in entity.components.items():
            if imgui.collapsing_header(comp_type.__name__, imgui.TREE_NODE_DEFAULT_OPEN):
                # Use reflection to show/edit fields
                for attr, value in component.__dict__.items():
                    if attr.startswith("_"):
                        continue
                    
                    # 1. Floats/Ints
                    if isinstance(value, (int, float)):
                        changed, new_val = imgui.drag_float(attr, float(value), 0.1)
                        if changed:
                            setattr(component, attr, type(value)(new_val))
                    
                    # 2. Strings
                    elif isinstance(value, str):
                        changed, new_val = imgui.input_text(attr, value, 128)
                        if changed:
                            setattr(component, attr, new_val)
                            
                    # 3. Vector2
                    elif isinstance(value, Vector2):
                        # imgui.drag_float2 returns (changed, (x, y))
                        changed, new_vals = imgui.drag_float2(attr, value.x, value.y, 0.5)
                        if changed:
                            # Re-instantiate to avoid read-only issues with Vec2d base
                            setattr(component, attr, Vector2(new_vals[0], new_vals[1]))
                            
                    # 4. Color
                    elif isinstance(value, Color):
                        # imgui.color_edit4 returns (changed, (r, g, b, a)) in 0.0-1.0
                        norm = (value.r/255.0, value.g/255.0, value.b/255.0, value.a/255.0)
                        changed, new_norm = imgui.color_edit4(attr, *norm)
                        if changed:
                            value.r = int(new_norm[0] * 255)
                            value.g = int(new_norm[1] * 255)
                            value.b = int(new_norm[2] * 255)
                            value.a = int(new_norm[3] * 255)
                            
                    else:
                        imgui.text(f"{attr}: {value} (Read Only)")

        imgui.end()